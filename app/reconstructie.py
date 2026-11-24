"""
Eindstand van een iteratie reconstrueren
========================================
Voor een iteratie die eindigde vóór de eerste momentopname. GitHub bewaart
niet op welke iteratie een taak stond, dus dat moet iemand opgeven: de
nummers van de taken die op het einde op die iteratie stonden en daarna zijn
verschoven. Taken die in de eerste echte momentopname nog op de iteratie
staan, komen er vanzelf bij.

De **status** op het einde komt wel van GitHub: uit de statusgeschiedenis van
elke taak, op de laatste dag van de iteratie om het laatste tijdstip uit
SNAPSHOT_TIJDEN. Een taak die toen nog niet op het bord stond, valt af.

Het resultaat is een momentopname met bron `reconstructie`. In de grafiek
staat die iteratie als "gereconstrueerd".

Zonder --uitvoeren laat het script alleen zien wat het zou wegschrijven.

Gebruik, in de draaiende container:

  docker exec AVX-AI-PROJECTS-INSIGHTS python reconstructie.py "WEEK 47" 39 43 44
  docker exec AVX-AI-PROJECTS-INSIGHTS python reconstructie.py "WEEK 47" 39 43 44 --uitvoeren
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

import github
import opslag


def _tijd(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00'))


def main():
    parser = argparse.ArgumentParser(description='Eindstand van een afgelopen iteratie reconstrueren.')
    parser.add_argument('iteratie', help='titel van de iteratie, letterlijk, bijvoorbeeld "WEEK 47"')
    parser.add_argument('nummers', nargs='+', type=int,
                        help='issuenummers van de taken die op het einde op deze iteratie stonden '
                             'en daarna zijn verschoven')
    parser.add_argument('--toelichting', help='waarom en door wie; staat bij de iteratie in de grafiek')
    parser.add_argument('--uitvoeren', action='store_true', help='echt wegschrijven')
    args = parser.parse_args()

    token = os.getenv('GITHUB_TOKEN', '')
    tijden = [t.strip() for t in os.getenv('SNAPSHOT_TIJDEN', '06:00,12:00,18:00').split(',') if t.strip()]
    conn = opslag.verbinding()
    opslag.maak_schema()

    gevonden = opslag.iteratie_op_titel(conn, args.iteratie)
    if len(gevonden) != 1:
        sys.exit(f'Iteratie "{args.iteratie}" {"niet gevonden" if not gevonden else "komt vaker voor"}.')
    it = gevonden[0]
    laatste_dag = it['einddatum'] - timedelta(days=1)
    if it['einddatum'] > date.today():
        sys.exit(f'{it["titel"]} is nog niet afgelopen.')

    bestaand = opslag.eindstand_momentopname(conn, it['startdatum'], it['einddatum'])
    if bestaand:
        soort = 'een reconstructie' if bestaand['bron'] == 'reconstructie' else 'een echte momentopname'
        sys.exit(f'{it["titel"]} heeft al een eindstand ({soort} van {bestaand["genomen_op"]:%d-%m %H:%M}). '
                 'Er wordt niets weggeschreven.')

    moment = opslag.lokaal_moment(conn, laatste_dag, max(tijden))
    basis = opslag.eerste_echte_momentopname(conn)
    if not basis:
        sys.exit('Er is nog geen echte momentopname om op te bouwen.')
    stand = opslag.stand(conn, basis['id'])

    per_nummer = {}
    for rij in stand.values():
        if rij['nummer'] is not None:
            per_nummer.setdefault(rij['nummer'], []).append(rij)
    kandidaten = {r['item_id']: (r, 'stond er nog op') for r in stand.values()
                  if r['iteratie_id'] == it['iteratie_id']}
    for nummer in args.nummers:
        rijen = per_nummer.get(nummer, [])
        if len(rijen) != 1:
            sys.exit(f'#{nummer} {"staat niet op het bord" if not rijen else "komt in meer repo s voor"}.')
        kandidaten.setdefault(rijen[0]['item_id'], (rijen[0], 'opgegeven als verschoven'))

    print(f'{it["titel"]}: eindstand op {laatste_dag:%d-%m-%Y} {max(tijden)} '
          f'(laatste dag, laatste tijdstip)\n')
    items, afgevallen = [], []
    for rij, herkomst in sorted(kandidaten.values(), key=lambda k: k[0]['nummer'] or 0):
        op_bord, geschiedenis = github.status_geschiedenis(token, rij['item_id'])
        if _tijd(op_bord) > moment:
            afgevallen.append(rij)
            continue
        status = None
        for wanneer, nieuw in geschiedenis:
            if _tijd(wanneer) <= moment:
                status = nieuw
        print(f'  #{rij["nummer"]:<5} {(status or "-"):<12} {herkomst:<26} {rij["titel"][:60]}')
        items.append({**rij, 'status': status, 'gearchiveerd': False,
                      'iteratie': {'iteratie_id': it['iteratie_id'], 'titel': it['titel'],
                                   'startdatum': it['startdatum'], 'duur_dagen': it['duur_dagen']}})
    for rij in afgevallen:
        print(f'  #{rij["nummer"]:<5} valt af: stond toen nog niet op het bord')

    toelichting = args.toelichting or (
        f'Gereconstrueerd op {date.today():%d-%m-%Y}: {len(args.nummers)} taken opgegeven als verschoven, '
        'status uit de statusgeschiedenis van GitHub.')
    print(f'\n{len(items)} taken. Toelichting: {toelichting}')

    if not args.uitvoeren:
        print('\nNiets weggeschreven. Klopt dit, draai dan opnieuw met --uitvoeren.')
        return

    bord = {'project_id': basis['project_id'], 'titel': basis['project_titel'],
            'iteraties': [], 'items': items}
    momentopname_id = opslag.sla_momentopname_op(conn, bord, genomen_op=moment,
                                                 bron='reconstructie', toelichting=toelichting)
    print(f'\nWeggeschreven als momentopname {momentopname_id} (bron: reconstructie).')


if __name__ == '__main__':
    main()
