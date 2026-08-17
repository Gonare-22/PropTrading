from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import json
import math
import io
import MetaTrader5 as mt5
import os
from typing import Dict, Tuple

app = FastAPI(title="EMA Strategy Backtest UI")
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(base_dir / "templates"))

# Pydantic model for request validation
class BacktestRequest(BaseModel):
    market: Optional[str] = "india"
    symbol: Optional[str] = ""
    custom_symbol: Optional[str] = ""
    start_date: str = ""
    end_date: str = ""
    interval: Optional[str] = "1d"
    initial_capital: Optional[float] = 100000
    risk_per_trade: Optional[float] = 100.0  # Percentage of capital to risk per trade
    lot_size: Optional[float] = 0.10
    data_source: Optional[str] = "yahoo"  # yahoo, alpha_vantage, polygon, tweleve_data, upload

DEFAULT_FOREX_LOT_SIZE = 0.10

# API Keys (set these in environment variables for production)
ALPHA_VANTAGE_KEY = "demo"  # Replace with your key or set env var
POLYGON_API_KEY = "demo"    # Replace with your key or set env var
TWELEVE_DATA_API_KEY = "25753a3ca5dd493896ae4e6a9a755631"  # Valid 12data API key

# MetaTrader5 Configuration
MT5_EMAIL = "vaishnavgonare1@gmail.com"
MT5_PASSWORD = "Vaishnav@2002"
MT5_SERVER = "ICMarketsSC-Demo"  # Common demo server for MT5, you can adjust if needed

# Initialize MT5 connection flag
MT5_INITIALIZED = False
MT5_CONNECTION_ERROR = None

MARKET_OPTIONS = {
    "india": [
        {"value": "^NSEI", "label": "Nifty 50"},
        {"value": "^NSEBANK", "label": "Nifty Bank"},
        {"value": "^CNXIT", "label": "Nifty IT"},
        {"value": "^CNXPHARMA", "label": "Nifty Pharma"},
        {"value": "^CNX100", "label": "Nifty 100"},
        {"value": "RELIANCE.NS", "label": "Reliance"},
        {"value": "TCS.NS", "label": "TCS"},
    ],
    "us": [
        {"value": "SPY", "label": "SPY"},
        {"value": "QQQ", "label": "QQQ"},
        {"value": "AAPL", "label": "Apple"},
        {"value": "MSFT", "label": "Microsoft"},
    ],
    "forex": [
        {"value": "XAUUSD", "label": "Gold (XAUUSD) - MetaTrader5", "source": "mt5"},
        {"value": "XAUUSDT", "label": "Gold (XAU/USDT) - Binance", "source": "binance"},
        {"value": "XAGUSDT", "label": "Silver (XAG/USDT) - Binance", "source": "binance"},
        {"value": "BTCUSDT", "label": "Bitcoin (BTC/USDT) - Binance", "source": "binance"},
    ],
}

def get_symbol_label(symbol: str, market: str):
    options = MARKET_OPTIONS.get(market, [])
    for item in options:
        if item["value"] == symbol:
            return item["label"]
    return symbol


def resolve_yahoo_symbol(symbol: str):
    """Map custom symbols to Yahoo Finance symbols"""
    mapping = {
        "XAUUSD=X": "GC=F",  # Gold Futures
        "XAGUSD=X": "SI=F",  # Silver Futures
    }
    return mapping.get(symbol, symbol)


