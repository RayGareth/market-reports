#!/usr/bin/env python3
"""Create a Korean-market closing brief with Yahoo–Naver cross-source checks.
The scheduled workflow runs at 18:00, 18:15 and 18:30 Asia/Seoul on weekdays.
No new report is created if the exchange is closed, data missing, or sources disagree.
"""
from __future__ import annotations
import json, math, os, pathlib, sys
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
KST=ZoneInfo("Asia/Seoul")
NOW=datetime.now(KST)
DATE=NOW.date()
def sources_for(symbol, ticker, date):
    """Yahoo daily OHLC only: explicit single-provider validation, not cross-source verification."""
    import yfinance as yf
    history=yf.Ticker(symbol).history(period="1mo",interval="1d",auto_adjust=False)
    if history is None or history.empty:raise ValueError(f"{symbol}: no Yahoo daily OHLC data")
    rows=[(idx,row) for idx,row in history.iterrows() if idx.date()==date]
    if not rows:return None
    idx,row=rows[-1]
    for field in ("Open","High","Low","Close"):
        value=float(row[field])
        if not math.isfinite(value) or value<=0:raise ValueError(f"{symbol}: invalid {field}")
    close=float(row["Close"])
    if not(float(row["Low"])<=close<=float(row["High"])):raise ValueError(f"{symbol}: OHLC inconsistent")
    older=history.loc[history.index.date<date]
    if older.empty:raise ValueError(f"{symbol}: previous day not available")
    previous=float(older["Close"].iloc[-1])
    if not math.isfinite(previous) or previous<=0:raise ValueError(f"{symbol}: previous close invalid")
    change=(close/previous-1)*100
    if abs(change)>25:raise ValueError(f"{symbol}: implausible daily index change {change:.2f}%")
    return {"close":round(close,2),"changePct":round(change,2),"previous":round(previous,2),"date":date.isoformat()}
def naver_close(code, date):
    """Read the public Naver Finance daily index endpoint, without login."""
    import requests
    url=f"https://m.stock.naver.com/api/index/{code}/price"
    response=requests.get(url,params={"page":1,"pageSize":10},headers={"User-Agent":"MarketDaily/1.0 (daily close verification; public endpoint)","Accept":"application/json"},timeout=12)
    response.raise_for_status()
    bars=response.json()
    if not isinstance(bars,list):
        raise ValueError(f"{code}: unexpected Naver daily response")
    matches=[bar for bar in bars if isinstance(bar,dict) and bar.get("localTradedAt","")[:10]==date.isoformat()]
    if not matches:return None
    value=float(str(matches[0]["closePrice"]).replace(",",""))
    if not math.isfinite(value) or value<=0:raise ValueError(f"{code}: invalid Naver close")
    return value
def cross_check(index_name, yahoo, naver):
    if yahoo is None or naver is None:
        raise ValueError(f"{index_name}: same-date close missing from one provider; stop publishing")
    # Tolerance 0.05%, with at least half a point of numeric rounding headroom.
    diff=abs(yahoo["close"]-naver)
    tolerance=max(0.5,naver*0.0005)
    if diff>tolerance:
        raise ValueError(f"{index_name}: Yahoo {yahoo['close']} / Naver {naver} differ by {diff:.2f} (limit {tolerance:.2f})")
    return yahoo
