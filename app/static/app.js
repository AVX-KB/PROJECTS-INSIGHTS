'use strict';

/*
 * Projects Insights — vraag: hoeveel taken worden er per iteratie niet afgerond?
 * Leest /api/status en /api/vragen/niet-afgerond en tekent de grafiek met ECharts.
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
const ZICHTBAAR = 12; // zoveel iteraties staan er standaard in beeld

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
const label = (cat, extra = '') =>
  `<span class="avx-pill non-interactive pi-label ${cat.kleur}">${esc(cat.label)}${extra}</span>`;

let grafiek = null;
let iteraties = [];

// ---------------------------------------------------------------------------
// Gegevens
// ---------------------------------------------------------------------------

async function haal(url, opties) {
  const antwoord = await fetch(url, opties);
  const data = await antwoord.json().catch(() => ({}));
  if (antwoord.status === 401) { location.href = 'login'; throw new Error('Niet ingelogd.'); }
  if (!antwoord.ok) throw new Error(data.fout || `Fout ${antwoord.status}`);
  return data;
}

async function laad() {
  zetStatus('loading', 'Laden…');
  $('melding').innerHTML = '';
  let status;
  try {
    status = await haal('api/status');
    toonStatus(status);
    const vraag = await haal('api/vragen/niet-afgerond');
    toonVraag(vraag);
  } catch (fout) {
    zetStatus('err', 'Fout bij laden');
    meld(fout.message);
    return;
  }
  if (status.laatste_fout) {
    const wanneer = status.laatste_fout_op ? moment(status.laatste_fout_op) : 'bij opstarten';
    meld(`Laatste momentopname mislukt (${wanneer}): ${status.laatste_fout}`);
  }
}

async function bijwerken() {
  const knop = $('bijwerken');
  knop.disabled = true;
  zetStatus('loading', 'Bord uitlezen…');
  try {
    await haal('api/momentopname', { method: 'POST' });
    await laad();
  } catch (fout) {
    zetStatus('err', 'Bijwerken mislukt');
    meld(fout.message);
  } finally {
    knop.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Weergave
// ---------------------------------------------------------------------------

function zetStatus(soort, tekst) {
  $('status-dot').className = 'avx-dot' + (soort ? ' ' + soort : '');
  $('status-tekst').textContent = tekst;
}

function meld(tekst) {
  $('melding').innerHTML = `<div class="avx-error">${esc(tekst)}</div>`;
}

function toonStatus(status) {
  const bord = status.bord;
  const naam = bord.titel ? `<b>${esc(bord.titel)}</b> · ` : '';
  $('bord').innerHTML = `${naam}<a href="${esc(bord.url)}" target="_blank" rel="noopener"
    style="color:inherit">${esc(bord.org)}/projects/${esc(bord.nummer)}</a> · veld ${esc(bord.sprint_veld)}`;
  $('afgerond-statussen').textContent = bord.afgerond_statussen.join(' of ');
  const t = status.snapshot_tijden;
  $('tijden').textContent = t.length > 1 ? `${t.slice(0, -1).join(', ')} en ${t[t.length - 1]}` : t.join('');

  const m = status.momentopnamen;
  if (m && m.laatste) zetStatus('', `Bijgewerkt ${moment(m.laatste)}`);
  else zetStatus('err', 'Nog geen momentopname');
}

function toonVraag(vraag) {
  iteraties = vraag.iteraties;
  $('aantal-iteraties').textContent = iteraties.length;
  toonKerngetallen(vraag);
  toonGrafiek();
  const laatste = iteraties[iteraties.length - 1];
  if (laatste) toonTaken(laatste);
  else {
    $('taken-titel').textContent = 'Taken';
    $('aantal-taken').textContent = 0;
    $('taken').innerHTML = '<div class="avx-empty">Nog geen afgelopen iteraties om te tonen.</div>';
  }
}

function toonKerngetallen(vraag) {
  const pills = [];
  const volledig = iteraties.filter(i => i.volledig && i.gepland);
  const recent = volledig.slice(-6);
  if (recent.length) {
    const niet = recent.reduce((s, i) => s + i.niet_afgerond, 0);
    const gepland = recent.reduce((s, i) => s + i.gepland, 0);
    pills.push(`<span class="avx-pill non-interactive orange">Gemiddeld niet afgerond
      <span class="num">${Math.round(100 * niet / gepland)}% · ${(niet / recent.length).toFixed(1)} per iteratie
      (laatste ${recent.length})</span></span>`);
  }
  const laatste = iteraties[iteraties.length - 1];
  if (laatste) {
    const van = laatste.gepland != null ? ` van ${laatste.gepland}` : '';
    pills.push(`<span class="avx-pill non-interactive red">${esc(laatste.titel)}
      <span class="num">${laatste.niet_afgerond}${van} niet afgerond</span></span>`);
  }
  if (vraag.lopend) {
    const l = vraag.lopend;
    pills.push(`<span class="avx-pill non-interactive blue">Lopend: ${esc(l.titel)}
      <span class="num">${l.open} van ${l.gepland} open · nog ${l.dagen_over} ${l.dagen_over === 1 ? 'dag' : 'dagen'}</span></span>`);
  }
  if (!pills.length) pills.push('<span class="avx-pill non-interactive gray">Nog geen gegevens</span>');
  $('kerngetallen').innerHTML = pills.join('');

  $('legenda').innerHTML = CATEGORIEEN.map(c =>
    `${label(c)} <span class="pi-legenda-uitleg">${esc(c.uitleg)}</span>`).join('<br>');
}

function tooltip(punten) {
  const it = iteraties[punten[0].dataIndex];
  const regels = CATEGORIEEN
    .filter(c => it.categorieen[c.sleutel])
    .map(c => `${label(c)} ${it.categorieen[c.sleutel]}`);
  const kop = `<b>${esc(it.titel)}</b> <span style="color:${token('--avx-text-muted')}">${periode(it)}</span>`;
  const totaal = it.volledig
    ? `${it.niet_afgerond} van ${it.gepland} niet afgerond (${it.percentage ?? 0}%)`
    : `${it.niet_afgerond} nu nog open · <i>onvolledig, geen eindstand</i>`;
  return [kop, totaal, ...regels].join('<br>');
}

function toonGrafiek() {
  if (!grafiek) {
    grafiek = echarts.init($('grafiek'), null, { renderer: 'svg' });
    // Klik ergens in de kolom van een iteratie, niet alleen precies op de staaf:
    // een iteratie met weinig of geen niet-afgeronde taken heeft een lage of geen staaf.
    grafiek.getZr().on('click', e => {
      const punt = [e.offsetX, e.offsetY];
      if (!grafiek.containPixel('grid', punt)) return;
      const index = grafiek.convertFromPixel({ seriesIndex: 0 }, punt)[0];
      if (iteraties[index]) toonTaken(iteraties[index]);
    });
    window.addEventListener('resize', () => grafiek.resize());
  }
  if (!iteraties.length) {
    grafiek.clear();
    grafiek.setOption({
      title: { text: 'Nog geen afgelopen iteraties', left: 'center', top: 'middle',
        textStyle: { color: token('--avx-text-muted'), fontSize: 13, fontStyle: 'italic', fontWeight: 400 } },
    });
    return;
  }

  const tekst = token('--avx-text-dim');
  const lijn = token('--avx-border');
  const zoom = iteraties.length > ZICHTBAAR;

  grafiek.setOption({
    textStyle: { fontFamily: token('--avx-font') },
    color: CATEGORIEEN.map(c => token(`--avx-${c.kleur}`)).concat(token('--avx-accent')),
    grid: { left: 44, right: 52, top: 52, bottom: zoom ? 96 : 60 },
    // 'scroll' houdt de legenda op één regel, ook op een smal scherm.
    legend: { type: 'scroll', top: 0, textStyle: { color: tekst }, itemWidth: 14, itemHeight: 10,
      pageIconColor: token('--avx-accent'), pageTextStyle: { color: tekst } },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: tooltip,
      backgroundColor: token('--avx-surface'), borderColor: token('--avx-border-strong'),
      textStyle: { color: token('--avx-text'), fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      data: iteraties.map(i => i.titel),
      axisLabel: { color: tekst, hideOverlap: true,
        formatter: (titel, index) => {
          const it = iteraties[index];
          return `${titel}\n{datum|${datum(it.startdatum)}}` + (it.volledig ? '' : '\n{onvolledig|onvolledig}');
        },
        rich: {
          datum: { color: token('--avx-text-muted'), fontSize: 10 },
          onvolledig: { color: token('--avx-text-muted'), fontSize: 10, fontStyle: 'italic' },
        } },
      axisLine: { lineStyle: { color: lijn } },
      axisTick: { show: false },
    },
    yAxis: [
      { type: 'value', name: 'Taken', minInterval: 1,
        nameTextStyle: { color: tekst }, axisLabel: { color: tekst },
        splitLine: { lineStyle: { color: lijn } } },
      { type: 'value', name: '% van gepland', min: 0, max: 100,
        nameTextStyle: { color: tekst }, axisLabel: { color: tekst, formatter: '{value}%' },
        splitLine: { show: false } },
    ],
    dataZoom: zoom
      ? [{ type: 'slider', startValue: iteraties.length - ZICHTBAAR, endValue: iteraties.length - 1,
           bottom: 12, height: 18, borderColor: lijn },
         { type: 'inside' }]
      : [],
    series: [
      ...CATEGORIEEN.map(c => ({
        name: c.label, type: 'bar', stack: 'niet-afgerond', barMaxWidth: 46,
        emphasis: { focus: 'series' },
        data: iteraties.map(i => ({
          value: i.categorieen[c.sleutel],
          itemStyle: i.volledig ? undefined : { opacity: 0.4 },
        })),
      })),
      {
        name: '% niet afgerond', type: 'line', yAxisIndex: 1,
        data: iteraties.map(i => i.percentage),
        symbolSize: 7, lineStyle: { width: 2 }, connectNulls: false, z: 5,
      },
    ],
  }, true);
}

function toonTaken(it) {
  $('taken-titel').textContent = `Niet afgerond in ${it.titel} (${periode(it)})`;
  $('aantal-taken').textContent = it.taken.length;
  if (!it.taken.length) {
    $('taken').innerHTML = '<div class="avx-empty">Alles op deze iteratie is afgerond.</div>';
    return;
  }
  const bron = it.volledig
    ? `<p class="pi-toelichting">Eindstand van ${esc(moment(it.eindstand_op))}.</p>`
    : '<p class="pi-toelichting">Onvolledig: geen momentopname uit deze iteratie. Alleen taken die nu nog op deze iteratie staan en niet afgerond zijn.</p>';
  const rijen = it.taken.map(t => {
    const nummer = t.nummer != null ? `#${t.nummer}` : 'concept';
    const link = t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(nummer)}</a>` : esc(nummer);
    return `<tr>
      <td class="pi-nowrap">${link}<br><span class="avx-text-muted">${esc(t.repo || '')}</span></td>
      <td>${esc(t.titel)}</td>
      <td class="pi-nowrap">${label(PER_CATEGORIE[t.categorie])}</td>
      <td class="pi-nowrap">${esc(t.status_eind || '—')}</td>
      <td class="pi-nowrap">${esc(t.iteratie_nu || '—')}</td>
      <td class="pi-nowrap">${esc(t.status_nu || '—')}</td>
    </tr>`;
  }).join('');
  $('taken').innerHTML = `${bron}
    <table class="avx-table avx-mt-sm">
      <thead><tr><th>Taak</th><th>Titel</th><th>Wat gebeurde er</th><th>Status bij einde</th>
        <th>Nu op iteratie</th><th>Status nu</th></tr></thead>
      <tbody>${rijen}</tbody>
    </table>`;
}

$('bijwerken').addEventListener('click', bijwerken);
laad();
