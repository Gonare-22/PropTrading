from fastapi import FastAPI, Request
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

app = FastAPI(title="EMA Strategy Backtest UI")
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(base_dir / "templates"))

# Pydantic model for request validation
class BacktestRequest(BaseModel):
    market: Optional[str] = "india"
    symbol: Optional[str] = ""
    custom_symbol: Optional[str] = ""
    start_date: str
    end_date: str
    interval: Optional[str] = "1d"
    initial_capital: Optional[float] = 100000
    risk_per_trade: Optional[float] = 100.0  # Percentage of capital to risk per trade
    lot_size: Optional[float] = 0.10
    data_source: Optional[str] = "yahoo"  # yahoo, alpha_vantage, polygon

DEFAULT_FOREX_LOT_SIZE = 0.10

# API Keys (set these in environment variables for production)
ALPHA_VANTAGE_KEY = "demo"  # Replace with your key or set env var
POLYGON_API_KEY = "demo"    # Replace with your key or set env var

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
        {"value": "XAUUSD=X", "label": "Gold (XAU/USD)"},
        {"value": "XAGUSD=X", "label": "Silver (XAG/USD)"},
        {"value": "BTC-USD", "label": "Bitcoin (BTC/USD)"},
        {"value": "ETH-USD", "label": "Ethereum (ETH/USD)"},
        {"value": "BTCXAU=X", "label": "BTC/Gold"},
    ],
}

DEFAULT_FOREX_LOT_SIZE = 0.10

# API Keys (set these in environment variables for production)
ALPHA_VANTAGE_KEY = "demo"  # Replace with your key or set env var
POLYGON_API_KEY = "demo"    # Replace with your key or set env var


def get_symbol_label(symbol: str, market: str):
    options = MARKET_OPTIONS.get(market, [])
    for item in options:
        if item["value"] == symbol:
            return item["label"]
    return symbol


def resolve_yahoo_symbol(symbol: str):
    mapping = {
        "XAUUSD=X": "GC=F",
        "XAGUSD=X": "SI=F",
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


def download_market_data(symbol: str, start: str, end: str, interval: str, data_source: str = "yahoo"):
    """
    Download market data from multiple sources
    data_source: 'yahoo', 'alpha_vantage', or 'polygon'
    """
    if data_source == "yahoo":
        return download_yahoo_data(symbol, start, end, interval)
    elif data_source == "alpha_vantage":
        return download_alpha_vantage_data(symbol, start, end, interval)
    elif data_source == "polygon":
        return download_polygon_data(symbol, start, end, interval)
    else:
        return download_yahoo_data(symbol, start, end, interval)


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
    use_lot_size = market == "forex"
    lot_value = float(lot_size or DEFAULT_FOREX_LOT_SIZE)
    
    # Convert risk percentage to decimal
    risk_multiplier = risk_per_trade / 100.0

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
            
            if use_lot_size:
                # For forex: calculate lot size based on trade capital
                # Standard lot = 100,000 units, Mini lot = 10,000, Micro = 1,000
                # entry_units = number of units (not lots)
                # With risk management: use proportional capital
                max_units = lot_value * 100000.0  # Base lot size in units
                entry_units = (trade_capital / entry_price) if risk_multiplier < 1.0 else max_units
            else:
                # For stocks/indices: simple position sizing
                entry_units = trade_capital / entry_price
            
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
        trade_log = trade_log.to_dict("records")
    else:
        trade_log = []

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


@app.post("/run-backtest")
async def run_backtest(req: BacktestRequest):
    try:
        print(f"Received request: {req.dict()}")  # Debug logging
        
        market = req.market or "india"
        selected_symbol = str(req.custom_symbol or req.symbol or "").strip()
        start_date = str(req.start_date or "")
        end_date = str(req.end_date or "")
        interval = str(req.interval or "1d")
        initial_capital = float(req.initial_capital or 100000)
        risk_per_trade = float(req.risk_per_trade or 100.0)
        lot_size = float(req.lot_size or DEFAULT_FOREX_LOT_SIZE) if market == "forex" else None
        data_source = req.data_source or "yahoo"
        
        print(f"Parsed values - Symbol: {selected_symbol}, Start: {start_date}, End: {end_date}, Interval: {interval}, Risk: {risk_per_trade}%")  # Debug logging

        if not selected_symbol:
            raise ValueError("Please select a symbol")
        if not start_date or not end_date:
            raise ValueError("Please provide start and end dates")

        df = download_market_data(selected_symbol, start_date, end_date, interval, data_source)
        print(f"Downloaded {len(df)} rows of data")  # Debug
        
        df = compute_emas(df)
        print(f"Computed EMAs, starting backtest...")  # Debug
        
        result = run_strategy(df, initial_capital, market=market, lot_size=lot_size, risk_per_trade=risk_per_trade)
        print(f"Backtest complete: {result['summary']['trades']} trades generated")  # Debug
        
        source_names = {
            "yahoo": "Yahoo Finance",
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
                "source": source_names.get(data_source, "Yahoo Finance"),
            }
        )
    except Exception as exc:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Error occurred: {error_detail}")  # Debug
        return JSONResponse({"success": False, "error": str(exc)}, status_code=200)
