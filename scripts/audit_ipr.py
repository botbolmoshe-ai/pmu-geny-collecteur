"""Rejouer l'IPR sur des checkpoints Git antérieurs à la course, en lecture seule."""
import argparse
from collections import Counter
from datetime import timedelta
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from pmu_geny.echeances_production import PARIS, instant, lire, sauver
from pmu_geny.identites_chevaux import IndexGeny
from pmu_geny.ipr import VERSION, calculer
from pmu_geny.ipr_prospectif import podium_verifie
from pmu_geny.liaison_chevaux_v22 import etablir
from pmu_geny.sync_google_sheets import course_info


def archive(root, ref, cache, folders):
    with subprocess.Popen(['git', 'archive', ref, *folders], cwd=root, stdout=subprocess.PIPE) as proc:
        subprocess.run(['tar', '-xf', '-', '-C', str(cache)], stdin=proc.stdout, check=True)
        if proc.wait():
            raise RuntimeError(f'Impossible de lire {ref}')


def audit(root, ref, requested, now):
    rejects = Counter()
    details = {}
    checkpoints = []
    with TemporaryDirectory() as final:
        archive(root, ref, final, ['arrivees'])
        for requested_time in sorted(requested):
            revision, commit = subprocess.check_output(
                ['git', 'log', '-1', '--first-parent', '--format=%H %cI', f'--before={requested_time.isoformat()}', ref],
                cwd=root, text=True).split()
            cutoff = instant(commit)
            if not cutoff or cutoff > requested_time:
                raise ValueError('Checkpoint postérieur à la coupure')
            day = cutoff.astimezone(PARIS).date().isoformat()
            checkpoints.append({'revision': revision, 'controle_utc': cutoff.isoformat()})
            with TemporaryDirectory() as checkpoint:
                cache = Path(checkpoint)
                folders = ['partants_actuels', 'sources_pmu', 'sources_geny', 'historiques',
                           'historiques_partiels', 'orchestration', 'etat_persistant.json', 'manifestes']
                present = subprocess.check_output(['git', 'ls-tree', '--name-only', revision], cwd=root, text=True).splitlines()
                archive(root, revision, cache, [folder for folder in folders if folder in present])
                index = IndexGeny(cache)
                for path in sorted((cache/'partants_actuels').glob(f'{day}_R*C*.json')):
                    key = path.stem
                    if key in details:
                        continue
                    doc = lire(path)
                    code = doc.get('course')
                    course = course_info(cache, code, day)
                    depart = instant(course.get('depart'))
                    observed = instant(doc.get('capture_utc'))
                    if (doc.get('source') != 'PMU_API_PARTICIPANTS' or not depart or not observed
                            or not observed <= cutoff < depart or cutoff-observed > timedelta(minutes=30)):
                        rejects['RELEVE_PREDEPART_NON_ATTESTE_OU_PERIME'] += 1
                        continue
                    podium = podium_verifie(lire(Path(final)/'arrivees'/path.name), key, depart, now)
                    if not podium:
                        rejects['ARRIVEE_PMU_NON_ADMISSIBLE'] += 1
                        continue
                    profiles = doc['chevaux']
                    links = etablir(cache, course, [{'numero': n, **horse} for n, horse in profiles.items()], index=index)
                    score = calculer(course, profiles, links, observed, cutoff)
                    eligible = score['partants']
                    horses = sum(score['chevaux'][n]['ipr_score'] is not None for n in eligible)
                    details[key] = {'checkpoint': revision, 'partants': len(eligible), 'notes': horses,
                                    'chevaux_podium': len(set(score['top3']) & podium) if score['top3'] else None}
    selected = [row['chevaux_podium'] for row in details.values() if row['chevaux_podium'] is not None]
    return {'nature': 'REJEU_SUR_ARCHIVES_PREDEPART_NON_PROSPECTIF', 'version': VERSION,
            'controle_utc': now.isoformat(), 'checkpoints': checkpoints, 'rejets_par_checkpoint': dict(rejects),
            'courses': details, 'partants': sum(r['partants'] for r in details.values()),
            'partants_notes': sum(r['notes'] for r in details.values()), 'courses_evaluables': len(selected),
            'moyenne_sur_3': sum(selected)/len(selected) if selected else None,
            'exact_3_sur_3': selected.count(3)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='origin/pmu-data')
    parser.add_argument('--checkpoint', action='append', type=instant, required=True)
    parser.add_argument('--arrete', type=instant, required=True)
    parser.add_argument('--sortie', type=Path, required=True)
    args = parser.parse_args()
    if args.arrete is None or any(stamp is None or stamp > args.arrete for stamp in args.checkpoint):
        parser.error('Instants horodatés et antérieurs à la clôture requis')
    sauver(args.sortie, audit(Path.cwd(), args.ref, args.checkpoint, args.arrete))
