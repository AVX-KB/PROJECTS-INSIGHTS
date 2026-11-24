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