def normalize_date_range(start: str, end: str):
    try:
        start_dt = pd.Timestamp(start).normalize()
        end_dt = pd.Timestamp(end).normalize()
    except Exception as exc:
        raise ValueError("Please enter valid dates in YYYY-MM-DD format") from exc

    if start_dt > end_dt:
        raise ValueError("Start date must be on or before the end date")

    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def fetch_yahoo_chunked(symbol: str, start: str, end: str, interval: str):
    max_window = {
        "1m": 7,
        "2m": 7,
        "5m": 60,
        "15m": 60,
        "30m": 60,
        "60m": 730,
        "1h": 730,
    }.get(interval, 30)

    start_dt = pd.Timestamp(start).normalize()
    end_dt = pd.Timestamp(end).normalize()
    frames = []
    current_start = start_dt

    while current_start <= end_dt:
        chunk_end = min(current_start + pd.Timedelta(days=max_window - 1), end_dt)
        chunk_start = current_start.strftime("%Y-%m-%d")
        chunk_end_str = (chunk_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        chunk = yf.download(
            symbol,
            start=chunk_start,
            end=chunk_end_str,
            interval=interval,
            auto_adjust=False,
            progress=False,
            prepost=False,
            threads=False,
        )
        if chunk.empty:
            return pd.DataFrame()
        if isinstance(chunk.columns, pd.MultiIndex):
            chunk.columns = [col[0] if isinstance(col, tuple) else col for col in chunk.columns]
        frames.append(chunk)
        current_start = chunk_end + pd.Timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    concatenated = pd.concat(frames).sort_index()
    concatenated = concatenated[~concatenated.index.duplicated(keep='first')]
    return concatenated


def initialize_mt5() -> Tuple[bool, str]:
    """
    Initialize MetaTrader5 connection with account credentials
    Returns: (success: bool, message: str)
    """
    global MT5_INITIALIZED, MT5_CONNECTION_ERROR
    
    try:
        if MT5_INITIALIZED:
            return True, "MT5 already initialized"
        
        # Initialize MT5
        if not mt5.initialize():
            error = mt5.last_error()
            MT5_CONNECTION_ERROR = f"MT5 initialization failed: {error}"
            print(MT5_CONNECTION_ERROR)
            return False, MT5_CONNECTION_ERROR
        
        print("✓ MT5 initialized successfully")
        MT5_INITIALIZED = True
        return True, "MT5 initialized successfully"
    
    except Exception as e:
        error_msg = f"MT5 initialization error: {str(e)}"
        MT5_CONNECTION_ERROR = error_msg
        print(error_msg)
        return False, error_msg


def download_mt5_data(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
    """
    Download 1-minute and intraday data from MetaTrader5
    Supports: XAUUSD, Forex pairs, stocks, indices
    
    Args:
        symbol: MT5 symbol (e.g., 'XAUUSD', 'EURUSD', 'AAPL')
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        interval: '1m', '5m', '15m', '1h', '1d'
    
    Returns:
        DataFrame with OHLCV data
    """
    
    global MT5_INITIALIZED

    # Initialize MT5 if not already done
    if not MT5_INITIALIZED:
        success, msg = initialize_mt5()
        if not success:
            raise ValueError(f"Cannot connect to MT5: {msg}. Please ensure MT5 terminal is running.")
    
    # Map interval to MT5 timeframe
    timeframe_map = {
        "1m": mt5.TIMEFRAME_M1,
        "5m": mt5.TIMEFRAME_M5,
        "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30,
        "60m": mt5.TIMEFRAME_H1,
        "1h": mt5.TIMEFRAME_H1,
        "1d": mt5.TIMEFRAME_D1,
    }
    
    timeframe = timeframe_map.get(interval, mt5.TIMEFRAME_M1)

    # MT5 requires native Python datetime objects (not pandas Timestamps)
    from datetime import datetime as _dt
    start_dt = pd.to_datetime(start).to_pydatetime().replace(tzinfo=None)
    end_dt = pd.to_datetime(end).to_pydatetime().replace(tzinfo=None)
    # MT5 rejects end dates in the future - cap at current time
    now = _dt.now()
    if end_dt >= now:
        end_dt = now
    else:
        # For past dates include the full end day
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
    
    print(f"[MT5] Fetching {symbol} at {interval} from {start_dt} to {end_dt}")
    print(f"[MT5] Timeframe: {timeframe}, Symbol: {symbol}")
    
    try:
        # Re-initialize MT5 in case connection was lost
        if not mt5.terminal_info():
            print("[MT5] Terminal not connected, re-initializing...")
            MT5_INITIALIZED = False
            success, msg = initialize_mt5()
            if not success:
                raise ValueError(f"Cannot connect to MT5: {msg}. Please ensure MT5 terminal is running.")

        # Select symbol first
        selected = mt5.symbol_select(symbol, True)
        print(f"[MT5] symbol_select({symbol}): {selected}")
        if not selected:
            last_err = mt5.last_error()
            raise ValueError(f"Symbol {symbol} not found in MT5 (error: {last_err}). Add it to Market Watch in MT5 terminal.")
        
        # Get rates from MT5
        rates = mt5.copy_rates_range(symbol, timeframe, start_dt, end_dt)
        print(f"[MT5] copy_rates_range returned: {type(rates)}, len: {len(rates) if rates is not None else 'None'}")
        
        # Check if rates is empty using .size for numpy array
        if rates is None or (hasattr(rates, 'size') and rates.size == 0) or len(rates) == 0:
            last_err = mt5.last_error()
            raise ValueError(
                f"No data found for {symbol} ({last_err}). "
                f"Ensure: 1) MT5 terminal is running, 2) Symbol {symbol} in Market Watch, "
                f"3) Date range has market data, 4) Market was open during that time"
            )
        
        print(f"[MT5] ✓ Downloaded {len(rates)} candles")
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={
            'time': 'datetime',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'tick_volume': 'Volume'
        })
        
        df = df[['datetime', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df = df.set_index('datetime')
        df = df.sort_index()
        
        print(f"[MT5] ✓ Data range: {df.index.min()} to {df.index.max()}")
        print(f"[MT5] ✓ Records: {len(df)}")
        
        return df
    
    except Exception as e:
        print(f"[MT5] Error: {str(e)}")
        raise ValueError(f"MT5 data fetch error: {str(e)}")


def shutdown_mt5():
    """Cleanup MT5 connection"""
    global MT5_INITIALIZED
    try:
        if MT5_INITIALIZED:
            mt5.shutdown()
            MT5_INITIALIZED = False
            print("MT5 connection closed")
    except Exception as e:
        print(f"Error closing MT5: {str(e)}")


def download_market_data(symbol: str, start: str, end: str, interval: str, data_source: str = "yahoo", uploaded_df: pd.DataFrame = None):
    """
    Download market data from multiple sources or use uploaded file
    data_source: 'yahoo', 'alpha_vantage', 'polygon', 'tweleve_data', 'binance', 'mt5', or 'upload'
    """
    if data_source == "upload" and uploaded_df is not None:
        return uploaded_df
    elif data_source == "yahoo":
        return download_yahoo_data(symbol, start, end, interval)
    elif data_source == "alpha_vantage":
        return download_alpha_vantage_data(symbol, start, end, interval)
    elif data_source == "polygon":
        return download_polygon_data(symbol, start, end, interval)
    elif data_source == "tweleve_data":
        return download_tweleve_data(symbol, start, end, interval)
    elif data_source == "binance":
        return download_binance_data(symbol, start, end, interval)
    elif data_source == "mt5":
        return download_mt5_data(symbol, start, end, interval)
    else:
        return download_yahoo_data(symbol, start, end, interval)


def process_uploaded_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """
    Process uploaded CSV or Excel file
    Handles large files efficiently (1GB+)
    Supports Unix Epoch timestamps
    Automatically downsamples very large datasets
    """
    print(f"Processing uploaded file: {filename}, size: {len(file_content) / 1024 / 1024:.2f} MB")
    
    try:
        # Determine file type
        if filename.endswith('.csv'):
            # Use chunks for large CSV files
            df = pd.read_csv(
                io.BytesIO(file_content),
                parse_dates=False,  # Don't auto-parse, we'll handle it
                low_memory=False  # Avoids mixed type warnings
            )
        elif filename.endswith(('.xlsx', '.xls')):
            # Excel files
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel (.xlsx, .xls)")
        
        print(f"Loaded {len(df)} rows from uploaded file")
        
        # IMPORTANT: Check if dataset is too large and downsample
        MAX_ROWS = 500000  # Maximum 500K rows for performance
        original_rows = len(df)
        if len(df) > MAX_ROWS:
            # Calculate sampling ratio
            sample_ratio = MAX_ROWS / len(df)
            print(f"⚠️ Dataset too large ({original_rows:,} rows). Downsampling to {MAX_ROWS:,} rows for performance...")
            
            # Use systematic sampling (every Nth row) to preserve time structure
            step = int(1 / sample_ratio)
            df = df.iloc[::step].reset_index(drop=True)
            print(f"✓ Downsampled to {len(df):,} rows (every {step}th row)")
        
        # Find datetime column
        datetime_col = None
        for col in df.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in ['date', 'time', 'datetime', 'timestamp', 'epoch']):
                datetime_col = col
                break
        
        if datetime_col is None:
            raise ValueError("Could not find datetime column. Ensure your file has a 'Date', 'DateTime', 'Timestamp', or 'Epoch' column")
        
        print(f"Found datetime column: {datetime_col}")
        
        # Check if it's Unix Epoch timestamp (numeric values)
        first_value = df[datetime_col].iloc[0]
        is_unix_epoch = False
        unit = 's'
        
        try:
            # Check if it's a number (Unix timestamp)
            if isinstance(first_value, (int, float, np.integer, np.floating)):
                timestamp_val = float(first_value)
                # Unix timestamps are typically 10 digits (seconds) or 13 digits (milliseconds)
                if 1000000000 <= timestamp_val <= 9999999999:  # Seconds (2001-2286)
                    is_unix_epoch = True
                    unit = 's'
                    print(f"Detected Unix Epoch timestamp in seconds")
                elif 1000000000000 <= timestamp_val <= 9999999999999:  # Milliseconds
                    is_unix_epoch = True
                    unit = 'ms'
                    print(f"Detected Unix Epoch timestamp in milliseconds")
            elif isinstance(first_value, str) and first_value.replace('.', '', 1).isdigit():
                # Handle string numeric values
                timestamp_val = float(first_value)
                if 1000000000 <= timestamp_val <= 9999999999:
                    is_unix_epoch = True
                    unit = 's'
                    print(f"Detected Unix Epoch timestamp in seconds (from string)")
                elif 1000000000000 <= timestamp_val <= 9999999999999:
                    is_unix_epoch = True
                    unit = 'ms'
                    print(f"Detected Unix Epoch timestamp in milliseconds (from string)")
        except:
            pass
        
        # Convert datetime column
        if is_unix_epoch:
            # Convert Unix Epoch to datetime
            df[datetime_col] = pd.to_datetime(df[datetime_col], unit=unit, errors='coerce')
            print(f"Converted Unix Epoch ({unit}) to datetime")
        else:
            # Try to parse as regular datetime string
            df[datetime_col] = pd.to_datetime(df[datetime_col], errors='coerce')
            print(f"Parsed as standard datetime format")
        
        # Remove rows where datetime conversion failed
        df = df.dropna(subset=[datetime_col])
        
        if df.empty:
            raise ValueError("No valid datetime values found. Check your timestamp format.")
        
        # Find OHLC columns
        column_mapping = {}
        required_columns = ['Open', 'High', 'Low', 'Close']
        
        for col in df.columns:
            col_lower = col.lower()
            if 'open' in col_lower and 'Open' not in column_mapping:
                column_mapping[col] = 'Open'
            elif 'high' in col_lower and 'High' not in column_mapping:
                column_mapping[col] = 'High'
            elif 'low' in col_lower and 'Low' not in column_mapping:
                column_mapping[col] = 'Low'
            elif 'close' in col_lower and 'Close' not in column_mapping:
                column_mapping[col] = 'Close'
            elif 'volume' in col_lower and 'Volume' not in column_mapping:
                column_mapping[col] = 'Volume'
        
        # Check if we have required columns
        if 'Close' not in column_mapping.values():
            raise ValueError("Could not find 'Close' price column. Ensure your file has OHLC data")
        
        print(f"Column mapping: {column_mapping}")
        
        # Rename columns
        df = df.rename(columns=column_mapping)
        
        # Set datetime index
        df = df.set_index(datetime_col)
        df = df.sort_index()
        
        # Fill missing OHLC columns if not present
        if 'Open' not in df.columns:
            df['Open'] = df['Close']
            print("'Open' not found, using Close price")
        if 'High' not in df.columns:
            df['High'] = df['Close']
            print("'High' not found, using Close price")
        if 'Low' not in df.columns:
            df['Low'] = df['Close']
            print("'Low' not found, using Close price")
        if 'Volume' not in df.columns:
            df['Volume'] = 0
            print("'Volume' not found, setting to 0")
        
        # Select only required columns
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        # Convert to numeric
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove any rows with NaN in Close
        df = df.dropna(subset=['Close'])
        
        if df.empty:
            raise ValueError("No valid data found after processing. Check your file format")
        
        print(f"✓ Successfully processed {len(df):,} rows")
        if original_rows > len(df) and original_rows > MAX_ROWS:
            print(f"  (downsampled from {original_rows:,} rows for performance)")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        
        return df
        
    except Exception as e:
        raise ValueError(f"Error processing uploaded file: {str(e)}")


@app.post("/upload-backtest")
async def upload_backtest(
    file: UploadFile = File(...),
    market: str = Form(...),
    initial_capital: float = Form(...),
    risk_per_trade: float = Form(...),
    lot_size: float = Form(0.10)
):
    """Handle file upload and run backtest"""
    try:
        print(f"Received file upload: {file.filename}")
        
        # Read file content
        file_content = await file.read()
        
        # Process uploaded file
        df = process_uploaded_file(file_content, file.filename)
        
        # Compute EMAs
        df = compute_emas(df)
        print(f"Computed EMAs, starting backtest...")
        
        # Run strategy
        result = run_strategy(df, initial_capital, market=market, risk_per_trade=risk_per_trade, lot_size=lot_size)
        print(f"Backtest complete: {result['summary']['trades']} trades generated")
        
        # Currency based on market
        currency = "₹" if market == "india" else "$"
        currency_code = "INR" if market == "india" else "USD"
        
        return JSONResponse({
            "success": True,
            "summary": result["summary"],
            "trade_log": result["trade_log"],
            "symbol": file.filename,
            "symbol_label": f"Uploaded: {file.filename}",
            "market": market,
            "market_label": market.capitalize(),
            "currency": currency,
            "currency_code": currency_code,
            "source": f"Uploaded File ({len(df)} rows)",
            "date_range": f"{df.index.min()} to {df.index.max()}"
        })
        
    except Exception as exc:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Error occurred: {error_detail}")
        return JSONResponse({"success": False, "error": str(exc)}, status_code=200)


def download_yahoo_data(symbol: str, start: str, end: str, interval: str):
    """Yahoo Finance data download - supports all intervals and long date ranges"""
    resolved_symbol = resolve_yahoo_symbol(symbol)
    start, end = normalize_date_range(start, end)
    
    print(f"Downloading {resolved_symbol} from {start} to {end} with interval {interval}")

    if resolved_symbol == "BTCXAU=X":
        btc = yf.download(
            "BTC-USD",
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            prepost=False,
            threads=False,
        )
        gold = yf.download(
            "GC=F",
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            prepost=False,
            threads=False,
        )
        if btc.empty or gold.empty:
            raise ValueError("No data found for BTC/XAU synthetic pair in the selected date range")
        if isinstance(btc.columns, pd.MultiIndex):
            btc.columns = [col[0] if isinstance(col, tuple) else col for col in btc.columns]
        if isinstance(gold.columns, pd.MultiIndex):
            gold.columns = [col[0] if isinstance(col, tuple) else col for col in gold.columns]
        btc = btc[["Close"]].dropna().rename(columns={"Close": "btc_close"})
        gold = gold[["Close"]].dropna().rename(columns={"Close": "gold_close"})
        merged = pd.concat([btc, gold], axis=1).dropna()
        merged["Close"] = merged["btc_close"] / merged["gold_close"]
        merged["Open"] = merged["Close"]
        merged["High"] = merged["Close"]
        merged["Low"] = merged["Close"]
        merged["Volume"] = 0
        merged = merged[["Open", "High", "Low", "Close", "Volume"]]
        return merged.sort_index()

    # For intraday data (1m, 5m, etc.), use chunked download
    if interval in {"1m", "2m", "5m", "15m", "30m", "60m", "1h"}:
        data = fetch_yahoo_chunked(resolved_symbol, start, end, interval)
        if not data.empty:
            data.index = pd.to_datetime(data.index)
            data = data.sort_index().dropna(subset=["Close"])
            print(f"Successfully downloaded {len(data)} rows of intraday data")
            return data
        else:
            raise ValueError(f"No intraday data available for {symbol}. Try daily interval (1d) or a shorter date range.")

    # For daily or longer intervals, direct download
    data = yf.download(
        resolved_symbol,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,
        progress=False,
        prepost=False,
        threads=False,
    )
    
    if data.empty:
        raise ValueError(f"No data found for {symbol} in the selected date range. Check symbol and dates.")
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
    
    data.index = pd.to_datetime(data.index)
    data = data.sort_index().dropna(subset=["Close"])
    
    print(f"Successfully downloaded {len(data)} rows of daily data")
    return data


def download_alpha_vantage_data(symbol: str, start: str, end: str, interval: str):
    """
    Alpha Vantage data download - supports intraday and daily data
    Free tier: 25 API calls/day, 500 calls/month
    """
    start, end = normalize_date_range(start, end)
    
    # Map intervals to Alpha Vantage format
    interval_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "60m": "60min",
        "1h": "60min",
        "1d": "daily",
    }
    
    av_interval = interval_map.get(interval, "daily")
    
    if av_interval == "daily":
        function = "TIME_SERIES_DAILY"
        time_key = "Time Series (Daily)"
    else:
        function = "TIME_SERIES_INTRADAY"
        time_key = f"Time Series ({av_interval})"
    
    # Build API URL
    params = {
        "function": function,
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_KEY,
        "outputsize": "full",  # Get full data (up to 20 years daily, last 2 months intraday)
        "datatype": "json"
    }
    
    if function == "TIME_SERIES_INTRADAY":
        params["interval"] = av_interval
    
    url = "https://www.alphavantage.co/query"
    response = requests.get(url, params=params, timeout=30)
    
    if response.status_code != 200:
        raise ValueError(f"Alpha Vantage API error: {response.status_code}")
    
    data_json = response.json()
    
    if "Error Message" in data_json:
        raise ValueError(f"Alpha Vantage error: {data_json['Error Message']}")
    
    if "Note" in data_json:
        raise ValueError("Alpha Vantage API limit reached. Try Yahoo Finance or wait a minute.")
    
    if time_key not in data_json:
        raise ValueError("No data returned from Alpha Vantage. Check symbol and try again.")
    
    # Parse JSON to DataFrame
    time_series = data_json[time_key]
    df = pd.DataFrame.from_dict(time_series, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    
    # Rename columns
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    df = df.astype(float)
    
    # Filter by date range
    df = df[(df.index >= start) & (df.index <= end)]
    
    if df.empty:
        raise ValueError(f"No data found for {symbol} in the selected date range from Alpha Vantage")
    
    return df


def download_polygon_data(symbol: str, start: str, end: str, interval: str):
    """
    Polygon.io data download - high quality market data
    Free tier: 5 API calls/minute
    """
    start, end = normalize_date_range(start, end)
    
    # Map intervals to Polygon format
    interval_map = {
        "1m": ("1", "minute"),
        "5m": ("5", "minute"),
        "15m": ("15", "minute"),
        "30m": ("30", "minute"),
        "60m": ("1", "hour"),
        "1h": ("1", "hour"),
        "1d": ("1", "day"),
    }
    
    multiplier, timespan = interval_map.get(interval, ("1", "day"))
    
    # Build API URL
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": POLYGON_API_KEY
    }
    
    response = requests.get(url, params=params, timeout=30)
    
    if response.status_code != 200:
        raise ValueError(f"Polygon API error: {response.status_code}")
    
    data_json = response.json()
    
    if data_json.get("status") == "ERROR":
        raise ValueError(f"Polygon error: {data_json.get('error', 'Unknown error')}")
    
    if "results" not in data_json or not data_json["results"]:
        raise ValueError(f"No data found for {symbol} from Polygon.io. Check symbol format (e.g., AAPL for stocks).")
    
    # Parse JSON to DataFrame
    results = data_json["results"]
    df = pd.DataFrame(results)
    
    # Convert timestamp (milliseconds) to datetime
    df["timestamp"] = pd.to_datetime(df["t"], unit="ms")
    df = df.set_index("timestamp")
    
    # Rename columns to standard format
    df = df.rename(columns={
        "o": "Open",
        "h": "High",
        "l": "Low",
        "c": "Close",
        "v": "Volume"
    })
    
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df = df.sort_index()
    
    if df.empty:
        raise ValueError(f"No data found for {symbol} in the selected date range from Polygon")
    
    return df


def download_binance_data(symbol: str, start: str, end: str, interval: str):
    """
    Binance API download - Cryptocurrency (Spot) and commodity (Futures) data
    Supports: 
    - Cryptocurrencies via Spot API: BTC, ETH, XRP, ADA, DOGE, SOL, etc.
    - Commodities via Futures API: Gold (XAU), Silver (XAG)
    Symbol format: BTCUSDT, ETHUSDT, XAUUSDT (Futures), XAGUSDT (Futures), etc.
    
    Rate Limits:
    - Spot API: 1200 requests per minute
    - Futures API: 2400 requests per minute
    - No API key required for public market data
    
    Binance APIs: 
    - Spot: https://binance-docs.github.io/apidocs/spot/
    - Futures: https://binance-docs.github.io/apidocs/futures/
    """
    start, end = normalize_date_range(start, end)
    
    # Validate symbol format and determine which API to use
    valid_suffixes = ('USDT', 'BUSD', 'USDC', 'TUSD')
    symbol_upper = symbol.upper()
    
    if not symbol_upper.endswith(valid_suffixes):
        # Try to append USDT if not present
        if symbol_upper in ['BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'SOL', 'LTC', 'BCH', 'XAU', 'XAG', 'LINK']:
            symbol_upper = symbol_upper + 'USDT'
        else:
            raise ValueError(f"Invalid Binance symbol: {symbol}. Use format like BTCUSDT, XAUUSDT, etc.")
    
    # Determine if this is a commodity (use Futures API) or crypto (use Spot API)
    is_commodity = symbol_upper.startswith(('XAU', 'XAG'))
    
    if is_commodity:
        return _download_binance_futures_data(symbol_upper, start, end, interval)
    else:
        return _download_binance_spot_data(symbol_upper, start, end, interval)


def _download_binance_spot_data(symbol: str, start: str, end: str, interval: str):
    """Download cryptocurrency data from Binance Spot API"""
    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "1h", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
    }
    
    binance_interval = interval_map.get(interval, "1d")
    base_url = "https://api.binance.com/api/v3/klines"
    
    print(f"[Binance Spot] Fetching {symbol} from {start} to {end}, interval: {binance_interval}")
    
    try:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        all_candles = []
        current_start = start_dt
        
        while current_start < end_dt:
            start_ms = int(current_start.timestamp() * 1000)
            params = {
                "symbol": symbol,
                "interval": binance_interval,
                "startTime": start_ms,
                "limit": 1000
            }
            
            print(f"[Binance Spot] Fetching chunk from {current_start.strftime('%Y-%m-%d %H:%M:%S')}")
            response = requests.get(base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                error_text = response.text
                print(f"[Binance Spot] Error {response.status_code}: {error_text}")
                raise ValueError(f"Binance Spot API error: {response.status_code} - {error_text}")
            
            candles = response.json()
            if not candles:
                break
            
            all_candles.extend(candles)
            last_candle_time = pd.Timestamp(int(candles[-1][0]) / 1000, unit='s')
            current_start = last_candle_time + pd.Timedelta(minutes=1)
            print(f"[Binance Spot] Got {len(candles)} candles")
            
            if last_candle_time >= end_dt:
                break
        
        if not all_candles:
            raise ValueError(f"No data found for {symbol}. Verify symbol exists on Binance Spot (e.g., BTCUSDT, ETHUSDT).")
        
        records = []
        for candle in all_candles:
            try:
                timestamp = pd.Timestamp(int(candle[0]) / 1000, unit='s')
                if timestamp > end_dt:
                    break
                records.append({
                    "datetime": timestamp,
                    "Open": float(candle[1]),
                    "High": float(candle[2]),
                    "Low": float(candle[3]),
                    "Close": float(candle[4]),
                    "Volume": float(candle[7])
                })
            except (IndexError, ValueError):
                continue
        
        if not records:
            raise ValueError("No valid candles after parsing")
        
        df = pd.DataFrame(records)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        df = df[~df.index.duplicated(keep='first')]
        
        print(f"[Binance Spot] ✓ Downloaded {len(df)} rows from {df.index.min()} to {df.index.max()}")
        return df
        
    except requests.exceptions.Timeout:
        raise ValueError("Binance API request timed out.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Cannot connect to Binance API. Check internet connection.")
    except Exception as e:
        print(f"[Binance Spot] Error: {str(e)}")
        raise ValueError(f"Binance Spot error: {str(e)}")


def _download_binance_futures_data(symbol: str, start: str, end: str, interval: str):
    """Download commodity data (Gold, Silver) from Binance Futures API"""
    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "1h", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
    }
    
    binance_interval = interval_map.get(interval, "1d")
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    
    print(f"[Binance Futures] Fetching {symbol} from {start} to {end}, interval: {binance_interval}")
    
    try:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        all_candles = []
        current_start = start_dt
        
        while current_start < end_dt:
            start_ms = int(current_start.timestamp() * 1000)
            params = {
                "symbol": symbol,
                "interval": binance_interval,
                "startTime": start_ms,
                "limit": 1500
            }
            
            print(f"[Binance Futures] Fetching chunk from {current_start.strftime('%Y-%m-%d %H:%M:%S')}")
            response = requests.get(base_url, params=params, timeout=30)
            
            if response.status_code != 200:
                error_text = response.text
                print(f"[Binance Futures] Error {response.status_code}: {error_text}")
                raise ValueError(f"Binance Futures API error: {response.status_code} - {error_text}")
            
            candles = response.json()
            if not candles:
                break
            
            all_candles.extend(candles)
            last_candle_time = pd.Timestamp(int(candles[-1][0]) / 1000, unit='s')
            current_start = last_candle_time + pd.Timedelta(minutes=1)
            print(f"[Binance Futures] Got {len(candles)} candles")
            
            if last_candle_time >= end_dt:
                break
        
        if not all_candles:
            raise ValueError(f"No data found for {symbol}. Verify {symbol} is available on Binance Futures (e.g., XAUUSDT, XAGUSDT).")
        
        records = []
        for candle in all_candles:
            try:
                timestamp = pd.Timestamp(int(candle[0]) / 1000, unit='s')
                if timestamp > end_dt:
                    break
                records.append({
                    "datetime": timestamp,
                    "Open": float(candle[1]),
                    "High": float(candle[2]),
                    "Low": float(candle[3]),
                    "Close": float(candle[4]),
                    "Volume": float(candle[7])
                })
            except (IndexError, ValueError):
                continue
        
        if not records:
            raise ValueError("No valid candles after parsing")
        
        df = pd.DataFrame(records)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        df = df[~df.index.duplicated(keep='first')]
        
        print(f"[Binance Futures] ✓ Downloaded {len(df)} rows from {df.index.min()} to {df.index.max()}")
        return df
        
    except requests.exceptions.Timeout:
        raise ValueError("Binance Futures API request timed out.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Cannot connect to Binance Futures API. Check internet connection.")
    except Exception as e:
        print(f"[Binance Futures] Error: {str(e)}")
        raise ValueError(f"Binance Futures error: {str(e)}")


def download_tweleve_data(symbol: str, start: str, end: str, interval: str):
    """
    Tweleve Data API download - real-time and historical market data
    Supports: stocks, forex, crypto, commodities, indices
    API Key: 25753a3ca5dd493896ae4e6a9a755631
    """
    start, end = normalize_date_range(start, end)
    
    # Map intervals to 12data format
    interval_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "60m": "60min",
        "1h": "60min",
        "1d": "1day",
    }
    
    tweleve_interval = interval_map.get(interval, "1day")
    
    # Normalize symbol for 12data (e.g., BTC-USD -> BTC/USD, EURUSD -> EUR/USD)
    original_symbol = symbol
    if symbol.endswith("=X"):
        # Yahoo forex format: convert to 12data format
        symbol = symbol.replace("=X", "").replace("USD", "/USD")
        if "/" not in symbol:
            symbol = symbol[:3] + "/" + symbol[3:]
    elif "-" in symbol and symbol.count("-") == 1:
        # Yahoo format: convert dash to slash for crypto
        symbol = symbol.replace("-", "/")
    elif "/" not in symbol and len(symbol) >= 6:
        # Convert forex pairs: EURUSD -> EUR/USD
        symbol = symbol[:3] + "/" + symbol[3:]
    
    print(f"[12data] Converting {original_symbol} -> {symbol}")
    print(f"[12data] Fetching {symbol} from {start} to {end}, interval: {tweleve_interval}")
    
    # Build API URL
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": tweleve_interval,
        "start_date": start,
        "end_date": end,
        "format": "JSON",
        "apikey": TWELEVE_DATA_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        print(f"[12data] Response Status: {response.status_code}")
        
        if response.status_code != 200:
            error_text = response.text
            print(f"[12data] Error - Status {response.status_code}: {error_text}")
            raise ValueError(f"12data API error: {response.status_code} - {error_text}")
        
        data_json = response.json()
        print(f"[12data] Response Status: {data_json.get('status')}")
        
        # Check for API errors
        if data_json.get("status") == "error":
            error_msg = data_json.get('message', 'Unknown error')
            print(f"[12data] API Error: {error_msg}")
            raise ValueError(f"12data error: {error_msg}")
        
        # Check if data exists
        if "values" not in data_json or not data_json["values"]:
            raise ValueError(f"No data found for {symbol}. Check symbol format (e.g., BTC/USD, EUR/USD, AAPL)")
        
        print(f"[12data] Got {len(data_json['values'])} candles from API")
        
        # Parse JSON to DataFrame
        records = []
        for candle in data_json["values"]:
            try:
                records.append({
                    "datetime": candle["datetime"],
                    "Open": float(candle["open"]),
                    "High": float(candle["high"]),
                    "Low": float(candle["low"]),
                    "Close": float(candle["close"]),
                    "Volume": float(candle.get("volume", 0))
                })
            except (KeyError, ValueError) as e:
                print(f"[12data] Skipping malformed candle: {candle} - {str(e)}")
                continue
        
        df = pd.DataFrame(records)
        
        if df.empty:
            raise ValueError(f"No valid candles after parsing")
        
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
        df = df.sort_index()
        
        print(f"[12data] ✓ Successfully downloaded {len(df)} valid rows from 12data API")
        print(f"[12data] Date range: {df.index.min()} to {df.index.max()}")
        return df
        
    except requests.exceptions.Timeout:
        raise ValueError("12data API request timed out. Try again later.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Cannot connect to 12data API. Check your internet connection.")
    except Exception as e:
        print(f"[12data] Unexpected error: {str(e)}")
        raise ValueError(f"12data error: {str(e)}")


