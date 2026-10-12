#!/usr/bin/env python3
"""Create a verified Korean-market closing brief; fail closed if the feeds disagree.
The scheduled workflow runs at 17:00 Asia/Seoul on weekdays.
No new report is created if the exchange is closed, data missing, or sources disagree.
"""
from __future__ import annotations
import json, math, os, pathlib, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
KST=ZoneInfo("Asia/Seoul")
NOW=datetime.now(KST)
DATE=NOW.date()
def verify_value(name, a, b):
    if not all(isinstance(x,(float,int)) and math.isfinite(x) and x>0 for x in [a,b]):
        raise ValueError(f"{name}: invalid price")
    diff=abs(a-b)/max(a,b)
    if diff>0.0005: raise ValueError(f"{name}: source mismatch {a} vs {b}, deviation {diff:.3%}")
    return round(float(a),2)
def sources_for(symbol,ticker,date):
    import yfinance as yf
    from pykrx import stock
    start=(date-timedelta(days=12)).strftime("%Y%m%d")
    end=date.strftime("%Y%m%d")
    table=stock.get_index_ohlcv_by_date(start,end,ticker)
    if table is None or table.empty:
        return None
    datekey=int(date.strftime("%Y%m%d"))
    keys=[int(x.strftime("%Y%m%d")) for x in table.index]
    if datekey not in keys:
        return None
    row=table.iloc[keys.index(datekey)]
    krx=float(row["종가"])
    history=yf.Ticker(symbol).history(period="1mo",interval="1d",auto_adjust=False)
    if history is None or history.empty:
        raise ValueError(f"{symbol}: Yahoo daily history unavailable")
    matched=[float(val) for idx,val in history["Close"].items() if idx.date()==date]
    if not matched: raise ValueError(f"{symbol}: Yahoo data for {date} unavailable")
    price=verify_value(symbol,krx,matched[-1])
    previous=table.iloc[keys.index(datekey)-1]["종가"] if keys.index(datekey)>0 else None
    if previous is None or float(previous)<=0: raise ValueError("previous close missing")
    change=round((price/float(previous)-1)*100,2)
    return {"close":price,"changePct":change,"previous":round(float(previous),2),"krx":krx,"yahoo":matched[-1],"date":date.isoformat()}
