// ── Config ───────────────────────────────────────────────────────────────────
const API_BASE = (window.RSVP_CONFIG && window.RSVP_CONFIG.apiBase) || 'http://localhost:8000';
const L        = (window.RSVP_CONFIG && window.RSVP_CONFIG.labels)  || {};

const DIETS = ['none', 'vegetarian', 'vegan'];

// answers mirror the guest list while the form is being filled in
const state = { key: null, invite: null, answers: [] };

function t(path, fallback) {
  return path.split('.').reduce((o, k) => (o == null ? o : o[k]), L) ?? fallback;
}

// Codes are printed in uppercase; forgive spaces, dashes and lower case
function cleanKey(raw) {
  return (raw || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

// ── Screen management ────────────────────────────────────────────────────────

function showScreen(id, errorMsg) {
  document.querySelectorAll('.screen').forEach(s => { s.hidden = true; });
  const el = document.getElementById(id);
  if (el) el.hidden = false;
  if (id === 'screen-key') {
    const errEl = document.getElementById('key-error');
    if (errEl) errEl.textContent = errorMsg || '';
  }
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
      const msg = t('invalidKey', 'Invite code not found. Please check and try again.');
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
    showError(t('networkError', 'Unable to connect. Please try again later.'));
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
            })),
        }),
      }
    );
    if (!res.ok) throw new Error('server');

    adoptInvite(await res.json());
    renderSummary();
    showScreen('screen-already');
  } catch (e) {
    showError(t('submitError', 'Failed to submit your response. Please try again.'));
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
  return { id: null, name: '', isExtra: true, attending: false, diet: 'none', allergies: '' };
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
      input.placeholder = t('guestNamePlaceholder', "Guest's name");
      input.value       = answer.name;
      input.setAttribute('aria-label', t('guestNamePlaceholder', "Guest's name"));
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
      remove.title     = t('removeGuest', 'Remove');
      remove.setAttribute('aria-label', t('removeGuest', 'Remove'));
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
    addBtn.textContent = t('addGuest', '+ Add someone');
  }

  const err = document.getElementById('attendance-error');
  if (err) err.textContent = '';

  updateNextLabel();
}

function buildToggle(answer, idx) {
  const wrap = document.createElement('div');
  wrap.className = 'toggle';

  [['yes', t('coming', 'Coming')], ['no', t('notComing', "Can't come")]].forEach(([val, text]) => {
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
  if (!btn) return;
  btn.textContent = attendingAnswers().length
    ? t('continueLabel', 'Continue')
    : t('sendResponse', 'Send response');
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
      name.textContent = answer.name.trim() || t('yourGuest', 'Your guest');
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
      span.textContent = t('diet.' + diet, diet);

      label.append(input, span);
      radios.appendChild(label);
    });
    block.appendChild(radios);

    const allergies = document.createElement('input');
    allergies.type        = 'text';
    allergies.className   = 'dietary-other';
    allergies.placeholder = t('allergiesPlaceholder', 'Allergies…');
    allergies.value       = answer.allergies;
    allergies.setAttribute('aria-label', t('allergiesLabel', 'Allergies'));
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
      t('attendanceLabel', 'Attendance'),
      t('noneAttending', 'Not attending'),
    ));
  } else {
    guests.forEach(g => {
      const bits = [g.attending ? t('coming', 'Coming') : t('notComing', "Can't come")];
      if (g.attending) {
        if (g.diet && g.diet !== 'none') bits.push(t('diet.' + g.diet, g.diet));
        if (g.allergies) bits.push(t('allergiesLabel', 'Allergies') + ': ' + g.allergies);
      }
      host.appendChild(summaryRow(g.name || t('yourGuest', 'Your guest'), bits.join(' · ')));
    });
  }

  if (state.invite.notes) {
    host.appendChild(summaryRow(t('notesLabel', 'Comments'), state.invite.notes));
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

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
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
    submitRSVP();
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
      if (err) err.textContent = t('needGuestName', 'Please enter a name for each additional guest.');
      return;
    }
    if (err) err.textContent = '';

    if (attendingAnswers().length) goToDetails();
    else                           submitRSVP();
  });

  // ── Details: submit ──
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