def compute_emas(df):
    df = df.copy()
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ema100"] = df["Close"].ewm(span=100, adjust=False).mean()
    return df


# Minimum candles before any signal is allowed
# EMA-100 needs ~100 bars to stabilize. Using 100 as warmup is sufficient.
# The old value of 300 caused 0 trades on datasets smaller than 300 bars (e.g. 1 year daily).
EMA_WARMUP_BARS = 100


def run_strategy(df, initial_capital: float, market: str = "india", lot_size: float | None = None, risk_per_trade: float = 100.0):
    """
    Fixed backtest logic with risk management:
    - Signal detected on bar N (EMA crossover at close)
    - Trade executed on bar N+1 open (actual strike price)
    - Risk per trade: percentage of current equity to use per trade
    - This avoids look-ahead bias and uses realistic execution prices
    """
    print(f"\n{'='*60}")
    print(f"STRATEGY BACKTEST STARTING")
    print(f"Initial Data: {len(df)} candles")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    print(f"Market: {market}, Initial Capital: {initial_capital}, Risk: {risk_per_trade}%")
    print(f"{'='*60}\n")
    
    df = df.copy()
    df["prev_ema20"] = df["ema20"].shift(1)
    df["prev_ema50"] = df["ema50"].shift(1)
    df["prev_ema100"] = df["ema100"].shift(1)
    
    # Debug: Show EMA values
    print("EMA Debug Info:")
    print(f"{'Bar':<5} {'DateTime':<20} {'Close':<10} {'EMA20':<10} {'EMA50':<10} {'EMA100':<10}")
    print("-" * 70)
    for i, (idx, row) in enumerate(df.iterrows()):
        if i < 10 or i >= len(df) - 5:  # Show first 10 and last 5 rows
            print(f"{i:<5} {str(idx):<20} {row['Close']:<10.2f} {row['ema20']:<10.2f} {row['ema50']:<10.2f} {row['ema100']:<10.2f}")
        elif i == 10:
            print("...")
    print()
    
    trades = []
    equity = float(initial_capital)
    position = 0
    entry_price = None
    entry_time = None
    entry_direction = None
    entry_units = 0.0
    entry_signal_bar = None
    exit_signal_bar = None
    stop_loss_price = None  # NEW: Track stop loss level
    
    # Store signal bar EMAs and prices for manual verification
    signal_bar_data = None
    exit_signal_bar_data = None
    
    pending_entry_direction = None
    pending_exit_signal = False
    
    # Lot sizing ONLY for forex market
    # For stocks/indices/uploaded data: always use simple position sizing
    use_lot_size = (market == "forex")
    lot_value = float(lot_size or DEFAULT_FOREX_LOT_SIZE) if market == "forex" else None
    
    # Convert risk percentage to decimal
    risk_multiplier = risk_per_trade / 100.0
    
    print(f"Strategy config: market={market}, use_lot_size={use_lot_size}, lot_value={lot_value}, risk={risk_per_trade}%, initial_capital={initial_capital}")
    print(f"Warmup Period: Skipping first {EMA_WARMUP_BARS} candles for EMA stabilization")

    df_list = list(df.iterrows())
    
    for i, (idx, row) in enumerate(df_list):
        close = float(row["Close"])
        open_price = float(row.get("Open", close))
        high_price = float(row.get("High", close))
        low_price = float(row.get("Low", close))
        prev20, prev50, prev100 = float(row["prev_ema20"]), float(row["prev_ema50"]), float(row["prev_ema100"])
        curr20, curr50, curr100 = float(row["ema20"]), float(row["ema50"]), float(row["ema100"])

        # Check if stop loss is hit (for active positions)
        # Loss % is calculated against INITIAL CAPITAL for the trade
        if position != 0:
            # Calculate unrealized loss based on worst price during candle
            if position == 1:  # LONG position
                worst_price = low_price
                unrealized_loss = entry_units * (entry_price - worst_price)
            else:  # SHORT position
                worst_price = high_price
                unrealized_loss = entry_units * (worst_price - entry_price)
            
            # Calculate loss % against INITIAL CAPITAL (not current equity)
            unrealized_loss_pct = (unrealized_loss / initial_capital) * 100.0
            
            # Check if unrealized loss exceeds risk limit
            if risk_per_trade < 100 and unrealized_loss_pct >= risk_per_trade:
                # Stop loss hit - calculate exit price to match exact risk % of INITIAL CAPITAL
                max_loss_amount = initial_capital * (risk_per_trade / 100.0)
                
                if position == 1:  # LONG
                    exit_price = entry_price - (max_loss_amount / entry_units)
                else:  # SHORT
                    exit_price = entry_price + (max_loss_amount / entry_units)
                
                # Exit due to stop loss
                if position == 1:
                    pnl = entry_units * (exit_price - entry_price)
                else:
                    pnl = entry_units * (entry_price - exit_price)
                
                equity += pnl
                pnl_pct = (pnl / initial_capital) * 100.0
                
                trades.append({
                    "entry_signal_bar": entry_signal_bar,
                    "entry_time": entry_time,
                    "exit_signal_bar": idx,
                    "exit_time": idx,
                    "direction": entry_direction,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "position_size": entry_units,
                    "capital_used": entry_units * entry_price,
                    "risk_pct": risk_per_trade,
                    "lot_size": lot_value if use_lot_size else None,
                    "equity_after": equity,
                    "stop_loss": True,
                    "signal_bar_close": signal_bar_data["close"] if signal_bar_data else None,
                    "signal_bar_ema20": signal_bar_data["ema20"] if signal_bar_data else None,
                    "signal_bar_ema50": signal_bar_data["ema50"] if signal_bar_data else None,
                    "signal_bar_ema100": signal_bar_data["ema100"] if signal_bar_data else None,
                    "exit_signal_close": close,
                    "exit_signal_ema20": curr20,
                    "exit_signal_ema50": curr50,
                })
                
                print(f"[STOP LOSS] Hit at {idx}: {entry_direction.upper()} closed at ${exit_price:.2f}, loss: ${abs(pnl):.2f} ({abs(pnl_pct):.2f}% of initial capital)")
                
                position = 0
                entry_price = None
                entry_time = None
                entry_direction = None
                entry_units = 0.0
                entry_signal_bar = None
                exit_signal_bar = None
                stop_loss_price = None
                signal_bar_data = None
                exit_signal_bar_data = None
                pending_exit_signal = False
                continue  # Skip normal exit logic

        # Execute pending entry at current bar's OPEN price
        if position == 0 and pending_entry_direction is not None:
            position = 1 if pending_entry_direction == "long" else -1
            entry_time = idx
            entry_price = open_price  # ACTUAL STRIKE PRICE at open
            entry_direction = pending_entry_direction
            
            # Calculate position size - FIXED, does not change with risk percentage
            if use_lot_size and lot_value is not None and market == "forex":
                # For FOREX/COMMODITIES: Fixed lot size (not adjusted by risk)
                entry_units = lot_value * 100
            else:
                # For STOCKS/INDICES/UPLOADED DATA: Fixed position sizing
                # Using 1% of equity as standard position size (or fixed amount)
                trade_capital = equity * 0.01  # Fixed 1% position size
                entry_units = trade_capital / entry_price
            
            # Calculate stop loss based on risk percentage of TOTAL ACCOUNT CAPITAL
            # Risk % = maximum loss as % of current equity
            if risk_per_trade == 100:
                # 100% risk = no stop loss
                stop_loss_price = None
                max_loss_amount = None
            else:
                # Maximum loss amount = risk% of current equity
                max_loss_amount = equity * (risk_per_trade / 100.0)
                
                # Calculate stop loss price based on max loss amount and position size
                # For LONG: stop_loss_price = entry_price - (max_loss / units)
                # For SHORT: stop_loss_price = entry_price + (max_loss / units)
                price_distance = max_loss_amount / entry_units
                
                if entry_direction == "long":
                    stop_loss_price = entry_price - price_distance
                else:
                    stop_loss_price = entry_price + price_distance
            
            stop_loss_str = f"${stop_loss_price:.2f}" if stop_loss_price is not None else "None (No Stop Loss)"
            max_loss_str = f"${max_loss_amount:.2f}" if max_loss_amount is not None else "Unlimited"
            print(f"Trade {len(trades)+1}: {entry_direction.upper()} entry at ${entry_price:.2f}, stop loss at {stop_loss_str}, max loss: {max_loss_str}, units={entry_units:.6f}, risk={risk_per_trade}%")
            
            pending_entry_direction = None
            
        # Execute pending exit at current bar's OPEN price
        elif position != 0 and pending_exit_signal:
            exit_price = open_price  # ACTUAL STRIKE PRICE at open
            if position == 1:
                pnl = entry_units * (exit_price - entry_price)
            else:
                pnl = entry_units * (entry_price - exit_price)
            
            equity += pnl
            pnl_pct = (pnl / initial_capital) * 100.0
            
            trades.append({
                "entry_signal_bar": entry_signal_bar,
                "entry_time": entry_time,
                "exit_signal_bar": exit_signal_bar,
                "exit_time": idx,
                "direction": entry_direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "position_size": entry_units,
                "capital_used": entry_units * entry_price,
                "risk_pct": risk_per_trade,
                "lot_size": lot_value if use_lot_size else None,
                "equity_after": equity,
                # Signal bar details for manual verification
                "signal_bar_close": signal_bar_data["close"] if signal_bar_data else None,
                "signal_bar_ema20": signal_bar_data["ema20"] if signal_bar_data else None,
                "signal_bar_ema50": signal_bar_data["ema50"] if signal_bar_data else None,
                "signal_bar_ema100": signal_bar_data["ema100"] if signal_bar_data else None,
                "exit_signal_close": exit_signal_bar_data["close"] if exit_signal_bar_data else None,
                "exit_signal_ema20": exit_signal_bar_data["ema20"] if exit_signal_bar_data else None,
                "exit_signal_ema50": exit_signal_bar_data["ema50"] if exit_signal_bar_data else None,
            })
            
            position = 0
            entry_price = None
            entry_time = None
            entry_direction = None
            entry_units = 0.0
            entry_signal_bar = None
            exit_signal_bar = None
            signal_bar_data = None
            exit_signal_bar_data = None
            pending_exit_signal = False

        # Detect entry signals at CLOSE of current bar
        if position == 0 and pending_entry_direction is None:
            # Skip warmup period to avoid false signals
            if i < EMA_WARMUP_BARS:
                continue
                
            # LONG signal: EMA50 crosses above EMA100
            if prev50 <= prev100 and curr50 > curr100:
                print(f"[SIGNAL] LONG at bar {i}: EMA50 crossed above EMA100 (prev50={prev50:.2f} <= prev100={prev100:.2f}, curr50={curr50:.2f} > curr100={curr100:.2f})")
                print(f"          EMA Values: EMA20={curr20:.2f}, EMA50={curr50:.2f}, EMA100={curr100:.2f}")
                pending_entry_direction = "long"
                entry_signal_bar = idx
                signal_bar_data = {
                    "close": close if not math.isnan(close) else None,
                    "ema20": curr20 if not math.isnan(curr20) else None,
                    "ema50": curr50 if not math.isnan(curr50) else None,
                    "ema100": curr100 if not math.isnan(curr100) else None,
                }
                    
            # SHORT signal: EMA50 crosses below EMA100
            elif prev50 >= prev100 and curr50 < curr100:
                print(f"[SIGNAL] SHORT at bar {i}: EMA50 crossed below EMA100 (prev50={prev50:.2f} >= prev100={prev100:.2f}, curr50={curr50:.2f} < curr100={curr100:.2f})")
                print(f"          EMA Values: EMA20={curr20:.2f}, EMA50={curr50:.2f}, EMA100={curr100:.2f}")
                pending_entry_direction = "short"
                entry_signal_bar = idx
                signal_bar_data = {
                    "close": close if not math.isnan(close) else None,
                    "ema20": curr20 if not math.isnan(curr20) else None,
                    "ema50": curr50 if not math.isnan(curr50) else None,
                    "ema100": curr100 if not math.isnan(curr100) else None,
                }
                
        # Detect exit signals at CLOSE of current bar
        elif position == 1 and not pending_exit_signal:
            if prev20 >= prev50 and curr20 < curr50:
                pending_exit_signal = True
                exit_signal_bar = idx
                # Store exit signal bar data for manual verification (handle NaN)
                exit_signal_bar_data = {
                    "close": close if not math.isnan(close) else None,
                    "ema20": curr20 if not math.isnan(curr20) else None,
                    "ema50": curr50 if not math.isnan(curr50) else None,
                }
                
        elif position == -1 and not pending_exit_signal:
            if prev20 <= prev50 and curr20 > curr50:
                pending_exit_signal = True
                exit_signal_bar = idx
                # Store exit signal bar data for manual verification (handle NaN)
                exit_signal_bar_data = {
                    "close": close if not math.isnan(close) else None,
                    "ema20": curr20 if not math.isnan(curr20) else None,
                    "ema50": curr50 if not math.isnan(curr50) else None,
                }

    # Handle open positions at end of data
    if position != 0 and entry_time is not None:
        last_close = float(df["Close"].iloc[-1])
        if position == 1:
            pnl = entry_units * (last_close - entry_price)
        else:
            pnl = entry_units * (entry_price - last_close)
        
        equity += pnl
        pnl_pct = (pnl / initial_capital) * 100.0
        
        trades.append({
            "entry_signal_bar": entry_signal_bar,
            "entry_time": entry_time,
            "exit_signal_bar": df.index[-1],
            "exit_time": df.index[-1],
            "direction": entry_direction,
            "entry_price": entry_price,
            "exit_price": last_close,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "position_size": entry_units,
            "capital_used": entry_units * entry_price,
            "risk_pct": risk_per_trade,
            "lot_size": lot_value if use_lot_size else None,
            "equity_after": equity,
            # Signal bar details for manual verification
            "signal_bar_close": signal_bar_data["close"] if signal_bar_data else None,
            "signal_bar_ema20": signal_bar_data["ema20"] if signal_bar_data else None,
            "signal_bar_ema50": signal_bar_data["ema50"] if signal_bar_data else None,
            "signal_bar_ema100": signal_bar_data["ema100"] if signal_bar_data else None,
            "exit_signal_close": None,
            "exit_signal_ema20": None,
            "exit_signal_ema50": None,
        })

    trade_df = pd.DataFrame(trades)
    if not trade_df.empty:
        trade_df["is_win"] = trade_df["pnl"] > 0
        trade_df["entry_signal_bar"] = pd.to_datetime(trade_df["entry_signal_bar"])
        trade_df["entry_time"] = pd.to_datetime(trade_df["entry_time"])
        trade_df["exit_signal_bar"] = pd.to_datetime(trade_df["exit_signal_bar"])
        trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
        trade_df = trade_df.sort_values("entry_time")
        
        # Replace NaN values with None for JSON compatibility
        trade_df = trade_df.replace({pd.NA: None, float('nan'): None, float('inf'): None, float('-inf'): None})
        trade_df = trade_df.where(pd.notnull(trade_df), None)
        
        # Format for frontend display
        trade_log = trade_df[[
            "entry_signal_bar", "entry_time", "exit_signal_bar", "exit_time", 
            "direction", "entry_price", "exit_price", "pnl", "pnl_pct", 
            "position_size", "capital_used", "risk_pct", "lot_size", "equity_after", "is_win",
            "signal_bar_close", "signal_bar_ema20", "signal_bar_ema50", "signal_bar_ema100",
            "exit_signal_close", "exit_signal_ema20", "exit_signal_ema50"
        ]].copy()
        
        trade_log["entry_signal_bar"] = trade_log["entry_signal_bar"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log["entry_time"] = trade_log["entry_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log["exit_signal_bar"] = trade_log["exit_signal_bar"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log["exit_time"] = trade_log["exit_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Limit trade log to prevent response size issues
        # For large backtests, only return the most recent 1000 trades
        max_trades_to_return = 1000
        total_trades = len(trade_log)
        if total_trades > max_trades_to_return:
            trade_log = trade_log.tail(max_trades_to_return)
            print(f"Trade log limited: showing last {max_trades_to_return} of {total_trades} trades")
        
        trade_log = trade_log.to_dict("records")
    else:
        trade_log = []
        total_trades = 0

    total_pnl = round(float(trade_df["pnl"].sum()), 2) if not trade_df.empty else 0.0
    avg_pnl = round(float(trade_df["pnl"].mean()), 2) if not trade_df.empty else 0.0
    
    # Calculate max drawdown
    if not trade_df.empty:
        equity_curve = [initial_capital] + trade_df["equity_after"].tolist()
        running_max = pd.Series(equity_curve).cummax()
        drawdown = ((pd.Series(equity_curve) / running_max) - 1).min() * 100.0
        max_drawdown = round(float(drawdown), 2)
    else:
        max_drawdown = 0.0

    summary = {
        "trades": int(len(trade_df)),
        "wins": int((trade_df["pnl"] > 0).sum()) if not trade_df.empty else 0,
        "losses": int((trade_df["pnl"] <= 0).sum()) if not trade_df.empty else 0,
        "accuracy": round((trade_df["pnl"] > 0).mean() * 100.0, 2) if not trade_df.empty else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "max_drawdown": max_drawdown,
        "ending_equity": round(equity, 2),
        "initial_capital": round(float(initial_capital), 2),
        "trades_displayed": len(trade_log) if trade_log else 0,
        "trades_limited": total_trades > len(trade_log) if not trade_df.empty else False,
    }
    
    print(f"\n{'='*60}")
    print(f"STRATEGY BACKTEST COMPLETE")
    print(f"Total Trades: {summary['trades']}")
    print(f"Wins: {summary['wins']} | Losses: {summary['losses']} | Accuracy: {summary['accuracy']}%")
    print(f"Total PnL: ${summary['total_pnl']} | Avg PnL: ${summary['avg_pnl']}")
    print(f"Ending Equity: ${summary['ending_equity']}")
    print(f"{'='*60}\n")
    
    return {"summary": summary, "trade_log": trade_log}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"markets": MARKET_OPTIONS})


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({"message": "No favicon"}, status_code=204)


