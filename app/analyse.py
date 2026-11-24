"""
Vragen aan het bord
===================
Drie vragen, elk een functie:

  niet_afgerond(...)  per iteratie: hoeveel taken zijn niet afgerond
  week_rapport(...)   één iteratie in detail: wat was gepland, wat is af, wat niet
  langlopers(...)     taken die al lang openstaan of steeds weer worden doorgeschoven


Niet afgerond per iteratie
--------------------------
Per afgelopen iteratie X kijken we naar de **eindstand**: de laatste
momentopname binnen de iteratie. Met momentopnamen om 06:00, 12:00 en 18:00
is dat 18:00 op de laatste dag.

  gepland        items die in de eindstand op X stonden
  afgerond       daarvan met een status uit AFGEROND_STATUSSEN
  niet afgerond  de rest, ingedeeld naar wat er daarna mee gebeurde:

    doorgeschoven       staat nu op een andere iteratie
    blijven staan       staat nu nog op X en is nog steeds niet afgerond
    na afloop afgerond  staat nu nog op X en is inmiddels wel afgerond
    uit iteratie        heeft nu geen iteratie meer, of staat niet meer op het bord

"Nu" is de laatste echte momentopname.

Iteraties die eindigden vóór de eerste momentopname hebben geen eindstand.
Daarvan tonen we alleen wat we nu kunnen zien: items die nu nog op X staan en
niet afgerond zijn ("blijven staan"). Die iteraties krijgen `volledig: False`.
Een iteratie kan ook een gereconstrueerde eindstand hebben (reconstructie.py):
dan is hij volledig, maar met `gereconstrueerd: True` en een toelichting.


Prioriteit
----------
Een taak "heeft prioriteit" als het prioriteitsveld een waarde heeft, welke
dan ook. We kijken naar de prioriteit van **nu**: een taak die nu prioriteit
heeft, telt ook in oude weken als prioriteitstaak. Staat hij niet meer op het
bord, dan geldt wat er in de momentopname stond.

Elke telling bestaat daarom twee keer: `alle` en `prio` (alleen taken met
prioriteit).


Langlopers
----------
Openstaande taken die al lang bestaan of in meerdere iteraties gepland
stonden. Volgorde:

  1. eerst taken die ooit op een iteratie stonden: steeds plannen en niet
     afmaken is erger dan lang op de backlog staan
  2. daarbinnen eerst taken met prioriteit
  3. dan het aantal iteraties waarin ze gepland stonden
  4. dan hoe lang ze al bestaan

"Ooit op een iteratie" gaat zo ver terug als de momentopnamen; wat daarvoor
gebeurde, weet GitHub niet meer.
"""

from datetime import timedelta

import opslag

CATEGORIEEN = ('doorgeschoven', 'blijven_staan', 'na_afloop_afgerond', 'uit_iteratie')

# Een taak hoort bij de langlopers als hij minstens zo lang bestaat, of in
# minstens zoveel iteraties gepland stond, of nog op een afgelopen iteratie staat.
LANGLOPER_DAGEN = 14
LANGLOPER_ITERATIES = 2


def _afgerond(rij, afgerond_statussen):
    return (rij.get('status') or '').strip().lower() in afgerond_statussen


def _statussen(afgerond_statussen):
    return {s.strip().lower() for s in afgerond_statussen if s.strip()}


def _categorie(iteratie_id, nu_rij, afgerond_statussen):
    if not nu_rij or not nu_rij['iteratie_id']:
        return 'uit_iteratie'
    if nu_rij['iteratie_id'] != iteratie_id:
        return 'doorgeschoven'
    return 'na_afloop_afgerond' if _afgerond(nu_rij, afgerond_statussen) else 'blijven_staan'


def _prioriteit(rij, nu):
    """De prioriteit van nu; staat de taak niet meer op het bord, die van toen."""
    nu_rij = nu.get(rij['item_id'])
    return (nu_rij or rij).get('prioriteit')


def _basis(it):
    return {
        'iteratie_id': it['iteratie_id'],
        'titel': it['titel'],
        'startdatum': it['startdatum'].isoformat(),
        'laatste_dag': (it['einddatum'] - timedelta(days=1)).isoformat(),
        'duur_dagen': it['duur_dagen'],
    }


