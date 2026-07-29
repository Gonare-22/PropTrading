import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

DEFAULT_INITIAL_CAPITAL = 100000.0
DEFAULT_EMA_SHORT = 20
DEFAULT_EMA_MEDIUM = 50
DEFAULT_EMA_LONG = 100


def parse_args():
    parser = argparse.ArgumentParser(description="Backtest an EMA 20/50/100 crossover strategy from CSV or Yahoo Finance")
    parser.add_argument("--csv", help="Path to a CSV file with OHLCV data")
    parser.add_argument("--ticker", default="^NSEI", help="Yahoo Finance ticker if no CSV is provided")
    parser.add_argument("--start", default="2026-07-20", help="Start date for Yahoo Finance download")
    parser.add_argument("--end", default="2026-07-25", help="End date for Yahoo Finance download")
    parser.add_argument("--interval", default="1m", help="Yahoo Finance interval (for example 1m)")
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL, help="Initial capital for the backtest")
    parser.add_argument("--output-dir", default=None, help="Directory where outputs should be written")
    return parser.parse_args()


def find_column(columns, candidates):
    lowered = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def load_csv_data(csv_path):
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError("CSV file is empty")

    datetime_col = None
    for candidate in ["datetime", "date", "time", "timestamp", "date_time"]:
        datetime_col = find_column(df.columns, [candidate])
        if datetime_col is not None:
            break

    if datetime_col is None:
        if "date" in df.columns and "time" in df.columns:
            df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
            datetime_col = "datetime"
        else:
            raise ValueError("CSV must contain a datetime-like column")

    close_col = find_column(df.columns, ["close", "closeprice", "price", "adj close", "adj_close"])
    if close_col is None:
        raise ValueError("CSV must contain a close-price column")

    high_col = find_column(df.columns, ["high", "highprice"])
    low_col = find_column(df.columns, ["low", "lowprice"])
    open_col = find_column(df.columns, ["open", "openprice"])

    df = df[[datetime_col, close_col] + ([high_col] if high_col else []) + ([low_col] if low_col else []) + ([open_col] if open_col else [])].copy()
    df[datetime_col] = pd.to_datetime(df[datetime_col], errors="coerce")
    df = df.dropna(subset=[datetime_col, close_col])
    df = df.sort_values(datetime_col)
    df = df.rename(columns={datetime_col: "Date", close_col: "Close"})

    if high_col is None:
        df["High"] = df["Close"]
    else:
        df = df.rename(columns={high_col: "High"})

    if low_col is None:
        df["Low"] = df["Close"]
    else:
        df = df.rename(columns={low_col: "Low"})

    if open_col is not None:
        df = df.rename(columns={open_col: "Open"})
    else:
        df["Open"] = df["Close"]

    df = df.set_index("Date")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["High"] = pd.to_numeric(df["High"], errors="coerce")
    df["Low"] = pd.to_numeric(df["Low"], errors="coerce")
    df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
    df = df.dropna(subset=["Close"])
    return df


def download_data(ticker, start, end, interval):
    data = yf.download(
        ticker,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,
        progress=False,
        prepost=False,
        threads=False,
    )
    if data.empty:
        raise RuntimeError("No data returned from Yahoo Finance")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_convert("Asia/Kolkata")
    else:
        data.index = data.index.tz_localize("Asia/Kolkata")

    data = data.sort_index()
    data = data.dropna(subset=["Close"])
    if interval.endswith("m"):
        data = data.between_time("09:15", "15:30")
    return data


def compute_emas(data, fast=20, medium=50, slow=100):
    df = data.copy()
    df["ema20"] = df["Close"].ewm(span=fast, adjust=False).mean()
    df["ema50"] = df["Close"].ewm(span=medium, adjust=False).mean()
    df["ema100"] = df["Close"].ewm(span=slow, adjust=False).mean()
    return df