def make_daily_quiz(date, kr, kq):
    """Deterministic, market-grounded quiz rotation; no extra data sources."""
    from datetime import date as date_type
    day=date_type.fromisoformat(date)
    spread=round(abs(kr["changePct"]-kq["changePct"]),2)
    leader="코스피" if kr["changePct"]>kq["changePct"] else "코스닥" if kq["changePct"]>kr["changePct"] else "동일"
    leader_wrong="코스닥" if leader=="코스피" else "코스피"
    questions=[
      {"question":f"{date} 코스피 {kr['changePct']:+.2f}%, 코스닥 {kq['changePct']:+.2f}%일 때 두 지수의 일간 수익률 차이는?",
       "options":[f"{spread:.2f}%p",f"{spread:.2f}%",f"{abs(kr['changePct'])+abs(kq['changePct']):.2f}%p"],
       "answer":0,"explanation":f"수익률 차이는 |{kr['changePct']:+.2f} - ({kq['changePct']:+.2f})| = {spread:.2f}%p입니다. 퍼센트끼리의 차이는 퍼센트포인트(%p)로 표시합니다."},
      {"question":f"{date} 코스피 {kr['changePct']:+.2f}%, 코스닥 {kq['changePct']:+.2f}%일 때 상대적으로 강했던 시장은?",
       "options":[leader_wrong,"두 시장의 등락률은 언제나 같다",leader],
       "answer":2,"explanation":f"등락률을 비교하면 {'두 시장이 동일합니다' if leader=='동일' else leader+'가 상대적으로 강했습니다'}. 상대 강도는 투자자별 순매수를 뜻하지 않습니다."},
      {"question":"코스피·코스닥 지수 등락률만으로 알 수 없는 정보는 무엇일까요?",
       "options":["두 지수의 상대 강도","외국인·기관·개인의 순매수 금액","두 지수의 상승·하락 방향"],
       "answer":1,"explanation":"지수 등락률만으로 투자 주체별 순매수액을 추론할 수 없습니다. 별도로 검증된 수급 데이터가 필요합니다."},
      {"question":"오늘의 종가와 전 거래일 종가를 비교한 수익률의 의미는 무엇일까요?",
       "options":["전 거래일 종가 대비 가격 변화율","장중 최고가 대비 가격 변화율","거래대금의 변화율"],
       "answer":0,"explanation":"일간 등락률은 (오늘 종가 / 전 거래일 종가 - 1) × 100으로 계산합니다."},
      {"question":"확정 종가와 장중 시세를 구분해야 하는 이유로 가장 적절한 것은?",
       "options":["장중 시세는 언제나 확정 종가와 같다","확정 종가는 다음 거래일에도 바뀌지 않는 예측치다","장중 가격은 계속 변하므로 거래일·기준 시각을 확인해야 한다"],
       "answer":2,"explanation":"장중 가격은 변동할 수 있습니다. 리포트는 같은 거래일의 마감 데이터를 확인하고 기준일을 표시해야 합니다."},
      {"question":"하루 동안 코스닥 수익률이 코스피보다 높았을 때 올바른 해석은?",
       "options":["모든 코스닥 종목이 상승했다","그날 코스닥 지수가 상대적으로 강했다","외국인이 코스닥을 순매수했다"],
       "answer":1,"explanation":"지수 간 상대 강도는 비교할 수 있지만, 개별 종목 상승 여부나 투자 주체별 매매는 별도 자료가 필요합니다."},
      {"question":"지수의 일간 수익률 차이가 2%p라는 표현의 의미는?",
       "options":["두 수익률의 차이가 2퍼센트포인트다","두 지수의 가격 차이가 2포인트다","두 지수의 거래량 차이가 2%다"],
       "answer":0,"explanation":"%p는 두 퍼센트 수치 사이의 산술적 차이를 뜻합니다. 지수 포인트나 거래량과는 다릅니다."},
    ]
    # Weekday rotation: adjacent weekday publications receive different quiz types.
    # Count weekdays rather than calendar days, avoiding weekly repeats.
    days=(day-date_type(2000,1,3)).days
    trading_slots=(days//7)*5+min(days%7,5)
    index=trading_slots%len(questions)
    return questions[index]

def main():
    # Github Actions must not publish before the standard closing feed has settled.
    if NOW.hour<16 or (NOW.hour==16 and NOW.minute<45):
        raise ValueError("Refusing to publish before 16:45 KST")
    kr= sources_for("^KS11","1001",DATE)
    kq= sources_for("^KQ11","2001",DATE)
    if kr is None and kq is None:
        print("NO_SAME_DAY_CLOSE: market holiday or delayed feed; no publication.")
        return
    if kr is None or kq is None:raise ValueError("Only one Korean index has a same-date Yahoo closing bar.")
    kr=cross_check("KOSPI",kr,naver_close("KOSPI",DATE))
    kq=cross_check("KOSDAQ",kq,naver_close("KOSDAQ",DATE))
    weekday=DATE.strftime("%Y-%m-%d")
    def direction(item):
        return "상승" if item["changePct"]>0 else "하락" if item["changePct"]<0 else "보합"
    market_lines=[
        f"KOSPI {kr['close']:,.2f}p ({kr['changePct']:+.2f}%), KOSDAQ {kq['close']:,.2f}p ({kq['changePct']:+.2f}%). 두 지수 모두 {weekday} 정규장 확정 종가입니다.",
        "지수별 종가는 Yahoo Finance의 일별 종가·OHLC를 네이버 금융의 동일 거래일 종가와 대조했습니다. 두 출처 간 0.05% 또는 최소 0.5포인트 이내로 일치할 때만 발행합니다."
    ]
    mix="같은 방향" if kr["changePct"]*kq["changePct"]>0 else "서로 다른 방향"
    # SECTION 05: explain only what the verified index changes establish.
    kp, qp = kr["changePct"], kq["changePct"]
    gap = abs(kp - qp)
    if kp > 0 and qp > 0:
        situation = "두 지수가 모두 상승"
        lesson = "상승률 비교"
        explanation = "두 지수가 함께 올라도 상승률은 다를 수 있습니다. 차이는 퍼센트포인트(%p)로 비교합니다."
    elif kp < 0 and qp < 0:
        situation = "두 지수가 모두 하락"
        lesson = "하락률과 변동 폭"
        explanation = "두 지수가 함께 하락해도 하락 폭은 다를 수 있습니다. 등락률의 차이는 퍼센트포인트(%p)로 표시합니다."
    elif kp * qp < 0:
        situation = "두 지수가 서로 다른 방향으로 움직임"
        lesson = "시장 간 차별화"
        explanation = "같은 날에도 시장별 지수 방향은 달라질 수 있습니다. 지수의 방향만으로 개별 종목의 움직임을 알 수는 없습니다."
    elif kp == 0 and qp == 0:
        situation = "두 지수의 등락률이 모두 0.00%"
        lesson = "보합과 등락률"
        explanation = "등락률 0.00%는 표시된 자릿수 기준의 값입니다. 모든 구성 종목의 가격이 같았다는 의미는 아닙니다."
    else:
        situation = "한 지수는 보합이고 다른 지수는 변동"
        lesson = "보합과 시장 비교"
        explanation = "보합과 상승·하락은 서로 다른 시장 흐름을 보여줍니다. 지수 변화만으로 원인을 확정할 수 없습니다."
    reading = [
        f"오늘의 시장 해석 | 오늘의 마감 특징은 {situation}입니다. 지수의 방향을 먼저 확인하고 두 시장의 움직임이 같은지 비교해 보세요.",
        f"오늘의 경제 개념 · {lesson} | {explanation}",
        "오늘의 이해 포인트 | 지수 등락률만으로 매매 주체별 수급이나 상승·하락의 원인을 단정할 수 없습니다. 추가 자료를 확인한 뒤 해석해야 합니다."
    ]
    sections=[
      {"title":"시장 온도: 정규장 종가","paragraphs":market_lines,"marketTable":{"date":weekday,"rows":[{"market":"KOSPI","close":kr["close"],"changePct":kr["changePct"]},{"market":"KOSDAQ","close":kq["close"],"changePct":kq["changePct"]}]}},
      {"title":"시장 흐름 타임라인","paragraphs":[f"{weekday} 국내 장 마감: 코스피는 {direction(kr)}, 코스닥은 {direction(kq)} 마감했습니다.","미국 등 해외 시장의 실시간 뉴스·종가는 이번 자동 원고의 검증 범위 밖입니다. 검증되지 않은 뉴스는 포함하지 않습니다."]},
      {"title":"핵심 인사이트: 상대 강도 점검","paragraphs":[f"코스피 등락률 {kr['changePct']:+.2f}%와 코스닥 등락률 {kq['changePct']:+.2f}%는 {mix}입니다.",f"두 지수의 일간 수익률 차이는 {abs(kr['changePct']-kq['changePct']):.2f}%p입니다. 단일 거래일의 차이만으로 주도 업종의 장기 전환을 판단하지 않습니다."]},
      {"title":"수급과 업종: 확인된 상대 강도와 미검증 수급","paragraphs":[f"시장 간 상대 강도: 코스피 {kr['changePct']:+.2f}%, 코스닥 {kq['changePct']:+.2f}%. {'코스피가 상대적으로 강했습니다' if kr['changePct']>kq['changePct'] else '코스닥이 상대적으로 강했습니다' if kr['changePct']<kq['changePct'] else '두 지수의 수익률이 같았습니다'}. 이는 시장 지수의 상대 강도일 뿐, 특정 업종이나 매매 주체의 움직임을 증명하지 않습니다.","외국인·기관·개인 순매수액과 업종별 등락률은 검증된 원천 데이터가 확보되지 않아 숫자를 기재하지 않습니다. 순매수는 거래대금 기준이며, 지수 하락만으로 외국인 순매도를 추정할 수 없습니다.","추가 검증 대상: 외국인·기관 순매수, 업종별 상승·하락 폭, 업종 거래대금, 대형주 지수 기여도. 수치와 출처가 확보된 경우에만 해당 항목의 해석을 발행합니다."]},
      {"title":"오늘의 시장 읽기","paragraphs":reading},
      {"title":"액션 플랜: 조건 중심 점검","paragraphs":["다음 거래일에는 금리·환율과 글로벌 선물 흐름, 대형주의 상대 강도, 외국인·기관 매매 자료를 함께 확인합니다.","이 내용은 매수·매도 추천이 아닌 관찰 항목입니다. 변동성 확대 시 개인의 투자 기간과 위험 감수 범위를 우선 고려하세요."]},
      {"title":"다음 거래일 관전 포인트","paragraphs":["장 마감 후 공개되는 공식 수급 집계와 주요 기업 공시를 점검합니다.","다음 거래일의 시장 방향은 확정할 수 없으므로 뉴스 해석과 가격 데이터를 구분합니다."]},
      {"title":"오늘의 복습 퀴즈","paragraphs":["시장 기준일 확인 퀴즈"]},
    ]
    q=make_daily_quiz(weekday,kr,kq)
    src=[
      {"label":"Yahoo Finance KOSPI Historical Data","url":"https://finance.yahoo.com/quote/%5EKS11/history/"},
      {"label":"Yahoo Finance KOSDAQ Historical Data","url":"https://finance.yahoo.com/quote/%5EKQ11/history/"},
      {"label":"네이버 금융 KOSPI 일별 시세","url":"https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI"},
      {"label":"네이버 금융 KOSDAQ 일별 시세","url":"https://finance.naver.com/sise/sise_index_day.naver?code=KOSDAQ"}
    ]
    note=f"발행 기준: {NOW.strftime('%Y-%m-%d %H:%M')} KST · 국내시장 {weekday} 정규장 종가. Yahoo Finance·네이버 금융 종가를 거래일별로 교차 점검 (허용 차이 0.05% 또는 최소 0.5포인트). 비공식 공개 데이터이므로 오류·지연 가능성이 있음. 해외 지수 및 투자자별 수급은 이번 자동 원고에서 제공하지 않습니다."
    doc={"date":weekday,"publish":True,"verification":"verified","headline":f"{weekday} 국내 증시 마감: 코스피 {kr['changePct']:+.2f}%, 코스닥 {kq['changePct']:+.2f}%","summary":f"코스피 {kr['close']:,.2f}p, 코스닥 {kq['close']:,.2f}p · Yahoo·네이버 교차 검증","dataNote":note,"market":["kr"],"tags":["국내 증시","Yahoo·네이버 교차검증"],"sections":sections,"quiz":q,"sources":src}
    dest=ROOT/"content"/"daily"/f"{weekday}.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    snapshot_path=ROOT/"data"/"market-snapshot.json"
    snapshot=json.loads(snapshot_path.read_text(encoding="utf-8"))
    for code,item in [("kospi",kr),("kosdaq",kq)]:
        for entry in snapshot["indices"]:
            if entry["id"]==code:
                entry.update({"close":item["close"],"changePct":item["changePct"],"date":weekday,"source":"https://finance.yahoo.com/quote/%5EKS11/history/" if code=="kospi" else "https://finance.yahoo.com/quote/%5EKQ11/history/"})
        history=snapshot["history"].setdefault("kr",[])
        # The existing history series only contains KOSPI, never splice in KOSDAQ.
        if code=="kospi":
            history[:]=[x for x in history if x["date"]!=weekday]+[{"date":weekday,"value":item["close"]}]
            history.sort(key=lambda x:x["date"])
            history[:]=history[-10:]
    snapshot["updatedAt"]=NOW.isoformat(timespec="seconds")
    snapshot["note"]="한국 2개 지수는 "+weekday+" Yahoo·네이버 종가 교차 점검. 미국 지수는 기존의 개별 기준일을 확인하세요. 실시간 데이터가 아닙니다."
    snapshot["historySources"]["kr"]="https://finance.yahoo.com/quote/%5EKS11/history/"
    snapshot_path.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CROSS_SOURCE_CHECKED",weekday,"KOSPI",kr["close"],"KOSDAQ",kq["close"])
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(f"VERIFICATION FAILED: {type(exc).__name__}: {exc}",file=sys.stderr)
        raise SystemExit(1)
