# SECTION 02 공식 발표 연동

## 첫 적용 범위

| 출처 | 확인한 내용 | 공개 표시 |
| --- | --- | --- |
| [미 연준 RSS](https://www.federalreserve.gov/feeds/feeds.htm) · [이용 조건](https://www.federalreserve.gov/disclaimer.htm) | RSS에 실린 FOMC 성명의 원문에서 목표 금리 범위와 결정 확인 | 공식 발표 링크, 출처, 시각, 한국어로 정리한 사실 |
| [미 노동통계국 RSS](https://www.bls.gov/feed/) · [이용 조건](https://www.bls.gov/opub/copyright-information.htm) | CPI·고용 Atom 피드. 게시 시각과 [공식 발표 일정](https://www.bls.gov/schedule/2026/home.htm) 대조 | 발표 제목·링크·출처와 명확히 추출한 숫자. 사진·로고 제외 |
| [국가데이터처 RSS](https://kosis.kr/serviceInfo/rssGuide.do) · [이용 조건](https://www.mods.go.kr/menu.es?mid=a10706000000) | [10월 고용동향](https://www.mods.go.kr/board.es?act=view&bid=210&list_no=447893&mid=a10301030200)은 공공누리 2유형. 수집기에서 피드와 원문 HTTP 503 | 원문별 표시 확인과 안정적 수집 검증 후 연결 |
| [한국은행 RSS](https://www.bok.or.kr/static/view/popup/rss_popup.html) · [이용 조건](https://www.bok.or.kr/portal/main/contents.do?menuNo=200228) | 경제통계 RSS 수신 확인. 제공대상 외 자료의 이용은 직접 링크 조건이 적용됨 | 본문을 요약하는 자동 발행 출처로는 보류 |

## 발행과 검증

- 같은 한국 날짜의 발표를 해당 발행 실행 시각까지 확인한다. 지연 실행에는 18:30 KST 상한, 오전 복구에는 기존 18:00 KST 기준을 사용한다. BLS가 08:30 ET에 공표하는 지표는 통상 국내 발행 이후여서 확인 대기가 발생할 수 있다.
- 출처와 원문 URL을 제한한다. 날짜가 맞고 사실을 추출할 수 있는 발표를 우선순위에 따라 최대 두 건 선택한다. 같은 주제는 당일 한 건, 같은 원문은 최근 7일 내 중복을 방지한다.
- 사실·해석·공부 포인트를 구분한다. 해석은 가격 변동 원인을 단정하지 않고 확인할 비교 기준을 설명한다. 개념 설명에는 해당 발표에서 확인된 수치를 적용한다.
- 신규 국내 리포트와 누락 복구에만 연결한다. 뉴스 조회는 별도 프로세스에서 최대 13초로 제한한다. 응답 오류·지연·날짜 불일치·사실 추출 실패 시 확인 대기로 시황 리포트를 발행한다.
- 실제 연준 피드와 2026-10-28 ET 성명 응답을 재생해 10월 29일 KST의 SECTION 02에 3.75~4% 동결을 표시했다. 같은 달력 날짜에 게시됐어도 발행 상한 이후인 BLS 수치는 제외한다.
- 새 국내 출처의 정상 응답과 원문별 허용 표기를 확인하고 범위를 넓힌다. 그 뒤 [SECTION 02–04 요구사항](section-02-04-requirements.md)에 따라 학습과 복습을 연결한다.
