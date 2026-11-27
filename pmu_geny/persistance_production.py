"""Restaurer un instantané pmu-data et publier ses changements sans écrasement."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REF = 'refs/heads/pmu-data'


class ConflitPersistance(RuntimeError):
    """Deux exécutions ont modifié les mêmes fichiers de données."""


def git(root, *args, **kwargs):
    return subprocess.check_output(['git', '-C', str(root), *args], **kwargs)


def distant(root):
    git(root, 'fetch', '--no-tags', 'origin', REF)
    return git(root, 'rev-parse', 'FETCH_HEAD').decode().strip()


def marqueur(cache):
    return cache.with_name(f'.{cache.name}.pmu-data-tree')


def retenir(cache, tree):
    target = marqueur(cache)
    temp = target.with_suffix('.tmp')
    temp.write_text(tree + '\n', encoding='ascii')
    temp.replace(target)


def restaurer(cache, root=ROOT):
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError('La restauration pmu-data exige un cache vide')
    revision = distant(root)
    with subprocess.Popen(['git', '-C', str(root), 'archive', revision],
                          stdout=subprocess.PIPE) as archive:
        subprocess.run(['tar', '-x', '-C', str(cache)], stdin=archive.stdout, check=True)
        if archive.wait():
            raise RuntimeError('Extraction pmu-data interrompue')
    retenir(cache, git(root, 'rev-parse', f'{revision}^{{tree}}').decode().strip())
    print('PMU_DATA_RESTAURE', revision, flush=True)
    return revision


def publier(cache, root=None, *, chemins=(), message='PMU : donnees et controles de production'):
    root = root or ROOT
    cache = Path(cache).resolve()
    if not cache.is_dir() or not any(cache.iterdir()):
        return 'AUCUNE_DONNEE'
    base = marqueur(cache).read_text(encoding='ascii').strip()
    paths = [str(path) for path in chemins if (cache / path).exists()] if chemins else ['.']
    if not paths:
        return 'DEJA_SAUVEGARDE'

    with tempfile.TemporaryDirectory(prefix='pmu-index-') as directory:
        git_dir = git(root, 'rev-parse', '--absolute-git-dir').decode().strip()
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(directory) / 'index')}

        def index(*args):
            return git(cache, f'--git-dir={git_dir}', f'--work-tree={cache}', *args, env=env)

        index('read-tree', base)
        index('add', '--ignore-removal', '-f', '--', *paths)
        local = index('write-tree').decode().strip()
        if local == base:
            return 'DEJA_SAUVEGARDE'
        remote = distant(root)
        for attempt in range(3):
            # Les fichiers inchangés dans le cache ne participent pas à l'écriture.
            # Toute modification concurrente du même fichier est explicite.
            index('read-tree', '--reset', remote)
            index('read-tree', '-im', base, remote, local)
            conflicts = index('diff', '--cached', '--name-only', '--diff-filter=U', '-z', remote)
            if conflicts:
                names = ', '.join(os.fsdecode(path) for path in conflicts.split(b'\0') if path)
                raise ConflitPersistance(f'CONFLIT_PMU_DATA : {names}')
            merged = index('write-tree').decode().strip()
            if merged == git(root, 'rev-parse', f'{remote}^{{tree}}').decode().strip():
                retenir(cache, local)
                return 'DEJA_SAUVEGARDE'
            commit = git(root, 'commit-tree', merged, '-p', remote, '-m', message).decode().strip()
            try:
                git(root, 'push', 'origin', f'{commit}:{REF}')
            except subprocess.CalledProcessError:
                new_remote = distant(root)
                if attempt == 2 or new_remote == remote:
                    raise
                remote = new_remote
            else:
                # Garder la vue du producteur pour les fichiers lus mais non modifiés.
                retenir(cache, local)
                return 'SAUVEGARDE'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--restaurer', action='store_true')
    args = parser.parse_args()
    if args.restaurer:
        restaurer(args.cache)
    else:
        print(publier(args.cache), flush=True)
