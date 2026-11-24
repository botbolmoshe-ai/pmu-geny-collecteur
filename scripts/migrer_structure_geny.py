"""Sauvegarde chiffrée puis migration du même instantané Sheets."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pmu_geny.moteur_sheets import SynchroniseurSheets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sauvegarde', type=Path, required=True)
    parser.add_argument('--appliquer', action='store_true')
    args = parser.parse_args()
    fingerprint = args.sauvegarde / 'sha256'
    engine = SynchroniseurSheets(args.archive, os.environ['GOOGLE_SHEETS_ID'])

    def sauvegarder(values):
        snapshot = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()
        digest = hashlib.sha256(snapshot).hexdigest()
        if args.appliquer:
            if digest != fingerprint.read_text().strip():
                raise ValueError('Le registre a changé depuis la sauvegarde')
            return
        args.sauvegarde.mkdir(parents=True, exist_ok=True)
        info = json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
        public = serialization.load_pem_private_key(info['private_key'].encode(), None).public_key()
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        wrapped = public.encrypt(key, padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        (args.sauvegarde / 'cle.rsa').write_bytes(wrapped)
        (args.sauvegarde / 'historique.aesgcm').write_bytes(nonce + AESGCM(key).encrypt(nonce, snapshot, None))
        fingerprint.write_text(digest + '\n')

    try:
        print(json.dumps(engine.migrer_structure_geny(sauvegarder, appliquer=args.appliquer),
                         ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        engine.fermer()


if __name__ == '__main__':
    main()