def run_strategy(data, initial_capital):
    df = data.copy()
    df["prev_ema20"] = df["ema20"].shift(1)
    df["prev_ema50"] = df["ema50"].shift(1)
    df["prev_ema100"] = df["ema100"].shift(1)

    trades = []
    position = 0
    entry_time = None
    entry_price = None
    entry_direction = None
    entry_units = 0.0
    equity = float(initial_capital)

    for idx, row in df.iterrows():
        current_close = float(row["Close"])
        prev_ema20 = float(row["prev_ema20"])
        prev_ema50 = float(row["prev_ema50"])
        prev_ema100 = float(row["prev_ema100"])
        curr_ema20 = float(row["ema20"])
        curr_ema50 = float(row["ema50"])
        curr_ema100 = float(row["ema100"])

        if position == 0:
            if prev_ema50 <= prev_ema100 and curr_ema50 > curr_ema100:
                position = 1
                entry_time = idx
                entry_price = current_close
                entry_direction = "long"
                entry_units = equity / entry_price
            elif prev_ema50 >= prev_ema100 and curr_ema50 < curr_ema100:
                position = -1
                entry_time = idx
                entry_price = current_close
                entry_direction = "short"
                entry_units = equity / entry_price
        elif position == 1:
            if prev_ema20 >= prev_ema50 and curr_ema20 < curr_ema50:
                exit_price = current_close
                pnl_cash = entry_units * (exit_price - entry_price)
                equity = equity + pnl_cash
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": idx,
                        "direction": entry_direction,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl_cash,
                        "pnl_pct": (pnl_cash / initial_capital) * 100.0,
                        "equity_after_trade": equity,
                    }
                )
                position = 0
                entry_time = None
                entry_price = None
                entry_direction = None
                entry_units = 0.0
        elif position == -1:
            if prev_ema20 <= prev_ema50 and curr_ema20 > curr_ema50:
                exit_price = current_close
                pnl_cash = entry_units * (entry_price - exit_price)
                equity = equity + pnl_cash
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": idx,
                        "direction": entry_direction,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl_cash,
                        "pnl_pct": (pnl_cash / initial_capital) * 100.0,
                        "equity_after_trade": equity,
                    }
                )
                position = 0
                entry_time = None
                entry_price = None
                entry_direction = None
                entry_units = 0.0

    if position != 0 and entry_time is not None and entry_price is not None:
        last_close = float(df["Close"].iloc[-1])
        if entry_direction == "long":
            pnl_cash = entry_units * (last_close - entry_price)
        else:
            pnl_cash = entry_units * (entry_price - last_close)
        equity = equity + pnl_cash
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": df.index[-1],
                "direction": entry_direction,
                "entry_price": entry_price,
                "exit_price": last_close,
                "pnl": pnl_cash,
                "pnl_pct": (pnl_cash / initial_capital) * 100.0,
                "equity_after_trade": equity,
            }
        )

    trade_df = pd.DataFrame(trades)
    if not trade_df.empty:
        trade_df["entry_time"] = pd.to_datetime(trade_df["entry_time"])
        trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
        trade_df = trade_df.sort_values("entry_time")
        trade_df["is_win"] = trade_df["pnl"] > 0
    else:
        trade_df = pd.DataFrame(columns=["entry_time", "exit_time", "direction", "entry_price", "exit_price", "pnl", "pnl_pct", "equity_after_trade", "is_win"])

    df["up_candle"] = df["Close"].gt(df["Close"].shift(1)).astype(int)
    df["down_candle"] = df["Close"].lt(df["Close"].shift(1)).astype(int)
    df["new_high"] = df["High"].gt(df["High"].shift(1)).astype(int)
    df["new_low"] = df["Low"].lt(df["Low"].shift(1)).astype(int)

    return trade_df, df, equity


