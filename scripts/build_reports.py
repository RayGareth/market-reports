#!/usr/bin/env python3
"""Build published Market Daily reports with the shared Ivory & Sage layout.
Usage: python3 scripts/build_reports.py
Only verified, publish:true, eight-section input is published.
"""
import html, json, pathlib, re
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"content"/"daily"
OUTPUT=ROOT/"reports"/"daily"
INDEX=ROOT/"reports"/"index.json"
NAMES=["MARKET TEMPERATURE","MARKET TIMELINE","CORE INSIGHT","FLOWS & SECTORS","MARKET READING","SCENARIOS","NEXT WATCH","QUICK QUIZ"]
def e(s):
    return html.escape(str(s),quote=True)
def generate(doc):
    date=doc["date"]
    if not re.fullmatch(r"20\d{2}-\d\d-\d\d",date): raise ValueError("Invalid date")
    sections=doc["sections"]
    if len(sections)!=8: raise ValueError("Eight sections required")
    quiz=doc["quiz"]
    options=quiz["options"]
    if len(options)<2 or not 0<=quiz["answer"]<len(options): raise ValueError("Quiz answer/options invalid")
    if not doc.get("sources"): raise ValueError("At least one source required")
    blocks=[]
    for idx,section in enumerate(sections):
        if not section.get("title") or not section.get("paragraphs"):raise ValueError("Missing section content")
        if idx==7:
            controls="".join('<label class="quiz-option"><input type="radio" name="answer" value="%s" required><span>%s</span></label>'%(i,e(opt)) for i,opt in enumerate(options))
            body='<div class="quiz"><form class="market-quiz" id="market-quiz" data-answer="%s"><fieldset><legend>%s</legend>%s</fieldset><div class="quiz-controls"><button class="button" type="submit">정답 확인</button><button type="reset" class="button-ghost">다시 풀기</button></div><div id="quiz-feedback" class="quiz-feedback" data-explanation="%s" role="status" aria-live="polite" hidden></div></form></div>'%(quiz["answer"],e(quiz["question"]),controls,e(quiz["explanation"]))
        else:body="".join("<p>%s</p>"%e(p) for p in section["paragraphs"])
        blocks.append('<section><div class="eyebrow">SECTION %02d / %s</div><h2>%s</h2>%s</section>'%(idx+1,NAMES[idx],e(section["title"]),body))
    sources="".join('<li><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></li>'%(e(x["url"]),e(x["label"])) for x in doc["sources"] if x["url"].startswith("https://"))
    blocks.append('<section><h2>자료 출처 및 기준</h2><p>%s</p><ul class="source-list">%s</ul></section>'%(e(doc["dataNote"]),sources))
    body="".join(blocks)
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f5ef"><title>%s | Market Daily</title><link rel="stylesheet" href="../../assets/style.css"></head><body><header class="site-header"><div class="container nav"><a class="brand" href="../../"><span class="brand-mark">◈</span>MARKET DAILY</a><nav class="navlinks"><a href="../../">대시보드</a><a class="active" href="../">리포트 아카이브</a></nav></div></header><main class="container"><section class="hero report-article"><div class="eyebrow">DAILY MARKET REPORT / %s</div><h1>%s</h1><p class="lead">%s</p><div class="notice">%s</div></section><article class="report-article">%s<p style="margin-top:45px"><a class="button" href="../">← 아카이브로 돌아가기</a></p></article></main><footer><div class="container footer-inner"><div>© MARKET DAILY</div><div>정보 제공 목적이며 투자 권유가 아닙니다.</div></div></footer><script src="../../assets/quiz.js" defer></script></body></html>'''%(e(date),e(date),e(doc["headline"]),e(doc["summary"]),e(doc["dataNote"]),body)
def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    existing=json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []
    by_date={r["date"]:r for r in existing}
    for path in sorted(DATA.glob("*.json")):
        doc=json.loads(path.read_text(encoding="utf-8"))
        if not doc.get("publish"):continue
        if doc.get("verification")!="verified":raise ValueError(f"Not verified: {path.name}")
        if doc["date"]!=path.stem:raise ValueError(f"Filename mismatch: {path.name}")
        (OUTPUT/(doc["date"]+".html")).write_text(generate(doc),encoding="utf-8")
        by_date[doc["date"]]={"date":doc["date"],"title":doc["headline"],"summary":doc["summary"],"market":doc.get("market",["kr","us"]),"tags":doc.get("tags",["정식 브리핑"]),"status":"published","url":"daily/"+doc["date"]+".html"}
        print("Built",doc["date"])
    INDEX.write_text(json.dumps(sorted(by_date.values(),key=lambda r:r["date"],reverse=True),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
