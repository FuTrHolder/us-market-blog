#!/usr/bin/env python3
"""
Morning Post (08:00 KST) — US Market Close Review
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
from utils.market_data import get_market_close_data, get_sector_performance, get_top_movers
from utils.image_gen import generate_thumbnail
from utils.blogger import publish_to_blogger
from utils.formatting import build_html_post

KST = timezone(timedelta(hours=9))


def build_prompt(market_data: dict) -> str:
    today = datetime.now(KST).strftime("%B %d, %Y")
    return f"""You are a professional US stock market analyst writing an SEO-optimized English blog post for retail investors.

Today (KST): {today}
Market Data (real-time from yfinance):
{json.dumps(market_data, indent=2)}

Write a comprehensive blog post reviewing yesterday's US stock market close.

TITLE RULES:
- Hook-driven, high click-through headline
- Include specific numbers or market moves from the data
- Examples: "Wall Street Tumbles as Fed Fears Return — What Every Investor Must Know"
           "S&P 500 Surges 1.2%: Is the Bull Run Just Getting Started?"

META DESCRIPTION: 150-160 characters, SEO-optimized.

CONTENT STRUCTURE (HTML, 800-1000 words):
<h2>Market Overview</h2>
  - S&P 500, NASDAQ, Dow Jones, Russell 2000 — specific numbers, key levels
  - Overall market tone (risk-on / risk-off)

<h2>Sector Performance</h2>
  - Best and worst performing sectors with pct changes
  - Notable rotation signals

<h2>Top Movers</h2>
  - Notable gainers and losers with brief reasons

<h2>Bond Market & Macro Context</h2>
  - 10Y Treasury yield, VIX, Dollar Index, Oil, Gold

<h2>Key Takeaways for Investors</h2>
  - 3-5 concise actionable bullet points

<h2>What to Watch Tomorrow</h2>
  - Upcoming earnings, economic releases, Fed events

SEO: Use keywords naturally: "stock market today", "S&P 500", "Wall Street", "market analysis".
Use hedging language. Do NOT speculate as fact.

THUMBNAIL PROMPT: 1 sentence, max 30 words — describe a professional financial thumbnail
(mood, colors, visual elements, market direction).

OUTPUT — ONLY valid JSON, no extra text:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-url-slug",
  "tags": ["US Stock Market", "S&P 500", "Market Analysis", "Wall Street", "Investing"],
  "content_html": "<h2>Market Overview</h2><p>...</p>...",
  "thumbnail_prompt": "..."
}}"""


def run():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] Morning post 시작")

    # 1. 시장 데이터 수집 (yfinance — 무료)
    print("시장 데이터 수집 중 (yfinance)...")
    market_data = {
        "indices": get_market_close_data(),
        "sectors": get_sector_performance(),
        "movers":  get_top_movers(),
    }

    # 2. Gemini로 포스트 생성 (무료)
    print("Gemini 2.0 Flash로 포스트 생성 중...")
    post = parse_json_response(generate_post(build_prompt(market_data)))
    print(f"  제목: {post['title']}")

    # 3. 썸네일 생성 (matplotlib — 무료)
    print("썸네일 생성 중...")
    thumb = generate_thumbnail(
        prompt=post["thumbnail_prompt"],
        filename=f"morning_{datetime.now(KST).strftime('%Y%m%d')}",
        market_data=market_data,
    )

    # 4. 최종 HTML 조립
    html = build_html_post(
        content_html=post["content_html"],
        thumbnail_path=thumb,
        market_data=market_data,
        post_type="morning",
    )

    # 5. Blogger 게시 (무료)
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