@app.post("/test")
async def test_endpoint(req: BacktestRequest):
    """Test endpoint to debug request parsing"""
    return JSONResponse({"received": req.dict(), "success": True})


@app.get("/test-risk-calc")
async def test_risk_calculation():
    """Test endpoint to verify risk calculations"""
    initial_capital = 100000
    entry_price = 24000  # Nifty price example
    
    test_cases = []
    for risk_pct in [3, 5, 10, 20, 100]:
        risk_multiplier = risk_pct / 100.0
        trade_capital = initial_capital * risk_multiplier
        position_size = trade_capital / entry_price
        
        test_cases.append({
            "risk_percent": risk_pct,
            "initial_capital": initial_capital,
            "trade_capital": round(trade_capital, 2),
            "entry_price": entry_price,
            "position_size": round(position_size, 2),
            "example": f"With {risk_pct}% risk on ₹{initial_capital:,}, you use ₹{trade_capital:,.0f} = {position_size:.2f} units at ₹{entry_price}"
        })
    
    # Forex example
    forex_cases = []
    forex_price = 1.08  # EUR/USD example
    for risk_pct in [3, 5, 10, 100]:
        risk_multiplier = risk_pct / 100.0
        trade_capital = initial_capital * risk_multiplier
        position_size = trade_capital / forex_price
        
        forex_cases.append({
            "risk_percent": risk_pct,
            "trade_capital": round(trade_capital, 2),
            "forex_price": forex_price,
            "position_size_units": round(position_size, 2),
            "equivalent_lots": round(position_size / 100000, 4),
            "example": f"With {risk_pct}% risk, you trade {position_size:,.0f} units = {position_size/100000:.4f} standard lots"
        })
    
    return JSONResponse({
        "success": True,
        "stocks_indices": test_cases,
        "forex": forex_cases,
        "note": "Position size automatically adjusts based on risk percentage"
    })


