"""
Kerwin 宏观对冲及AI精选组合 — 周报生成脚本
用法: python3 kerwin_yahoo_weekly.py
依赖: pip install pandas matplotlib yfinance
输出: kerwin_yahoo_weekly/ 目录下的 PNG / CSV 文件
"""

import json
import time
import urllib.request
import urllib.parse
import datetime as dt
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager

TICKERS = [
    "SNDK","9747.HK","7709.HK","POWL","LITE","MRVL","NBIS","ARM","COHR","INTC",
    "000660.KS","SMSN.IL","039030.KQ","005930.KS","MU","DELL","CRWV","NOK",
    "EQIX","AMD","CCJ","ETN","CRCL","TSM","BEP","6268.T","AVGO","FCX","WPM",
    "6594.T","FNV","AEM","COPX","AMZN","6324.T","GLD","GOOG","NVDA","ARKG",
    "AAPL","META","ARKK","SNPS","LEU","ORCL","BTC-USD","COIN","MSFT","TSLA",
    "ETH-USD","HOOD","CRM"
]

AS_OF = "2026-04-24"
START = "2025-12-20"
END   = "2026-04-25"

OUT_DIR = Path("kerwin_yahoo_weekly")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def to_unix(date_str: str) -> int:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def fetch_yahoo_chart(ticker: str) -> pd.DataFrame:
    p1 = to_unix(START)
    p2 = to_unix(END)
    symbol = urllib.parse.quote(ticker, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={p1}&period2={p2}&interval=1d"
        f"&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8")

    data = json.loads(raw)
    result = data.get("chart", {}).get("result")
    error  = data.get("chart", {}).get("error")
    if error:
        raise RuntimeError(f"Yahoo error: {error}")
    if not result:
        raise RuntimeError("No chart result")

    result = result[0]
    timestamps = result.get("timestamp", [])
    closes     = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])

    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
        rows.append({"date": date, "close": float(close)})

    if not rows:
        raise RuntimeError("No close data")

    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def last_on_or_before(df: pd.DataFrame, date_str: str) -> pd.Series:
    x = df[df["date"] <= date_str]
    if x.empty:
        raise RuntimeError(f"No price on or before {date_str}")
    return x.iloc[-1]


def pct(now: float, base: float) -> float:
    return (now / base - 1.0) * 100.0


def build_records() -> tuple[list[dict], list[dict]]:
    records, errors = [], []
    for ticker in TICKERS:
        try:
            df = fetch_yahoo_chart(ticker)

            current_row   = last_on_or_before(df, AS_OF)
            current_date  = current_row["date"]
            current_close = current_row["close"]

            df_to_cur = df[df["date"] <= current_date].reset_index(drop=True)
            if len(df_to_cur) < 6:
                raise RuntimeError("Not enough data for 5D")

            base_5d  = df_to_cur.iloc[-6]
            base_mtd = last_on_or_before(df, "2026-03-31")
            base_ytd = last_on_or_before(df, "2025-12-31")

            records.append({
                "标的":           ticker,
                "current_date":   current_date,
                "current_close":  current_close,
                "5D_base_date":   base_5d["date"],
                "5D_base_close":  base_5d["close"],
                "MTD_base_date":  base_mtd["date"],
                "MTD_base_close": base_mtd["close"],
                "YTD_base_date":  base_ytd["date"],
                "YTD_base_close": base_ytd["close"],
                "5D":  pct(current_close, base_5d["close"]),
                "MTD": pct(current_close, base_mtd["close"]),
                "YTD": pct(current_close, base_ytd["close"]),
            })
            print(f"OK  {ticker}")
        except Exception as e:
            errors.append({"标的": ticker, "error": str(e)})
            print(f"ERR {ticker}: {e}")
        time.sleep(0.25)
    return records, errors


def fmt_pct(x) -> str:
    return "" if pd.isna(x) else f"{x:+.2f}%"


def setup_cjk_font():
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    font_path = next((p for p in candidates if Path(p).exists()), None)
    if font_path:
        font_manager.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams["axes.unicode_minus"] = False


def draw_table(ax, df: pd.DataFrame):
    ax.axis("off")
    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="center",
        colLoc="center",
        bbox=[0, 0, 1, 1],
        colWidths=[0.14, 0.23, 0.21, 0.21, 0.21],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.6)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D9E1EA")
        cell.set_linewidth(0.6)
        if row == 0:
            cell.set_facecolor("#0B234A")
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
            cell.set_height(0.040)
        else:
            cell.set_facecolor("white")
            cell.set_height(0.036)
            if col in (2, 3, 4):
                txt = cell.get_text().get_text()
                if txt.startswith("+"):
                    cell.get_text().set_color("#0B7A2A")
                elif txt.startswith("-"):
                    cell.get_text().set_color("#D71920")
                else:
                    cell.get_text().set_color("#111111")
            else:
                cell.get_text().set_color("#111111")
                if col == 1:
                    cell.get_text().set_fontweight("bold")


def render_png(display_df: pd.DataFrame, png_path: Path):
    setup_cjk_font()
    left  = display_df.iloc[:26]
    right = display_df.iloc[26:52]

    fig = plt.figure(figsize=(10, 17), dpi=220)
    fig.patch.set_facecolor("white")

    fig.text(0.5, 0.965,
             "Kerwin宏观对冲及AI精选组合周报",
             ha="center", va="top", fontsize=25, fontweight="bold", color="#0B234A")
    fig.text(0.5, 0.925,
             f"数据更新至 {AS_OF.replace('-', '.')}｜口径：Yahoo Finance｜指标：5D / MTD / YTD",
             ha="center", va="top", fontsize=12.5, color="#333333")
    fig.text(0.5, 0.900,
             "单位：涨跌幅｜排序：按5D降序",
             ha="center", va="top", fontsize=11, color="#333333")

    ax1 = fig.add_axes([0.045, 0.045, 0.44, 0.82])
    ax2 = fig.add_axes([0.515, 0.045, 0.44, 0.82])
    draw_table(ax1, left)
    draw_table(ax2, right)

    plt.savefig(png_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    records, errors = build_records()

    if not records:
        raise SystemExit("No data fetched. Check network access to Yahoo Finance.")

    result = (
        pd.DataFrame(records)
        .sort_values("5D", ascending=False)
        .reset_index(drop=True)
    )
    result.insert(0, "排名", range(1, len(result) + 1))

    display_df = result[["排名", "标的", "5D", "MTD", "YTD"]].copy()
    for col in ("5D", "MTD", "YTD"):
        display_df[col] = display_df[col].map(fmt_pct)

    tag = AS_OF
    csv_path    = OUT_DIR / f"kerwin_yahoo_weekly_{tag}.csv"
    detail_path = OUT_DIR / f"kerwin_yahoo_weekly_{tag}_detail.csv"
    err_path    = OUT_DIR / f"kerwin_yahoo_weekly_{tag}_errors.csv"
    png_path    = OUT_DIR / f"kerwin_yahoo_weekly_{tag}.png"

    display_df.to_csv(csv_path,    index=False, encoding="utf-8-sig")
    result.to_csv(detail_path,     index=False, encoding="utf-8-sig")
    pd.DataFrame(errors).to_csv(err_path, index=False, encoding="utf-8-sig")

    render_png(display_df, png_path)

    print()
    print("DONE")
    print(f"PNG:    {png_path}")
    print(f"CSV:    {csv_path}")
    print(f"DETAIL: {detail_path}")
    print(f"ERRORS: {err_path}")
    if errors:
        print(f"\n{len(errors)} ticker(s) failed — see {err_path}")


if __name__ == "__main__":
    main()
