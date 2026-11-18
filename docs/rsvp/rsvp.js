// ── Config ───────────────────────────────────────────────────────────────────
const API_BASE = (window.RSVP_CONFIG && window.RSVP_CONFIG.apiBase) || 'http://localhost:8000';

// The page's language: index.html is English; fr.html and ro.html load it
// with <html lang="fr"> / "ro". Text written in index.html is switched by
// ../lang.css; text this script writes picks its language with tr().
const LANG = document.documentElement.lang;

/** The text in the page's language. */
function tr(en, fr, ro) {
  return { en, fr, ro }[LANG] ?? en;
}

const DIETS = ['none', 'vegetarian', 'vegan'];
const DIET_LABELS = {
  none:       tr('No restrictions', 'Aucune restriction', 'Fără restricții'),
  vegetarian: tr('Vegetarian', 'Végétarien', 'Vegetarian'),
  vegan:      tr('Vegan', 'Végétalien', 'Vegan'),
};

// answers mirror the guest list while the form is being filled in
const state = { key: null, invite: null, answers: [] };

// Codes are printed in uppercase; forgive spaces, dashes and lower case
function cleanKey(raw) {
  return (raw || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

// ── Screen management ────────────────────────────────────────────────────────

function showScreen(id, errorMsg) {
  document.querySelectorAll('.screen').forEach(s => { s.hidden = true; });
  const el = document.getElementById(id);
  if (el) {
    el.hidden = false;
    const canGoBack = !!previousScreen(id);
    el.querySelectorAll('.btn-back').forEach(b => { b.hidden = !canGoBack; });
  }
  if (id === 'screen-key') {
    const errEl = document.getElementById('key-error');
    if (errEl) errEl.textContent = errorMsg || '';
  }
}

/**
 * The step before `id` in the form, worked out from the current answers
 * rather than a history stack, so it always matches the path forward.
 * The first step leads back to the stored response when updating one.
 */
function previousScreen(id) {
  if (!state.invite) return null;
  const first = isSimpleInvite() ? 'screen-question' : 'screen-attendance';
  switch (id) {
    case 'screen-question':
    case 'screen-attendance':
      return state.invite.responded ? 'screen-already' : null;
    case 'screen-details':
      return first;
    case 'screen-notes':
      return attendingAnswers().length ? 'screen-details' : first;
    default:
      return null;
  }
}

function goBack() {
  const current = document.querySelector('.screen:not([hidden])');
  const prev = current && previousScreen(current.id);
  if (!prev) return;
  // Answers live in `state`, so re-rendering keeps what was typed
  if (prev === 'screen-attendance') renderAttendance();
  if (prev === 'screen-details')    renderDetails();
  showScreen(prev);
}

function showError(msg) {
  showScreen('screen-error');
  document.getElementById('error-text').textContent = msg;
}

// ── API ───────────────────────────────────────────────────────────────────────

async function fetchInvite(key) {
  const keyIsFromUrl = cleanKey(new URLSearchParams(window.location.search).get('invite')) === key;
  showScreen('screen-loading');
  try {
    const res = await fetch(API_BASE + '/invite/' + encodeURIComponent(key));
    if (res.status === 404) {
      const msg = tr('Invite code not found. Please check and try again.',
                     "Code d'invitation introuvable. Veuillez vérifier et réessayer.",
                     'Cod de invitație negăsit. Vă rugăm verificați și încercați din nou.');
      if (keyIsFromUrl) showError(msg);
      else              showScreen('screen-key', msg);
      return;
    }
    if (!res.ok) throw new Error('server');

    state.key = key;
    adoptInvite(await res.json());

    if (state.invite.responded) {
      renderSummary();
      showScreen('screen-already');
    } else {
      startForm();
    }
  } catch (e) {
    showError(tr('Unable to connect. Please try again later.',
                 'Impossible de se connecter. Veuillez réessayer plus tard.',
                 'Nu se poate conecta. Vă rugăm încercați mai târziu.'));
  }
}

async function submitRSVP() {
  showScreen('screen-loading');
  try {
    const res = await fetch(
      API_BASE + '/invite/' + encodeURIComponent(state.key) + '/rsvp',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notes: (document.getElementById('notes') || {}).value || '',
          guests: state.answers
            .filter(a => !a.isExtra || (a.attending && a.name.trim()))
            .map(a => ({
              id:        a.isExtra ? null : a.id,
              name:      a.name.trim(),
              attending: !!a.attending,
              diet:      a.attending ? a.diet : 'none',
              allergies: a.attending ? a.allergies.trim() : '',
              choir:     a.attending ? !!a.choir : false,
              brunch:    a.attending ? !!a.brunch : false,
            })),
        }),
      }
    );
    if (!res.ok) throw new Error('server');

    adoptInvite(await res.json());
    renderSummary();
    showScreen('screen-already');
  } catch (e) {
    showError(tr('Failed to submit your response. Please try again.',
                 "Échec de l'envoi. Veuillez réessayer.",
                 'Trimiterea a eșuat. Vă rugăm încercați din nou.'));
  }
}

