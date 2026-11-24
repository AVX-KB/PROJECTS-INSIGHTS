"""
Opslag in Postgres
==================
Eigen database `AVX-AI-DB-PROJECTS-INSIGHTS` op `AVX-AI-DB`. Alle tabellen
beginnen met `pi_`.

  pi_momentopname  wanneer het bord is uitgelezen
  pi_item_stand    per momentopname: elk item met zijn iteratie en Status
  pi_iteratie      de iteraties van het iteratieveld (titel, start, duur)

Deze momentopnamen zijn de enige plek waar de geschiedenis van het bord staat:
GitHub zelf onthoudt niet op welke iteratie een taak eerder stond. Wat hier
weg is, komt niet terug.

Datums rekenen we in Postgres uit, in de tijdzone uit TIJDZONE. Zo hangt
"vandaag" en "op de laatste dag van de iteratie" niet af van de klok of de
tijdzonebestanden in de container.
"""

import os

import psycopg2
import psycopg2.extras

TIJDZONE = os.getenv('TIJDZONE', 'Europe/Amsterdam')

SCHEMA = """
CREATE TABLE IF NOT EXISTS pi_momentopname (
    id            serial PRIMARY KEY,
    genomen_op    timestamptz NOT NULL DEFAULT now(),
    project_id    text NOT NULL,
    project_titel text,
    aantal_items  integer NOT NULL
);

CREATE TABLE IF NOT EXISTS pi_iteratie (
    iteratie_id   text PRIMARY KEY,
    titel         text NOT NULL,
    startdatum    date NOT NULL,
    duur_dagen    integer NOT NULL,
    bijgewerkt_op timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pi_item_stand (
    momentopname_id integer NOT NULL REFERENCES pi_momentopname(id) ON DELETE CASCADE,
    item_id         text NOT NULL,
    soort           text,
    nummer          integer,
    titel           text,
    url             text,
    repo            text,
    staat           text,
    status          text,
    iteratie_id     text,
    gearchiveerd    boolean NOT NULL DEFAULT false,
    PRIMARY KEY (momentopname_id, item_id)
);

CREATE INDEX IF NOT EXISTS pi_item_stand_iteratie ON pi_item_stand (iteratie_id);
"""


def verbinding():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'avx-ai-db'),
        port=int(os.getenv('DB_POORT', '5432')),
        dbname=os.getenv('DB_NAAM', 'AVX-AI-DB-PROJECTS-INSIGHTS'),
        user=os.getenv('DB_GEBRUIKER', 'svc_projects_insights'),
        password=os.getenv('DB_WACHTWOORD', ''),
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def maak_schema():
    with verbinding() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.close()


def _lokaal(kolom):
    """SQL-fragment: een timestamptz-kolom als lokale tijd."""
    return f"({kolom} AT TIME ZONE %(tz)s)"


# ---------------------------------------------------------------------------
# Schrijven
# ---------------------------------------------------------------------------

def sla_momentopname_op(conn, bord):
    """Eén momentopname wegschrijven, in één transactie. Geeft het id terug."""
    with conn.cursor() as cur:
        # Iteraties komen uit de veldinstellingen én uit de items zelf: een
        # iteratie die uit de instellingen is verwijderd, hangt soms nog aan een item.
        iteraties = {i['iteratie_id']: i for i in bord['iteraties']}
        for item in bord['items']:
            if item['iteratie']:
                iteraties.setdefault(item['iteratie']['iteratie_id'], item['iteratie'])
        for it in iteraties.values():
            cur.execute("""
                INSERT INTO pi_iteratie (iteratie_id, titel, startdatum, duur_dagen)
                VALUES (%(iteratie_id)s, %(titel)s, %(startdatum)s, %(duur_dagen)s)
                ON CONFLICT (iteratie_id) DO UPDATE
                   SET titel = EXCLUDED.titel, startdatum = EXCLUDED.startdatum,
                       duur_dagen = EXCLUDED.duur_dagen, bijgewerkt_op = now()
            """, it)

        cur.execute("""
            INSERT INTO pi_momentopname (project_id, project_titel, aantal_items)
            VALUES (%s, %s, %s) RETURNING id
        """, (bord['project_id'], bord['titel'], len(bord['items'])))
        momentopname_id = cur.fetchone()['id']

        psycopg2.extras.execute_values(cur, """
            INSERT INTO pi_item_stand (momentopname_id, item_id, soort, nummer, titel, url,
                                       repo, staat, status, iteratie_id, gearchiveerd)
            VALUES %s
        """, [(momentopname_id, i['item_id'], i['soort'], i['nummer'], i['titel'], i['url'],
               i['repo'], i['staat'], i['status'],
               i['iteratie']['iteratie_id'] if i['iteratie'] else None, i['gearchiveerd'])
              for i in bord['items']])
    conn.commit()
    return momentopname_id


