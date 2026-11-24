"""Vérifier les parcours de l'interface Streamlit sur le registre réel, en lecture seule."""
import json
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest


def main():
    app = AppTest.from_file(str(Path('dashboard/app.py')), default_timeout=90)
    app.secrets['app_password'] = 'test-interne-github-actions'
    app.secrets['google_service_account'] = json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    app.secrets['spreadsheet_id'] = os.environ['GOOGLE_SHEETS_ID']
    app.session_state.authenticated = True
    app.run()
    if app.exception or app.error or not app.radio:
        raise RuntimeError('Échec de lecture du registre Streamlit')
    for page in ('Courses', 'Résultats', 'Performance', 'Qualité'):
        app.radio[0].set_value(page).run()
        if app.exception or app.error:
            raise RuntimeError(f'Échec de rendu Streamlit : {page}')
    for mode in ('Registre actuel', 'Relevés historiques'):
        app.selectbox(key='quality_mode').set_value(mode).run()
        if app.exception or app.error:
            raise RuntimeError(f'Échec de rendu Streamlit : {mode}')
    print('STREAMLIT_REGISTRE_REEL_VERIFIE=1')


if __name__ == '__main__':
    main()
