"""
Projects Insights - webserver
=============================
Eén container doet twee dingen:

  1. een paar keer per dag een momentopname van het GitHub-bord in Postgres zetten
     (een achtergrondthread, op de tijdstippen uit SNAPSHOT_TIJDEN in TIJDZONE)
  2. de pagina en de API uitserveren waar de grafieken uit lezen,
     achter één gedeeld wachtwoord (toegang.py)

Elke vraag aan het bord is een eigen endpoint onder /api/vragen/. Een nieuwe
vraag is dus een functie in analyse.py plus een endpoint hier, en een blok in
de pagina.
"""

import logging
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, send_from_directory
from waitress import serve

import analyse
import github
import opslag
import toegang

HIER = os.path.dirname(os.path.abspath(__file__))

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GITHUB_ORG = os.getenv('GITHUB_ORG', '')
GITHUB_PROJECT = os.getenv('GITHUB_PROJECT', '0')
SPRINT_VELD = os.getenv('SPRINT_VELD', 'WEEK')
STATUS_VELD = os.getenv('STATUS_VELD', 'Status')
AFGEROND_STATUSSEN = os.getenv('AFGEROND_STATUSSEN', 'Done').split(',')
# Tijdstippen van de momentopnamen, HH:MM gescheiden door komma's.
SNAPSHOT_TIJDEN = [t.strip() for t in os.getenv('SNAPSHOT_TIJDEN', '06:00,12:00,18:00').split(',') if t.strip()]
POORT = int(os.getenv('POORT', '8080'))

# Handmatig bijwerken mag niet vaker dan dit; GitHub telt elke aanvraag mee.
MIN_SECONDEN_TUSSEN_HANDMATIG = 120
# Na een mislukte geplande poging wachten we dit lang voor de volgende.
WACHT_NA_FOUT = 15 * 60

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('projects-insights')

app = Flask(__name__, static_folder=os.path.join(HIER, 'static'), static_url_path='')
app.json.sort_keys = False
toegang.bewaak(app)

_slot = threading.Lock()
_toestand = {'laatste_poging': 0.0, 'laatste_fout': None, 'laatste_fout_op': None}


def neem_momentopname():
    """Bord uitlezen en wegschrijven. Geeft het id van de momentopname terug."""
    with _slot:
        _toestand['laatste_poging'] = time.time()
        try:
            bord = github.haal_bord(GITHUB_TOKEN, GITHUB_ORG, GITHUB_PROJECT, SPRINT_VELD, STATUS_VELD)
            conn = opslag.verbinding()
            try:
                momentopname_id = opslag.sla_momentopname_op(conn, bord)
            finally:
                conn.close()
        except Exception as fout:
            _toestand['laatste_fout'] = str(fout)
            _toestand['laatste_fout_op'] = datetime.now().isoformat(timespec='minutes')
            log.error('Momentopname mislukt: %s', fout)
            raise
        _toestand['laatste_fout'] = None
        _toestand['laatste_fout_op'] = None
        log.info('Momentopname %s: %d items, %d iteraties',
                 momentopname_id, len(bord['items']), len(bord['iteraties']))
        return momentopname_id


def planner():
    """Achtergrondthread: schema aanmaken, daarna elke minuut kijken of het tijd is."""
    while True:
        try:
            opslag.maak_schema()
            break
        except Exception as fout:
            _toestand['laatste_fout'] = f'Database niet bereikbaar: {fout}'
            log.error('Schema aanmaken mislukt, opnieuw over een minuut: %s', fout)
            time.sleep(60)

    while True:
        try:
            if _toestand['laatste_fout'] and time.time() - _toestand['laatste_poging'] < WACHT_NA_FOUT:
                pass
            else:
                conn = opslag.verbinding()
                try:
                    nodig = opslag.geplande_momentopname_nodig(conn, SNAPSHOT_TIJDEN)
                finally:
                    conn.close()
                if nodig:
                    neem_momentopname()
        except Exception:
            pass  # al gelogd in neem_momentopname, of de database is even weg
        time.sleep(60)


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

@app.get('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.get('/health')
def health():
    return {'ok': True}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get('/api/status')
def status():
    antwoord = {
        'bord': {
            'org': GITHUB_ORG,
            'nummer': GITHUB_PROJECT,
            'url': f'https://github.com/orgs/{GITHUB_ORG}/projects/{GITHUB_PROJECT}',
            'sprint_veld': SPRINT_VELD,
            'status_veld': STATUS_VELD,
            'afgerond_statussen': [s.strip() for s in AFGEROND_STATUSSEN if s.strip()],
        },
        'snapshot_tijden': SNAPSHOT_TIJDEN,
        'laatste_fout': _toestand['laatste_fout'],
        'laatste_fout_op': _toestand['laatste_fout_op'],
        'momentopnamen': None,
    }
    try:
        conn = opslag.verbinding()
        try:
            overzicht = opslag.overzicht_momentopnamen(conn)
            laatste = opslag.laatste_momentopname(conn)
        finally:
            conn.close()
        antwoord['momentopnamen'] = {
            'aantal': overzicht['aantal'],
            'reconstructies': overzicht['reconstructies'],
            'eerste': overzicht['eerste'].isoformat(timespec='minutes') if overzicht['eerste'] else None,
            'laatste': overzicht['laatste'].isoformat(timespec='minutes') if overzicht['laatste'] else None,
        }
        if laatste:
            antwoord['bord']['titel'] = laatste['project_titel']
    except Exception as fout:
        antwoord['laatste_fout'] = f'Database niet bereikbaar: {fout}'
    return jsonify(antwoord)


@app.post('/api/momentopname')
def momentopname_nu():
    wacht = MIN_SECONDEN_TUSSEN_HANDMATIG - (time.time() - _toestand['laatste_poging'])
    if wacht > 0:
        return jsonify({'fout': f'Net bijgewerkt. Probeer het over {int(wacht) + 1} seconden opnieuw.'}), 429
    try:
        momentopname_id = neem_momentopname()
    except Exception as fout:
        return jsonify({'fout': str(fout)}), 502
    return jsonify({'id': momentopname_id})


@app.get('/api/vragen/niet-afgerond')
def vraag_niet_afgerond():
    try:
        conn = opslag.verbinding()
        try:
            return jsonify(analyse.niet_afgerond(conn, AFGEROND_STATUSSEN))
        finally:
            conn.close()
    except Exception as fout:
        log.exception('Vraag niet-afgerond mislukt')
        return jsonify({'fout': f'Kon de gegevens niet ophalen: {fout}'}), 503


if __name__ == '__main__':
    threading.Thread(target=planner, name='planner', daemon=True).start()
    log.info('Projects Insights luistert op poort %d (bord %s/projects/%s)', POORT, GITHUB_ORG, GITHUB_PROJECT)
    if not toegang.is_ingesteld():
        log.warning('Geen TOEGANGSWACHTWOORD in de .env: de pagina blijft op slot.')
    serve(app, host='0.0.0.0', port=POORT)
