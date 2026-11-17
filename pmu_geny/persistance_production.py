"""Sauvegarde de production sous le verrou GitHub partagé, sans force push."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def publier(cache, root=None):
    cache = Path(cache).resolve()
    if not cache.exists() or not any(p.is_file() for p in cache.rglob('*')):
        return 'AUCUNE_DONNEE'
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    def git(*args, cwd=root):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()
    git('fetch', '--no-tags', 'origin', 'pmu-data')
    with tempfile.TemporaryDirectory(prefix='pmu-production-') as tmp:
        target = Path(tmp)/'data'
        git('worktree', 'add', '--detach', str(target), 'origin/pmu-data')
        try:
            shutil.copytree(cache, target, dirs_exist_ok=True)
            git('add', '-A', cwd=target)
            unchanged = subprocess.run(['git','diff','--cached','--quiet'], cwd=target).returncode == 0
            if unchanged:
                return 'DEJA_SAUVEGARDE'
            git('commit', '-m', 'PMU : donnees et controles de production', cwd=target)
            git('push', 'origin', 'HEAD:refs/heads/pmu-data', cwd=target)
        finally:
            git('worktree', 'remove', '--force', str(target))
    return 'SAUVEGARDE'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    print(publier(parser.parse_args().cache))
