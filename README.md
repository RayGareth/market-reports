# Market Daily 🌿

Ivory & Sage 테마의 국내·미국 시장 리서치 대시보드.

- [웹사이트](https://raygareth.github.io/market-reports/)
- [리포트 아카이브](https://raygareth.github.io/market-reports/reports/)

## 공통 리포트 템플릿

앞으로 발행할 리포트는 `content/daily/YYYY-MM-DD.json` 원고를 이용해 `scripts/build_reports.py`가 HTML로 생성합니다.

- 8개 고정 섹션, Sage 구분선, 객관식 선택 → 정답 확인 → 해설 → 다시 풀기 기능
- 기존 CSS `assets/style.css` 및 퀴즈 엔진 `assets/quiz.js` 공통 사용
- `reports/index.json`에서 아카이브 목록 자동 생성
- `content/daily/2026-10-13.json`은 **발행되지 않는 예시 초안**입니다.

### 리포트 발행 절차

1. 해당 거래일의 종가·거래일·수급·뉴스 출처를 확인합니다.
2. `content/daily/YYYY-MM-DD.json`에 검증한 원고를 채웁니다.
3. `publish: true` 및 `verification: "verified"`를 설정합니다.
4. GitHub 저장소 → **Actions** → **Build Market Daily Reports** → **Run workflow**를 실행합니다.
5. GitHub Pages 자동 배포가 완료되면 HTML과 아카이브가 공개됩니다.

로컬에서 테스트할 때는 `python3 scripts/build_reports.py`를 실행할 수 있습니다.

> 중요: GitHub Actions 발행 워크플로는 **수동 실행** 방식입니다. 장 마감만으로 리포트가 자동 작성되지는 않습니다. 자동 자료 수집·검증·뉴스 분석·스케줄 실행은 후속 개발 대상입니다. 검증되지 않은 숫자를 임의로 채우지 않습니다.

기존 2026-10-12 리포트는 오후 작성판으로 국내 **10월 8일 확정 종가**를 사용하고 있습니다. 국내 **10월 12일 마감 종가로 갱신한 버전은 아직 아닙니다**.

## 거래일 오후 5시(KST) 자동 발행

- 예약 실행: `.github/workflows/publish-close.yml` · 월~금 **08:00 UTC = 17:00 KST**
- 수집: `scripts/collect_close.py` · 한국거래소 `pykrx` (1.2.9) + Yahoo Finance 종가 대조
- 검증: 실제 **오늘 거래일**의 KOSPI/KOSDAQ 종가가 양쪽에서 조회되고 각각 0.05% 이내 일치해야 함
- 휴장일: 해당 날짜의 KRX 거래 데이터가 두 지수 모두 없는 경우 새 리포트를 발행하지 않음
- 검증 실패 또는 인증 오류: 워크플로 실패 처리, 오늘 리포트 미발행
- 발행: 공통 생성기로 8개 섹션+선택형 퀴즈를 생성하고 아카이브·대시보드를 갱신
- 미국 지수 및 검증하지 못한 투자자별 수급 수치는 **이 자동 마감판에서 갱신하지 않음** (기존 값은 날짜와 함께 유지)

### 최초 실행 전: GitHub Actions Secrets 설정 필수

GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret 에서 다음 두 항목을 설정하세요.

- `KRX_ID`: 본인 KRX 정보데이터시스템 계정 아이디
- `KRX_PW`: 해당 계정 비밀번호

**이 채팅에 ID/비밀번호를 보내지 마세요.** GitHub의 암호화된 Secrets 입력창에만 등록하세요. 
Secrets가 없거나 데이터 조회가 실패하면 설정된 스케줄로 실행되더라도 **리포트를 발행하지 않습니다**.

GitHub Actions 예약 실행은 실제 시작 시점이 혼잡도에 따라 지연될 수 있으므로 **17:00 정각 게시가 보장되지는 않습니다**. 최초 1회 검증은 Actions → Publish Verified Market Daily at 17 KST → Run workflow를 이용하세요.
