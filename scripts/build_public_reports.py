#!/usr/bin/env python3
"""Build four-section, public-safe study notes without reading private data.
Existing dated HTML and manuscripts are preserved. No market data is scraped.
"""
import argparse
import html
import json
import math
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TITLES = ['오늘의 시장 한눈에 보기', '오늘의 주요 이슈와 시장 흐름', '오늘의 경제 공부', '오늘의 복습 퀴즈']
SOURCE = 'https://www.investor.gov/introduction-investing'
# Original short explanations; numeric examples are explicitly hypothetical.
LESSONS = [
    {'term': '복리', 'explanation': '복리는 원금에서 생긴 이자가 다음 이자를 계산하는 바탕에 함께 들어가는 방식입니다.',
     'example': '예금을 고를 때는 이율뿐 아니라 이자를 언제 지급하고 다시 계산하는지도 살펴보세요. 실제 수익은 세금과 조건에 따라 달라집니다.',
     'question': '복리를 설명한 문장은 무엇일까요?', 'options': ['원금과 쌓인 이자를 함께 기준으로 이자를 계산한다', '이자를 항상 원금에서만 계산한다', '어떤 상품이든 원금이 보장된다'], 'answer': 0, 'why': '복리는 이전에 쌓인 이자도 다음 이자 계산에 포함하는 방식입니다.'},
    {'term': '분산', 'explanation': '여러 대상에 나누면 한 대상의 변화에만 결과가 좌우되는 정도를 줄일 수 있습니다. 손실 가능성이 없어지는 것은 아닙니다.',
     'example': '이름이 다른 펀드라도 담고 있는 기업이 비슷할 수 있습니다. 이름보다 구성 내용을 살펴보면 분산의 의미가 더 잘 보입니다.',
     'question': '분산에 대한 설명 중 알맞은 것은?', 'options': ['손실을 완전히 없앤다', '특정 대상에 대한 집중을 줄인다', '상품 이름만 다르면 충분하다'], 'answer': 1, 'why': '분산은 집중을 줄이는 방법이며 손실을 없애는 보장은 아닙니다.'},
    {'term': '지수', 'explanation': '시장 지수는 정해진 여러 자산의 움직임을 하나의 수치로 요약합니다. 지수의 움직임과 모든 개별 종목의 움직임이 같지는 않습니다.',
     'example': '학급 평균이 올라가도 모든 학생의 점수가 오른 것은 아닙니다. 시장 전체의 요약과 개별 기업의 상황도 나누어 읽어보세요.',
     'question': '지수가 올랐다는 사실만으로 알 수 없는 것은?', 'options': ['지수의 방향', '지수가 시장을 요약한다는 점', '모든 구성 종목이 올랐는지 여부'], 'answer': 2, 'why': '전체를 요약한 지수와 구성 종목 각각의 움직임은 다를 수 있습니다.'},
    {'term': '저축과 투자', 'explanation': '저축은 돈을 모아 두는 활동이고, 투자는 자산의 가치 변화나 이자·배당 등의 성과를 기대하며 자산을 보유하는 활동입니다. 투자에는 손실 위험이 있습니다.',
     'example': '곧 쓸 생활비와 오랫동안 쓰지 않을 돈은 사용 시점이 다릅니다. 금융 뉴스를 읽을 때도 자금의 목적과 기간을 함께 생각해 보세요.',
     'question': '투자에 대한 설명으로 알맞은 것은?', 'options': ['성과를 기대하지만 손실 위험도 있다', '모든 투자의 이익은 확정되어 있다', '투자는 언제나 저축과 같은 보장을 받는다'], 'answer': 0, 'why': '투자는 성과를 기대하는 활동이지만 결과를 보장하지는 않습니다.'},
]

def esc(value):
    return html.escape(str(value), quote=True)

def https(value):
    return isinstance(value, str) and value.startswith('https://') and len(value) > 8

def approved(item):
    rights = item.get('publication', {})
    return item.get('verified') is True and rights.get('status') == 'approved_public' and https(rights.get('evidence')) and https(item.get('source'))

