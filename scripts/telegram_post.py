#!/usr/bin/env python3
"""
scripts/telegram_post.py
텔레그램 봇으로 전달받은 기사 URL을 처리하는 메인 스크립트.

[모드 1] --mode fact_check
  - 기사 본문 크롤링
  - Gemini로 팩트체크 (사실 검증 + 신뢰도 점수)
  - 웹 검색으로 관련 최신 정보 확인
  - 결과를 JSON으로 저장 + 텔레그램 전송

[모드 2] --mode publish
  - fact_check 결과 로드
  - Gemini로 블로그 포스트 생성 (기존 로직과 동일)
  - 썸네일 생성
  - Blogger에 게시
  - 텔레그램에 완료 메시지 전송
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.gemini_client   import generate_post, parse_json_response
from utils.article_fetcher import fetch_article
from utils.image_gen       import generate_thumbnail
from utils.blogger         import publish_to_blogger
from utils.formatting      import build_html_post
from utils.telegram_notify import TelegramNotifier

KST          = timezone(timedelta(hours=9))
RESULT_FILE  = Path("fact_check_result.json")


# ─────────────────────────────────────────────────────────
# Argument Parsing
# ─────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",    required=True, choices=["fact_check", "publish"])
    p.add_argument("--url",     required=True)
    p.add_argument("--chat",    required=True)
    p.add_argument("--comment", default="")
    return p.parse_args()


# ─────────────────────────────────────────────────────────
# Mode 1: Fact Check
# ─────────────────────────────────────────────────────────

def run_fact_check(url: str, chat_id: str, comment: str, bot: TelegramNotifier):
    """
    기사를 읽고 팩트 체크를 수행합니다.
    결과를 fact_check_result.json에 저장하고 텔레그램으로 전송.
    """

    # ── Step 1: 기사 크롤링 ──────────────────────────────
    bot.send(chat_id,
        "📖 <b>[1/4] 기사 읽는 중...</b>\n"
        f"🔗 {url[:60]}{'...' if len(url) > 60 else ''}"
    )

    article = fetch_article(url)

    if not article.get("text"):
        bot.send(chat_id,
            "❌ 기사 본문을 가져오지 못했습니다.\n\n"
            "가능한 원인:\n"
            "• 페이월(유료 구독) 기사\n"
            "• JavaScript 렌더링 필요 사이트\n"
            "• 접근 차단된 URL\n\n"
            "다른 기사 링크를 시도해보세요."
        )
        sys.exit(1)

    bot.send(chat_id,
        f"✅ 기사 로드 완료\n"
        f"📰 제목: <b>{article.get('title', 'N/A')[:80]}</b>\n"
        f"📝 본문: {len(article.get('text',''))}자\n\n"
        "🔍 <b>[2/4] AI 팩트체크 진행 중...</b>"
    )

    # ── Step 2: Gemini 팩트체크 ───────────────────────────
    fact_result = run_gemini_fact_check(article, comment)

    # ── Step 3: 결과 전송 ─────────────────────────────────
    score        = fact_result.get("credibility_score", 0)
    verdict      = fact_result.get("verdict", "UNKNOWN")
    issues       = fact_result.get("issues", [])
    related_info = fact_result.get("related_information", "")
    proceed      = fact_result.get("proceed_to_publish", False)

    score_emoji = (
        "🟢" if score >= 80 else
        "🟡" if score >= 60 else
        "🔴"
    )

    verdict_map = {
        "VERIFIED":    "✅ 사실 확인됨",
        "MOSTLY_TRUE": "🟡 대체로 사실",
        "MIXED":       "⚠️ 혼재된 정보",
        "UNVERIFIED":  "❓ 검증 불가",
        "FALSE":       "❌ 사실과 다름",
    }
    verdict_str = verdict_map.get(verdict, f"❓ {verdict}")

    issues_str = ""
    if issues:
        issues_str = "\n\n⚠️ <b>지적 사항:</b>\n" + "\n".join(f"• {i}" for i in issues[:3])

    bot.send(chat_id,
        f"📊 <b>[팩트체크 결과]</b>\n\n"
        f"{score_emoji} 신뢰도: <b>{score}/100</b>\n"
        f"판정: <b>{verdict_str}</b>\n"
        f"{issues_str}\n\n"
        f"📌 <b>관련 최신 정보:</b>\n{related_info[:400]}"
    )

    if not proceed:
        bot.send(chat_id,
            "🛑 <b>블로그 게시를 중단합니다.</b>\n\n"
            "신뢰도가 낮거나 사실과 다른 내용이 포함되어 있습니다.\n"
            "다른 출처의 기사를 시도해보세요."
        )
        # 결과 저장 후 비정상 종료
        RESULT_FILE.write_text(json.dumps({**fact_result, "article": article}, ensure_ascii=False, indent=2))
        sys.exit(1)

    bot.send(chat_id,
        "✅ <b>팩트체크 통과!</b>\n\n"
        "블로그 포스팅을 진행합니다...\n"
        "🖼️ <b>[3/4] 썸네일 생성 및 포스트 작성 중...</b>"
    )

    # ── Step 4: 결과 저장 ─────────────────────────────────
    RESULT_FILE.write_text(
        json.dumps({**fact_result, "article": article}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[팩트체크] 완료 — verdict={verdict}, score={score}, proceed={proceed}")


def run_gemini_fact_check(article: dict, comment: str) -> dict:
    """Gemini로 기사 팩트체크 수행"""
    today = datetime.now(KST).strftime("%B %d, %Y")
    title = article.get("title", "")
    text  = article.get("text", "")[:3000]  # 토큰 절약: 앞 3000자

    prompt = f"""You are a professional fact-checker for financial and market news.