def load_csv_data(file_content: bytes):
    """Load and validate CSV data from uploaded file"""
    try:
        # Try to read the CSV
        df = pd.read_csv(io.BytesIO(file_content))
        
        if df.empty:
            raise ValueError("CSV file is empty")
        
        # Find datetime column
        datetime_col = None
        for candidate in ["datetime", "date", "time", "timestamp", "Date", "DateTime", "Timestamp"]:
            if candidate in df.columns:
                datetime_col = candidate
                break
        
        if datetime_col is None:
            # Try combining date and time columns
            if "date" in df.columns and "time" in df.columns:
                df["DateTime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
                datetime_col = "DateTime"
            else:
                raise ValueError("CSV must contain a datetime column (Date, DateTime, or Timestamp)")
        
        # Find OHLC columns (case-insensitive)
        col_map = {}
        df_cols_lower = {col.lower(): col for col in df.columns}
        
        for required in ["open", "high", "low", "close"]:
            if required in df_cols_lower:
                col_map[required] = df_cols_lower[required]
            elif required.capitalize() in df.columns:
                col_map[required] = required.capitalize()
            else:
                raise ValueError(f"CSV must contain '{required}' column")
        
        # Create clean dataframe
        clean_df = pd.DataFrame({
            "Date": pd.to_datetime(df[datetime_col], errors="coerce"),
            "Open": pd.to_numeric(df[col_map["open"]], errors="coerce"),
            "High": pd.to_numeric(df[col_map["high"]], errors="coerce"),
            "Low": pd.to_numeric(df[col_map["low"]], errors="coerce"),
            "Close": pd.to_numeric(df[col_map["close"]], errors="coerce"),
        })
        
        # Add volume if available
        if "volume" in df_cols_lower:
            clean_df["Volume"] = pd.to_numeric(df[df_cols_lower["volume"]], errors="coerce").fillna(0)
        else:
            clean_df["Volume"] = 0
        
        # Clean and validate
        clean_df = clean_df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
        clean_df = clean_df.set_index("Date").sort_index()
        
        if clean_df.empty:
            raise ValueError("No valid data rows found in CSV after cleaning")
        
        print(f"Loaded {len(clean_df)} rows from CSV, date range: {clean_df.index.min()} to {clean_df.index.max()}")
        
        return clean_df
        
    except Exception as e:
        raise ValueError(f"Error reading CSV file: {str(e)}")


@app.post("/run-backtest")
async def run_backtest(
    request: Request,
    market: Optional[str] = Form(None),
    symbol: Optional[str] = Form(None),
    custom_symbol: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    interval: Optional[str] = Form(None),
    initial_capital: Optional[float] = Form(None),
    risk_per_trade: Optional[float] = Form(None),
    lot_size: Optional[float] = Form(None),
    data_source: Optional[str] = Form(None),
    csv_file: Optional[UploadFile] = File(None),
):
    """
    Backtest endpoint supporting both JSON and multipart form data (for file upload)
    """
    try:
        # Check if this is a JSON request (no file upload)
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            # Parse JSON body
            body = await request.json()
            market = body.get("market", "india")
            selected_symbol = str(body.get("custom_symbol") or body.get("symbol") or "").strip()
            start_date = str(body.get("start_date") or "")
            end_date = str(body.get("end_date") or "")
            interval = str(body.get("interval") or "1d")
            initial_capital = float(body.get("initial_capital") or 100000)
            risk_per_trade_val = float(body.get("risk_per_trade") or 100.0)
            lot_size_val = float(body.get("lot_size") or DEFAULT_FOREX_LOT_SIZE) if market == "forex" else None
            data_source_val = body.get("data_source") or "yahoo"
            csv_file = None
        else:
            # Form data (with potential file upload)
            market = market or "india"
            selected_symbol = str(custom_symbol or symbol or "").strip()
            start_date = start_date or ""
            end_date = end_date or ""
            interval = interval or "1d"
            initial_capital = float(initial_capital or 100000)
            risk_per_trade_val = float(risk_per_trade or 100.0)
            lot_size_val = float(lot_size or DEFAULT_FOREX_LOT_SIZE) if market == "forex" else None
            data_source_val = data_source or "yahoo"
        
        print(f"Received request - Market: {market}, Symbol: {selected_symbol}, Source: {data_source_val}, Risk: {risk_per_trade_val}%")
        
        # Handle file upload data source
        if data_source_val == "upload":
            if csv_file is None:
                raise ValueError("Please upload a CSV or Excel file")
            
            # Read uploaded file
            file_content = await csv_file.read()
            
            # Check file extension
            filename = csv_file.filename.lower()
            if filename.endswith('.csv'):
                df = process_uploaded_file(file_content, csv_file.filename)
            elif filename.endswith(('.xlsx', '.xls')):
                df = process_uploaded_file(file_content, csv_file.filename)
            else:
                raise ValueError("Unsupported file format. Please upload CSV or Excel (.xlsx, .xls) file")
            
            selected_symbol = csv_file.filename  # Use filename as symbol
            print(f"Processed uploaded file: {csv_file.filename}, rows: {len(df)}, date range: {df.index.min()} to {df.index.max()}")
            
        else:
            # Use standard data sources
            if not selected_symbol:
                raise ValueError("Please select a symbol")
            if not start_date or not end_date:
                raise ValueError("Please provide start and end dates")
            
            # Auto-detect Binance symbols and use Binance API
            if data_source_val == "yahoo" and selected_symbol.upper().endswith(('USDT', 'BUSD', 'USDC', 'TUSD')):
                print(f"Auto-detected Binance symbol: {selected_symbol}, switching to Binance API")
                data_source_val = "binance"
            
            df = download_market_data(selected_symbol, start_date, end_date, interval, data_source_val)
        
        print(f"Downloaded {len(df)} rows of data")
        
        # Add performance warning for very large datasets
        if len(df) > 100000:
            print(f"⚠️ Large dataset detected ({len(df):,} rows). Computing EMAs...")
        
        df = compute_emas(df)
        print(f"✓ Computed EMAs, starting backtest with {len(df):,} rows...")
        
        result = run_strategy(df, initial_capital, market=market, lot_size=lot_size_val, risk_per_trade=risk_per_trade_val)
        print(f"✓ Backtest complete: {result['summary']['trades']} trades generated")
        
        source_names = {
            "yahoo": "Yahoo Finance",
            "tweleve_data": "12data API",
            "upload": f"Uploaded CSV ({csv_file.filename if csv_file else 'file'})",
            "alpha_vantage": "Alpha Vantage",
            "polygon": "Polygon.io",
            "binance": "Binance API"
        }
        
        return JSONResponse(
            {
                "success": True,
                "summary": result["summary"],
                "trade_log": result["trade_log"],
                "symbol": selected_symbol,
                "symbol_label": get_symbol_label(selected_symbol, market),
                "market": market,
                "market_label": market.capitalize(),
                "currency": "₹" if market == "india" else "$",
                "currency_code": "INR" if market == "india" else "USD",
                "source": source_names.get(data_source_val, "Custom Data"),
                "date_range": f"{df.index.min().strftime('%Y-%m-%d %H:%M:%S')} to {df.index.max().strftime('%Y-%m-%d %H:%M:%S')}" if data_source_val == "upload" else None,
                "rows_processed": len(df) if data_source_val == "upload" else None,
            }
        )
    except Exception as exc:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Error occurred: {error_detail}")  # Debug
        return JSONResponse({"success": False, "error": str(exc)}, status_code=200)
