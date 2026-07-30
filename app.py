from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import pandas as pd
import yfinance as yf

app = FastAPI(title="EMA Strategy Backtest UI")
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(base_dir / "templates"))

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
        {"value": "USDINR=X", "label": "USD/INR"},
        {"value": "XAUUSD=X", "label": "XAU/USD"},
        {"value": "BTCUSD=X", "label": "BTC/USD"},
        {"value": "BTCXAU=X", "label": "BTC/XAU"},
    ],
}
BROKERAGE_RATES = {
    "Zerodha": 20.0,
    "Groww": 20.0,
    "Upstox": 20.0,
    "Angel One": 20.0,
}
DEFAULT_FOREX_LOT_SIZE = 0.10


def get_symbol_label(symbol: str, market: str):
    options = MARKET_OPTIONS.get(market, [])
    for item in options:
        if item["value"] == symbol:
            return item["label"]
    return symbol


def resolve_yahoo_symbol(symbol: str):
    mapping = {
        "XAUUSD=X": "GC=F",
        "BTCUSD=X": "BTC-USD",
        "BTCXAU=X": "BTCXAU=X",
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


def download_market_data(symbol: str, start: str, end: str, interval: str):
    resolved_symbol = resolve_yahoo_symbol(symbol)
    start, end = normalize_date_range(start, end)

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

    if interval in {"1m", "2m", "5m", "15m", "30m", "60m", "1h"}:
        data = fetch_yahoo_chunked(resolved_symbol, start, end, interval)
        if not data.empty:
            data.index = pd.to_datetime(data.index)
            data = data.sort_index().dropna(subset=["Close"])
            return data

    for attempt_interval in ([interval] if interval not in {"1m", "5m", "15m", "1h"} else ["1d"]):
        data = yf.download(
            resolved_symbol,
            start=start,
            end=end,
            interval=attempt_interval,
            auto_adjust=False,
            progress=False,
            prepost=False,
            threads=False,
        )
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
            data.index = pd.to_datetime(data.index)
            data = data.sort_index().dropna(subset=["Close"])
            return data

    raise ValueError(f"No data found for {symbol} in the selected date range. Try a broader date range or daily data")


def compute_emas(df):
    df = df.copy()
    df["ema20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ema100"] = df["Close"].ewm(span=100, adjust=False).mean()
    return df


def run_strategy(df, initial_capital: float, market: str = "india", lot_size: float | None = None):
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
    pending_entry_direction = None
    pending_exit_signal = False
    use_lot_size = market == "forex"
    lot_value = float(lot_size or DEFAULT_FOREX_LOT_SIZE)

    for idx, row in df.iterrows():
        close = float(row["Close"])
        open_price = float(row.get("Open", close))
        prev20, prev50, prev100 = float(row["prev_ema20"]), float(row["prev_ema50"]), float(row["prev_ema100"])
        curr20, curr50, curr100 = float(row["ema20"]), float(row["ema50"]), float(row["ema100"])

        if position == 0:
            if pending_entry_direction is not None:
                position = 1 if pending_entry_direction == "long" else -1
                entry_time = idx
                entry_price = open_price
                entry_direction = pending_entry_direction
                entry_units = (lot_value * 100000.0) if use_lot_size else (equity / entry_price)
                pending_entry_direction = None
            elif prev50 <= prev100 and curr50 > curr100:
                pending_entry_direction = "long"
            elif prev50 >= prev100 and curr50 < curr100:
                pending_entry_direction = "short"
        elif position == 1:
            if pending_exit_signal:
                exit_price = open_price
                pnl = entry_units * (exit_price - entry_price)
                equity += pnl
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": idx,
                        "direction": entry_direction,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "position_size": entry_units,
                        "lot_size": lot_value if use_lot_size else None,
                    }
                )
                position = 0
                entry_price = None
                entry_time = None
                entry_direction = None
                entry_units = 0.0
                pending_exit_signal = False
            elif prev20 >= prev50 and curr20 < curr50:
                pending_exit_signal = True
        elif position == -1:
            if pending_exit_signal:
                exit_price = open_price
                pnl = entry_units * (entry_price - exit_price)
                equity += pnl
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": idx,
                        "direction": entry_direction,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "position_size": entry_units,
                        "lot_size": lot_value if use_lot_size else None,
                    }
                )
                position = 0
                entry_price = None
                entry_time = None
                entry_direction = None
                entry_units = 0.0
                pending_exit_signal = False
            elif prev20 <= prev50 and curr20 > curr50:
                pending_exit_signal = True

    if position != 0 and entry_time is not None:
        last_open = float(df["Open"].iloc[-1]) if "Open" in df.columns else float(df["Close"].iloc[-1])
        pnl = entry_units * (last_open - entry_price) if entry_direction == "long" else entry_units * (entry_price - last_open)
        equity += pnl
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": df.index[-1],
                "direction": entry_direction,
                "entry_price": entry_price,
                "exit_price": last_open,
                "pnl": pnl,
                "position_size": entry_units,
                "lot_size": lot_value if use_lot_size else None,
            }
        )

    trade_df = pd.DataFrame(trades)
    if not trade_df.empty:
        trade_df["is_win"] = trade_df["pnl"] > 0
        trade_df["entry_time"] = pd.to_datetime(trade_df["entry_time"])
        trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
        trade_df = trade_df.sort_values("entry_time")
        trade_log = trade_df[["entry_time", "exit_time", "direction", "entry_price", "exit_price", "pnl", "position_size", "lot_size", "is_win"]].copy()
        trade_log["entry_time"] = trade_log["entry_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log["exit_time"] = trade_log["exit_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trade_log = trade_log.to_dict("records")
    else:
        trade_log = []

    total_pnl = round(float(trade_df["pnl"].sum()), 2) if not trade_df.empty else 0.0
    brokerage_summary = []
    if not trade_df.empty:
        orders = int(len(trade_df)) * 2
        for broker, rate in BROKERAGE_RATES.items():
            cost = round(orders * rate, 2)
            net = round(total_pnl - cost, 2)
            brokerage_summary.append(f"{broker}: ₹{cost} total, net PnL ₹{net}")

    summary = {
        "trades": int(len(trade_df)),
        "wins": int((trade_df["pnl"] > 0).sum()) if not trade_df.empty else 0,
        "losses": int((trade_df["pnl"] <= 0).sum()) if not trade_df.empty else 0,
        "accuracy": round((trade_df["pnl"] > 0).mean() * 100.0, 2) if not trade_df.empty else 0.0,
        "total_pnl": total_pnl,
        "ending_equity": round(equity, 2),
        "initial_capital": round(float(initial_capital), 2),
        "brokerage_summary": brokerage_summary,
    }
    return {"summary": summary, "trade_log": trade_log}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"markets": MARKET_OPTIONS})