// ── Invite → answers ─────────────────────────────────────────────────────────

function adoptInvite(data) {
  state.invite = data;

  const fresh = !data.responded;
  state.answers = data.guests.map(g => ({
    id:        g.id,
    name:      g.name || '',
    isExtra:   g.source === 'guest',
    attending: g.attending === null ? (g.source === 'host' && fresh) : !!g.attending,
    diet:      DIETS.includes(g.diet) ? g.diet : 'none',
    allergies: g.allergies || '',
    choir:     g.choir === true,
    brunch:    g.brunch === true,
  }));

  // A plus-one invitation always offers its companion row up front
  if (data.invite_type === 'plus_one' && !state.answers.some(a => a.isExtra)) {
    state.answers.push(blankExtra());
  }

  document.querySelectorAll('.guest-name').forEach(el => {
    el.textContent = (state.answers[0] && state.answers[0].name) || data.label;
  });
  document.querySelectorAll('.invite-label').forEach(el => { el.textContent = data.label; });

  const notes = document.getElementById('notes');
  if (notes) notes.value = data.notes || '';
}

function blankExtra() {
  return { id: null, name: '', isExtra: true, attending: false, diet: 'none', allergies: '', choir: false, brunch: false };
}

function extraCount() {
  return state.answers.filter(a => a.isExtra).length;
}

/** A lone invitee with nobody to add gets the plain accept / decline screen. */
function isSimpleInvite() {
  return state.answers.length === 1 && !state.invite.extra_guests_allowed;
}

function startForm() {
  if (isSimpleInvite()) {
    showScreen('screen-question');
  } else {
    renderAttendance();
    showScreen('screen-attendance');
  }
}

// ── Attendance screen ─────────────────────────────────────────────────────────

function renderAttendance() {
  const host = document.getElementById('guest-attendance');
  if (!host) return;
  host.innerHTML = '';

  state.answers.forEach((answer, idx) => {
    const row = document.createElement('div');
    row.className = 'guest-row';

    if (answer.isExtra) {
      const input = document.createElement('input');
      input.type        = 'text';
      input.className   = 'guest-row-input';
      input.placeholder = tr("Guest's name", 'Nom de la personne', 'Numele persoanei');
      input.value       = answer.name;
      input.setAttribute('aria-label', tr("Guest's name",
                                          'Nom de la personne',
                                          'Numele persoanei'));
      input.addEventListener('input', () => { answer.name = input.value; });
      row.appendChild(input);
    } else {
      const name = document.createElement('p');
      name.className   = 'guest-row-name';
      name.textContent = answer.name;
      row.appendChild(name);
    }

    row.appendChild(buildToggle(answer, idx));

    if (answer.isExtra && state.invite.invite_type !== 'plus_one') {
      const remove = document.createElement('button');
      remove.type      = 'button';
      remove.className = 'guest-row-remove';
      remove.title     = tr('Remove', 'Retirer', 'Ștergeți');
      remove.setAttribute('aria-label', tr('Remove', 'Retirer', 'Ștergeți'));
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        state.answers.splice(idx, 1);
        renderAttendance();
      });
      row.appendChild(remove);
    }

    host.appendChild(row);
  });

  const addBtn = document.getElementById('btn-add-guest');
  if (addBtn) {
    const canAdd = state.invite.invite_type !== 'plus_one'
      && extraCount() < (state.invite.extra_guests_allowed || 0);
    addBtn.hidden = !canAdd;
    addBtn.textContent = tr('+ Add someone', '+ Ajouter une personne', '+ Adăugați o persoană');
  }

  const err = document.getElementById('attendance-error');
  if (err) err.textContent = '';

  updateNextLabel();
}

function buildToggle(answer, idx) {
  const wrap = document.createElement('div');
  wrap.className = 'toggle';

  [['yes', tr('Coming',
              'Présent(e)',
              'Prezent(ă)')], ['no', tr("Can't come", 'Absent(e)', 'Absent(ă)')]].forEach(([val, text]) => {
    const btn = document.createElement('button');
    btn.type      = 'button';
    btn.className = 'toggle-btn' + ((val === 'yes') === !!answer.attending ? ' is-on' : '');
    btn.textContent = text;
    btn.addEventListener('click', () => {
      answer.attending = val === 'yes';
      wrap.querySelectorAll('.toggle-btn').forEach(b => {
        b.classList.toggle('is-on', b === btn);
      });
      updateNextLabel();
    });
    wrap.appendChild(btn);
  });

  wrap.dataset.idx = String(idx);
  return wrap;
}

