#!/usr/bin/env python3
"""
Afternoon Post (KST 16:30) — Hong Kong / Asia Market Session Review
AI: Google Gemini 2.5 Flash Lite (무료, 1,500 req/day)
썸네일: Nano Banana 2 (gemini-3.1-flash-image-preview) 우선

[cron-job.org 설정]
KST 16:30 = UTC 07:30
  Cron   : 30 7 * * 1,2,3,4,5
  Body   : {"ref":"main","inputs":{"post_type":"afternoon"}}
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from utils.gemini_client import generate_post, parse_json_response, compress_market_data
from utils.market_data import get_asia_market_data, get_hsi_sector_performance, get_hsi_top_movers
from utils.post_image import get_post_image
from utils.blogger import publish_to_blogger
from utils.formatting import build_html_post

KST = timezone(timedelta(hours=9))
HKT = timezone(timedelta(hours=8))


def build_prompt(market_data: dict) -> str:
    today_kst = datetime.now(KST).strftime("%B %d, %Y")
    today_hkt = datetime.now(HKT).strftime("%B %d, %Y")
    data_summary = compress_market_data(market_data)

    return f"""You are a professional Asian stock market analyst writing an SEO-optimized English blog post for retail investors.

Today (KST): {today_kst}  |  Today (HKT): {today_hkt}
Market Data:
{data_summary}

Write a comprehensive blog post reviewing today's Hong Kong and Asian stock market session.

TITLE: Hook-driven headline with specific numbers. Examples:
  "Hang Seng Surges 2.3%: China Stimulus Fuels Asia Rally — What Investors Must Know"
  "HSI Drops 1.8%: Tech Selloff Drags Hong Kong Markets Lower"
  "Asia Markets Mixed: Hang Seng Flat as US Tariff Fears Weigh on Sentiment"

META DESCRIPTION: 150-160 characters, SEO-optimized.

CONTENT (HTML, 800-1000 words):
<h2>Hong Kong Market Overview</h2> — Hang Seng Index, Hang Seng Tech Index, key sectors
<h2>Mainland China Markets</h2> — Shanghai Composite, Shenzhen, CSI 300, A-share themes
<h2>Broader Asia-Pacific Session</h2> — Nikkei 225, KOSPI, ASX 200, key movers
<h2>Top Movers & Sector Highlights</h2> — Major gainers/losers with reasons (Alibaba, Tencent, Meituan, etc.)
<h2>Macro Context & China Policy Watch</h2> — PBOC, RMB/USD, HK-US policy, commodity prices
<h2>Key Takeaways for Investors</h2> — 3-5 actionable bullet points
<h2>What to Watch: US & Asia Session Tonight</h2> — Pre-market signals, upcoming data

SEO keywords: "Hang Seng today", "Hong Kong stock market", "Asia markets", "HSI", "China stocks".
Use hedging language. Do NOT speculate as fact.

THUMBNAIL PROMPT: 1 sentence, max 20 words, real-world photorealistic scene (NO charts/text).
  Good: "Hong Kong financial district skyline at dusk with glowing skyscrapers over Victoria Harbour"
  Bad: "HSI chart with upward trend"

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-slug",
  "tags": ["Hang Seng", "Hong Kong Stock Market", "Asia Markets", "HSI", "China Stocks", "Investing"],
  "content_html": "<h2>Hong Kong Market Overview</h2><p>...</p>...",
  "thumbnail_prompt": "..."
}}"""


def run():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}] Afternoon post 시작 (홍콩/아시아 마감 리뷰)")

    print("아시아 시장 데이터 수집 중 (yfinance)...")
    market_data = {
        "indices": get_asia_market_data(),
    }

    # HSI 섹터/모버 수집 (함수 존재 시)
    try:
        market_data["sectors"] = get_hsi_sector_performance()
        print(f"  HSI 섹터 데이터: {len(market_data['sectors'])}개")
    except Exception as e:
        print(f"  HSI 섹터 수집 실패 (무시): {e}")

    try:
        market_data["movers"] = get_hsi_top_movers()
        gainers = len(market_data["movers"].get("gainers", []))
        losers  = len(market_data["movers"].get("losers",  []))
        print(f"  HSI 모버: 상승 {gainers}개 / 하락 {losers}개")
    except Exception as e:
        print(f"  HSI 모버 수집 실패 (무시): {e}")

    print("Gemini 2.5 Flash Lite로 포스트 생성 중...")
    post = parse_json_response(generate_post(build_prompt(market_data)))
    print(f"  제목: {post['title']}")

    print("썸네일 생성 중 (Nano Banana 2 → Pillow 폴백)...")
    thumb = get_post_image(
        post_data   = post,
        article     = {},
        filename    = f"afternoon_{datetime.now(KST).strftime('%Y%m%d')}",
        post_type   = "afternoon",
        market_data = market_data,
    )

    html = build_html_post(
        content_html   = post["content_html"],
        thumbnail_path = thumb,
        market_data    = market_data,
        post_type      = "afternoon",
    )

    print("Blogger에 게시 중...")
    result = publish_to_blogger(
        title   = post["title"],
        content = html,
        labels  = post["tags"],
        blog_id = os.environ["BLOGGER_BLOG_ID"],
    )

    print(f"✅ 게시 완료: {result.get('url')}")
    return result


if __name__ == "__main__":
    run()
