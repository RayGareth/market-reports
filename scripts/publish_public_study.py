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

def publish(repo, attempts=3, before_push=None, build_args=(), region=None):
    repo = Path(repo).resolve()
    for attempt in range(attempts):
        git(repo, 'fetch', 'origin', 'main')
        head = git(repo, 'rev-parse', 'FETCH_HEAD').stdout.strip()
        with tempfile.TemporaryDirectory(prefix='market-public-') as tmp:
            work = Path(tmp) / 'checkout'
            git(repo, 'worktree', 'add', '--detach', str(work), head)
            try:
                if region:
                    command = ['scripts/refresh_public_market.py', '--region', region]
                else:
                    command = ['scripts/build_public_reports.py', *build_args]
                result = subprocess.run([os.environ.get('PYTHON', 'python3'), *command],
                                        cwd=work, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError('Public report validation/build failed; no publication')
                # U.S. refreshes may also create a dated revision and archive link.
                outputs = [path for path in OUTPUTS if (work / path).exists()]
                if outputs:
                    git(work, 'add', '--', *outputs)
                if git(work, 'diff', '--cached', '--quiet', check=False).returncode == 0:
                    return head
                message = 'Refresh public U.S. closes' if region == 'us' else 'Publish public daily study'
                git(work, 'commit', '-m', message)
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', required=True, choices=('kr', 'us'))
    print('Published public revision:', publish(Path(__file__).resolve().parents[1],
                                               region=parser.parse_args().region))