class _Context:
    """Wat elke vraag nodig heeft, één keer opgehaald."""

    def __init__(self, conn, afgerond_statussen):
        self.conn = conn
        self.afgerond_statussen = _statussen(afgerond_statussen)
        self.vandaag, _ = opslag.nu_lokaal(conn)
        self.laatste = opslag.laatste_momentopname(conn)
        self.iteraties = opslag.iteraties(conn)
        self.titels = {it['iteratie_id']: it['titel'] for it in self.iteraties}
        self.per_id = {it['iteratie_id']: it for it in self.iteraties}
        self._standen = {}
        self.nu = self.stand(self.laatste['id']) if self.laatste else {}

    def stand(self, momentopname_id):
        if momentopname_id not in self._standen:
            self._standen[momentopname_id] = opslag.stand(self.conn, momentopname_id)
        return self._standen[momentopname_id]

    def afgerond(self, rij):
        return _afgerond(rij, self.afgerond_statussen)

    def fase(self, it):
        if it['startdatum'] > self.vandaag:
            return 'toekomst'
        return 'lopend' if it['einddatum'] > self.vandaag else 'afgelopen'

    def eindstand(self, it):
        """(items op de iteratie in de eindstand, momentopname of None).

        Zonder eindstand: wat er nu nog op de iteratie staat.
        """
        eind = opslag.eindstand_momentopname(self.conn, it['startdatum'], it['einddatum'])
        bron = self.stand(eind['id']) if eind else self.nu
        return [r for r in bron.values() if r['iteratie_id'] == it['iteratie_id']], eind


def _telling(rijen, ctx, iteratie_id, volledig):
    """Tellingen over een lijst taken van één iteratie (eindstand)."""
    aantallen = dict.fromkeys(CATEGORIEEN, 0)
    klaar = 0
    for rij in rijen:
        if ctx.afgerond(rij):
            klaar += 1
            continue
        categorie = (_categorie(iteratie_id, ctx.nu.get(rij['item_id']), ctx.afgerond_statussen)
                     if volledig else 'blijven_staan')
        aantallen[categorie] += 1
    niet = len(rijen) - klaar
    return {
        # Zonder eindstand weten we niet hoeveel er gepland was.
        'gepland': len(rijen) if volledig else None,
        'afgerond': klaar if volledig else None,
        'niet_afgerond': niet,
        'percentage': round(100 * niet / len(rijen)) if volledig and rijen else None,
        'categorieen': aantallen,
    }


def _beide(rijen, ctx, maak):
    """Een telling voor alle taken en voor alleen de taken met prioriteit."""
    return {
        'alle': maak(rijen),
        'prio': maak([r for r in rijen if _prioriteit(r, ctx.nu)]),
    }


def _lopend(it, ctx):
    rijen = [r for r in ctx.nu.values() if r['iteratie_id'] == it['iteratie_id']]

    def telling(deel):
        klaar = sum(1 for r in deel if ctx.afgerond(r))
        return {'gepland': len(deel), 'afgerond': klaar, 'open': len(deel) - klaar}

    return {**_basis(it), **_beide(rijen, ctx, telling),
            'dagen_over': (it['einddatum'] - ctx.vandaag).days}


# ---------------------------------------------------------------------------
# Vraag 1: niet afgerond per iteratie
# ---------------------------------------------------------------------------

def niet_afgerond(conn, afgerond_statussen):
    ctx = _Context(conn, afgerond_statussen)
    if not ctx.laatste:
        return {'iteraties': [], 'lopend': None, 'nu': None}

    resultaat, lopend = [], None
    for it in ctx.iteraties:
        fase = ctx.fase(it)
        if fase == 'toekomst':
            continue
        if fase == 'lopend':
            lopend = _lopend(it, ctx)
            continue
        rijen, eind = ctx.eindstand(it)
        volledig = eind is not None
        resultaat.append({
            **_basis(it),
            'volledig': volledig,
            'gereconstrueerd': bool(eind and eind['bron'] == 'reconstructie'),
            'toelichting': eind['toelichting'] if eind else None,
            'eindstand_op': eind['genomen_op'].isoformat(timespec='minutes') if eind else None,
            **_beide(rijen, ctx, lambda deel: _telling(deel, ctx, it['iteratie_id'], volledig)),
        })

    return {'iteraties': resultaat, 'lopend': lopend,
            'nu': ctx.laatste['genomen_op'].isoformat(timespec='minutes')}


# ---------------------------------------------------------------------------
# Vraag 2: weekrapport
# ---------------------------------------------------------------------------

def _taak(rij, ctx, **extra):
    nu_rij = ctx.nu.get(rij['item_id'])
    nu_iteratie = (nu_rij or {}).get('iteratie_id')
    return {
        'nummer': rij['nummer'],
        'titel': rij['titel'],
        'url': rij['url'],
        'repo': rij['repo'],
        'prioriteit': _prioriteit(rij, ctx.nu),
        'status': rij['status'],
        'status_nu': (nu_rij or {}).get('status'),
        'iteratie_nu': ctx.titels.get(nu_iteratie) if nu_iteratie else None,
        **extra,
    }


