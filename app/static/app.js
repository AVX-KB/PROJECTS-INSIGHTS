'use strict';

/*
 * Projects Insights — overzicht.
 * Leest /api/status, /api/vragen/niet-afgerond en /api/vragen/langlopers.
 * Klik op een week opent het weekrapport (week.html).
 * Gedeelde hulpjes (kleuren, labels, haal) staan in gemeen.js.
 */

const ZICHTBAAR = 12;        // zoveel iteraties staan er standaard in beeld
const LANGLOPERS_KORT = 15;  // zoveel langlopers tot je op "Toon alle" klikt

let grafiek = null;
let vraag = null;            // antwoord van /api/vragen/niet-afgerond
let lopers = null;           // antwoord van /api/vragen/langlopers
let alleenPrio = new URLSearchParams(location.search).get('prio') === '1';
let alleLangloper = false;

const deel = obj => (obj ? obj[alleenPrio ? 'prio' : 'alle'] : null);

// ---------------------------------------------------------------------------
// Gegevens
// ---------------------------------------------------------------------------

async function laad() {
  zetStatus('loading', 'Laden…');
  meld('');
  let status;
  try {
    [status, vraag, lopers] = await Promise.all([
      haal('api/status'), haal('api/vragen/niet-afgerond'), haal('api/vragen/langlopers')]);
  } catch (fout) {
    zetStatus('err', 'Fout bij laden');
    meld(fout.message);
    return;
  }
  toonStatus(status);
  teken();
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

function zetFilter(prio) {
  alleenPrio = prio;
  document.querySelectorAll('#filter .avx-pill').forEach(knop =>
    knop.setAttribute('aria-pressed', String((knop.dataset.prio === '1') === prio)));
  const url = new URL(location.href);
  if (prio) url.searchParams.set('prio', '1'); else url.searchParams.delete('prio');
  history.replaceState(null, '', url);
  teken();
}

function teken() {
  if (!vraag) return;
  toonKerngetallen();
  toonGrafiek();
  toonLanglopers();
}

// ---------------------------------------------------------------------------
// Weergave
// ---------------------------------------------------------------------------

function toonStatus(status) {
  const bord = status.bord;
  toonBord(bord);
  $('afgerond-statussen').textContent = bord.afgerond_statussen.join(' of ');
  $('prio-veld').textContent = bord.prio_veld;
  const t = status.snapshot_tijden;
  $('tijden').textContent = t.length > 1 ? `${t.slice(0, -1).join(', ')} en ${t[t.length - 1]}` : t.join('');
  $('legenda').innerHTML = CATEGORIEEN.map(c =>
    `<div class="pi-legenda-regel">${pill(c.kleur, c.label)} <span>${esc(c.uitleg)}</span></div>`).join('');

  const m = status.momentopnamen;
  if (m && m.laatste) zetStatus('', `Bijgewerkt ${moment(m.laatste)}`);
  else zetStatus('err', 'Nog geen momentopname');
}

function weekUrl(iteratie_id) {
  return `week?id=${encodeURIComponent(iteratie_id)}`;
}

function toonKerngetallen() {
  const its = vraag.iteraties;
  const pills = [];
  const recent = its.filter(i => i.volledig && deel(i).gepland).slice(-6);
  if (recent.length) {
    const niet = recent.reduce((s, i) => s + deel(i).niet_afgerond, 0);
    const gepland = recent.reduce((s, i) => s + deel(i).gepland, 0);
    pills.push(`<span class="avx-pill non-interactive orange">Gemiddeld niet afgerond
      <span class="num">${Math.round(100 * niet / gepland)}% · ${(niet / recent.length).toFixed(1)} per week
      (laatste ${recent.length})</span></span>`);
  }
  const laatste = its[its.length - 1];
  if (laatste) {
    const d = deel(laatste);
    const van = d.gepland != null ? ` van ${d.gepland}` : '';
    pills.push(`<a class="avx-pill red" href="${weekUrl(laatste.iteratie_id)}">${esc(laatste.titel)}
      <span class="num">${d.niet_afgerond}${van} niet afgerond</span></a>`);
  }
  if (vraag.lopend) {
    const l = vraag.lopend, d = deel(l);
    pills.push(`<a class="avx-pill blue" href="${weekUrl(l.iteratie_id)}">Lopend: ${esc(l.titel)}
      <span class="num">${d.open} van ${d.gepland} open · nog ${l.dagen_over} ${l.dagen_over === 1 ? 'dag' : 'dagen'}</span></a>`);
  }
  const prioOpen = lopers.taken.filter(t => t.prioriteit).length;
  if (!alleenPrio) {
    pills.push(`<span class="avx-pill non-interactive gray">Langlopers met prioriteit
      <span class="num">${prioOpen}</span></span>`);
  }
  if (!pills.length) pills.push('<span class="avx-pill non-interactive gray">Nog geen gegevens</span>');
  $('kerngetallen').innerHTML = pills.join('');
}

function tooltip(punten) {
  const it = vraag.iteraties[punten[0].dataIndex], d = deel(it);
  const regels = CATEGORIEEN
    .filter(c => d.categorieen[c.sleutel])
    .map(c => `${pill(c.kleur, c.label)} ${d.categorieen[c.sleutel]}`);
  const kop = `<b>${esc(it.titel)}</b> <span style="color:${token('--avx-text-muted')}">${periode(it)}</span>`;
  const totaal = it.volledig
    ? `${d.niet_afgerond} van ${d.gepland} niet afgerond (${d.percentage ?? 0}%)`
    : `${d.niet_afgerond} nu nog open · <i>onvolledig, geen eindstand</i>`;
  const herkomst = it.gereconstrueerd
    ? [`<i style="color:${token('--avx-text-muted')}">${esc(it.toelichting || 'Gereconstrueerde eindstand.')}</i>`] : [];
  const klik = `<span style="color:${token('--avx-text-muted')}">Klik voor het weekrapport</span>`;
  return [kop, totaal, ...regels, ...herkomst, klik].join('<br>');
}

function toonGrafiek() {
  const its = vraag.iteraties;
  $('aantal-iteraties').textContent = its.length;
  if (!grafiek) {
    grafiek = echarts.init($('grafiek'), null, { renderer: 'svg' });
    // Klik ergens in de kolom van een week, niet alleen precies op de staaf.
    grafiek.getZr().on('click', e => {
      const punt = [e.offsetX, e.offsetY];
      if (!grafiek.containPixel('grid', punt)) return;
      const index = grafiek.convertFromPixel({ seriesIndex: 0 }, punt)[0];
      const it = vraag.iteraties[index];
      if (it) location.href = weekUrl(it.iteratie_id);
    });
    window.addEventListener('resize', () => grafiek.resize());
  }

  const leeg = !its.length || (alleenPrio && !its.some(i => deel(i).niet_afgerond || deel(i).gepland));
  if (leeg) {
    grafiek.clear();
    grafiek.setOption({
      title: {
        text: alleenPrio ? 'Nog geen taken met prioriteit in afgelopen weken' : 'Nog geen afgelopen iteraties',
        left: 'center', top: 'middle',
        textStyle: { color: token('--avx-text-muted'), fontSize: 13, fontStyle: 'italic', fontWeight: 400 },
      },
    });
    return;
  }

  const tekst = token('--avx-text-dim');
  const lijn = token('--avx-border');
  const zoom = its.length > ZICHTBAAR;

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
      extraCssText: 'max-width: 340px; white-space: normal;',
    },
    xAxis: {
      type: 'category',
      data: its.map(i => i.titel),
      axisLabel: { color: tekst, interval: 0, hideOverlap: true, fontSize: 11,
        formatter: (titel, index) => {
          const it = its[index];
          // kort, zodat de labels naast elkaar passen; de tooltip legt het uit
          const extra = !it.volledig ? '\n{klein|onvolledig}' : it.gereconstrueerd ? '\n{klein|gereconstr.}' : '';
          return `${titel}\n{datum|${datum(it.startdatum)}}` + extra;
        },
        rich: {
          datum: { color: token('--avx-text-muted'), fontSize: 10 },
          klein: { color: token('--avx-text-muted'), fontSize: 10, fontStyle: 'italic' },
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
      ? [{ type: 'slider', startValue: its.length - ZICHTBAAR, endValue: its.length - 1,
           bottom: 12, height: 18, borderColor: lijn },
         { type: 'inside' }]
      : [],
    series: [
      ...CATEGORIEEN.map(c => ({
        name: c.label, type: 'bar', stack: 'niet-afgerond', barMaxWidth: 46,
        emphasis: { focus: 'series' },
        cursor: 'pointer',
        data: its.map(i => ({
          value: deel(i).categorieen[c.sleutel],
          itemStyle: i.volledig ? undefined : { opacity: 0.4 },
        })),
      })),
      {
        name: '% niet afgerond', type: 'line', yAxisIndex: 1,
        data: its.map(i => deel(i).percentage),
        symbolSize: 7, lineStyle: { width: 2 }, connectNulls: false, z: 5,
      },
    ],
  }, true);
}

function toonLanglopers() {
  const alle = lopers.taken.filter(t => !alleenPrio || t.prioriteit);
  $('aantal-langlopers').textContent = alle.length;
  const d = lopers.drempel;
  $('langlopers-uitleg').innerHTML =
    `Open taken die ${d.dagen} dagen of langer bestaan, in ${d.iteraties} of meer iteraties gepland stonden,
     of nog op een afgelopen iteratie staan${alleenPrio ? ', alleen met prioriteit' : ''}.
     "Gepland in" kijkt terug tot ${lopers.geschiedenis_vanaf ? esc(datum(lopers.geschiedenis_vanaf)) : 'de eerste momentopname'};
     wat daarvoor gebeurde, bewaart GitHub niet.`;

  if (!alle.length) {
    $('langlopers').innerHTML = `<div class="avx-empty">${alleenPrio
      ? 'Geen langlopers met prioriteit.' : 'Geen langlopers.'}</div>`;
    return;
  }

  const koppen = ['Taak', 'Titel', 'Prioriteit', 'Status', 'Staat nu op', 'Gepland in', 'Open'];
  const cellen = t => {
    const nuOp = t.iteratie_nu
      ? `${esc(t.iteratie_nu)}${t.iteratie_nu_afgelopen ? ' <span class="pi-waarschuwing">afgelopen</span>' : ''}`
      : '<span class="avx-text-muted">backlog</span>';
    const gepland = t.gepland_in.length
      ? `<b>${t.gepland_in.length}×</b> <span class="avx-text-muted" title="${esc(t.gepland_in.join(' → '))}">${
          esc(t.gepland_in.map(w => w.replace(/^\D+/, '')).join(' → '))}</span>`
      : '<span class="avx-text-muted">—</span>';
    return `<td class="pi-nowrap">${prioLabel(t.prioriteit)}</td>
      <td class="pi-nowrap">${esc(t.status || '—')}</td>
      <td class="pi-nowrap">${nuOp}</td>
      <td class="pi-nowrap">${gepland}</td>
      <td class="pi-nowrap">${t.dagen_open != null ? `${t.dagen_open} dagen` : '—'}</td>`;
  };

  // Per groep een boom. Ingekort wordt alleen tussen bomen, nooit midden in een boom.
  const rijen = [];
  let getoond = 0;
  for (const [gepland, kop] of [[true, 'Stond gepland en is nog niet af'], [false, 'Alleen op de backlog']]) {
    const groep = alle.filter(t => t.ooit_gepland === gepland);
    if (!groep.length || (!alleLangloper && getoond >= LANGLOPERS_KORT)) continue;
    rijen.push(`<tr class="pi-groep"><td colspan="${koppen.length}">${kop}
      <span class="avx-text-muted">(${groep.length})</span></td></tr>`);
    for (const regel of boom(groep)) {
      const nieuweBoom = regel.soort === 'hoofd' || regel.diepte === 0;
      if (nieuweBoom && !alleLangloper && getoond >= LANGLOPERS_KORT) break;
      if (regel.soort === 'hoofd') { rijen.push(hoofdRij(regel, koppen.length)); continue; }
      getoond++;
      rijen.push(`<tr>
        <td class="pi-nowrap">${taakLink(regel.taak)}</td>
        ${boomTitel(regel)}
        ${cellen(regel.taak)}
      </tr>`);
    }
  }
  const meer = (alleLangloper && alle.length > LANGLOPERS_KORT) || (!alleLangloper && alle.length > getoond)
    ? `<button type="button" class="avx-btn avx-mt-sm" id="meer-langlopers">${alleLangloper
        ? 'Minder tonen' : `Toon alle ${alle.length}`}</button>` : '';
  $('langlopers').innerHTML = tabel(koppen, rijen) + meer;
  const knop = $('meer-langlopers');
  if (knop) knop.addEventListener('click', () => { alleLangloper = !alleLangloper; toonLanglopers(); });
}

$('bijwerken').addEventListener('click', bijwerken);
document.querySelectorAll('#filter .avx-pill').forEach(knop =>
  knop.addEventListener('click', () => zetFilter(knop.dataset.prio === '1')));
zetFilter(alleenPrio);
laad();