Today: {today}
Article Title: {title}
Article Content (first 3000 chars):
{text}

{"User comment: " + comment if comment else ""}

TASK: Analyze this article and:
1. Verify key factual claims (numbers, statistics, company names, dates)
2. Check for misleading framing or context issues
3. Search your knowledge for related recent developments
4. Determine if this is appropriate for a financial blog

OUTPUT — ONLY valid JSON:
{{
  "verdict": "VERIFIED|MOSTLY_TRUE|MIXED|UNVERIFIED|FALSE",
  "credibility_score": <0-100>,
  "key_claims": [
    {{"claim": "...", "status": "VERIFIED|FALSE|UNVERIFIABLE", "note": "..."}}
  ],
  "issues": ["issue1", "issue2"],
  "related_information": "2-3 sentences about the latest related market context you know",
  "blog_angle": "Suggested angle/hook for the blog post",
  "proceed_to_publish": <true if score>=60 and verdict is not FALSE>,
  "summary_for_blog": "3-4 sentence summary of verified facts for blog writing"
}}"""

    raw = generate_post(prompt)
    return parse_json_response(raw)


# ─────────────────────────────────────────────────────────
# Mode 2: Publish
# ─────────────────────────────────────────────────────────

def run_publish(url: str, chat_id: str, bot: TelegramNotifier):
    """
    팩트체크 결과를 바탕으로 블로그 포스트를 생성하고 게시.
    """

    # ── 결과 로드 ─────────────────────────────────────────
    if not RESULT_FILE.exists():
        bot.send(chat_id, "❌ 팩트체크 결과 파일을 찾을 수 없습니다.")
        sys.exit(1)

    data    = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    article = data.get("article", {})

    # ── 포스트 생성 ───────────────────────────────────────
    post = generate_blog_post(data, article, url)

    # ── 썸네일 생성 ───────────────────────────────────────
    thumb = generate_thumbnail(
        prompt=post.get("thumbnail_prompt", "professional financial news analysis"),
        filename=f"telegram_{datetime.now(KST).strftime('%Y%m%d_%H%M')}",
        market_data=None,
    )

    # ── HTML 빌드 ─────────────────────────────────────────
    source_credit = (
        f'<p style="font-size:13px;color:#888;">'
        f'📌 원문 출처: <a href="{url}" target="_blank" rel="nofollow">{article.get("source","원문 보기")}</a>'
        f'</p>\n'
    )
    full_html = build_html_post(
        content_html=source_credit + post["content_html"],
        thumbnail_path=thumb,
        market_data={},
        post_type="telegram",
    )

    # ── Blogger 게시 ──────────────────────────────────────
    result = publish_to_blogger(
        title=post["title"],
        content=full_html,
        labels=post["tags"],
        blog_id=os.environ["BLOGGER_BLOG_ID"],
    )

    post_url = result.get("url", "")

    # ── 완료 알림 ─────────────────────────────────────────
    fact_score   = data.get("credibility_score", "N/A")
    verdict_map  = {
        "VERIFIED":    "✅ 사실 확인됨",
        "MOSTLY_TRUE": "🟡 대체로 사실",
        "MIXED":       "⚠️ 혼재된 정보",
    }
    verdict_str  = verdict_map.get(data.get("verdict", ""), data.get("verdict", ""))

    bot.send(chat_id,
        f"🎉 <b>[4/4] 블로그 게시 완료!</b>\n\n"
        f"📰 <b>{post['title'][:80]}</b>\n\n"
        f"📊 팩트체크: {verdict_str} ({fact_score}/100)\n"
        f"🏷️ 태그: {', '.join(post['tags'][:3])}\n\n"
        f"🔗 <a href=\"{post_url}\">블로그에서 보기</a>"
    )

    print(f"[게시 완료] {result.get('url')}")


def generate_blog_post(fact_data: dict, article: dict, source_url: str) -> dict:
    """팩트체크 결과 기반 블로그 포스트 생성"""
    today = datetime.now(KST).strftime("%B %d, %Y")

    prompt = f"""You are a professional US stock market analyst writing an SEO-optimized blog post.

