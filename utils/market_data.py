#!/usr/bin/env python3
"""
Market Data Utility — 100% FREE
Primary source: yfinance (completely free, no API key)
Earnings calendar: yfinance .calendar + earnings_dates
Economic calendar: investpy-style scraping via pandas_datareader (FRED = free)
Top movers: calculated directly from yfinance on S&P 500 ETFs

No FMP, no Alpha Vantage, no paid tier required.
"""

import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional

import yfinance as yf

KST = timezone(timedelta(hours=9))


# ─────────────────────────────────────────────
# INDEX & PRICE DATA  (yfinance — free)
# ─────────────────────────────────────────────

def get_market_close_data() -> dict:
    """Previous day closing data for major indices — yfinance only."""
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
    """Sector ETF performance — yfinance only."""
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
    # Return only change_pct for sectors
    return {k: {"etf": sectors[k], "change_pct": v.get("change_pct")}
            for k, v in raw.items() if "error" not in v}


def get_top_movers(n: int = 5) -> dict:
    """
    Compute top gainers & losers from a curated list of large-cap stocks.
    Uses yfinance — no paid API.
    """
    watchlist = list(get_major_sp500_symbols())
    result = {"gainers": [], "losers": []}

    try:
        # Download in one batch (much faster than individual calls)
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
                changes.append({"symbol": sym, "change_pct": round(float(pct), 2),
                                 "price": round(float(hist.iloc[-1]), 2)})
            except Exception:
                continue

        changes.sort(key=lambda x: x["change_pct"], reverse=True)
        result["gainers"] = changes[:n]
        result["losers"]  = changes[-n:][::-1]

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────
# FUTURES & PRE-MARKET  (yfinance — free)
# ─────────────────────────────────────────────

def get_market_futures() -> dict:
    """Futures via yfinance continuous contract symbols."""
    futures = {
        "S&P 500 Futures":    "ES=F",
        "NASDAQ Futures":     "NQ=F",
        "Dow Futures":        "YM=F",
        "Russell 2000 Fut.":  "RTY=F",
    }
    return _fetch_yf_batch(futures, period="5d")


def get_premarket_data() -> dict:
    """Asian + European market closes via yfinance."""
    markets = {
        "Nikkei 225 (Japan)":     "^N225",
        "Hang Seng (HK)":         "^HSI",
        "KOSPI (Korea)":          "^KS11",
        "Shanghai Composite":     "000001.SS",
        "DAX (Germany)":          "^GDAXI",
        "FTSE 100 (UK)":          "^FTSE",
        "CAC 40 (France)":        "^FCHI",
    }
    return _fetch_yf_batch(markets, period="5d")


# ─────────────────────────────────────────────
# EARNINGS CALENDAR  (yfinance — free)
# ─────────────────────────────────────────────

def get_earnings_calendar() -> list:
    """
    Get earnings for the next 7 days from yfinance for major S&P 500 names.
    yfinance's .calendar returns the next expected earnings date per ticker.
    We poll the major-symbol watchlist and collect those due soon.
    """
    today = datetime.now(KST).date()
    major = list(get_major_sp500_symbols())
    due_today = []

    for sym in major:
        try:
            t   = yf.Ticker(sym)
            cal = t.calendar  # dict with 'Earnings Date', 'EPS Estimate', etc.
            if not cal:
                continue

            # calendar['Earnings Date'] is a list of Timestamps
            earn_dates = cal.get("Earnings Date", [])
            if not earn_dates:
                continue

            # Normalise — may be a single value or list
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
                        "symbol":          sym,
                        "name":            _get_company_name(sym),
                        "date":            str(ed_date),
                        "time":            "TBD",          # yfinance doesn't supply BMO/AMC
                        "eps_estimate":    float(eps_est)  if eps_est  is not None else None,
                        "eps_actual":      None,           # not yet released
                        "revenue_estimate":float(rev_est)  if rev_est  is not None else None,
                        "revenue_actual":  None,
                        "eps_history":     history,
                        "fiscal_quarter":  "",
                    })
                    break  # one entry per symbol

        except Exception:
            continue

    return due_today


def get_eps_history(symbol: str) -> list:
    """
    Historical EPS actual vs estimate — last 4 quarters.
    Uses yfinance quarterly_earnings (free).
    """
    try:
        t    = yf.Ticker(symbol)
        qe   = t.quarterly_earnings  # DataFrame: index=quarter, cols=[Revenue,Earnings]
        esur = t.earnings_history     # DataFrame: EPS Estimate, Reported EPS, Surprise(%)

        history = []

        if esur is not None and not esur.empty:
            for i, (idx, row) in enumerate(esur.iterrows()):
                if i >= 4:
                    break
                est  = row.get("EPS Estimate")
                act  = row.get("Reported EPS")
                surp = row.get("Surprise(%)")
                history.append({
                    "quarter":    str(idx)[:7],
                    "eps_actual":  float(act)  if pd.notna(act)  else None,
                    "eps_estimate":float(est)  if pd.notna(est)  else None,
                    "surprise_pct":round(float(surp), 1) if pd.notna(surp) else None,
                })
        return history

    except Exception:
        return []


