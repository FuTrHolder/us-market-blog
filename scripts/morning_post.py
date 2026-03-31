#!/usr/bin/env python3
"""
Morning Post (08:00 KST) — US Market Close Review
AI: Google Gemini 2.5 Flash Lite (무료, 1,500 req/day)
"""

import json
import os
import sys

# 레포 루트를 path에 추가 — utils 패키지 인식
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from utils.gemini_client import generate_post, parse_json_response, compress_market_data
from utils.market_data import get_market_close_data, get_sector_performance, get_top_movers
from utils.image_gen import generate_thumbnail
from utils.blogger import publish_to_blogger
from utils.formatting import build_html_post

KST = timezone(timedelta(hours=9))


def build_prompt(market_data: dict) -> str:
    today = datetime.now(KST).strftime("%B %d, %Y")
    data_summary = compress_market_data(market_data)

    return f"""You are a professional US stock market analyst writing an SEO-optimized English blog post for retail investors.

Today (KST): {today}
Market Data:
{data_summary}

Write a comprehensive blog post reviewing yesterday's US stock market close.

TITLE: Hook-driven headline with specific numbers. Examples:
  "Wall Street Tumbles as Fed Fears Return — What Every Investor Must Know"
  "S&P 500 Surges 1.2%: Is the Bull Run Just Getting Started?"

META DESCRIPTION: 150-160 characters, SEO-optimized.

CONTENT (HTML, 800-1000 words):
<h2>Market Overview</h2> — S&P 500, NASDAQ, Dow Jones, Russell 2000 performance
<h2>Sector Performance</h2> — Best/worst sectors, rotation signals
<h2>Top Movers</h2> — Key gainers and losers with reasons
<h2>Bond Market & Macro Context</h2> — Treasury, VIX, Dollar, Oil, Gold
<h2>Key Takeaways for Investors</h2> — 3-5 actionable bullet points
<h2>What to Watch Tomorrow</h2> — Upcoming earnings, data, Fed events

SEO keywords: "stock market today", "S&P 500", "Wall Street", "market analysis".
Use hedging language. Do NOT speculate as fact.

THUMBNAIL PROMPT: 1 sentence, max 20 words, real-world photorealistic scene (NO charts/text).
  Good: "Traders on a busy New York Stock Exchange floor watching screens intently"
  Bad: "Financial chart with upward green trend lines"

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-slug",
  "tags": ["US Stock Market", "S&P 500", "Market Analysis", "Wall Street", "Investing"],
  "content_html": "<h2>Market Overview</h2><p>...</p>...",
  "thumbnail_prompt": "..."
}}"""


def run():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] Morning post 시작")

    print("시장 데이터 수집 중 (yfinance)...")
    market_data = {
        "indices": get_market_close_data(),
        "sectors": get_sector_performance(),
        "movers":  get_top_movers(),
    }

    print("Gemini 2.5 Flash Lite로 포스트 생성 중...")
    post = parse_json_response(generate_post(build_prompt(market_data)))
    print(f"  제목: {post['title']}")

    print("썸네일 생성 중 (Gemini Imagen → Pillow 폴백)...")
    thumb = generate_thumbnail(
        prompt=post["thumbnail_prompt"],
        filename=f"morning_{datetime.now(KST).strftime('%Y%m%d')}",
        market_data=market_data,
        post_data=post,          # ← 블로그 글 내용 전달 (맥락 기반 프롬프트)
        post_type="morning",
    )

    html = build_html_post(
        content_html=post["content_html"],
        thumbnail_path=thumb,
        market_data=market_data,
        post_type="morning",
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
