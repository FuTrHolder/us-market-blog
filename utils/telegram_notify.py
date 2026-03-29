#!/usr/bin/env python3
"""
utils/telegram_notify.py
텔레그램 메시지 전송 유틸리티.

GitHub Actions 스텝에서 진행상황을 텔레그램으로 전송.
HTML parse_mode 지원, 긴 메시지 자동 분할.
"""

import time
import requests


TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MSG_LEN  = 4096  # Telegram 메시지 최대 길이


class TelegramNotifier:
    """텔레그램 봇 메시지 전송 클래스"""

    def __init__(self, token: str):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        self.token = token

    def send(self, chat_id: str, text: str, parse_mode: str = "HTML") -> dict | None:
        """
        텔레그램 메시지 전송.
        4096자 초과 시 자동 분할.
        """
        if not text:
            return None

        # 긴 메시지 분할
        if len(text) > MAX_MSG_LEN:
            chunks = _split_message(text, MAX_MSG_LEN)
            last   = None
            for chunk in chunks:
                last = self._send_single(chat_id, chunk, parse_mode)
                time.sleep(0.3)  # Rate limit 방지
            return last

        return self._send_single(chat_id, text, parse_mode)

    def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> dict | None:
        """로컬 이미지 파일을 텔레그램으로 전송"""
        try:
            url = TELEGRAM_API.format(token=self.token, method="sendPhoto")
            with open(photo_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=30,
                )
            return resp.json()
        except Exception as e:
            print(f"[TelegramNotifier] 이미지 전송 실패: {e}")
            return None

    def _send_single(self, chat_id: str, text: str, parse_mode: str) -> dict | None:
        """단일 메시지 전송 (재시도 포함)"""
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")

        for attempt in range(3):
            try:
                resp = requests.post(
                    url,
                    json={
                        "chat_id":                  chat_id,
                        "text":                     text,
                        "parse_mode":               parse_mode,
                        "disable_web_page_preview": False,
                    },
                    timeout=15,
                )
                data = resp.json()

                if data.get("ok"):
                    return data

                # HTML 파싱 오류 → plain text로 재시도
                if "can't parse entities" in str(data.get("description", "")):
                    resp2 = requests.post(
                        url,
                        json={"chat_id": chat_id, "text": _strip_html(text)},
                        timeout=15,
                    )
                    return resp2.json()

                # Rate limit
                if resp.status_code == 429:
                    retry_after = data.get("parameters", {}).get("retry_after", 5)
                    print(f"[Telegram] Rate limit — {retry_after}초 대기")
                    time.sleep(retry_after + 1)
                    continue

                print(f"[TelegramNotifier] 오류: {data}")
                return data

            except requests.RequestException as e:
                print(f"[TelegramNotifier] 네트워크 오류 (시도 {attempt+1}): {e}")
                time.sleep(3)

        return None


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int) -> list[str]:
    """메시지를 max_len 이하로 분할 (줄바꿈 기준)"""
    lines  = text.split("\n")
    chunks = []
    buf    = ""
    for line in lines:
        if len(buf) + len(line) + 1 > max_len:
            if buf:
                chunks.append(buf.rstrip())
            buf = line + "\n"
        else:
            buf += line + "\n"
    if buf.strip():
        chunks.append(buf.rstrip())
    return chunks or [text[:max_len]]


def _strip_html(text: str) -> str:
    """HTML 태그 제거 (plain text 폴백용)"""
    import re
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return clean
