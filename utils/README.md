# 📈 US Market Blog — 100% 완전 무료 자동화

매일 2개의 미국 증시 블로그 포스트를 자동 생성·게시합니다. **비용 $0**.

| 시간 (KST) | 내용 | AI 모델 |
|-----------|------|---------|
| 오전 08:00 | 미국 증시 마감 리뷰 | Gemini 2.0 Flash (무료) |
| 저녁 10:00 | 프리마켓 프리뷰 + 실적 + 경제지표 | Gemini 2.0 Flash (무료) |

---

## 💸 완전 무료인 이유

| 구성 요소 | 서비스 | 비용 |
|----------|--------|------|
| AI 글 작성 | **Google Gemini 2.0 Flash** (Google AI Studio) | **$0** — 1,500 req/day 무료 |
| 시장 데이터 | **yfinance** (Yahoo Finance) | **$0** — API 키 불필요 |
| 경제 지표 | **FRED** (미국 연준 공개 데이터) | **$0** — API 키 불필요 |
| 썸네일 이미지 | **matplotlib + Pillow** (Python 라이브러리) | **$0** |
| 블로그 플랫폼 | **Google Blogger** | **$0** |
| 자동화 실행 | **GitHub Actions** (월 2,000분 무료) | **$0** |
| **총합** | | **$0 / 월** |

---

## 🔑 GitHub Secrets 등록 (3개, 모두 무료)

GitHub 레포 → **Settings → Secrets and variables → Actions**

### 1️⃣ GEMINI_API_KEY (Google AI Studio — 무료)

1. [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) 접속
2. Google 계정으로 로그인 (신용카드 불필요)
3. **"Create API Key"** 클릭
4. 생성된 `AIzaSy...` 키 복사
5. GitHub Secret에 `GEMINI_API_KEY` 이름으로 등록

> 무료 한도: **1,500 requests/day, 15 requests/minute**
> 하루 2개 포스트이므로 한도의 0.1%만 사용

### 2️⃣ BLOGGER_BLOG_ID (Blogger — 무료)

1. [blogger.com](https://www.blogger.com) → Google 계정 로그인
2. 블로그가 없으면 **"새 블로그 만들기"** 클릭
3. 블로그 ID 확인:
   - URL에서 확인: `https://www.blogger.com/blog/posts/`**`숫자`**
   - 또는: 블로그 대시보드 → 설정 → 기본 → "블로그 ID"
4. 숫자만 복사해서 `BLOGGER_BLOG_ID`로 등록

### 3️⃣ BLOGGER_SERVICE_ACCOUNT_JSON (Google Cloud — 무료)

**A. Google Cloud 프로젝트 생성 (무료)**
1. [console.cloud.google.com](https://console.cloud.google.com) 접속
2. 프로젝트 선택 → **"새 프로젝트"** → 이름 입력 (예: `market-blog`) → 만들기

**B. Blogger API 활성화**
1. **API 및 서비스 → API 라이브러리**
2. `Blogger API v3` 검색 → **사용 설정**

**C. 서비스 계정 생성**
1. **IAM 및 관리자 → 서비스 계정 → 서비스 계정 만들기**
2. 이름: `blog-publisher` → 만들기 및 계속 → 완료
3. 생성된 서비스 계정 클릭 → **키 → 키 추가 → JSON**
4. JSON 파일 다운로드 (안전하게 보관)

**D. 블로그에 서비스 계정 권한 부여**
1. 다운로드된 JSON 파일 열기 → `client_email` 값 복사
   (예: `blog-publisher@market-blog.iam.gserviceaccount.com`)
2. Blogger 대시보드 → **설정 → 권한**
3. **"작성자 초대"** → 서비스 계정 이메일 입력
4. **관리자** 권한으로 설정

**E. GitHub Secret 등록**
- JSON 파일 전체 내용을 `BLOGGER_SERVICE_ACCOUNT_JSON`으로 등록

---

## 🚀 실행 방법

### 로컬 테스트
```bash
git clone https://github.com/YOUR_USERNAME/us-market-blog.git
cd us-market-blog

pip install -r requirements.txt

# .env 파일 생성
cp .env.example .env
# .env 파일에 실제 값 입력 후 저장

# 오전 포스트 테스트
python scripts/morning_post.py

# 저녁 포스트 테스트
python scripts/evening_post.py
```

### GitHub Actions 수동 실행 (테스트)
1. GitHub 레포 → **Actions 탭**
2. **"US Market Blog — Auto Post"** 클릭
3. **"Run workflow"** → `morning` 또는 `evening` 선택 → **Run**

---

## 📊 포스트 구성

### 오전 포스트 (08:00 KST) — 증시 마감 리뷰
- ✅ S&P 500, NASDAQ, 다우, 러셀 2000 실제 데이터 (yfinance)
- ✅ 11개 섹터 ETF 등락률 (yfinance)
- ✅ 대형주 상승/하락 상위 5종목 (yfinance 배치 다운로드)
- ✅ 국채 금리, VIX, 달러, 유가, 금 (yfinance)
- ✅ 동적 썸네일: 실제 지수값 + 등락 표시 (matplotlib 자동 생성)
- ✅ SEO 최적화 제목·태그·메타 설명

### 저녁 포스트 (22:00 KST) — 프리마켓 프리뷰
- ✅ ES/NQ/YM/RTY 선물 현황 (yfinance)
- ✅ 아시아·유럽 시장 마감 (yfinance)
- ✅ 오늘 실적 발표 기업 (yfinance .calendar)
  - **실적 비교표**: EPS 예상 vs 실제, 매출 예상 vs 실제, 서프라이즈 %
  - **과거 4분기 히스토리** 비교
- ✅ 경제 지표 발표 (FRED 공개 CSV)
  - **지표 비교표**: 이전치, 예상치, 실제치, 영향도(High/Medium)
  - CPI, PCE, NFP, 실업률 등 15개 주요 지표

---

## 🗓️ 크론 스케줄

```yaml
# KST 08:00 = UTC 23:00  (오전 포스트, 월~금)
- cron: "0 23 * * 0-4"

# KST 22:00 = UTC 13:00  (저녁 포스트, 월~금)
- cron: "0 13 * * 0-4"
```

> GitHub Actions 크론은 UTC 기준 / KST = UTC+9

---

## 🐛 문제 해결

**Gemini 429 오류 (rate limit)**
- 무료 티어 한도: 15 requests/minute
- 코드에 자동 재시도 로직 내장 (60초 대기 후 재시도)
- 하루 포스트 2개이므로 실제로는 거의 발생하지 않음

**yfinance 데이터 없음**
- Yahoo Finance 일시적 rate limit — 다음 실행 시 정상화
- GitHub Actions 환경에서는 프록시 제한 없이 정상 동작

**Blogger 401 오류**
- 서비스 계정 이메일이 블로그에 Author 이상 권한으로 등록됐는지 확인
- Blogger API v3가 Google Cloud Console에서 활성화됐는지 확인
- `BLOGGER_BLOG_ID`가 숫자만 있는지 확인 (URL이 아님)

**FRED 데이터 없음**
- FRED 서버 일시 다운 시 해당 지표만 건너뜀 (다른 포스트 내용에는 영향 없음)
- 경제 지표 캘린더는 최근 2일 내 발표된 데이터만 표시
