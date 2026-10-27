#!/usr/bin/env python3
"""Two live collection rounds and loopback-only UI checks. No prices in output.

Requires a local config outside any git checkout. Explicit private grants must
cover collection, temporary storage, display and derived returns. Never deploys,
commits, creates public artifacts, or enables public provider settings.
"""
import argparse
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import build_public_reports as builder
from market_close import collect_private

ROOT = Path(__file__).resolve().parents[1]
BANNER = '비공개 연결 검증 · 재배포 금지 · 실제 확정 종가'


def preview(root, market, now):
    """Only accepts the private collector schema; never calls public build()."""
    if any(row.get('publication', {}).get('status') != 'private_only' for row in market['indices']):
        raise ValueError('Private observations required')
    for name in ('index.html', 'assets', 'reports'):
        source, target = ROOT / name, root / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
    page = root / 'index.html'
    page.write_text(page.read_text().replace('<body>', '<body><div class="notice">' + BANNER + '</div>'))
    # Only this disposable loopback copy accepts private observations.
    script = root / 'assets/market.js'
    script.write_text(script.read_text().replace("status==='approved_public'", "status==='private_only'"))
    latest = root / 'assets/latest.js'
    latest.write_text(latest.read_text().replace('공개 학습판', '비공개 검증판'))
    day = now.astimezone(ZoneInfo('Asia/Seoul')).date()
    doc = builder.make_doc(day)
    doc.update(indices=market['indices'], marketStatus=market['marketStatus'], previewAudience='private')
    html = builder.generate(doc, audience='private').replace('<body>', '<body><div class="notice">' + BANNER + '</div>')
    html = html.replace('공개 학습판 · 확인되지 않은 시세를 포함하지 않습니다.', BANNER + '.')
    target = root / 'reports/daily' / (day.isoformat() + '.html')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html)
    alias = html.replace('href="../../', 'href="../').replace('src="../../', 'src="../')
    (root / 'reports/latest.html').write_text(alias)
    index = root / 'reports/index.json'
    entries = json.loads(index.read_text())
    entries = [e for e in entries if e['date'] != day.isoformat()]
    entries.insert(0, {'date':day.isoformat(), 'title':BANNER, 'summary':'비공개 시험', 'market':['kr','us'], 'tags':['비공개'], 'status':'published', 'url':'daily/' + target.name})
    index.write_text(json.dumps(entries, ensure_ascii=False))
    (root / 'data').mkdir(exist_ok=True)
    (root / 'data/public-market.json').write_text(json.dumps(market, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--rounds', type=int, default=2, choices=(1, 2))
    args = parser.parse_args()
    config_path = args.config.resolve()
    if any((p / '.git').exists() for p in (config_path.parent, *config_path.parents)):
        raise ValueError('Private config must be outside git')
    if os.environ.get('GITHUB_ACTIONS'):
        raise ValueError('Run locally, never in public Actions')
    cfg = json.loads(config_path.read_text())
    logging.disable(logging.CRITICAL)
    summaries = []
    with tempfile.TemporaryDirectory(prefix='market-private-') as tmp:
        os.chmod(tmp, 0o700)
        roots = []
        for n in range(args.rounds):
            now = datetime.now(timezone.utc)
            # Third-party libraries can print URLs, exceptions or values.
            # Discard their diagnostics; return only our finite status codes.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                market = collect_private(cfg, now=now)
            root = Path(tmp) / str(n)
            root.mkdir(mode=0o700)
            preview(root, market, now)
            roots.append(str(root))
            summaries.append({'checkedAt':market['checkedAt'], 'indices':[
                {'id':s['id'], 'expectedAsOf':s.get('expectedAsOf'), 'status':s['status']}
                for s in market['marketStatus']]})
        check = subprocess.run(['node', str(ROOT / 'tests/private-market-ui.cjs'), *roots], capture_output=True, text=True)
        ui = json.loads(check.stdout) if check.returncode == 0 else {'status':'failed_redacted'}
    print(json.dumps({'rounds':summaries, 'ui':ui, 'publicDataWritten':False, 'temporaryDataRemoved':True}, ensure_ascii=False, indent=2))
    return 0 if ui.get('status') == 'passed' and all(s['status'] == 'verified' for r in summaries for s in r['indices']) else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"private_test_failed_redacted","publicDataWritten":false}')
        raise SystemExit(1)
