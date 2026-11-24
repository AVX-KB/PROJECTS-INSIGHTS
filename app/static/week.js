'use strict';

/*
 * Projects Insights — weekrapport van één iteratie (week?id=<iteratie_id>).
 * Leest /api/status, /api/vragen/niet-afgerond (voor vorige/volgende) en
 * /api/vragen/week/<id>. Taken met prioriteit staan bovenaan.
 */

const iteratieId = new URLSearchParams(location.search).get('id');

async function laad() {
  if (!iteratieId) { location.href = './'; return; }
  let status, lijst, week;
  try {
    [status, lijst, week] = await Promise.all([
      haal('api/status'), haal('api/vragen/niet-afgerond'),
      haal(`api/vragen/week/${encodeURIComponent(iteratieId)}`)]);
  } catch (fout) {
    zetStatus('err', 'Fout bij laden');
    meld(fout.message);
    return;
  }
  toonBord(status.bord);
  toonNavigatie(lijst);
  toonWeek(week);
}

function toonNavigatie(lijst) {
  const weken = [...lijst.iteraties, ...(lijst.lopend ? [lijst.lopend] : [])];
  const i = weken.findIndex(w => w.iteratie_id === iteratieId);
  const knop = (w, tekst) => w
    ? `<a class="avx-pill gray" href="week?id=${encodeURIComponent(w.iteratie_id)}">${tekst}</a>`
    : `<span class="avx-pill gray non-interactive pi-uit">${tekst}</span>`;
  const vorige = weken[i - 1], volgende = weken[i + 1];
  $('navigatie').innerHTML =
    knop(vorige, `‹ ${vorige ? esc(vorige.titel) : 'vorige'}`) +
    knop(volgende, `${volgende ? esc(volgende.titel) : 'volgende'} ›`);
}

function getallenAfgelopen(d, volledig) {
  if (!volledig) {
    return [pill('red', 'Nu nog open', d.niet_afgerond)];
  }
  const p = [
    pill('gray', 'Gepland', d.gepland),
    pill('green', 'Afgerond', d.afgerond),
    pill('orange', 'Niet afgerond', `${d.niet_afgerond} (${d.percentage ?? 0}%)`),
  ];
  for (const c of CATEGORIEEN) {
    if (d.categorieen[c.sleutel]) p.push(pill(c.kleur, c.label, d.categorieen[c.sleutel]));
  }
  return p;
}

function getallenLopend(d) {
  return [pill('gray', 'Gepland', d.gepland), pill('green', 'Afgerond', d.afgerond), pill('blue', 'Open', d.open)];
}

function toonWeek(w) {
  document.title = `${w.titel} — Projects Insights`;
  $('titel').textContent = `${w.titel} · ${periode(w)}`;

  if (w.fase === 'toekomst') {
    zetStatus('', 'Nog niet begonnen');
    meld('Deze week is nog niet begonnen.', 'pi-notitie');
    return;
  }

  const lopend = w.fase === 'lopend';
  if (lopend) {
    zetStatus('loading', `Loopt nog · stand ${moment(w.stand_op)}`);
    meld(`Deze week loopt nog, nog ${w.dagen_over} ${w.dagen_over === 1 ? 'dag' : 'dagen'}. Dit is de stand van nu.`, 'pi-notitie');
    $('getallen-alle').innerHTML = getallenLopend(w.alle).join('');
    $('getallen-prio').innerHTML = w.prio.gepland ? getallenLopend(w.prio).join('') : geenPrio();
  } else {
    zetStatus(w.volledig ? '' : 'err',
      w.volledig ? `Eindstand ${moment(w.eindstand_op)}` : 'Geen eindstand');
    if (w.gereconstrueerd) meld(w.toelichting || 'Gereconstrueerde eindstand.', 'pi-notitie');
    else if (!w.volledig) {
      meld('Onvolledig: deze week eindigde voordat het vastleggen begon. Je ziet alleen wat er nu nog op deze week staat.', 'pi-notitie');
    }
    $('getallen-alle').innerHTML = getallenAfgelopen(w.alle, w.volledig).join('');
    const prioIets = w.prio.niet_afgerond || w.prio.gepland;
    $('getallen-prio').innerHTML = prioIets ? getallenAfgelopen(w.prio, w.volledig).join('') : geenPrio();
  }

  toonNietAfgerond(w, lopend);
  toonAfgerond(w, lopend);
}

function geenPrio() {
  return '<span class="avx-text-muted pi-klein">Geen taken met prioriteit in deze week.</span>';
}

const rijKlasse = t => (t.prioriteit ? ' class="pi-prio"' : '');

function toonNietAfgerond(w, lopend) {
  const taken = w.niet_afgerond_taken;
  $('kop-niet').textContent = lopend ? 'Nog open' : 'Niet afgerond';
  $('aantal-niet').textContent = taken.length;
  if (!taken.length) {
    $('niet-afgerond').innerHTML = `<div class="avx-empty">${lopend ? 'Alles is af.' : 'Alles op deze week is afgerond.'}</div>`;
    return;
  }
  if (lopend) {
    $('niet-afgerond').innerHTML = tabel(['Taak', 'Titel', 'Parent issue', 'Prioriteit', 'Status'], taken.map(t => `<tr${rijKlasse(t)}>
      <td class="pi-nowrap">${taakLink(t)}</td><td>${esc(t.titel)}</td><td>${ouderLabel(t.ouder)}</td>
      <td class="pi-nowrap">${prioLabel(t.prioriteit)}</td><td class="pi-nowrap">${esc(t.status || '—')}</td></tr>`));
    return;
  }
  $('niet-afgerond').innerHTML = tabel(
    ['Taak', 'Titel', 'Parent issue', 'Prioriteit', 'Wat gebeurde er', w.volledig ? 'Status bij einde' : 'Status', 'Nu op', 'Status nu'],
    taken.map(t => `<tr${rijKlasse(t)}>
      <td class="pi-nowrap">${taakLink(t)}</td>
      <td>${esc(t.titel)}</td><td>${ouderLabel(t.ouder)}</td>
      <td class="pi-nowrap">${prioLabel(t.prioriteit)}</td>
      <td class="pi-nowrap">${categorieLabel(t.categorie)}</td>
      <td class="pi-nowrap">${esc(t.status || '—')}</td>
      <td class="pi-nowrap">${esc(t.iteratie_nu || 'backlog')}</td>
      <td class="pi-nowrap">${esc(t.status_nu || '—')}</td>
    </tr>`));
}

function toonAfgerond(w, lopend) {
  const taken = w.afgerond_taken;
  $('kop-af').textContent = !lopend && !w.volledig ? 'Nu afgerond op deze week' : 'Afgerond';
  $('aantal-af').textContent = taken.length;
  $('afgerond').innerHTML = taken.length
    ? tabel(['Taak', 'Titel', 'Parent issue', 'Prioriteit'], taken.map(t => `<tr${rijKlasse(t)}>
        <td class="pi-nowrap">${taakLink(t)}</td><td>${esc(t.titel)}</td><td>${ouderLabel(t.ouder)}</td>
        <td class="pi-nowrap">${prioLabel(t.prioriteit)}</td></tr>`))
    : '<div class="avx-empty">Niets afgerond.</div>';
}

laad();
