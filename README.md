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

> 중요: GitHub Actions 발행 공통 생성 워크플로는 **수동 실행**이며, 별도 오후 5시 예약 발행 워크플로가 있습니다. 자동 자료 수집과 예약 실행은 추가됐지만 첫 실제 성공 여부를 확인해야 합니다. 뉴스 분석은 수동 보강 대상입니다. 검증되지 않은 숫자를 임의로 채우지 않습니다.

기존 2026-10-12 리포트는 오후 작성판으로 국내 **10월 8일 확정 종가**를 사용하고 있습니다. 국내 **10월 12일 마감 종가로 갱신한 버전은 아직 아닙니다**.

## 거래일 오후 5시(KST) 자동 발행 — KRX 계정 불필요

- 스케줄: 평일 08:00 UTC, 한국시간 17:00 (GitHub Actions 예약 실행은 지연될 수 있음)
- 데이터: Yahoo Finance의 KOSPI(`^KS11`)와 KOSDAQ(`^KQ11`) **단일 제공처 일별 OHLC**
- 품질 확인: 날짜가 오늘인지, OHLC가 유효하고 논리적으로 일치하는지, 직전 종가가 존재하는지, 일간 변동폭이 비정상적이지 않은지 점검
- **독립 출처 교차 검증은 수행하지 않음.** 기준 출처를 리포트와 대시보드에 명시
- 두 지수의 당일 마감 데이터가 모두 없거나 이상이 있으면 발행하지 않음. 공휴일 또는 제공처 반영 지연이면 발행이 생략되거나 실패할 수 있음
- 데이터 점검을 통과한 때에만 8개 섹션 + 퀴즈를 만들고 아카이브 및 대시보드를 업데이트
- 뉴스와 외국인·기관 수급, 미국 시장 최신 종가는 이 자동 마감판에서 자동 확인하지 않음
- 계정/비밀번호, GitHub Secrets 설정은 불필요
- 현재 생성 코드는 GitHub에 저장되어 있지만 **첫 예약 작업의 성공 여부는 아직 검증되지 않음**

실행 확인: GitHub 저장소 → Actions → Publish Market Daily at 17 KST (Yahoo single-source) → Run workflow. 17:00에 작업이 예정돼 있어도 GitHub 시스템 상황에 따라 지연될 수 있습니다.

기존 2026-10-12 오후 브리핑은 아직 종가 기준 갱신본이 아니며, 첫 실행 성공 시 같은 날짜의 자동 마감 리포트로 교체됩니다.