# ─────────────────────────────────────────────
# ECONOMIC CALENDAR  (FRED via pandas_datareader — free / no key for most series)
# ─────────────────────────────────────────────

# Key US economic indicators with their FRED series IDs and release schedules
# We check if the most recent release was today (KST)
FRED_INDICATORS = {
    "CPI (YoY)":                    "CPIAUCSL",
    "Core CPI (YoY)":               "CPILFESL",
    "PPI (YoY)":                    "PPIACO",
    "PCE Price Index":              "PCEPI",
    "Core PCE":                     "PCEPILFE",
    "Nonfarm Payrolls":             "PAYEMS",
    "Unemployment Rate":            "UNRATE",
    "Initial Jobless Claims":       "ICSA",
    "Retail Sales (MoM)":           "RSAFS",
    "ISM Manufacturing PMI":        "MANEMP",
    "Industrial Production":        "INDPRO",
    "Housing Starts":               "HOUST",
    "Consumer Confidence":          "CSCICP03USM665S",
    "GDP Growth Rate":              "A191RL1Q225SBEA",
    "Federal Funds Rate":           "FEDFUNDS",
}

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

def get_economic_calendar() -> list:
    """
    Checks FRED for recent releases of major US economic indicators.
    Returns events whose most recent data point was released within 2 days of today (KST).
    No API key required for public FRED CSV endpoint.
    """
    today = datetime.now(KST).date()
    cutoff = today - timedelta(days=2)  # look back 2 days to catch overnight releases
    events = []

    for indicator, series_id in FRED_INDICATORS.items():
        try:
            url = f"{FRED_BASE}{series_id}"
            df  = pd.read_csv(url, parse_dates=["DATE"], index_col="DATE")
            df  = df.dropna()

            if df.empty:
                continue

            latest_date  = df.index[-1].date()
            latest_val   = float(df.iloc[-1, 0])
            prev_val     = float(df.iloc[-2, 0]) if len(df) > 1 else None
            prev2_val    = float(df.iloc[-3, 0]) if len(df) > 2 else None

            # Only include if released recently
            if latest_date < cutoff:
                continue

            change     = round(latest_val - prev_val, 4) if prev_val is not None else None
            change_pct = round((latest_val - prev_val) / abs(prev_val) * 100, 2) \
                         if prev_val and prev_val != 0 else None

            # Simple impact heuristic
            high_impact = ["CPI", "PCE", "Nonfarm", "Unemployment", "GDP", "Federal Funds"]
            impact = "High" if any(h in indicator for h in high_impact) else "Medium"

            events.append({
                "event":      indicator,
                "country":    "US",
                "date":       str(latest_date),
                "actual":     latest_val,
                "estimate":   None,      # FRED doesn't provide forecasts
                "previous":   prev_val,
                "previous2":  prev2_val,  # 2 periods ago for trend context
                "change":     change,
                "change_pct": change_pct,
                "impact":     impact,
            })

        except Exception:
            continue

        time.sleep(0.15)  # Polite rate-limit for FRED CSV endpoint

    return events


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _fetch_yf_batch(symbol_map: dict, period: str = "5d") -> dict:
    """
    Batch-download OHLCV for a dict {display_name: ticker}.
    Returns dict {display_name: {close, change, change_pct, high, low, volume}}.
    Uses multi-ticker download for efficiency.
    """
    tickers = list(symbol_map.values())
    names   = list(symbol_map.keys())
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

                prev  = float(hist.iloc[-2])
                curr  = float(hist.iloc[-1])
                chg   = curr - prev
                chgp  = chg / prev * 100

                # High/Low/Volume (best-effort)
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
                    "high":       round(hi, 2)  if hi  else None,
                    "low":        round(lo, 2)  if lo  else None,
                    "volume":     vol,
                }
            except Exception as e:
                result[name] = {"error": str(e)}

    except Exception as e:
        for name in names:
            result[name] = {"error": str(e)}

    return result


def _get_company_name(symbol: str) -> str:
    """Resolve ticker → company name via yfinance (cached in memory)."""
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
        "GE": "GE Aerospace", "BRK.B": "Berkshire Hathaway",
    }
    return _NAMES.get(symbol, symbol)


def get_major_sp500_symbols() -> set:
    """High-profile S&P 500 names — used for earnings scan and mover calculation."""
    return {
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK.B",
        "LLY", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "MRK",
        "AVGO", "COST", "ABBV", "CVX", "AMD", "CRM", "NFLX", "KO", "PEP",
        "BAC", "WMT", "DIS", "INTC", "CSCO", "GS", "MS", "BA", "CAT",
        "IBM", "GE", "MMM", "VZ", "T",
    }