Today (KST): {today}
Original Article Title: {article.get('title', '')}
Source URL: {source_url}
Fact-Check Verdict: {fact_data.get('verdict')} (Score: {fact_data.get('credibility_score')}/100)
Verified Summary: {fact_data.get('summary_for_blog', '')}
Blog Angle: {fact_data.get('blog_angle', '')}
Related Information: {fact_data.get('related_information', '')}

Write a comprehensive SEO-optimized English blog post based on the VERIFIED facts above.

TITLE: Hook-driven, high-CTR headline with specific numbers/impact.

META DESCRIPTION: 150-160 chars, SEO-optimized.

CONTENT (HTML, 700-900 words):
<h2>What Happened</h2> — The verified key facts, concisely
<h2>Market Impact Analysis</h2> — What this means for investors
<h2>Context & Background</h2> — Historical context, related trends  
<h2>Key Takeaways for Investors</h2> — 3-4 actionable bullet points
<h2>What to Watch Next</h2> — Follow-up signals, upcoming events

SEO keywords: "stock market", "investor analysis", relevant tickers/sectors.
Use hedging language. Do NOT speculate as fact.
Mark any AI-generated analysis clearly with "[Analysis]" prefix.

THUMBNAIL PROMPT: 1 sentence, max 20 words — professional financial thumbnail.

OUTPUT — ONLY valid JSON:
{{
  "title": "...",
  "meta_description": "...",
  "slug": "kebab-case-slug",
  "tags": ["Market Analysis", "Investing", "Wall Street", "Stock Market", "...relevant tag"],
  "content_html": "<h2>What Happened</h2><p>...</p>...",
  "thumbnail_prompt": "..."
}}"""

    raw  = generate_post(prompt)
    return parse_json_response(raw)


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

def main():
    args = parse_args()
    bot  = TelegramNotifier(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    )

    if args.mode == "fact_check":
        run_fact_check(args.url, args.chat, args.comment, bot)
    elif args.mode == "publish":
        run_publish(args.url, args.chat, bot)


if __name__ == "__main__":
    main()
