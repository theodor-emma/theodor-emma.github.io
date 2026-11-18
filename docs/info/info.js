// ── Information page: tabs, map of places to stay, copy buttons ─────────────

// The page's language: index.html is English; fr.html and ro.html load it
// with <html lang="fr"> / "ro". Text written in index.html is switched by
// ../lang.css; text this script writes picks its language with tr().
const LANG = document.documentElement.lang;

/** The text in the page's language. */
function tr(en, fr, ro) {
  return { en, fr, ro }[LANG] ?? en;
}

// Price units and place types are written in English in places.js;
// these tables give each one in the page's language
const UNITS = Object.fromEntries([
  // English (as in places.js), French, Romanian
  ['per night',                                           'par nuit', 'pe noapte'],
  ['per week',                                            'par semaine', 'pe săptămână'],
  ['per week (high season)',                              'par semaine (haute saison)', 'pe săptămână (sezon de vârf)'],
  ['per weekend',                                         'le week-end', 'pe weekend'],
  ['per 2-night weekend',                                 'le week-end de 2 nuits', 'pe weekend (2 nopți)'],
  ['per 2-night stay',                                    'le séjour de 2 nuits', 'pentru un sejur de 2 nopți'],
  ['per room per night',                                  'par chambre et par nuit', 'pe cameră pe noapte'],
  ['per pitch per night',                                 'par emplacement et par nuit', 'pe loc de campare pe noapte'],
  ['per night (family offer)',                            'par nuit (offre famille)', 'pe noapte (ofertă de familie)'],
  ['per night for 2 adults (package)',                    'par nuit pour 2 adultes (forfait)', 'pe noapte pentru 2 adulți (pachet)'],
  ['per night for 2 people (package)',                    'par nuit pour 2 personnes (forfait)', 'pe noapte pentru 2 persoane (pachet)'],
  ['per night (2 people, breakfast included)',            'par nuit (2 personnes, petit-déjeuner inclus)', 'pe noapte (2 persoane, mic dejun inclus)'],
  ['per night (whole château)',                           'par nuit (château entier)', 'pe noapte (tot castelul)'],
  ['per room per night (1–2 people, breakfast included)', 'par chambre et par nuit (1 à 2 personnes, petit-déjeuner inclus)', 'pe cameră pe noapte (1–2 persoane, mic dejun inclus)'],
  ['per room per night (2 people, breakfast included)',   'par chambre et par nuit (2 personnes, petit-déjeuner inclus)', 'pe cameră pe noapte (2 persoane, mic dejun inclus)'],
].map(([en, fr, ro]) => [en, tr(en, fr, ro)]));
const TYPES = Object.fromEntries([
  // English (as in places.js), French, Romanian
  ['Hotel',                   'Hôtel', 'Hotel'],
  ['Chalet / lodge',          'Chalet', 'Cabană'],
  ['Airbnb / holiday rental', 'Location de vacances', 'Închiriere de vacanță'],
  ["Chambre d'hôtes",         "Chambre d'hôtes", 'Pensiune'],
].map(([en, fr, ro]) => [en, tr(en, fr, ro)]));

const CHATEAU = { name: 'Château de Beauvoir', lat: 46.4665086, lon: 3.6349779,
                  note: tr('Reception · Pavillon de Chasse & Gîte du Moulin: contact Emma',
                           'Réception · Pavillon de Chasse et Gîte du Moulin : contactez Emma',
                           'Recepție · Pavillon de Chasse și Gîte du Moulin: contactați-o pe Emma') };
const CHURCH  = { name: 'Église Saint-Joseph', lat: 46.5210270, lon: 3.6816493,
                  note: tr('Ceremony, Dompierre-sur-Besbre',
                           'Cérémonie, Dompierre-sur-Besbre',
                           'Ceremonie, Dompierre-sur-Besbre') };

// Hotels in Vichy, Moulins etc. stay on the map, but the opening view frames
// the places within this distance so the cluster round the château is legible.
const FRAME_KM = 22;

// One colour for every place: availability isn't shown on the map, because it
// would only be a stale snapshot. The shared list says what is taken.
const COLOURS = { stay: '#b8975a', place: '#8e5a66' };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Tabs (the URL hash remembers the open one: #general, #map…) ──

let map = null;

function openTab(name) {
  document.querySelectorAll('.tab').forEach(t => {
    const on = t.dataset.tab === name;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
  });
  if (history.replaceState) history.replaceState(null, '', '#' + name);
  if (name === 'map') {
    if (!map) buildMap();
    else map.invalidateSize();       // Leaflet measures itself; it was hidden
  }
}

document.querySelectorAll('.tab').forEach(t =>
  t.addEventListener('click', () => openTab(t.dataset.tab)));


// Arrow keys move between tabs, as screen-reader users expect
document.querySelector('.tabs').addEventListener('keydown', e => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const tabs = [...document.querySelectorAll('.tab')];
  const i = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  openTab(next.dataset.tab);
  next.focus();
});

// ── Map ──