def main():
    # Github Actions must not publish before the standard closing feed has settled.
    if os.getenv("ALLOW_EARLY")!="1" and (NOW.hour<16 or (NOW.hour==16 and NOW.minute<45)):
        raise ValueError("Refusing to publish before 16:45 KST")
    kr= sources_for("^KS11","1001",DATE)
    kq= sources_for("^KQ11","2001",DATE)
    if kr is None and kq is None:
        print("No Korean-market session today; skipping (holiday/weekend).")
        return
    if kr is None or kq is None:raise ValueError("Only one local index has a confirmed closing price.")
    weekday=DATE.strftime("%Y-%m-%d")
    def direction(item):
        return "상승" if item["changePct"]>0 else "하락" if item["changePct"]<0 else "보합"
    market_lines=[
        f"KOSPI {kr['close']:,.2f}p ({kr['changePct']:+.2f}%), KOSDAQ {kq['close']:,.2f}p ({kq['changePct']:+.2f}%). 두 지수 모두 {weekday} 정규장 확정 종가입니다.",
        "지수별 종가는 한국거래소(pykrx)와 Yahoo Finance 일별 시세가 0.05% 이내에서 일치하는 경우에만 기록합니다."
    ]
    mix="같은 방향" if kr["changePct"]*kq["changePct"]>0 else "서로 다른 방향"
    sections=[
      {"title":"시장 온도: 국내 정규장 종가","paragraphs":market_lines},
      {"title":"시장 흐름 타임라인","paragraphs":[f"{weekday} 국내 장 마감: 코스피는 {direction(kr)}, 코스닥은 {direction(kq)} 마감했습니다.","미국 등 해외 시장의 실시간 뉴스·종가는 이번 자동 원고의 검증 범위 밖입니다. 검증되지 않은 뉴스는 포함하지 않습니다."]},
      {"title":"핵심 인사이트: 상대 강도 점검","paragraphs":[f"코스피 등락률 {kr['changePct']:+.2f}%와 코스닥 등락률 {kq['changePct']:+.2f}%는 {mix}입니다.",f"두 지수의 일간 수익률 차이는 {abs(kr['changePct']-kq['changePct']):.2f}%p입니다. 단일 거래일의 차이만으로 주도 업종의 장기 전환을 판단하지 않습니다."]},
      {"title":"수급과 업종: 미검증 항목 구분","paragraphs":["자동 수집이 확정한 범위는 코스피·코스닥 종가입니다. 투자자별 순매수 및 섹터별 등락은 검증된 원천 데이터가 확보되지 않아 수치를 기재하지 않습니다.","수급을 해석할 때는 외국인·기관·개인 매매와 시가총액 상위 종목의 기여도를 함께 확인해야 합니다."]},
      {"title":"경제 리딩: 지수와 등락률","paragraphs":["지수 수준은 특정 시점의 시장 가격을 요약한 값이며, 일간 등락률은 직전 거래일 종가와 오늘 종가를 비교해 계산합니다.","같은 1% 변동이라도 시가총액과 업종 구성에 따라 투자자가 체감하는 영향은 다를 수 있습니다."]},
      {"title":"액션 플랜: 조건 중심 점검","paragraphs":["다음 거래일에는 금리·환율과 글로벌 선물 흐름, 대형주의 상대 강도, 외국인·기관 매매 자료를 함께 확인합니다.","이 내용은 매수·매도 추천이 아닌 관찰 항목입니다. 변동성 확대 시 개인의 투자 기간과 위험 감수 범위를 우선 고려하세요."]},
      {"title":"다음 거래일 관전 포인트","paragraphs":["장 마감 후 공개되는 공식 수급 집계와 주요 기업 공시를 점검합니다.","다음 거래일의 시장 방향은 확정할 수 없으므로 뉴스 해석과 가격 데이터를 구분합니다."]},
      {"title":"오늘의 복습 퀴즈","paragraphs":["시장 기준일 확인 퀴즈"]},
    ]
    q={"question":"자동 시장 리포트의 '확정 종가'로 인정하기 위한 조건은 무엇일까요?","options":["장중 시세 한 곳만 확인한다.","한국거래소와 별도 시세 제공처의 거래일 및 종가를 대조한다.","전 거래일 종가를 오늘 날짜로 표시한다."],"answer":1,"explanation":"같은 날짜의 정규장 종가를 서로 독립적인 데이터 제공처에서 확인한 후 허용 오차 이내로 일치할 때만 발행합니다."}
    src=[
      {"label":"한국거래소 KRX 정보데이터시스템","url":"https://data.krx.co.kr/"},
      {"label":"Yahoo Finance KOSPI Historical Data","url":"https://finance.yahoo.com/quote/%5EKS11/history/"},
      {"label":"Yahoo Finance KOSDAQ Historical Data","url":"https://finance.yahoo.com/quote/%5EKQ11/history/"}
    ]
    note=f"발행 기준: {NOW.strftime('%Y-%m-%d %H:%M')} KST · 국내시장 {weekday} 정규장 종가. KRX와 Yahoo Finance 데이터를 대조했으며 허용 차이 0.05% 이하. 해외 지수 및 투자자별 수급은 이번 자동 원고에서 제공하지 않습니다."
    doc={"date":weekday,"publish":True,"verification":"verified","headline":f"{weekday} 국내 증시 마감: 코스피 {kr['changePct']:+.2f}%, 코스닥 {kq['changePct']:+.2f}%","summary":f"코스피 {kr['close']:,.2f}p, 코스닥 {kq['close']:,.2f}p · 장 마감 종가 대조 확인","dataNote":note,"market":["kr"],"tags":["국내 증시","마감 확정","자동 검증"],"sections":sections,"quiz":q,"sources":src}
    dest=ROOT/"content"/"daily"/f"{weekday}.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    snapshot_path=ROOT/"data"/"market-snapshot.json"
    snapshot=json.loads(snapshot_path.read_text(encoding="utf-8"))
    for code,item in [("kospi",kr),("kosdaq",kq)]:
        for entry in snapshot["indices"]:
            if entry["id"]==code:
                entry.update({"close":item["close"],"changePct":item["changePct"],"date":weekday,"source":"https://data.krx.co.kr/"})
        history=snapshot["history"].setdefault("kr",[])
        # The existing history series only contains KOSPI, never splice in KOSDAQ.
        if code=="kospi":
            history[:]=[x for x in history if x["date"]!=weekday]+[{"date":weekday,"value":item["close"]}]
            history.sort(key=lambda x:x["date"])
            history[:]=history[-10:]
    snapshot["updatedAt"]=NOW.isoformat(timespec="seconds")
    snapshot["note"]="한국 2개 지수는 "+weekday+" 확정 종가 대조 검증. 미국 지수는 기존의 개별 기준일을 확인하세요. 실시간 데이터가 아닙니다."
    snapshot["historySources"]["kr"]="https://data.krx.co.kr/"
    snapshot_path.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("VERIFIED",weekday,"KOSPI",kr["close"],"KOSDAQ",kq["close"])
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(f"VERIFICATION FAILED: {type(exc).__name__}: {exc}",file=sys.stderr)
        raise SystemExit(1)