async def parse_backtest_payload(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        return {
            "market": payload.get("market", "india"),
            "symbol": payload.get("symbol", ""),
            "custom_symbol": payload.get("custom_symbol", ""),
            "start_date": payload.get("start_date", ""),
            "end_date": payload.get("end_date", ""),
            "interval": payload.get("interval", "1m"),
            "initial_capital": payload.get("initial_capital", 100000),
            "lot_size": payload.get("lot_size", DEFAULT_FOREX_LOT_SIZE),
        }

    form = await request.form()
    return {
        "market": form.get("market", "india"),
        "symbol": form.get("symbol", ""),
        "custom_symbol": form.get("custom_symbol", ""),
        "start_date": form.get("start_date", ""),
        "end_date": form.get("end_date", ""),
        "interval": form.get("interval", "1m"),
        "initial_capital": form.get("initial_capital", 100000),
        "lot_size": form.get("lot_size", DEFAULT_FOREX_LOT_SIZE),
    }


@app.post("/run-backtest")
async def run_backtest(request: Request):
    try:
        payload = await parse_backtest_payload(request)
        market = payload.get("market") or "india"
        selected_symbol = str(payload.get("custom_symbol") or payload.get("symbol") or "").strip()
        start_date = str(payload.get("start_date") or "")
        end_date = str(payload.get("end_date") or "")
        interval = str(payload.get("interval") or "1m")
        initial_capital = float(payload.get("initial_capital") or 100000)
        lot_size = float(payload.get("lot_size") or DEFAULT_FOREX_LOT_SIZE) if market == "forex" else None

        if not selected_symbol:
            raise ValueError("Please select a symbol")
        if not start_date or not end_date:
            raise ValueError("Please provide start and end dates")

        df = download_market_data(selected_symbol, start_date, end_date, interval)
        df = compute_emas(df)
        result = run_strategy(df, initial_capital, market=market, lot_size=lot_size)
        return JSONResponse(
            {
                "success": True,
                "summary": result["summary"],
                "trade_log": result["trade_log"],
                "symbol": selected_symbol,
                "symbol_label": get_symbol_label(selected_symbol, market),
                "market": market,
                "market_label": market.capitalize(),
                "source": "Yahoo Finance via backend service",
            }
        )
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=200)
