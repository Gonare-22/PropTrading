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

    if start_dt == end_dt:
        end_dt = end_dt + pd.Timedelta(days=1)

    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


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

    for attempt_interval in ([interval] if interval not in {"1m", "5m", "15m", "1h"} else [interval, "1d"]):
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


def run_strategy(df, initial_capital: float):
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

    for idx, row in df.iterrows():
        close = float(row["Close"])
        prev20, prev50, prev100 = float(row["prev_ema20"]), float(row["prev_ema50"]), float(row["prev_ema100"])
        curr20, curr50, curr100 = float(row["ema20"]), float(row["ema50"]), float(row["ema100"])

        if position == 0:
            if prev50 <= prev100 and curr50 > curr100:
                position = 1
                entry_time = idx
                entry_price = close
                entry_direction = "long"
                entry_units = equity / entry_price
            elif prev50 >= prev100 and curr50 < curr100:
                position = -1
                entry_time = idx
                entry_price = close
                entry_direction = "short"
                entry_units = equity / entry_price
        elif position == 1:
            if prev20 >= prev50 and curr20 < curr50:
                exit_price = close
                pnl = entry_units * (exit_price - entry_price)
                equity += pnl
                trades.append({"entry_time": entry_time, "exit_time": idx, "pnl": pnl, "direction": entry_direction})
                position = 0
        elif position == -1:
            if prev20 <= prev50 and curr20 > curr50:
                exit_price = close
                pnl = entry_units * (entry_price - exit_price)
                equity += pnl
                trades.append({"entry_time": entry_time, "exit_time": idx, "pnl": pnl, "direction": entry_direction})
                position = 0

    if position != 0 and entry_time is not None:
        last_close = float(df["Close"].iloc[-1])
        pnl = entry_units * (last_close - entry_price) if entry_direction == "long" else entry_units * (entry_price - last_close)
        equity += pnl
        trades.append({"entry_time": entry_time, "exit_time": df.index[-1], "pnl": pnl, "direction": entry_direction})

    trade_df = pd.DataFrame(trades)
    if not trade_df.empty:
        trade_df["is_win"] = trade_df["pnl"] > 0
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
    return summary


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

        if not selected_symbol:
            raise ValueError("Please select a symbol")
        if not start_date or not end_date:
            raise ValueError("Please provide start and end dates")

        df = download_market_data(selected_symbol, start_date, end_date, interval)
        df = compute_emas(df)
        summary = run_strategy(df, initial_capital)
        return JSONResponse(
            {
                "success": True,
                "summary": summary,
                "symbol": selected_symbol,
                "symbol_label": get_symbol_label(selected_symbol, market),
                "market": market,
                "market_label": market.capitalize(),
                "source": "Yahoo Finance via backend service",
            }
        )
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=200)