function popup(p) {
  const facts = [
    p.sleeps    != null && tr(`Sleeps ${p.sleeps}`,
                              `${p.sleeps} couchages`,
                              `${p.sleeps} persoane`),
    p.bedrooms  != null && (p.bedrooms === 1
      ? tr('1 bedroom', '1 chambre', '1 dormitor')
      : tr(`${p.bedrooms} bedrooms`, `${p.bedrooms} chambres`, `${p.bedrooms} dormitoare`)),
    p.bathrooms != null && (p.bathrooms === 1
      ? tr('1 bathroom', '1 salle de bain', '1 baie')
      : tr(`${p.bathrooms} bathrooms`, `${p.bathrooms} salles de bain`, `${p.bathrooms} băi`)),
  ].filter(Boolean).join(' · ');

  const dist = [
    p.kmChateau != null && tr(`${p.kmChateau} km to the château`,
                              `${p.kmChateau} km du château`,
                              `${p.kmChateau} km până la castel`),
    p.kmChurch  != null && tr(`${p.kmChurch} km (${p.minChurch} min) to the church`,
                              `${p.kmChurch} km (${p.minChurch} min) de l'église`,
                              `${p.kmChurch} km (${p.minChurch} min) până la biserică`),
  ].filter(Boolean).join(' · ');

  const unit  = UNITS[p.priceUnit] ?? p.priceUnit;
  const price = p.price != null ? `${esc(tr('Last seen:',
                                            'Dernier prix vu :',
                                            'Ultimul preț văzut:'))} ${p.price} € ${esc(unit)}` : '';
  const type  = TYPES[p.type] ?? p.type;
  // French numbers are written 04 70…; dial them as +33 4 70… so they also
  // work from a Romanian or British phone
  const dial  = (p.phone || '').replace(/[^+\d]/g, '').replace(/^0(?=\d{9}$)/, '+33');
  const phone = p.phone ? `<a href="tel:${esc(dial)}">${esc(p.phone)}</a>` : '';

  return `
    <div class="pop-name">${esc(p.name)}</div>
    <div class="pop-meta">${esc([type, p.village].filter(Boolean).join(' · '))}</div>
    ${facts ? `<div>${esc(facts)}</div>` : ''}
    ${price ? `<div>${price}</div>` : ''}
    ${dist  ? `<div>${esc(dist)}</div>` : ''}
    ${p.approx ? `<div class="pop-approx">${esc(tr('Approximate location (village centre)',
                                                   'Emplacement approximatif (centre du village)',
                                                   'Locație aproximativă (centrul satului)'))}</div>` : ''}
    ${p.link  ? `<div><a href="${esc(p.link)}" target="_blank" rel="noopener">${esc(tr('See the listing',
                                                                                       "Voir l'annonce",
                                                                                       'Vedeți anunțul'))}</a></div>` : ''}
    ${phone   ? `<div>${phone}</div>` : ''}`;
}

// Several places share one address (twin gîtes, a hotel's rooms): fan them out
// in a small fixed spiral so each one can be clicked.
function spread(places) {
  const seen = new Map();
  return places.map(p => {
    const key = p.lat.toFixed(5) + ',' + p.lon.toFixed(5);
    const n = seen.get(key) || 0;
    seen.set(key, n + 1);
    if (!n) return p;
    const angle = n * 2.4, r = 0.00045 * Math.sqrt(n);
    return { ...p, lat: p.lat + r * Math.sin(angle), lon: p.lon + r * Math.cos(angle) * 1.45 };
  });
}

function buildMap() {
  document.getElementById('map').setAttribute('aria-label', tr('Map of places to stay',
                                                               'Carte des hébergements',
                                                               'Harta locurilor de cazare'));
  map = L.map('map', { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  // Scroll-zoom only once the map has been clicked, so the page still scrolls
  map.once('focus', () => map.scrollWheelZoom.enable());

  const frame = [];
  spread(window.PLACES || []).forEach(p => {
    const colour = COLOURS.stay;
    L.circleMarker([p.lat, p.lon], {
      radius: 7,
      color: p.approx ? '#7a6e5f' : '#2c2416',
      weight: 1.2,
      opacity: p.approx ? 0.8 : 0.55,
      dashArray: p.approx ? '3 3' : null,
      fillColor: colour,
      fillOpacity: p.approx ? 0.45 : 0.9,
    }).bindPopup(popup(p), { maxWidth: 280 }).addTo(map);
    if (p.kmChateau == null || p.kmChateau <= FRAME_KM) frame.push([p.lat, p.lon]);
  });

  [CHATEAU, CHURCH].forEach(s => {
    L.circleMarker([s.lat, s.lon], {
      radius: 10, color: '#faf6ef', weight: 2.5, fillColor: COLOURS.place, fillOpacity: 1,
    })
      .bindTooltip(s.name, { permanent: true, direction: 'top', offset: [0, -10], className: 'place-label' })
      .bindPopup(`<div class="pop-name">${esc(s.name)}</div><div class="pop-meta">${esc(s.note)}</div>`)
      .addTo(map);
    frame.push([s.lat, s.lon]);
  });

  map.fitBounds(frame, { padding: [24, 24] });
}

// ── Copy buttons (bank details) ──

document.querySelectorAll('[data-copy]').forEach(b =>
  b.addEventListener('click', async () => {
    const text = document.getElementById(b.dataset.copy).textContent.replace(/\s+/g, '');
    try {
      await navigator.clipboard.writeText(text);
      const label = b.innerHTML;           // the three language versions
      b.textContent = tr('Copied', 'Copié', 'Copiat');
      setTimeout(() => { b.innerHTML = label; }, 1600);
    } catch (_) { /* no clipboard access: the text is still selectable */ }
  }));

// ── Boot ──
const TABS = [...document.querySelectorAll('.tab')].map(t => t.dataset.tab);
const fromHash = location.hash.slice(1);
openTab(TABS.includes(fromHash) ? fromHash : 'general');

// Links in the text (<a href="#map">) switch tabs through the hash, so the
// translated paragraphs in index.html need no special markup
window.addEventListener('hashchange', () => {
  const name = location.hash.slice(1);
  if (!TABS.includes(name)) return;
  openTab(name);
  document.querySelector('.tabs').scrollIntoView({ behavior: 'smooth' });
});
