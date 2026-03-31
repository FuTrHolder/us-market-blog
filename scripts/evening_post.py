#!/usr/bin/env python3
"""
Evening Post (22:00 KST) — Pre-Market Preview
AI: Google Gemini 2.5 Flash Lite (무료, 1,500 req/day)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from utils.gemini_client import generate_post, parse_json_response, compress_market_data
from utils.market_data import (
    get_premarket_data, get_market_futures,
    get_earnings_calendar, get_economic_calendar,
)
from utils.post_image import get_post_image
from utils.blogger import publish_to_blogger
from utils.formatting import build_html_post, build_earnings_table, build_economic_table

KST = timezone(timedelta(hours=9))


def build_prompt(market_data: dict) -> str:
    today = datetime.now(KST).strftime("%B %d, %Y")
    data_summary = compress_market_data(market_data)

    has_earnings = bool(market_data.get("earnings_calendar"))
    has_econ     = bool(market_data.get("economic_calendar"))

    return f"""You are a professional US stock market analyst writing a pre-market preview blog post.

Today (KST): {today}
Market Data:
{data_summary}

Write an SEO-optimized English blog post about what to expect in tonight's US market session.

TITLE: Hook-driven, high-CTR. Examples:
  "NVIDIA Earnings Tonight — Will the AI Darling Beat Wall Street Expectations?"
  "CPI Report Today: Here's Exactly What It Means for Your Portfolio"
  "5 Market-Moving Events You Can't Ignore Before Tonight's Opening Bell"

META DESCRIPTION: 150-160 chars, SEO-optimized.

CONTENT (HTML, 800-1000 words):
<h2>Pre-Market Snapshot</h2> — Futures, Asia/Europe closes, VIX, Dollar, Oil, Gold
<h2>Key Catalysts & Market Themes</h2> — Top 3-5 themes, Fed speakers, major news
{"<h2>Earnings in the Spotlight</h2> — Per company: estimates, key metrics, history" if has_earnings else ""}
{"<h2>Economic Data Releases</h2> — Indicators, previous vs forecast, market impact" if has_econ else ""}
<h2>Technical Levels to Watch</h2> — S&P 500 and NASDAQ support/resistance
<h2>Investor Positioning</h2> — Risk-on/off signals, 3-4 actionable bullet points

SEO: "pre-market preview", "stock market today", "earnings tonight", "S&P 500 outlook".
Use hedging language. Do NOT speculate as fact.

THUMBNAIL PROMPT: 1 sentence, max 20 words, real-world photorealistic scene (NO charts/text).
  Good: "Busy trading floor at dawn with monitors and traders preparing for market open"
  Bad: "Upward arrow with stock market data"

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-slug",
  "tags": ["Pre-Market Preview", "Earnings", "Economic Data", "S&P 500", "Stock Market"],
  "content_html": "...",
  "thumbnail_prompt": "...",
  "has_earnings": {"true" if has_earnings else "false"},
  "has_economic_data": {"true" if has_econ else "false"}
}}"""


def run():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] Evening post 시작")

    print("선물/프리마켓 데이터 수집 중 (yfinance)...")
    futures   = get_market_futures()
    premarket = get_premarket_data()

    print("실적 캘린더 수집 중 (yfinance)...")
    earnings  = get_earnings_calendar()
    print(f"  오늘 실적 발표: {len(earnings)}건")

    print("경제 지표 캘린더 수집 중 (FRED)...")
    economic  = get_economic_calendar()
    print(f"  경제 지표: {len(economic)}건")

    market_data = {
        "futures":           futures,
        "premarket":         premarket,
        "earnings_calendar": earnings,
        "economic_calendar": economic,
    }

    print("Gemini 2.5 Flash Lite로 포스트 생성 중...")
    post = parse_json_response(generate_post(build_prompt(market_data)))
    print(f"  제목: {post['title']}")

    earnings_tbl = build_earnings_table(earnings) if post.get("has_earnings") and earnings else ""
    economic_tbl = build_economic_table(economic) if post.get("has_economic_data") and economic else ""

    print("썸네일 생성 중 (Nano Banana 2 → Pillow 폴백)...")
    thumb = get_post_image(
        post_data   = post,
        article     = {},
        filename    = f"evening_{datetime.now(KST).strftime('%Y%m%d')}",
        post_type   = "evening",
        market_data = {"indices": futures},
    )

    html = build_html_post(
        content_html=post["content_html"],
        thumbnail_path=thumb,
        market_data=market_data,
        post_type="evening",
        earnings_table_html=earnings_tbl,
        economic_table_html=economic_tbl,
    )

    print("Blogger에 게시 중...")
    result = publish_to_blogger(
        title=post["title"],
        content=html,
        labels=post["tags"],
        blog_id=os.environ["BLOGGER_BLOG_ID"],
    )

    print(f"✅ 게시 완료: {result.get('url')}")
    return result


if __name__ == "__main__":
    run()