function attendingAnswers() {
  return state.answers.filter(a => a.attending && (!a.isExtra || a.name.trim()));
}

function updateNextLabel() {
  const btn = document.getElementById('btn-attendance-next');
  if (btn) btn.textContent = tr('Continue', 'Continuer', 'Continuați');
}

// ── Details (diet + allergies) screen ─────────────────────────────────────────

function renderDetails() {
  const host = document.getElementById('guest-details');
  if (!host) return;
  host.innerHTML = '';

  attendingAnswers().forEach((answer, i) => {
    const block = document.createElement('div');
    block.className = 'guest-detail';

    if (!isSimpleInvite()) {
      const name = document.createElement('p');
      name.className   = 'guest-detail-name';
      name.textContent = answer.name.trim() || tr('Your guest',
                                                  'Votre accompagnant',
                                                  'Însoțitorul dumneavoastră');
      block.appendChild(name);
    }

    const radios = document.createElement('div');
    radios.className = 'radio-row';
    DIETS.forEach(diet => {
      const label = document.createElement('label');
      label.className = 'radio-item';

      const input = document.createElement('input');
      input.type    = 'radio';
      input.name    = 'diet-' + i;
      input.value   = diet;
      input.checked = answer.diet === diet;
      input.addEventListener('change', () => { answer.diet = diet; });

      const span = document.createElement('span');
      span.textContent = DIET_LABELS[diet];

      label.append(input, span);
      radios.appendChild(label);
    });
    block.appendChild(radios);

    const allergies = document.createElement('input');
    allergies.type        = 'text';
    allergies.className   = 'dietary-other';
    allergies.placeholder = tr('Allergies (nuts, shellfish…)',
                               'Allergies (fruits à coque, fruits de mer…)',
                               'Alergii (nuci, fructe de mare…)');
    allergies.value       = answer.allergies;
    allergies.setAttribute('aria-label', tr('Allergies', 'Allergies', 'Alergii'));
    allergies.addEventListener('input', () => { answer.allergies = allergies.value; });
    block.appendChild(allergies);

    host.appendChild(block);
  });
}

// ── Response summary ─────────────────────────────────────────────────────────

function renderSummary() {
  const host = document.getElementById('summary');
  if (!host) return;
  host.innerHTML = '';

  const guests = state.invite.guests;
  const anyAttending = guests.some(g => g.attending);

  if (!anyAttending) {
    host.appendChild(summaryRow(
      tr('Attendance', 'Présence', 'Prezență'),
      tr('Not attending', 'Absent(e)', 'Absent(ă)'),
    ));
  } else {
    guests.forEach(g => {
      const bits = [g.attending ? tr('Coming',
                                     'Présent(e)',
                                     'Prezent(ă)') : tr("Can't come", 'Absent(e)', 'Absent(ă)')];
      if (g.attending) {
        if (g.diet && g.diet !== 'none') bits.push(DIET_LABELS[g.diet]);
        if (g.allergies) bits.push(tr('Allergies', 'Allergies', 'Alergii') + ': ' + g.allergies);
        if (g.choir) bits.push(tr('Would like to sing in the choir',
                                  'Souhaite chanter dans la chorale',
                                  'Dorește să cânte în cor'));
        if (g.brunch) bits.push(tr('Coming to the Sunday brunch',
                                   'Sera au brunch du dimanche',
                                   'Vine la brunch-ul de duminică'));
      }
      host.appendChild(summaryRow(g.name || tr('Your guest',
                                               'Votre accompagnant',
                                               'Însoțitorul dumneavoastră'), bits.join(' · ')));
    });
  }

  if (state.invite.notes) {
    host.appendChild(summaryRow(tr('Comments', 'Commentaires', 'Comentarii'), state.invite.notes));
  }
}