# ---------------------------------------------------------------------------
# Lezen
# ---------------------------------------------------------------------------

def nu_lokaal(conn):
    """(datum, tijd) van dit moment in TIJDZONE."""
    with conn.cursor() as cur:
        cur.execute("SELECT (now() AT TIME ZONE %(tz)s)::date AS datum, "
                    "(now() AT TIME ZONE %(tz)s)::time AS tijd", {'tz': TIJDZONE})
        rij = cur.fetchone()
    return rij['datum'], rij['tijd']


def geplande_momentopname_nodig(conn, tijdstippen):
    """Waar als er sinds het laatst verstreken tijdstip nog geen momentopname is.

    `tijdstippen` is een lijst als ['06:00', '12:00', '18:00']. Het laatst
    verstreken tijdstip kan ook van gisteren zijn: draaide de app om 18:00
    niet, dan wordt die momentopname bij de volgende start alsnog gemaakt.
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH nu AS (SELECT now() AT TIME ZONE %(tz)s AS t),
            slot AS (
              SELECT max(dag + tijd::time) AS t
                FROM nu,
                     unnest(%(tijden)s::text[]) AS tijd,
                     unnest(ARRAY[nu.t::date, nu.t::date - 1]) AS dag
               WHERE dag + tijd::time <= nu.t
            )
            SELECT NOT EXISTS (SELECT 1 FROM pi_momentopname) AS nog_geen,
                   (SELECT t FROM slot) IS NOT NULL AND NOT EXISTS (
                     SELECT 1 FROM pi_momentopname
                      WHERE {_lokaal('genomen_op')} >= (SELECT t FROM slot)
                   ) AS slot_gemist
        """, {'tz': TIJDZONE, 'tijden': list(tijdstippen)})
        rij = cur.fetchone()
    return rij['nog_geen'] or rij['slot_gemist']


def overzicht_momentopnamen(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT count(*) AS aantal,
                   min({_lokaal('genomen_op')}) AS eerste,
                   max({_lokaal('genomen_op')}) AS laatste
              FROM pi_momentopname
        """, {'tz': TIJDZONE})
        return cur.fetchone()


def laatste_momentopname(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, project_titel, aantal_items, {_lokaal('genomen_op')} AS genomen_op
              FROM pi_momentopname ORDER BY genomen_op DESC LIMIT 1
        """, {'tz': TIJDZONE})
        return cur.fetchone()


def eindstand_momentopname(conn, startdatum, einddatum):
    """De laatste momentopname binnen [startdatum, einddatum), in lokale datums.

    einddatum is de eerste dag ná de iteratie. Geen momentopname in die periode
    betekent: van deze iteratie weten we niet hoe hij eindigde.
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, {_lokaal('genomen_op')} AS genomen_op
              FROM pi_momentopname
             WHERE {_lokaal('genomen_op')}::date >= %(start)s
               AND {_lokaal('genomen_op')}::date <  %(eind)s
             ORDER BY genomen_op DESC LIMIT 1
        """, {'tz': TIJDZONE, 'start': startdatum, 'eind': einddatum})
        return cur.fetchone()


def iteraties(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT iteratie_id, titel, startdatum, duur_dagen,
                   startdatum + duur_dagen AS einddatum
              FROM pi_iteratie ORDER BY startdatum, titel
        """)
        return cur.fetchall()


def stand(conn, momentopname_id):
    """Alle items van één momentopname, als {item_id: rij}."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT item_id, soort, nummer, titel, url, repo, staat, status,
                   iteratie_id, gearchiveerd
              FROM pi_item_stand WHERE momentopname_id = %s
        """, (momentopname_id,))
        return {rij['item_id']: rij for rij in cur.fetchall()}