def save_outputs(trade_df, df, symbol, start, end, interval, initial_capital, output_dir):
    output_dir = Path(output_dir or Path(__file__).resolve().parent)
    output_dir.mkdir(parents=True, exist_ok=True)

    trade_path = output_dir / f"{symbol.replace('/', '_')}_ema_trades.csv"
    trade_df.to_csv(trade_path, index=False)

    if not trade_df.empty:
        wins = int((trade_df["pnl"] > 0).sum())
        losses = int((trade_df["pnl"] <= 0).sum())
        win_rate = round(wins / len(trade_df) * 100.0, 2) if len(trade_df) else 0.0
        total_pnl = round(float(trade_df["pnl"].sum()), 2)
        avg_pnl = round(float(trade_df["pnl"].mean()), 2) if not trade_df.empty else 0.0
        profit_factor = round(abs(float(trade_df.loc[trade_df["pnl"] > 0, "pnl"].sum())) / abs(float(trade_df.loc[trade_df["pnl"] < 0, "pnl"].sum()))) if (trade_df["pnl"] < 0).any() else 0.0
        ending_equity = round(float(trade_df["equity_after_trade"].iloc[-1]) if not trade_df.empty else initial_capital, 2)
        total_return_pct = round(((ending_equity / initial_capital) - 1) * 100.0, 2)
        equity_curve = trade_df["equity_after_trade"].tolist()
        running_max = pd.Series(equity_curve).cummax()
        drawdown = ((pd.Series(equity_curve) / running_max) - 1).min() * 100.0 if len(equity_curve) else 0.0
    else:
        wins = losses = 0
        win_rate = 0.0
        total_pnl = 0.0
        avg_pnl = 0.0
        profit_factor = 0.0
        ending_equity = initial_capital
        total_return_pct = 0.0
        drawdown = 0.0

    summary = {
        "symbol": symbol,
        "start_date": start,
        "end_date": end,
        "timeframe": interval,
        "initial_capital": initial_capital,
        "ending_equity": ending_equity,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "trades": int(len(trade_df)),
        "wins": wins,
        "losses": losses,
        "accuracy_pct": win_rate,
        "avg_pnl": avg_pnl,
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(float(drawdown), 2),
        "up_candles": int(df["up_candle"].sum()),
        "down_candles": int(df["down_candle"].sum()),
        "new_highs": int(df["new_high"].sum()),
        "new_lows": int(df["new_low"].sum()),
    }

    summary_path = output_dir / f"{symbol.replace('/', '_')}_ema_summary.txt"
    with summary_path.open("w", encoding="utf-8") as fh:
        for key, value in summary.items():
            fh.write(f"{key}: {value}\n")

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df.index, df["Close"], label="Close", color="black", linewidth=1.0)
    ax.plot(df.index, df["ema20"], label="EMA20", color="royalblue", linewidth=1.2)
    ax.plot(df.index, df["ema50"], label="EMA50", color="orange", linewidth=1.2)
    ax.plot(df.index, df["ema100"], label="EMA100", color="green", linewidth=1.2)
    if not trade_df.empty:
        ax.scatter(trade_df["entry_time"], trade_df["entry_price"], color="green", marker="^", s=40, label="Entry", zorder=5)
        ax.scatter(trade_df["exit_time"], trade_df["exit_price"], color="red", marker="v", s=40, label="Exit", zorder=5)
    ax.set_title(f"{symbol} EMA 20/50/100 strategy")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_dir / f"{symbol.replace('/', '_')}_ema_chart.png", dpi=150)
    plt.close(fig)

    print("Saved trade CSV:", trade_path)
    print("Saved summary:", summary_path)
    print("Saved chart:", output_dir / f"{symbol.replace('/', '_')}_ema_chart.png")
    print("\nSummary")
    for key, value in summary.items():
        print(f"{key}: {value}")


def main():
    args = parse_args()
    output_dir = args.output_dir or str(Path(__file__).resolve().parent)

    if args.csv:
        data = load_csv_data(args.csv)
        symbol = Path(args.csv).stem
        start = data.index.min().strftime("%Y-%m-%d") if len(data.index) else ""
        end = data.index.max().strftime("%Y-%m-%d") if len(data.index) else ""
        interval = "csv"
    else:
        data = download_data(args.ticker, args.start, args.end, args.interval)
        symbol = args.ticker
        start = args.start
        end = args.end
        interval = args.interval

    data = compute_emas(data, DEFAULT_EMA_SHORT, DEFAULT_EMA_MEDIUM, DEFAULT_EMA_LONG)
    trades, df, _ = run_strategy(data, args.initial_capital)
    save_outputs(trades, df, symbol, start, end, interval, args.initial_capital, output_dir)


if __name__ == "__main__":
    main()
