# Projects Insights

Grafieken over een GitHub Project-bord: vragen die GitHub zelf niet beantwoordt. De eerste vraag is **hoeveel taken er per iteratie (veld `WEEK` op het bord) niet worden afgerond**, en wat er daarna mee gebeurt: doorgeschoven, blijven staan, na afloop afgerond of uit de iteratie gehaald.

GitHub bewaart niet op welke iteratie een taak eerder stond. Daarom zet deze app drie keer per dag een momentopname van het bord in een eigen database. Die momentopnamen zijn de geschiedenis.

**Documentatie staat in de wiki:** [Projects Insights](http://wiki.ai-dev.cops.ota/solutions/projects-insights/overzicht). Daar staan de architectuur, het beheer en de handleiding.

## Lokaal starten

Vereist: de database `AVX-AI-DB-PROJECTS-INSIGHTS` met gebruiker `svc_projects_insights` op `AVX-AI-DB`, en het netwerk `avx-ai-net`.

```bash
cp .env.example .env          # en vul de waarden uit KeePass in
docker compose up -d --build
```

De pagina staat daarna op poort 4002.

## Onderdelen

| Bestand | Wat het doet |
|---|---|
| `app/github.py` | het bord uitlezen via de GraphQL-API van GitHub |
| `app/opslag.py` | momentopnamen in Postgres (tabellen `pi_*`) |
| `app/analyse.py` | de vragen: niet afgerond per iteratie, weekrapport, langlopers |
| `app/app.py` | webserver, API en de planner |
| `app/toegang.py` | het gedeelde wachtwoord en de sessie |
| `app/static/week.html`, `week.js` | het weekrapport |
| `app/reconstructie.py` | eenmalig: de eindstand van een afgelopen iteratie achteraf samenstellen |
| `app/static/` | de pagina, met `avex-core.css` en Apache ECharts 5.6.0 |

`app/static/vendor/echarts-5.6.0.min.js` is Apache ECharts (Apache-2.0), ongewijzigd overgenomen van cdnjs. SHA-512: `XSmbX3mhrD2ix5fXPTRQb2FwK22sRMVQTpBP2ac8hX7Dh/605hA2QDegVWiAvZPiXIxOV0CbkmUjGionDpbCmw==`.

## Changelog

### v1.0.3 — 24 november 2026

**Weekrapport, langlopers en prioriteit**
- Klik op een week in de grafiek (of op een week bij de kerngetallen) voor het **weekrapport** op `/week?id=<iteratie>`: gepland, afgerond en niet afgerond, voor alle taken en voor taken met prioriteit, met de lijsten niet afgerond en afgerond en knoppen naar de vorige en volgende week. Werkt ook voor de lopende week, met de stand van nu.
- De takenlijst onder de grafiek is weg. Daar staan nu de **langlopers**: open taken die 14 dagen of langer bestaan, in 2 of meer iteraties gepland stonden, of nog op een afgelopen iteratie staan. Eerst wat ooit gepland was, daarbinnen eerst prioriteit, dan het aantal iteraties, dan de leeftijd. De eerste 15 staan er, de rest met **Toon alle**.
- **Prioriteit**: een taak met een waarde in het veld uit `PRIO_VELD` (standaard `Priority`), welke waarde ook, heeft prioriteit. Dat veld is een issue-veld van de organisatie: de waarde wordt van het issue gelezen (`issueFieldValues`), met een projectveld met dezelfde naam als terugval. Met **Alleen met prioriteit** tonen de grafiek, de kerngetallen en de langlopers alleen die taken. In lijsten staan ze bovenaan, met de waarde als label.
- `pi_item_stand` heeft de kolommen `prioriteit`, `aangemaakt_op` en `op_bord_sinds`; ze worden bij het opstarten vanzelf toegevoegd en vanaf de eerste momentopname gevuld.
- Wat het overzicht en het weekrapport delen, staat in `app/static/gemeen.js`.

### v1.0.2 — 24 november 2026

**Gereconstrueerde eindstand**
- Nieuw script `app/reconstructie.py`: stelt achteraf de eindstand samen van een afgelopen iteratie zonder momentopname. Welke taken verschoven zijn geef je op; de status op het einde komt uit de statusgeschiedenis van GitHub. Zonder `--uitvoeren` laat het alleen zien wat het zou schrijven.
- `pi_momentopname` heeft de kolommen `bron` (`github` of `reconstructie`) en `toelichting`; ze worden bij het opstarten vanzelf toegevoegd. Een reconstructie telt alleen als eindstand van die iteratie, niet als stand van nu en niet voor de planner. Een echte momentopname gaat voor.
- In de grafiek staat "gereconstr." onder zo'n iteratie, met de toelichting in de tooltip en boven de takenlijst.
- Alle iteraties krijgen een label onder de as, ook als het krap wordt.
- WEEK 47 van bord 13 is gereconstrueerd: 14 taken zijn op 23 november naar WEEK 48 verschoven, vóór de eerste momentopname.

### v1.0.1 — 24 november 2026

**Wachtwoord en proxy**
- De pagina zit achter één gedeeld wachtwoord uit `TOEGANGSWACHTWOORD` (KeePass). Zonder wachtwoord in de `.env` gaat alles op slot. Na inloggen blijf je 30 dagen ingelogd; rechtsboven staat **Afmelden**.
- De container hangt nu ook in `proxy-net`, voor `insights.ai-dev.cops.ota`. Poort 4002 blijft tot die naam werkt.
- Op een smal scherm staan de knoppen in de header op een eigen regel.

### v1.0.0 — 24 november 2026

**Start**
- Momentopname van bord `AVEXInternational/projects/13` op de tijdstippen uit `SNAPSHOT_TIJDEN` (standaard 06:00, 12:00 en 18:00), plus een knop **Nu bijwerken**. Een gemist tijdstip, ook van de vorige dag, wordt bij de volgende start ingehaald. Zijn er nog geen momentopnamen, dan wordt de eerste direct bij het opstarten gemaakt.
- Vraag **Niet afgerond per iteratie**: een gestapelde staafgrafiek per afgelopen iteratie, met een lijn voor het aandeel van wat gepland stond. Klik op een iteratie voor de lijst met taken.
- Kerngetallen: gemiddeld niet afgerond over de laatste zes volledige iteraties, de laatste iteratie, en de stand van de lopende iteratie.
- Iteraties die eindigden vóór de eerste momentopname zijn als **onvolledig** gemarkeerd.
