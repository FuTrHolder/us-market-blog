#!/usr/bin/env python3
"""
Market Data Utility — 100% FREE
yfinance + FRED 공개 CSV
"""

import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import yfinance as yf

KST = timezone(timedelta(hours=9))


# ─────────────────────────────────────────────
# INDEX & PRICE DATA
# ─────────────────────────────────────────────

def get_market_close_data() -> dict:
    symbols = {
        "S&P 500":      "^GSPC",
        "NASDAQ":       "^IXIC",
        "Dow Jones":    "^DJI",
        "Russell 2000": "^RUT",
        "VIX":          "^VIX",
        "10Y Treasury": "^TNX",
        "DXY (Dollar)": "DX-Y.NYB",
        "WTI Oil":      "CL=F",
        "Gold":         "GC=F",
    }
    return _fetch_yf_batch(symbols, period="5d")


def get_sector_performance() -> dict:
    sectors = {
        "Technology":             "XLK",
        "Healthcare":             "XLV",
        "Financials":             "XLF",
        "Energy":                 "XLE",
        "Consumer Discretionary": "XLY",
        "Consumer Staples":       "XLP",
        "Industrials":            "XLI",
        "Materials":              "XLB",
        "Utilities":              "XLU",
        "Real Estate":            "XLRE",
        "Communication Services": "XLC",
    }
    raw = _fetch_yf_batch(sectors, period="5d")
    return {k: {"etf": sectors[k], "change_pct": v.get("change_pct")}
            for k, v in raw.items() if "error" not in v}


