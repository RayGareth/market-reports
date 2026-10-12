#!/usr/bin/env python3
"""Create a Korean-market closing brief with Yahoo–Naver cross-source checks.
The scheduled workflow runs at 17:00 Asia/Seoul on weekdays.
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
def main():
    # Github Actions must not publish before the standard closing feed has settled.
    if os.getenv("ALLOW_EARLY")!="1" and (NOW.hour<16 or (NOW.hour==16 and NOW.minute<45)):
        raise ValueError("Refusing to publish before 16:45 KST")
    kr= sources_for("^KS11","1001",DATE)
    kq= sources_for("^KQ11","2001",DATE)
    if kr is None and kq is None:
        raise ValueError("No same-day Yahoo daily bars; holiday or provider delay. Publishing blocked.")
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
    q={"question":"자동 시장 리포트의 '확정 종가'로 인정하기 위한 조건은 무엇일까요?","options":["장중 시세 한 곳만 확인한다.","Yahoo Finance와 네이버 금융의 거래일·종가 일치 여부를 대조한다.","전 거래일 종가를 오늘 날짜로 표시한다."],"answer":1,"explanation":"당일 Yahoo Finance 일별 종가와 네이버 금융 일별 종가를 교차 대조하며, 어느 한쪽이라도 누락되거나 허용 차이를 넘으면 발행하지 않습니다."}
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
