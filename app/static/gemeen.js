'use strict';

/*
 * Projects Insights — wat het overzicht en het weekrapport delen.
 * Kleuren komen uit de tokens van avex-core.css, niet uit deze code.
 */

const CATEGORIEEN = [
  { sleutel: 'doorgeschoven',      label: 'Doorgeschoven',        kleur: 'orange',
    uitleg: 'staat nu op een andere iteratie' },
  { sleutel: 'blijven_staan',      label: 'Blijven staan',        kleur: 'red',
    uitleg: 'staat nog op de oude iteratie en is nog niet afgerond' },
  { sleutel: 'na_afloop_afgerond', label: 'Na afloop afgerond',   kleur: 'amber',
    uitleg: 'staat nog op de oude iteratie en is later alsnog afgerond' },
  { sleutel: 'uit_iteratie',       label: 'Uit iteratie gehaald', kleur: 'gray',
    uitleg: 'heeft geen iteratie meer, of staat niet meer op het bord' },
];
const PER_CATEGORIE = Object.fromEntries(CATEGORIEEN.map(c => [c.sleutel, c]));

const $ = id => document.getElementById(id);
const token = naam => getComputedStyle(document.documentElement).getPropertyValue(naam).trim();

function esc(tekst) {
  return String(tekst ?? '').replace(/[&<>"']/g, t =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[t]));
}

const datum = iso => new Date(iso + 'T00:00:00')
  .toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' });
const moment = iso => new Date(iso)
  .toLocaleString('nl-NL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const periode = it => `${datum(it.startdatum)} – ${datum(it.laatste_dag)}`;

function pill(kleur, tekst, getal) {
  const num = getal === undefined ? '' : ` <span class="num">${esc(getal)}</span>`;
  return `<span class="avx-pill non-interactive pi-label ${kleur}">${esc(tekst)}${num}</span>`;
}
const categorieLabel = sleutel => {
  const c = PER_CATEGORIE[sleutel];
  return c ? pill(c.kleur, c.label) : '';
};
const prioLabel = prio => (prio ? pill('blue', prio) : '<span class="avx-text-muted">—</span>');

// De repo staat in de tooltip: op bord 13 komt alles uit één repo, en een
// tweede regel per taak kost de titel te veel ruimte.
function taakLink(t) {
  const nummer = t.nummer != null ? `#${t.nummer}` : 'concept';
  const titel = t.repo ? ` title="${esc(t.repo)}"` : '';
  return t.url
    ? `<a href="${esc(t.url)}" target="_blank" rel="noopener"${titel}>${esc(nummer)}</a>`
    : `<span${titel}>${esc(nummer)}</span>`;
}

// ---------------------------------------------------------------------------
// Boom: hoofdissues met hun sub-issues
// ---------------------------------------------------------------------------
//
// Zet een gesorteerde lijst taken om in boomvolgorde. Een sub-issue komt onder
// zijn hoofdissue. Staat het hoofdissue zelf niet in de lijst, dan komt het als
// kopregel boven zijn sub-issues. Een boom staat op de plek van zijn hoogst
// geplaatste taak, zodat de volgorde van de lijst (prioriteit eerst enz.) blijft.
//
// Geeft regels terug: { soort: 'taak', taak, diepte, aantalSub }
//                  of { soort: 'hoofd', ouder, aantalSub }  (kopregel)

function boom(taken) {
  const perUrl = new Map(taken.filter(t => t.url).map(t => [t.url, t]));
  const directeOuder = t => {
    const url = t.ouder && t.ouder.url;
    return url && url !== t.url ? perUrl.get(url) || null : null;
  };
  // Een taak die via zijn voorouders bij zichzelf uitkomt, staat in een kring.
  // Op GitHub kan dat niet, maar dan krijgt hij hier geen ouder, in plaats van
  // dat de boom eindeloos doorloopt.
  const inKring = t => {
    const gezien = new Set([t]);
    for (let o = directeOuder(t); o; o = directeOuder(o)) {
      if (gezien.has(o)) return o === t;
      gezien.add(o);
    }
    return false;
  };
  const kring = new Set(taken.filter(inKring));
  const ouderInLijst = t => (kring.has(t) ? null : directeOuder(t));
  // Hoogste voorouder binnen de lijst.
  const top = t => {
    while (ouderInLijst(t)) t = ouderInLijst(t);
    return t;
  };

  const kinderen = new Map();
  const wortels = new Map();   // sleutel -> wortel, in volgorde van eerste voorkomen
  for (const t of taken) {
    const ouder = ouderInLijst(t);
    if (ouder) {
      if (!kinderen.has(ouder)) kinderen.set(ouder, []);
      kinderen.get(ouder).push(t);
    }
    const bovenste = top(t);
    // Een hoofdissue als kopregel alleen als het zelf niet in de lijst staat.
    const extern = bovenste.ouder && bovenste.ouder.url && !perUrl.has(bovenste.ouder.url) ? bovenste.ouder : null;
    const sleutel = extern ? `hoofd:${extern.url}` : `taak:${bovenste.url || bovenste.nummer}`;
    if (!wortels.has(sleutel)) {
      wortels.set(sleutel, extern ? { soort: 'hoofd', ouder: extern, leden: [] } : { soort: 'taak', taak: bovenste });
    }
    if (extern && bovenste === t) wortels.get(sleutel).leden.push(t);
  }

  const regels = [];
  const telSub = t => (kinderen.get(t) || []).reduce((n, k) => n + 1 + telSub(k), 0);
  const zet = (t, diepte) => {
    regels.push({ soort: 'taak', taak: t, diepte, aantalSub: telSub(t) });
    for (const k of kinderen.get(t) || []) zet(k, diepte + 1);
  };
  for (const w of wortels.values()) {
    if (w.soort === 'hoofd') {
      regels.push({ soort: 'hoofd', ouder: w.ouder,
        aantalSub: w.leden.reduce((n, t) => n + 1 + telSub(t), 0) });
      for (const t of w.leden) zet(t, 1);
    } else {
      zet(w.taak, 0);
    }
  }
  return regels;
}

// De titelcel van een taak in de boom: ingesprongen met een haakje, en bij een
// hoofdissue het aantal sub-issues in deze lijst.
function boomTitel(regel) {
  const t = regel.taak;
  const haak = regel.diepte ? '<span class="pi-boom-haak" aria-hidden="true">└</span>' : '';
  const sub = regel.aantalSub
    ? ` <span class="pi-boom-aantal">${regel.aantalSub} sub-issue${regel.aantalSub === 1 ? '' : 's'}</span>` : '';
  const klasse = regel.aantalSub ? ' pi-boom-hoofd' : '';
  return `<td class="pi-boom pi-boom-${Math.min(regel.diepte, 3)}${klasse}">${haak}${esc(t.titel)}${sub}</td>`;
}

// Kopregel voor een hoofdissue dat zelf niet in de lijst staat.
function hoofdRij(regel, kolommen) {
  const o = regel.ouder;
  const tekst = `#${o.nummer} ${o.titel || ''}`;
  const link = o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(tekst)}</a>` : esc(tekst);
  return `<tr class="pi-hoofd-rij"><td colspan="${kolommen}">
    <span class="pi-boom-label">Hoofdissue</span> ${link}
    <span class="pi-boom-aantal">${regel.aantalSub} sub-issue${regel.aantalSub === 1 ? '' : 's'} hieronder</span>
  </td></tr>`;
}

// Een hele tabel als boom. `cellen(taak)` geeft de cellen ná Taak en Titel.
function boomTabel(koppen, taken, cellen, rijKlasse = () => '') {
  const rijen = boom(taken).map(regel => regel.soort === 'hoofd'
    ? hoofdRij(regel, koppen.length)
    : `<tr${rijKlasse(regel.taak)}>
        <td class="pi-nowrap">${taakLink(regel.taak)}</td>
        ${boomTitel(regel)}
        ${cellen(regel.taak)}
      </tr>`);
  return tabel(koppen, rijen);
}

function tabel(koppen, rijen) {
  return `<table class="avx-table">
    <thead><tr>${koppen.map(k => `<th>${esc(k)}</th>`).join('')}</tr></thead>
    <tbody>${rijen.join('')}</tbody>
  </table>`;
}

async function haal(url, opties) {
  const antwoord = await fetch(url, opties);
  const data = await antwoord.json().catch(() => ({}));
  if (antwoord.status === 401) { location.href = 'login'; throw new Error('Niet ingelogd.'); }
  if (!antwoord.ok) throw new Error(data.fout || `Fout ${antwoord.status}`);
  return data;
}

function zetStatus(soort, tekst) {
  $('status-dot').className = 'avx-dot' + (soort ? ' ' + soort : '');
  $('status-tekst').textContent = tekst;
}

function meld(tekst, soort = 'avx-error') {
  $('melding').innerHTML = tekst ? `<div class="${soort}">${esc(tekst)}</div>` : '';
}

function toonBord(bord) {
  const naam = bord.titel ? `<b>${esc(bord.titel)}</b> · ` : '';
  $('bord').innerHTML = `${naam}<a href="${esc(bord.url)}" target="_blank" rel="noopener"
    style="color:inherit">${esc(bord.org)}/projects/${esc(bord.nummer)}</a> · veld ${esc(bord.sprint_veld)}`;
}