def get_top_movers(n: int = 5) -> dict:
    # ✅ 수정 1: BRK.B → BRK-B (Yahoo Finance는 점(.) 대신 하이픈(-) 사용)
    watchlist = list(get_major_sp500_symbols())
    result = {"gainers": [], "losers": []}

    try:
        raw = yf.download(
            watchlist,
            period="5d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        changes = []
        for sym in watchlist:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close_col = (sym, "Close") if (sym, "Close") in raw.columns else None
                    if close_col is None:
                        continue
                    hist = raw[close_col].dropna()
                else:
                    hist = raw["Close"].dropna() if len(watchlist) == 1 else None
                    if hist is None:
                        continue

                if len(hist) < 2:
                    continue
                pct = (hist.iloc[-1] - hist.iloc[-2]) / hist.iloc[-2] * 100
                changes.append({
                    "symbol": sym,
                    "change_pct": round(float(pct), 2),
                    "price": round(float(hist.iloc[-1]), 2),
                })
            except Exception:
                continue

        changes.sort(key=lambda x: x["change_pct"], reverse=True)
        result["gainers"] = changes[:n]
        result["losers"]  = changes[-n:][::-1]

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────
# FUTURES & PRE-MARKET
# ─────────────────────────────────────────────

def get_market_futures() -> dict:
    futures = {
        "S&P 500 Futures":   "ES=F",
        "NASDAQ Futures":    "NQ=F",
        "Dow Futures":       "YM=F",
        "Russell 2000 Fut.": "RTY=F",
    }
    return _fetch_yf_batch(futures, period="5d")


def get_premarket_data() -> dict:
    markets = {
        "Nikkei 225 (Japan)":  "^N225",
        "Hang Seng (HK)":      "^HSI",
        "KOSPI (Korea)":       "^KS11",
        "Shanghai Composite":  "000001.SS",
        "DAX (Germany)":       "^GDAXI",
        "FTSE 100 (UK)":       "^FTSE",
        "CAC 40 (France)":     "^FCHI",
    }
    return _fetch_yf_batch(markets, period="5d")


# ─────────────────────────────────────────────
# EARNINGS CALENDAR
# ─────────────────────────────────────────────

def get_earnings_calendar() -> list:
    today = datetime.now(KST).date()
    major = list(get_major_sp500_symbols())
    due_today = []

    for sym in major:
        try:
            t   = yf.Ticker(sym)
            cal = t.calendar
            if not cal:
                continue

            earn_dates = cal.get("Earnings Date", [])
            if not earn_dates:
                continue
            if not isinstance(earn_dates, (list, tuple)):
                earn_dates = [earn_dates]

            for ed in earn_dates:
                try:
                    ed_date = pd.Timestamp(ed).date()
                except Exception:
                    continue

                if ed_date == today:
                    eps_est = cal.get("EPS Estimate")
                    rev_est = cal.get("Revenue Estimate")
                    history = get_eps_history(sym)

                    due_today.append({
                        "symbol":           sym,
                        "name":             _get_company_name(sym),
                        "date":             str(ed_date),
                        "time":             "TBD",
                        "eps_estimate":     float(eps_est) if eps_est is not None else None,
                        "eps_actual":       None,
                        "revenue_estimate": float(rev_est) if rev_est is not None else None,
                        "revenue_actual":   None,
                        "eps_history":      history,
                        "fiscal_quarter":   "",
                    })
                    break
        except Exception:
            continue

    return due_today


def get_eps_history(symbol: str) -> list:
    try:
        t    = yf.Ticker(symbol)
        esur = t.earnings_history
        history = []
        if esur is not None and not esur.empty:
            for i, (idx, row) in enumerate(esur.iterrows()):
                if i >= 4:
                    break
                est  = row.get("EPS Estimate")
                act  = row.get("Reported EPS")
                surp = row.get("Surprise(%)")
                history.append({
                    "quarter":     str(idx)[:7],
                    "eps_actual":  float(act)  if pd.notna(act)  else None,
                    "eps_estimate":float(est)  if pd.notna(est)  else None,
                    "surprise_pct":round(float(surp), 1) if pd.notna(surp) else None,
                })
        return history
    except Exception:
        return []


# ─────────────────────────────────────────────
# ECONOMIC CALENDAR  (FRED 공개 CSV — 무료, 키 불필요)
# ─────────────────────────────────────────────

FRED_INDICATORS = {
    "CPI (YoY)":           "CPIAUCSL",
    "Core CPI (YoY)":      "CPILFESL",
    "PPI (YoY)":           "PPIACO",
    "Core PCE":            "PCEPILFE",
    "Nonfarm Payrolls":    "PAYEMS",
    "Unemployment Rate":   "UNRATE",
    "Initial Jobless Claims": "ICSA",
    "Retail Sales (MoM)":  "RSAFS",
    "Industrial Production": "INDPRO",
    "Housing Starts":      "HOUST",
    "GDP Growth Rate":     "A191RL1Q225SBEA",
    "Federal Funds Rate":  "FEDFUNDS",
}

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def get_economic_calendar() -> list:
    today  = datetime.now(KST).date()
    cutoff = today - timedelta(days=2)
    events = []

    for indicator, series_id in FRED_INDICATORS.items():
        try:
            url = f"{FRED_BASE}{series_id}"
            df  = pd.read_csv(url, parse_dates=["DATE"], index_col="DATE").dropna()

            if df.empty:
                continue

            latest_date = df.index[-1].date()
            if latest_date < cutoff:
                continue

            latest_val = float(df.iloc[-1, 0])
            prev_val   = float(df.iloc[-2, 0]) if len(df) > 1 else None

            change = round(latest_val - prev_val, 4) if prev_val is not None else None
            high_impact = ["CPI", "PCE", "Nonfarm", "Unemployment", "GDP", "Federal Funds"]
            impact = "High" if any(h in indicator for h in high_impact) else "Medium"

            events.append({
                "event":    indicator,
                "date":     str(latest_date),
                "actual":   latest_val,
                "previous": prev_val,
                "change":   change,
                "impact":   impact,
            })
        except Exception:
            continue

        time.sleep(0.15)

    return events


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _fetch_yf_batch(symbol_map: dict, period: str = "5d") -> dict:
    tickers = list(symbol_map.values())
    result  = {}

    try:
        raw = yf.download(
            tickers,
            period=period,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        for name, sym in symbol_map.items():
            try:
                if len(tickers) == 1:
                    hist = raw["Close"].dropna()
                else:
                    if (sym, "Close") not in raw.columns:
                        result[name] = {"error": "no data"}
                        continue
                    hist = raw[(sym, "Close")].dropna()

                if len(hist) < 2:
                    result[name] = {"error": "insufficient history"}
                    continue

                prev = float(hist.iloc[-2])
                curr = float(hist.iloc[-1])
                chg  = curr - prev
                chgp = chg / prev * 100

                try:
                    if len(tickers) == 1:
                        hi  = float(raw["High"].dropna().iloc[-1])
                        lo  = float(raw["Low"].dropna().iloc[-1])
                        vol = int(raw["Volume"].dropna().iloc[-1])
                    else:
                        hi  = float(raw[(sym, "High")].dropna().iloc[-1])
                        lo  = float(raw[(sym, "Low")].dropna().iloc[-1])
                        vol = int(raw[(sym, "Volume")].dropna().iloc[-1])
                except Exception:
                    hi = lo = vol = None

                result[name] = {
                    "close":      round(curr, 2),
                    "change":     round(chg,  2),
                    "change_pct": round(chgp, 2),
                    "high":       round(hi, 2) if hi else None,
                    "low":        round(lo, 2) if lo else None,
                    "volume":     vol,
                }
            except Exception as e:
                result[name] = {"error": str(e)}

    except Exception as e:
        for name in symbol_map:
            result[name] = {"error": str(e)}

    return result


def _get_company_name(symbol: str) -> str:
    _NAMES = {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet",
        "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla", "JPM": "JPMorgan Chase",
        "V": "Visa", "LLY": "Eli Lilly", "UNH": "UnitedHealth", "XOM": "ExxonMobil",
        "MA": "Mastercard", "JNJ": "J&J", "PG": "P&G", "HD": "Home Depot",
        "MRK": "Merck", "AVGO": "Broadcom", "COST": "Costco", "ABBV": "AbbVie",
        "CVX": "Chevron", "AMD": "AMD", "CRM": "Salesforce", "NFLX": "Netflix",
        "KO": "Coca-Cola", "PEP": "PepsiCo", "BAC": "Bank of America", "WMT": "Walmart",
        "DIS": "Disney", "INTC": "Intel", "CSCO": "Cisco", "GS": "Goldman Sachs",
        "MS": "Morgan Stanley", "BA": "Boeing", "CAT": "Caterpillar", "IBM": "IBM",
        "GE": "GE Aerospace",
        # ✅ 수정 1: BRK.B → BRK-B
        "BRK-B": "Berkshire Hathaway",
    }
    return _NAMES.get(symbol, symbol)


def get_major_sp500_symbols() -> set:
    return {
        # ✅ 수정 1: BRK.B → BRK-B (Yahoo Finance 표준 티커)
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
        "LLY", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "MRK",
        "AVGO", "COST", "ABBV", "CVX", "AMD", "CRM", "NFLX", "KO", "PEP",
        "BAC", "WMT", "DIS", "INTC", "CSCO", "GS", "MS", "BA", "CAT",
        "IBM", "GE", "MMM", "VZ", "T",
    }


# ─────────────────────────────────────────────────────────
# HONG KONG / ASIA MARKET DATA (afternoon_post 전용)
# ─────────────────────────────────────────────────────────

def get_asia_market_data() -> dict:
    """아시아 주요 지수 + HSI 관련 ETF/선물 데이터"""
    symbols = {
        # 홍콩
        "Hang Seng Index":      "^HSI",
        "Hang Seng Tech":       "^HSTECH",
        # 중국 본토
        "Shanghai Composite":   "000001.SS",
        "Shenzhen Component":   "399001.SZ",
        "CSI 300":              "000300.SS",
        # 기타 아시아
        "Nikkei 225 (Japan)":   "^N225",
        "KOSPI (Korea)":        "^KS11",
        "ASX 200 (Australia)":  "^AXJO",
        "Taiwan Weighted":      "^TWII",
        # 홍콩 달러 / 위안
        "USD/HKD":              "USDHKD=X",
        "USD/CNY":              "USDCNY=X",
        # 관련 원자재
        "Gold":                 "GC=F",
        "Brent Oil":            "BZ=F",
    }
    return _fetch_yf_batch(symbols, period="5d")


def get_hsi_sector_performance() -> dict:
    """홍콩 섹터 ETF 및 주요 테마 성과"""
    sectors = {
        "HK Financials":        "3033.HK",   # CSOP HS Finance
        "HK Tech (iShares)":    "2804.HK",   # iShares HS Tech
        "China Consumer":       "3032.HK",
        "China Healthcare":     "2828.HK",   # Hang Seng H-Share
        "HK Real Estate":       "823.HK",    # Link REIT (proxy)
    }
    raw = _fetch_yf_batch(sectors, period="5d")
    return {k: {"ticker": sectors[k], "change_pct": v.get("change_pct")}
            for k, v in raw.items() if "error" not in v}


# HSI 주요 구성종목 (시총 기준 상위)
HSI_MAJOR_TICKERS = {
    "0700.HK",  # Tencent
    "9988.HK",  # Alibaba
    "3690.HK",  # Meituan
    "1299.HK",  # AIA
    "0005.HK",  # HSBC
    "0388.HK",  # HK Exchanges
    "2318.HK",  # Ping An Insurance
    "0939.HK",  # CCB
    "1398.HK",  # ICBC
    "0941.HK",  # China Mobile
    "2020.HK",  # ANTA Sports
    "0027.HK",  # Galaxy Entertainment
    "9999.HK",  # NetEase
    "0857.HK",  # PetroChina
    "2382.HK",  # Sunny Optical
    "1810.HK",  # Xiaomi
    "0016.HK",  # Sun Hung Kai
    "0002.HK",  # CLP Holdings
    "0003.HK",  # HK & China Gas
    "1177.HK",  # Sino Biopharm
}

_HSI_COMPANY_NAMES = {
    "0700.HK": "Tencent",
    "9988.HK": "Alibaba",
    "3690.HK": "Meituan",
    "1299.HK": "AIA Group",
    "0005.HK": "HSBC",
    "0388.HK": "HKEX",
    "2318.HK": "Ping An",
    "0939.HK": "CCB",
    "1398.HK": "ICBC",
    "0941.HK": "China Mobile",
    "2020.HK": "ANTA Sports",
    "9999.HK": "NetEase",
    "0857.HK": "PetroChina",
    "1810.HK": "Xiaomi",
    "0016.HK": "Sun Hung Kai",
}


def get_hsi_top_movers(n: int = 5) -> dict:
    """HSI 주요 구성종목 상승/하락 Top N"""
    watchlist = list(HSI_MAJOR_TICKERS)
    result    = {"gainers": [], "losers": []}

    try:
        raw = yf.download(
            watchlist,
            period      = "5d",
            group_by    = "ticker",
            auto_adjust = True,
            progress    = False,
            threads     = True,
        )

        changes = []
        for sym in watchlist:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close_col = (sym, "Close") if (sym, "Close") in raw.columns else None
                    if close_col is None:
                        continue
                    hist = raw[close_col].dropna()
                else:
                    hist = raw["Close"].dropna() if len(watchlist) == 1 else None
                    if hist is None:
                        continue

                if len(hist) < 2:
                    continue
                pct = (hist.iloc[-1] - hist.iloc[-2]) / hist.iloc[-2] * 100
                changes.append({
                    "symbol":     sym,
                    "name":       _HSI_COMPANY_NAMES.get(sym, sym),
                    "change_pct": round(float(pct), 2),
                    "price":      round(float(hist.iloc[-1]), 2),
                })
            except Exception:
                continue

        changes.sort(key=lambda x: x["change_pct"], reverse=True)
        result["gainers"] = changes[:n]
        result["losers"]  = changes[-n:][::-1]

    except Exception as e:
        result["error"] = str(e)

    return result