def validate(doc):
    date.fromisoformat(doc['date'])
    if doc.get('schemaVersion') != 4 or doc.get('publication') != 'original_study':
        raise ValueError('Only reviewed four-section original study notes are supported')
    lesson = doc['lesson']
    if not lesson.get('term') or not lesson.get('explanation') or not https(lesson.get('source')):
        raise ValueError('Lesson text and source required')
    if not 0 <= lesson['answer'] < len(lesson['options']):
        raise ValueError('Invalid quiz answer')
    for item in doc.get('indices', []):
        if not approved(item):
            raise ValueError('Unconfirmed market-data publication permission: refusing to render')
        date.fromisoformat(item['asOf'])
        if item.get('region') not in ('kr', 'us') or not item.get('name'):
            raise ValueError('Index region and name required')
        if not all(isinstance(item.get(k), (float, int)) and not isinstance(item[k], bool) and math.isfinite(item[k]) for k in ('close', 'changePct')) or item['close'] <= 0:
            raise ValueError('Invalid closing figures')
    for item in doc.get('distribution', []):
        if not approved(item):
            raise ValueError('Unconfirmed distribution publication permission')
        date.fromisoformat(item['asOf'])
        if item.get('name') not in ('KOSPI', 'KOSDAQ'):
            raise ValueError('Invalid distribution market')
        if not all(type(item.get(k)) is int and item[k] >= 0 for k in ('up', 'down', 'flat')):
            raise ValueError('Invalid distribution counts')
    for item in doc.get('issues', []):
        if not approved(item) or not item.get('fact'):
            raise ValueError('News needs verified facts, source and publication approval')

def make_doc(day, backfill=False):
    lesson = dict(LESSONS[(day - date(2026, 10, 12)).days % len(LESSONS)])
    lesson['source'] = SOURCE
    return {'schemaVersion': 4, 'date': day.isoformat(), 'publication': 'original_study',
            'edition': 'archive-study' if backfill else 'daily-study',
            'headline': day.isoformat() + ' · ' + lesson['term'] + ' 함께 읽기',
            'summary': '시장 자료는 확인된 항목만, 경제 공부는 한 가지씩.',
            'indices': [], 'distribution': [], 'issues': [], 'lesson': lesson}

def generate(doc):
    validate(doc)
    day, lesson = doc['date'], doc['lesson']
    overview = ''
    for region, label in [('kr', '국내'), ('us', '미국')]:
        rows = [x for x in doc.get('indices', []) if x['region'] == region]
        overview += '<h3>' + label + ' 주요 지수</h3>'
        if rows:
            overview += '<div class="market-table-wrap"><table class="market-close-table"><thead><tr><th>시장</th><th>확정 종가</th><th>등락률</th><th>기준일</th></tr></thead><tbody>'
            for row in rows:
                overview += '<tr><th>' + esc(row['name']) + '</th><td>' + format(row['close'], ',.2f') + '</td><td>' + format(row['changePct'], '+.2f') + '%</td><td><a href="' + esc(row['source']) + '" target="_blank" rel="noopener noreferrer">' + esc(row['asOf']) + '</a></td></tr>'
            overview += '</tbody></table></div>'
        else:
            overview += '<p class="report-status">확정 종가·등락률: 공개 가능한 검증 자료가 아직 연결되지 않았습니다.</p>'
    for item in doc.get('distribution', []):
        overview += '<p>' + esc(item['name']) + ' · ' + esc(item['asOf']) + ' | 상승 ' + str(item['up']) + ' · 하락 ' + str(item['down']) + ' · 보합 ' + str(item['flat']) + '종목 · <a href="' + esc(item['source']) + '">출처</a></p>'
    if not doc.get('distribution'):
        overview += '<p class="report-status">코스피·코스닥 종목 분포: 공개 가능한 검증 자료가 있을 때 표시합니다.</p>'
    issues = ''
    for item in doc.get('issues', []):
        issues += '<div class="reading-item"><b class="fact-label">확인된 사실</b><p>' + esc(item['fact']) + '</p>'
        if item.get('interpretation'):
            issues += '<b class="fact-label">해석 · 작성자의 관점</b><p>' + esc(item['interpretation']) + '</p>'
        issues += '<a href="' + esc(item['source']) + '" target="_blank" rel="noopener noreferrer">원문 출처 읽기 ↗</a></div>'
    if not issues:
        issues = '<p>이 날짜의 주요 뉴스와 시장 반응은 아직 확인된 자료가 등록되지 않았습니다.</p><p>뉴스를 읽을 때는 발표된 사실과 그 영향에 대한 해석을 나누어 기록해 보세요. 이 학습판에서는 당일 시장의 움직임이나 원인을 추정하지 않습니다.</p>'
    study = '<div class="reading-item reading-featured"><h3>' + esc(lesson['term']) + '</h3><p>' + esc(lesson['explanation']) + '</p><p>' + esc(lesson['example']) + '</p><a href="' + esc(lesson['source']) + '" target="_blank" rel="noopener noreferrer">개념 참고 자료 · Investor.gov ↗</a></div>'
    controls = ''.join('<label class="quiz-option"><input type="radio" name="answer" value="%d" required><span>%s</span></label>' % (i, esc(opt)) for i, opt in enumerate(lesson['options']))
    quiz = '<div class="quiz"><form id="market-quiz" class="market-quiz" data-answer="%d"><fieldset><legend>%s</legend>%s</fieldset><div class="quiz-controls"><button class="button" type="submit">정답 확인</button><button class="button-ghost" type="reset">다시 풀기</button></div><div id="quiz-feedback" class="quiz-feedback" role="status" aria-live="polite" data-explanation="%s" hidden></div></form></div>' % (lesson['answer'], esc(lesson['question']), controls, esc(lesson['why']))
    sections = ''.join('<section><div class="eyebrow">SECTION %02d</div><h2>%s</h2>%s</section>' % (i + 1, TITLES[i], body) for i, body in enumerate([overview, issues, study, quiz]))
    note = '공개 학습판 · 확인되지 않은 시세를 포함하지 않습니다. 실시간 시세가 아닙니다.'
    if doc.get('edition') == 'archive-study':
        note = '이 날짜의 경제 공부를 위해 새로 작성한 공개 학습판입니다. 과거 시황을 재구성한 자료가 아니며, 기존 상세 원본은 별도로 보존됩니다.'
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f5ef"><title>%s | Market Daily</title><link rel="stylesheet" href="../../assets/style.css"></head><body><header class="site-header"><div class="container nav"><a class="brand" href="../../"><span class="brand-mark">◈</span>MARKET DAILY</a><nav class="navlinks" aria-label="메인 탐색"><a href="../../">대시보드</a><a href="../">리포트 아카이브</a></nav></div></header><main class="container"><section class="hero report-article"><div class="eyebrow">DAILY STUDY / %s</div><h1>%s</h1><p class="lead">%s</p><div class="notice">%s</div></section><article class="report-article">%s<p><a class="button" href="../">← 아카이브로 돌아가기</a></p></article></main><footer><div class="container footer-inner"><div>MARKET DAILY · RAY'S MARKET NOTE</div><div>개인 경제 공부와 시장 기록</div></div></footer><script src="../../assets/quiz.js" defer></script></body></html>''' % (esc(day), esc(day), esc(doc['headline']), esc(doc['summary']), esc(note), sections)

