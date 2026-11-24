"""
Vraag: hoeveel taken worden er per iteratie niet afgerond?
==========================================================
Per afgelopen iteratie X kijken we naar de **eindstand**: de laatste
momentopname binnen de iteratie. Met momentopnamen om 06:00, 12:00 en 18:00
is dat 18:00 op de laatste dag; wat daarna nog wordt afgerond, telt als
"na afloop afgerond".

  gepland        items die in de eindstand op X stonden
  afgerond       daarvan met een status uit AFGEROND_STATUSSEN
  niet afgerond  de rest, ingedeeld naar wat er daarna mee gebeurde:

    doorgeschoven       staat nu op een andere iteratie
    blijven staan       staat nu nog op X en is nog steeds niet afgerond
    na afloop afgerond  staat nu nog op X en is inmiddels wel afgerond
    uit iteratie        heeft nu geen iteratie meer, of staat niet meer op het bord

"Nu" is de laatste momentopname.

Iteraties die eindigden vóór de eerste momentopname hebben geen eindstand.
Daarvan tonen we alleen wat we nu kunnen zien: items die nu nog op X staan en
niet afgerond zijn ("blijven staan"). Wat toen al was doorgeschoven, is niet
meer terug te halen. Die iteraties krijgen `volledig: False`.
"""

from datetime import timedelta

import opslag

CATEGORIEEN = ('doorgeschoven', 'blijven_staan', 'na_afloop_afgerond', 'uit_iteratie')


def _afgerond(rij, afgerond_statussen):
    return (rij.get('status') or '').strip().lower() in afgerond_statussen


def _taak(rij, categorie, nu_rij, titels):
    nu_iteratie = (nu_rij or {}).get('iteratie_id')
    return {
        'nummer': rij['nummer'],
        'titel': rij['titel'],
        'url': rij['url'],
        'repo': rij['repo'],
        'status_eind': rij['status'],
        'status_nu': (nu_rij or {}).get('status'),
        'iteratie_nu': titels.get(nu_iteratie) if nu_iteratie else None,
        'categorie': categorie,
    }


def _categorie(iteratie_id, nu_rij, afgerond_statussen):
    if not nu_rij or not nu_rij['iteratie_id']:
        return 'uit_iteratie'
    if nu_rij['iteratie_id'] != iteratie_id:
        return 'doorgeschoven'
    return 'na_afloop_afgerond' if _afgerond(nu_rij, afgerond_statussen) else 'blijven_staan'


def niet_afgerond(conn, afgerond_statussen):
    afgerond_statussen = {s.strip().lower() for s in afgerond_statussen if s.strip()}
    vandaag, _ = opslag.nu_lokaal(conn)
    laatste = opslag.laatste_momentopname(conn)
    alle_iteraties = opslag.iteraties(conn)
    titels = {it['iteratie_id']: it['titel'] for it in alle_iteraties}

    if not laatste:
        return {'iteraties': [], 'lopend': None, 'nu': None}

    nu = opslag.stand(conn, laatste['id'])
    standen = {laatste['id']: nu}

    resultaat, lopend = [], None
    for it in alle_iteraties:
        basis = {
            'iteratie_id': it['iteratie_id'],
            'titel': it['titel'],
            'startdatum': it['startdatum'].isoformat(),
            'laatste_dag': (it['einddatum'] - timedelta(days=1)).isoformat(),
            'duur_dagen': it['duur_dagen'],
        }

        if it['startdatum'] > vandaag:
            continue  # nog niet begonnen

        if it['einddatum'] > vandaag:
            # Lopende iteratie: alleen de stand van nu.
            op_x = [r for r in nu.values() if r['iteratie_id'] == it['iteratie_id']]
            klaar = sum(1 for r in op_x if _afgerond(r, afgerond_statussen))
            lopend = {**basis, 'gepland': len(op_x), 'afgerond': klaar,
                      'open': len(op_x) - klaar,
                      'dagen_over': (it['einddatum'] - vandaag).days}
            continue

        eind = opslag.eindstand_momentopname(conn, it['startdatum'], it['einddatum'])
        if eind:
            if eind['id'] not in standen:
                standen[eind['id']] = opslag.stand(conn, eind['id'])
            op_x = [r for r in standen[eind['id']].values() if r['iteratie_id'] == it['iteratie_id']]
            volledig = True
        else:
            op_x = [r for r in nu.values() if r['iteratie_id'] == it['iteratie_id']]
            volledig = False

        aantallen = dict.fromkeys(CATEGORIEEN, 0)
        taken, klaar = [], 0
        for rij in op_x:
            if _afgerond(rij, afgerond_statussen):
                klaar += 1
                continue
            nu_rij = nu.get(rij['item_id'])
            categorie = _categorie(it['iteratie_id'], nu_rij, afgerond_statussen) if volledig else 'blijven_staan'
            aantallen[categorie] += 1
            taken.append(_taak(rij, categorie, nu_rij, titels))

        niet = len(op_x) - klaar
        resultaat.append({
            **basis,
            'volledig': volledig,
            'eindstand_op': eind['genomen_op'].isoformat(timespec='minutes') if eind else None,
            # Zonder eindstand weten we niet hoeveel er gepland was.
            'gepland': len(op_x) if volledig else None,
            'afgerond': klaar if volledig else None,
            'niet_afgerond': niet,
            'percentage': round(100 * niet / len(op_x)) if volledig and op_x else None,
            'categorieen': aantallen,
            'taken': sorted(taken, key=lambda t: (CATEGORIEEN.index(t['categorie']), t['repo'] or '', t['nummer'] or 0)),
        })

    return {
        'iteraties': resultaat,
        'lopend': lopend,
        'nu': laatste['genomen_op'].isoformat(timespec='minutes'),
    }
