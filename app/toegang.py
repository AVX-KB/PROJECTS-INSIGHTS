"""
Toegang
=======
Eén gedeeld wachtwoord voor de hele pagina. Bedoeld om toevallige bezoekers
buiten te houden, niet als echte beveiliging: er zijn geen accounts, en zonder
TLS gaat het wachtwoord leesbaar over het netwerk.

Instellen in .env (niet in git), met de waarde uit KeePass:

  TOEGANGSWACHTWOORD=<uit KeePass>

Staat er geen wachtwoord, dan gaat alles op slot in plaats van open.

De sleutel waarmee de sessiecookie wordt ondertekend, is afgeleid van het
wachtwoord. Daardoor is er geen tweede secret nodig, blijft iedereen ingelogd
na een herstart, en is iedereen uitgelogd zodra het wachtwoord verandert.
"""

import hashlib
import hmac
import os
import time
from datetime import timedelta

from flask import jsonify, redirect, request, send_from_directory, session

SESSIE_SLEUTEL = 'ingelogd'
INGELOGD_BLIJVEN = timedelta(days=30)

# Zonder inloggen bereikbaar: het inlogscherm en wat het nodig heeft.
OPEN_PADEN = {'/login', '/health', '/app.css'}
OPEN_MAPPEN = ('/stylesheet/',)


def _wachtwoord():
    return os.getenv('TOEGANGSWACHTWOORD', '')


def is_ingesteld():
    return bool(_wachtwoord())


def klopt(invoer):
    wachtwoord = _wachtwoord()
    if not wachtwoord:
        return False
    # compare_digest: de reactietijd verraadt niet hoeveel tekens er klopten.
    return hmac.compare_digest(wachtwoord.encode(), (invoer or '').encode())


def bewaak(app):
    """Zet de sessie-instellingen, de inlogroutes en de controle op elke aanvraag."""
    app.secret_key = hashlib.sha256(
        b'projects-insights-sessie:' + _wachtwoord().encode()).hexdigest()
    app.permanent_session_lifetime = INGELOGD_BLIJVEN
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_NAME='projects_insights')

    @app.before_request
    def _controleer():
        pad = request.path
        if pad in OPEN_PADEN or pad.startswith(OPEN_MAPPEN):
            return None
        if session.get(SESSIE_SLEUTEL):
            return None
        if pad.startswith('/api/'):
            return jsonify({'fout': 'Niet ingelogd. Ververs de pagina.'}), 401
        return redirect('/login')

    @app.get('/login')
    def _login_scherm():
        return send_from_directory(app.static_folder, 'login.html')

    @app.post('/login')
    def _login():
        if not is_ingesteld():
            return redirect('/login?fout=niet-ingesteld')
        if not klopt(request.form.get('wachtwoord')):
            time.sleep(1)  # raden kost tijd
            return redirect('/login?fout=onjuist')
        session.clear()
        session[SESSIE_SLEUTEL] = True
        session.permanent = True
        return redirect('/')

    @app.post('/logout')
    def _logout():
        session.clear()
        return redirect('/login')
