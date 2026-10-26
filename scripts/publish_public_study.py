#!/usr/bin/env python3
"""Publish from fresh, disposable git worktrees; never rebase generated files."""
import os
import subprocess
import tempfile
from pathlib import Path

OUTPUTS = ['content/daily', 'reports/daily', 'reports/index.json', 'reports/latest.html', 'data/public-market.json']

def git(repo, *args, check=True):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError('Git publication operation failed; no remote overwrite attempted')
    return result

def publish(repo, attempts=3, before_push=None, build_args=()):
    repo = Path(repo).resolve()
    for attempt in range(attempts):
        git(repo, 'fetch', 'origin', 'main')
        head = git(repo, 'rev-parse', 'FETCH_HEAD').stdout.strip()
        with tempfile.TemporaryDirectory(prefix='market-public-') as tmp:
            work = Path(tmp) / 'checkout'
            git(repo, 'worktree', 'add', '--detach', str(work), head)
            try:
                result = subprocess.run([os.environ.get('PYTHON', 'python3'), 'scripts/build_public_reports.py', *build_args], cwd=work, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError('Public report validation/build failed; no publication')
                git(work, 'add', '--', *OUTPUTS)
                if git(work, 'diff', '--cached', '--quiet', check=False).returncode == 0:
                    return head
                git(work, 'commit', '-m', 'Publish public daily study')
                if before_push:
                    before_push(attempt)
                # Fast-forward only. On a race, discard this worktree and rebuild on current main.
                if git(work, 'push', 'origin', 'HEAD:refs/heads/main', check=False).returncode == 0:
                    return git(work, 'rev-parse', 'HEAD').stdout.strip()
            finally:
                git(repo, 'worktree', 'remove', '--force', str(work), check=False)
    raise RuntimeError('Publication could not fast-forward; existing remote reports are preserved')

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run through the publication workflow; no local checkout is modified')
    print('Published public revision:', publish(Path(__file__).resolve().parents[1]))
