#!/usr/bin/env python3
"""
Evening Post (22:00 KST) — Pre-Market Preview
AI 모델: Google Gemini 2.0 Flash (완전 무료)
  - API Key: https://aistudio.google.com/app/apikey
  - 무료 한도: 1,500 req/day, 신용카드 불필요
"""

import json
import os
import sys

# ✅ 수정 2: 레포 루트를 sys.path에 추가 — utils 패키지를 어디서 실행해도 찾을 수 있음
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta

from utils.gemini_client import generate_post, parse_json_response
from utils.market_data import (
    get_premarket_data,
    get_market_futures,
    get_earnings_calendar,
    get_economic_calendar,
)
from utils.image_gen import generate_thumbnail
from utils.blogger import publish_to_blogger
from utils.formatting import build_html_post, build_earnings_table, build_economic_table

KST = timezone(timedelta(hours=9))


def build_prompt(market_data: dict) -> str:
    today = datetime.now(KST).strftime("%B %d, %Y")
    return f"""You are a professional US stock market analyst writing a pre-market preview blog post for retail investors.

Today (KST): {today}
Market Data:
{json.dumps(market_data, indent=2)}

Write a comprehensive, SEO-optimized English blog post about what to expect in tonight's US market session.

TITLE RULES — hook-driven, high-CTR. Examples:
  "NVIDIA Earnings Tonight — Will the AI Darling Beat Wall Street Expectations?"
  "CPI Report Today: Here's Exactly What It Means for Your Portfolio"
  "5 Market-Moving Events You Can't Ignore Before Tonight's Opening Bell"
  If no specific catalyst: use futures direction + key theme as hook.

META DESCRIPTION: 150-160 chars, SEO-optimized.

CONTENT STRUCTURE (HTML, 800-1000 words):
<h2>Pre-Market Snapshot</h2>
  - Futures direction and % change (ES, NQ, YM)
  - Asian market closes, European direction
  - VIX, Dollar, Oil, Gold

<h2>Key Catalysts & Market Themes</h2>
  - Top 3-5 macro/sector/geopolitical themes driving sentiment
  - Fed speakers, Treasury auctions, major news

<h2>Earnings in the Spotlight</h2>
  [Include ONLY if earnings_calendar is non-empty]
  - Per company: consensus estimate, key metrics to watch, historical beat/miss record
  - Mention that a detailed earnings comparison table appears below

<h2>Economic Data Releases</h2>
  [Include ONLY if economic_calendar is non-empty]
  - Which indicators are released, previous vs forecast
  - Impact analysis: what a beat or miss means for markets
  - Mention that a data comparison table appears below

<h2>Technical Levels to Watch</h2>
  - S&P 500 and NASDAQ key support and resistance levels

<h2>Investor Positioning</h2>
  - Risk-on vs risk-off signals
  - 3-4 actionable bullet points

SEO keywords: "pre-market preview", "stock market today", "earnings tonight", "economic calendar", "S&P 500 outlook".
Use hedging language. Do NOT speculate as fact.

THUMBNAIL PROMPT: 1 sentence, max 30 words — professional financial thumbnail description.

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-url-slug",
  "tags": ["Pre-Market Preview", "Earnings", "Economic Data", "S&P 500", "Stock Market"],
  "content_html": "...",
  "thumbnail_prompt": "...",
  "has_earnings": true,
  "has_economic_data": true
}}"""


def run():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] Evening post 시작")

    # 1. 모든 데이터 수집 (무료 API)
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

    # 2. Gemini로 포스트 생성 (무료)
    print("Gemini 2.0 Flash로 포스트 생성 중...")
    post = parse_json_response(generate_post(build_prompt(market_data)))
    print(f"  제목: {post['title']}")

    # 3. 비교 테이블 생성
    earnings_tbl = build_earnings_table(earnings) if post.get("has_earnings") and earnings else ""
    economic_tbl = build_economic_table(economic) if post.get("has_economic_data") and economic else ""

    # 4. 썸네일 생성 (matplotlib — 무료)
    print("썸네일 생성 중...")
    thumb = generate_thumbnail(
        prompt=post["thumbnail_prompt"],
        filename=f"evening_{datetime.now(KST).strftime('%Y%m%d')}",
        market_data={"indices": futures},
    )

    # 5. 최종 HTML 조립
    html = build_html_post(
        content_html=post["content_html"],
        thumbnail_path=thumb,
        market_data=market_data,
        post_type="evening",
        earnings_table_html=earnings_tbl,
        economic_table_html=economic_tbl,
    )

    # 6. Blogger 게시 (무료)
    print("Blogger에 게시 중...")
    result = publish_to_blogger(
        title=post["title"],
        content=html,
        labels=post["tags"],
        blog_id=os.environ["BLOGGER_BLOG_ID"],
    )

    print(f"게시 완료: {result.get('url')}")
    return result


if __name__ == "__main__":
    run()