def _prio_eerst(taak):
    categorie = CATEGORIEEN.index(taak['categorie']) if taak.get('categorie') else 0
    return (taak['prioriteit'] is None, categorie, taak['repo'] or '', taak['nummer'] or 0)


def week_rapport(conn, afgerond_statussen, iteratie_id):
    ctx = _Context(conn, afgerond_statussen)
    it = ctx.per_id.get(iteratie_id)
    if not it or not ctx.laatste:
        return None
    fase = ctx.fase(it)
    if fase == 'toekomst':
        return {**_basis(it), 'fase': fase}

    if fase == 'lopend':
        rijen = [r for r in ctx.nu.values() if r['iteratie_id'] == iteratie_id]
        return {
            **_lopend(it, ctx),
            'fase': fase,
            'stand_op': ctx.laatste['genomen_op'].isoformat(timespec='minutes'),
            'niet_afgerond_taken': sorted((_taak(r, ctx) for r in rijen if not ctx.afgerond(r)), key=_prio_eerst),
            'afgerond_taken': sorted((_taak(r, ctx) for r in rijen if ctx.afgerond(r)), key=_prio_eerst),
        }

    rijen, eind = ctx.eindstand(it)
    volledig = eind is not None
    niet, klaar = [], []
    for rij in rijen:
        if ctx.afgerond(rij):
            klaar.append(_taak(rij, ctx))
        else:
            categorie = (_categorie(iteratie_id, ctx.nu.get(rij['item_id']), ctx.afgerond_statussen)
                         if volledig else 'blijven_staan')
            niet.append(_taak(rij, ctx, categorie=categorie))

    return {
        **_basis(it),
        'fase': fase,
        'volledig': volledig,
        'gereconstrueerd': bool(eind and eind['bron'] == 'reconstructie'),
        'toelichting': eind['toelichting'] if eind else None,
        'eindstand_op': eind['genomen_op'].isoformat(timespec='minutes') if eind else None,
        **_beide(rijen, ctx, lambda deel: _telling(deel, ctx, iteratie_id, volledig)),
        'niet_afgerond_taken': sorted(niet, key=_prio_eerst),
        # Zonder eindstand is dit wat er nu af is, niet wat er toen af was.
        'afgerond_taken': sorted(klaar, key=_prio_eerst),
    }


# ---------------------------------------------------------------------------
# Vraag 3: langlopers
# ---------------------------------------------------------------------------

def langlopers(conn, afgerond_statussen):
    ctx = _Context(conn, afgerond_statussen)
    if not ctx.laatste:
        return {'taken': [], 'nu': None}
    per_item = opslag.iteraties_per_item(conn)

    taken = []
    for rij in ctx.nu.values():
        if ctx.afgerond(rij):
            continue
        gepland = sorted((ctx.per_id[i] for i in per_item.get(rij['item_id'], []) if i in ctx.per_id),
                         key=lambda it: it['startdatum'])
        nu_it = ctx.per_id.get(rij['iteratie_id'])
        nu_afgelopen = bool(nu_it and ctx.fase(nu_it) == 'afgelopen')
        sinds = rij['aangemaakt_op'] or rij['op_bord_sinds']
        dagen = (ctx.vandaag - sinds.date()).days if sinds else None

        if not (len(gepland) >= LANGLOPER_ITERATIES or nu_afgelopen
                or (dagen is not None and dagen >= LANGLOPER_DAGEN)):
            continue
        taken.append({
            'nummer': rij['nummer'],
            'titel': rij['titel'],
            'url': rij['url'],
            'repo': rij['repo'],
            'status': rij['status'],
            'prioriteit': rij['prioriteit'],
            'iteratie_nu': nu_it['titel'] if nu_it else None,
            'iteratie_nu_afgelopen': nu_afgelopen,
            'ooit_gepland': bool(gepland),
            'gepland_in': [it['titel'] for it in gepland],
            'open_sinds': sinds.date().isoformat() if sinds else None,
            'dagen_open': dagen,
        })

    taken.sort(key=lambda t: (not t['ooit_gepland'], t['prioriteit'] is None,
                              -len(t['gepland_in']), -(t['dagen_open'] or 0)))
    eerste = opslag.overzicht_momentopnamen(conn)['eerste']
    return {
        'taken': taken,
        'nu': ctx.laatste['genomen_op'].isoformat(timespec='minutes'),
        'drempel': {'dagen': LANGLOPER_DAGEN, 'iteraties': LANGLOPER_ITERATIES},
        'geschiedenis_vanaf': eerste.date().isoformat() if eerste else None,
    }
