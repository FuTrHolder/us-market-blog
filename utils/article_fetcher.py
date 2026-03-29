#!/usr/bin/env python3
"""
utils/article_fetcher.py
기사 URL에서 본문 텍스트와 메타데이터를 추출합니다.

전략:
  1. newspaper3k  — 가장 강력한 기사 파서 (자동 본문/제목 추출)
  2. trafilatura  — newspaper3k 실패 시 폴백 (다양한 사이트 지원)
  3. requests + BeautifulSoup — 최후 수단 (기본 HTML 파싱)

지원 사이트 예시:
  - Yahoo Finance, CNBC, Bloomberg (무료 기사)
  - Reuters, MarketWatch, Seeking Alpha (무료 부분)
  - 대부분의 공개 뉴스 사이트
"""

import re
import time
from urllib.parse import urlparse

import requests

# 사용 가능한 라이브러리에 따라 graceful import
try:
    import newspaper
    from newspaper import Article as NewspaperArticle
    HAS_NEWSPAPER = True
except ImportError:
    HAS_NEWSPAPER = False

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_ARTICLE_CHARS = 8000  # Gemini 토큰 절약을 위한 최대 길이


def fetch_article(url: str) -> dict:
    """
    URL에서 기사를 가져옵니다.

    Returns:
        {
            "url":         원본 URL,
            "title":       기사 제목,
            "text":        본문 텍스트 (최대 MAX_ARTICLE_CHARS자),
            "authors":     저자 목록,
            "publish_date": 게시일 문자열,
            "source":      도메인명,
            "meta_description": 메타 설명,
            "top_image":   대표 이미지 URL,
            "method":      사용된 파서 ("newspaper"|"trafilatura"|"bs4"|"error"),
        }
    """
    domain = urlparse(url).netloc.replace("www.", "")

    result = {
        "url":              url,
        "title":            "",
        "text":             "",
        "authors":          [],
        "publish_date":     "",
        "source":           domain,
        "meta_description": "",
        "top_image":        "",
        "method":           "error",
    }

    # ── Method 1: newspaper3k ─────────────────────────────
    if HAS_NEWSPAPER:
        try:
            art = NewspaperArticle(url, language="en", fetch_images=False)
            art.download()
            time.sleep(0.5)
            art.parse()

            text = art.text or ""
            if len(text) > 200:
                result.update({
                    "title":        art.title or "",
                    "text":         _clean_text(text)[:MAX_ARTICLE_CHARS],
                    "authors":      art.authors or [],
                    "publish_date": str(art.publish_date or ""),
                    "top_image":    art.top_image or "",
                    "method":       "newspaper",
                })
                result["meta_description"] = _extract_meta_description(art)
                return result
        except Exception as e:
            print(f"[newspaper3k] 실패: {e}")

    # ── Method 2: trafilatura ─────────────────────────────
    if HAS_TRAFILATURA:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                )
                if text and len(text) > 200:
                    title = _extract_title_from_html(downloaded)
                    result.update({
                        "title":  title,
                        "text":   _clean_text(text)[:MAX_ARTICLE_CHARS],
                        "method": "trafilatura",
                    })
                    return result
        except Exception as e:
            print(f"[trafilatura] 실패: {e}")

    # ── Method 3: requests + BeautifulSoup ────────────────
    if HAS_BS4:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # 제목
            title = ""
            if soup.title:
                title = soup.title.string or ""
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", title)

            # 메타 설명
            meta_desc = ""
            og_desc = soup.find("meta", property="og:description")
            if og_desc:
                meta_desc = og_desc.get("content", "")

            # 본문 추출 (article 태그 우선)
            article_tag = soup.find("article")
            if article_tag:
                text = article_tag.get_text(separator="\n", strip=True)
            else:
                # p 태그에서 긴 문단 수집
                paragraphs = [
                    p.get_text(strip=True)
                    for p in soup.find_all("p")
                    if len(p.get_text(strip=True)) > 50
                ]
                text = "\n".join(paragraphs)

            if text and len(text) > 200:
                result.update({
                    "title":            title.strip(),
                    "text":             _clean_text(text)[:MAX_ARTICLE_CHARS],
                    "meta_description": meta_desc,
                    "method":           "bs4",
                })
                return result
        except Exception as e:
            print(f"[BeautifulSoup] 실패: {e}")

    # ── 모든 방법 실패 ────────────────────────────────────
    print(f"[article_fetcher] 모든 파서 실패: {url}")
    return result


def _clean_text(text: str) -> str:
    """기사 텍스트 정리"""
    # 과도한 공백/줄바꿈 제거
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    # 광고성 문구 제거 패턴
    ad_patterns = [
        r'Sign up for.*?newsletter',
        r'Subscribe to.*?free',
        r'Advertisement\n',
        r'ADVERTISEMENT\n',
        r'Read more:.*?\n',
    ]
    for pat in ad_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)
    return text.strip()


def _extract_title_from_html(html: str) -> str:
    """HTML에서 제목 추출"""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        og_title = soup.find("meta", property="og:title")
        if og_title:
            return og_title.get("content", "")
        if soup.title:
            return soup.title.string or ""
    # regex 폴백
    m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_meta_description(art) -> str:
    """newspaper Article에서 메타 설명 추출"""
    try:
        # newspaper는 meta_description 속성이 없을 수 있음
        return getattr(art, "meta_description", "") or ""
    except Exception:
        return ""
