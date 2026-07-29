import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SYMBOLS = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNX100"]


def main():
    combined_lines = []
    for symbol in SYMBOLS:
        cmd = [
            sys.executable,
            str(BASE_DIR / "nifty_ema_backtest.py"),
            "--ticker",
            symbol,
            "--start",
            "2026-07-20",
            "--end",
            "2026-07-25",
            "--interval",
            "1m",
            "--initial-capital",
            "100000",
            "--output-dir",
            str(BASE_DIR),
        ]
        print(f"Running {symbol}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            raise RuntimeError(f"Backtest failed for {symbol}")

        summary_path = BASE_DIR / f"{symbol.replace('/', '_')}_ema_summary.txt"
        if summary_path.exists():
            combined_lines.append(f"===== {symbol} =====")
            combined_lines.extend(summary_path.read_text(encoding="utf-8").strip().splitlines())
            combined_lines.append("")

    combined_path = BASE_DIR / "multi_index_ema_summary.txt"
    combined_path.write_text("\n".join(combined_lines), encoding="utf-8")
    print(f"Wrote combined summary to {combined_path}")


if __name__ == "__main__":
    main()