def build(root, day, backfill=False):
    manuscript = root / 'content/daily' / (day.isoformat() + '.json')
    target = root / 'reports/daily' / (day.isoformat() + '.html')
    doc = json.loads(manuscript.read_text()) if manuscript.exists() else make_doc(day, backfill)
    validate(doc)  # Fail before writing any unapproved input.
    if doc['date'] != day.isoformat():
        raise ValueError('Manuscript date mismatch')
    rendered = generate(doc)
    for p in (manuscript, target):
        p.parent.mkdir(parents=True, exist_ok=True)
    if not manuscript.exists():
        manuscript.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
    if not target.exists():
        target.write_text(rendered)
    # Rebuild only from this public-safe schema; never copy the private index.
    old_index = root / 'reports/index.json'
    previous = json.loads(old_index.read_text()) if old_index.exists() else []
    by_date = {r['date']: r for r in previous if r.get('url') == 'daily/' + r.get('date', '') + '.html' and (root / 'reports' / r['url']).is_file()}
    entries = []
    for path in sorted((root / 'content/daily').glob('*.json'), reverse=True):
        item = json.loads(path.read_text())
        if item.get('schemaVersion') != 4:
            continue
        validate(item)
        if (root / 'reports/daily' / (item['date'] + '.html')).exists():
            entries.append({'date': item['date'], 'title': item['headline'], 'summary': item['summary'], 'market': ['kr', 'us'], 'tags': ['공개 학습판', item['lesson']['term']], 'status': 'published', 'url': 'daily/' + item['date'] + '.html'})
    by_date.update({r['date']: r for r in entries})
    entries = sorted(by_date.values(), key=lambda r: r['date'], reverse=True)
    (root / 'reports/index.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
    if entries:
        # A real fallback page works without JavaScript, no redirect race.
        latest_day = next(r['date'] for r in entries if (root / 'content/daily' / (r['date'] + '.json')).exists())
        latest_doc = json.loads((root / 'content/daily' / (latest_day + '.json')).read_text())
        latest_html = (root / 'reports/daily' / (latest_day + '.html')).read_text()
        alias = latest_html.replace('href="../../', 'href="../').replace('src="../../', 'src="../')
        alias = alias.replace('href="../">리포트 아카이브', 'href="./">리포트 아카이브').replace('href="../">← 아카이브', 'href="./">← 아카이브')
        (root / 'reports/latest.html').write_text(alias)
        (root / 'data').mkdir(exist_ok=True)
        snapshot = {'reportDate': latest_day, 'indices': latest_doc.get('indices', []), 'distribution': latest_doc.get('distribution', [])}
        (root / 'data/public-market.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=date.fromisoformat)
    args = parser.parse_args()
    day = args.date or datetime.now(ZoneInfo('Asia/Seoul')).date()
    if not args.date and day.weekday() >= 5:
        print('Weekend: no scheduled study note')
        return
    build(ROOT, day)
    print('Built public study note:', day)

if __name__ == '__main__':
    main()