function summaryRow(label, value) {
  const row = document.createElement('div');
  row.className = 'summary-row';
  const l = document.createElement('p');
  l.className = 'summary-label';
  l.textContent = label;
  const v = document.createElement('p');
  v.className = 'summary-value';
  v.textContent = value;
  row.append(l, v);
  return row;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function updateLangLinks(key) {
  document.querySelectorAll('.lang-switcher a').forEach(a => {
    try {
      const url = new URL(a.href);
      if (key) url.searchParams.set('invite', key);
      else     url.searchParams.delete('invite');
      a.href = url.toString();
    } catch (_) {}
  });
}

function goToDetails() {
  renderDetails();
  showScreen('screen-details');
}

/**
 * One yes/no question for everyone coming: a single checkbox when only one
 * person is coming, otherwise one per name.
 */
function renderChecklist(blockId, listId, field, attendees, soloLabel) {
  const block = document.getElementById(blockId);
  const list  = document.getElementById(listId);
  if (!block || !list) return;

  block.hidden = attendees.length === 0;
  list.innerHTML = '';
  attendees.forEach(answer => {
    const label = document.createElement('label');
    label.className = 'choir-item';

    const box = document.createElement('input');
    box.type    = 'checkbox';
    box.checked = !!answer[field];
    box.addEventListener('change', () => { answer[field] = box.checked; });

    const text = document.createElement('span');
    // One invitee needs no name — just the question
    text.textContent = attendees.length === 1
      ? soloLabel
      : (answer.name.trim() || tr('Your guest',
                                  'Votre accompagnant',
                                  'Însoțitorul dumneavoastră'));

    label.append(box, text);
    list.appendChild(label);
  });
}

/** Last step: brunch and choir (when anyone is coming) and a free-text note. */
function goToNotes() {
  const attendees = attendingAnswers();
  renderChecklist('brunch-block', 'brunch-list', 'brunch', attendees,
                  tr('Yes, I will come to the brunch',
                     'Oui, je viendrai au brunch',
                     'Da, voi veni la brunch'));
  renderChecklist('choir-block', 'choir-list', 'choir', attendees,
                  tr('Yes, I would like to sing in the choir',
                     'Oui, je souhaite chanter dans la chorale',
                     'Da, aș dori să cânt în cor'));

  const submit = document.getElementById('btn-submit');
  if (submit) {
    submit.textContent = attendees.length
      ? tr('Confirm attendance', 'Confirmer ma présence', 'Confirmați prezența')
      : tr('Send response', 'Envoyer ma réponse', 'Trimiteți răspunsul');
  }

  showScreen('screen-notes');
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Attributes can't be switched by lang.css, so they are set here
  const keyInput0 = document.getElementById('key-input');
  if (keyInput0) keyInput0.placeholder = tr('Your invite code',
                                            "Votre code d'invitation",
                                            'Codul invitației');
  const notes0 = document.getElementById('notes');
  if (notes0) notes0.placeholder = tr('Comments or notes for us…',
                                      'Commentaires ou remarques pour nous…',
                                      'Comentarii sau mențiuni pentru noi…');
  updateNextLabel();

  const urlKey = cleanKey(new URLSearchParams(window.location.search).get('invite'));

  if (urlKey) {
    updateLangLinks(urlKey);
    fetchInvite(urlKey);
  } else {
    showScreen('screen-key');
  }

  // ── Key screen ──
  const keyInput = document.getElementById('key-input');
  keyInput.addEventListener('input', () => {
    const cleaned = cleanKey(keyInput.value);
    if (cleaned !== keyInput.value) keyInput.value = cleaned;
  });
  document.getElementById('key-submit').addEventListener('click', () => {
    const val = cleanKey(keyInput.value);
    if (!val) return;
    const url = new URL(window.location.href);
    url.searchParams.set('invite', val);
    window.location.href = url.toString();
  });
  keyInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('key-submit').click();
  });

  // ── Single invitee: accept / decline ──
  document.getElementById('btn-yes').addEventListener('click', () => {
    state.answers[0].attending = true;
    goToDetails();
  });
  document.getElementById('btn-no').addEventListener('click', () => {
    state.answers[0].attending = false;
    goToNotes();
  });

  // ── Group invitation: who is coming ──
  document.getElementById('btn-add-guest').addEventListener('click', () => {
    if (extraCount() >= (state.invite.extra_guests_allowed || 0)) return;
    state.answers.push(blankExtra());
    renderAttendance();
  });

  document.getElementById('btn-attendance-next').addEventListener('click', () => {
    const err = document.getElementById('attendance-error');
    const missingName = state.answers.some(a => a.isExtra && a.attending && !a.name.trim());
    if (missingName) {
      if (err) err.textContent = tr('Please enter a name for each additional guest.',
                                    'Merci d’indiquer le nom de chaque personne supplémentaire.',
                                    'Vă rugăm să completați numele fiecărei persoane adăugate.');
      return;
    }
    if (err) err.textContent = '';

    if (attendingAnswers().length) goToDetails();
    else                           goToNotes();
  });

  // ── Meals → choir and comments ──
  document.getElementById('btn-details-next').addEventListener('click', goToNotes);

  // ── Back, on every form step ──
  document.querySelectorAll('.btn-back').forEach(el => el.addEventListener('click', goBack));

  // ── Last screen: submit ──
  document.getElementById('btn-submit').addEventListener('click', submitRSVP);

  // ── Update an existing response ──
  document.querySelectorAll('.btn-update').forEach(el => {
    el.addEventListener('click', () => {
      adoptInvite(state.invite);          // reload the stored answers into the form
      startForm();
    });
  });

  // ── Error: retry ──
  document.getElementById('btn-retry').addEventListener('click', () => {
    if (state.key) fetchInvite(state.key);
    else           showScreen('screen-key');
  });
});
