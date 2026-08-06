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
TWELEVE_DATA_API_KEY = "25753a3ca5dd493896ae4e6a9a755631add"  # Tweleve Data API key

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
        {"value": "EURUSD=X", "label": "EUR/USD"},
        {"value": "GBPUSD=X", "label": "GBP/USD"},
        {"value": "USDJPY=X", "label": "USD/JPY"},
        {"value": "AUDUSD=X", "label": "AUD/USD"},
        {"value": "USDCAD=X", "label": "USD/CAD"},
        {"value": "USDCHF=X", "label": "USD/CHF"},
        {"value": "NZDUSD=X", "label": "NZD/USD"},
        {"value": "EURGBP=X", "label": "EUR/GBP"},
        {"value": "EURJPY=X", "label": "EUR/JPY"},
        {"value": "GBPJPY=X", "label": "GBP/JPY"},
        {"value": "USDINR=X", "label": "USD/INR"},
        {"value": "EURINR=X", "label": "EUR/INR"},
        {"value": "GBPINR=X", "label": "GBP/INR"},
        {"value": "JPYINR=X", "label": "JPY/INR"},
        {"value": "GLD", "label": "Gold (GLD ETF - Recommended)"},
        {"value": "SLV", "label": "Silver (SLV ETF)"},
        {"value": "BTC-USD", "label": "Bitcoin (BTC/USD)"},
        {"value": "ETH-USD", "label": "Ethereum (ETH/USD)"},
        {"value": "BTCXAU=X", "label": "BTC/Gold (Synthetic)"},
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


def download_market_data(symbol: str, start: str, end: str, interval: str, data_source: str = "yahoo", uploaded_df: pd.DataFrame = None):
    """
    Download market data from multiple sources or use uploaded file
    data_source: 'yahoo', 'alpha_vantage', 'polygon', 'tweleve_data', or 'upload'
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


def download_tweleve_data(symbol: str, start: str, end: str, interval: str):
    """
    Tweleve Data API download - real-time and historical market data
    Supports multiple asset classes: stocks, forex, crypto, commodities
    API Key: 25753a3ca5dd493896ae4e6a9a755631add
    """
    start, end = normalize_date_range(start, end)
    
    # Map intervals to Tweleve Data format
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
    
    print(f"Fetching {symbol} from Tweleve Data: {start} to {end}, interval: {tweleve_interval}")
    
    response = requests.get(url, params=params, timeout=30)
    
    if response.status_code != 200:
        raise ValueError(f"Tweleve Data API error: {response.status_code}")
    
    data_json = response.json()
    
    # Check for errors
    if data_json.get("status") == "error":
        raise ValueError(f"Tweleve Data error: {data_json.get('message', 'Unknown error')}")
    
    if "data" not in data_json or not data_json["data"]:
        raise ValueError(f"No data found for {symbol} from Tweleve Data. Check symbol format.")
    
    # Parse JSON to DataFrame
    records = []
    for candle in data_json["data"]:
        records.append({
            "datetime": candle["datetime"],
            "Open": float(candle["open"]),
            "High": float(candle["high"]),
            "Low": float(candle["low"]),
            "Close": float(candle["close"]),
            "Volume": float(candle.get("volume", 0))
        })
    
    df = pd.DataFrame(records)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    df = df.sort_index()
    
    if df.empty:
        raise ValueError(f"No data found for {symbol} in the selected date range from Tweleve Data")
    
    print(f"✓ Successfully downloaded {len(df)} rows from Tweleve Data")
    return df


def compute_emas(df):
    df = df.copy()
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ema100"] = df["Close"].ewm(span=100, adjust=False).mean()
    return df


def run_strategy(df, initial_capital: float, market: str = "india", lot_size: float | None = None, risk_per_trade: float = 100.0):
    """
    Fixed backtest logic with risk management:
    - Signal detected on bar N (EMA crossover at close)
    - Trade executed on bar N+1 open (actual strike price)
    - Risk per trade: percentage of current equity to use per trade
    - This avoids look-ahead bias and uses realistic execution prices
    """
    df = df.copy()
    df["prev_ema20"] = df["ema20"].shift(1)
    df["prev_ema50"] = df["ema50"].shift(1)
    df["prev_ema100"] = df["ema100"].shift(1)
    
    trades = []
    equity = float(initial_capital)
    position = 0
    entry_price = None
    entry_time = None
    entry_direction = None
    entry_units = 0.0
    entry_signal_bar = None
    exit_signal_bar = None
    
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

    df_list = list(df.iterrows())
    
    for i, (idx, row) in enumerate(df_list):
        close = float(row["Close"])
        open_price = float(row.get("Open", close))
        prev20, prev50, prev100 = float(row["prev_ema20"]), float(row["prev_ema50"]), float(row["prev_ema100"])
        curr20, curr50, curr100 = float(row["ema20"]), float(row["ema50"]), float(row["ema100"])

        # Execute pending entry at current bar's OPEN price
        if position == 0 and pending_entry_direction is not None:
            position = 1 if pending_entry_direction == "long" else -1
            entry_time = idx
            entry_price = open_price  # ACTUAL STRIKE PRICE at open
            entry_direction = pending_entry_direction
            
            # Calculate position size based on risk percentage
            trade_capital = equity * risk_multiplier
            
            if use_lot_size and lot_value is not None and market == "forex":
                # For FOREX: lot_value is DIRECT units to trade
                # lot_value = 0.10 means trade 0.10 BTC (not 0.10 lots)
                # lot_value = 1 means trade 1 BTC
                # Position size is directly the lot size (in units of the asset)
                entry_units = lot_value
            else:
                # For STOCKS/INDICES/UPLOADED DATA: position sizing based on capital
                # entry_units = how many shares/units to buy
                # Formula: units = (equity * risk%) / entry_price
                entry_units = trade_capital / entry_price
            
            print(f"Trade {len(trades)+1}: equity={equity:.2f}, capital={trade_capital:.2f}, price={entry_price:.2f}, units={entry_units:.6f}, use_lot_size={use_lot_size}")
            
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
            if prev50 <= prev100 and curr50 > curr100:
                pending_entry_direction = "long"
                entry_signal_bar = idx
                # Store signal bar data for manual verification (handle NaN)
                signal_bar_data = {
                    "close": close if not math.isnan(close) else None,
                    "ema20": curr20 if not math.isnan(curr20) else None,
                    "ema50": curr50 if not math.isnan(curr50) else None,
                    "ema100": curr100 if not math.isnan(curr100) else None,
                }
            elif prev50 >= prev100 and curr50 < curr100:
                pending_entry_direction = "short"
                entry_signal_bar = idx
                # Store signal bar data for manual verification (handle NaN)
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
            "tweleve_data": "Tweleve Data API",
            "upload": f"Uploaded CSV ({csv_file.filename if csv_file else 'file'})",
            "alpha_vantage": "Alpha Vantage",
            "polygon": "Polygon.io"
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
