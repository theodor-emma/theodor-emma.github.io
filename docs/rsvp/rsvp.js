// ── Config ───────────────────────────────────────────────────────────────────
const API_BASE = (window.RSVP_CONFIG && window.RSVP_CONFIG.apiBase) || 'http://localhost:8000';
const L        = (window.RSVP_CONFIG && window.RSVP_CONFIG.labels)  || {};

const state = { key: null, name: null, plusOne: false };

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

// ── API ───────────────────────────────────────────────────────────────────────

async function fetchInvite(key) {
  const keyIsFromUrl = new URLSearchParams(window.location.search).get('invite') === key;
  showScreen('screen-loading');
  try {
    const res = await fetch(API_BASE + '/invite/' + encodeURIComponent(key));
    if (res.status === 404) {
      if (keyIsFromUrl) {
        showScreen('screen-error');
        document.getElementById('error-text').textContent =
          L.invalidKey || 'Invite code not found. Please check your invitation.';
      } else {
        showScreen('screen-key', L.invalidKey || 'Invite code not found. Please check and try again.');
      }
      return;
    }
    if (!res.ok) throw new Error('server');

    const data = await res.json();
    state.key  = key;
    state.name = data.name;

    updateLangLinks(key);
    document.querySelectorAll('.guest-name').forEach(el => el.textContent = data.name);

    if (data.responded) {
      populatePrevResponse(data);
      showScreen('screen-already');
    } else {
      showScreen('screen-question');
    }
  } catch (e) {
    showScreen('screen-error');
    document.getElementById('error-text').textContent =
      L.networkError || 'Unable to connect. Please try again later.';
  }
}

async function submitRSVP(attending) {
  showScreen('screen-loading');
  const dietary      = collectDietary();
  const comments     = collectComments();
  const plusOneName  = (document.getElementById('plus-one-name') || {}).value || '';
  const plusOneDiet  = collectPlusOneDietary();

  try {
    const res = await fetch(
      API_BASE + '/invite/' + encodeURIComponent(state.key) + '/rsvp',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          attending:            attending,
          dietary_restrictions: dietary,
          notes:                comments,
          plus_one:             attending ? state.plusOne : false,
          plus_one_name:        attending ? plusOneName.trim() : '',
          plus_one_dietary:     attending ? plusOneDiet.trim() : '',
        }),
      }
    );
    if (!res.ok) throw new Error('server');
    window.location.reload();
  } catch (e) {
    showScreen('screen-error');
    document.getElementById('error-text').textContent =
      L.submitError || 'Failed to submit. Please try again.';
  }
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

function populatePrevResponse(data) {
  const attendingEl = document.getElementById('prev-attending');
  if (attendingEl) attendingEl.textContent = data.attending ? (L.yes || 'Yes') : (L.no || 'No');

  const dietWrap = document.getElementById('prev-dietary-wrap');
  const dietEl   = document.getElementById('prev-dietary');
  if (dietWrap && dietEl) {
    dietEl.textContent = (data.attending && data.dietary_restrictions)
      ? data.dietary_restrictions
      : (L.noDietary || 'No restrictions');
    dietWrap.hidden = false;
  }

  const commentsWrap = document.getElementById('prev-comments-wrap');
  const commentsEl   = document.getElementById('prev-comments');
  if (commentsWrap && commentsEl) {
    const show = data.notes && data.notes.trim();
    commentsEl.textContent = show ? data.notes : '';
    commentsWrap.hidden = !show;
  }

  // +1
  const plusOneWrap = document.getElementById('prev-plus-one-wrap');
  if (plusOneWrap) {
    plusOneWrap.hidden = !data.attending;
    const plusOneEl   = document.getElementById('prev-plus-one');
    if (plusOneEl) plusOneEl.textContent = data.plus_one ? (data.plus_one_name || (L.yes || 'Yes')) : (L.no || 'No');
    const plusOneDietWrap = document.getElementById('prev-plus-one-dietary-wrap');
    const plusOneDietEl   = document.getElementById('prev-plus-one-dietary');
    if (plusOneDietWrap && plusOneDietEl) {
      plusOneDietEl.textContent = (data.plus_one && data.plus_one_dietary)
        ? data.plus_one_dietary
        : (L.noDietary || 'No restrictions');
      plusOneDietWrap.hidden = !data.plus_one;
    }
  }
}

function initDietaryLabels() {
  const map = L.dietary || {};
  document.querySelectorAll('.dietary-check-group .check-item').forEach(label => {
    const key  = label.dataset.key;
    const text = map[key] || key;
    label.querySelector('input').value      = text;
    label.querySelector('span').textContent = text;
  });
}

function collectDietary() {
  const checked = Array.from(
    document.querySelectorAll('#dietary-checks input:checked')
  ).map(cb => cb.value);
  const other = (document.getElementById('dietary-other') || {}).value || '';
  if (other.trim()) checked.push(other.trim());
  return checked.join(', ');
}

function collectPlusOneDietary() {
  const checked = Array.from(
    document.querySelectorAll('#dietary-checks-plus-one input:checked')
  ).map(cb => cb.value);
  const other = (document.getElementById('dietary-other-plus-one') || {}).value || '';
  if (other.trim()) checked.push(other.trim());
  return checked.join(', ');
}

function collectComments() {
  return ((document.getElementById('dietary-comments') || {}).value || '').trim();
}

function showPlusOneDietarySection(show) {
  const section = document.getElementById('plus-one-dietary-section');
  if (section) section.hidden = !show;
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const urlKey = params.get('invite');

  initDietaryLabels();

  if (urlKey) {
    updateLangLinks(urlKey);
    fetchInvite(urlKey);
  } else {
    showScreen('screen-key');
  }

  // ── Key screen ──
  document.getElementById('key-submit').addEventListener('click', () => {
    const val = (document.getElementById('key-input').value || '').trim();
    if (!val) return;
    const url = new URL(window.location.href);
    url.searchParams.set('invite', val);
    window.location.href = url.toString();
  });
  document.getElementById('key-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('key-submit').click();
  });

  // ── Attending: Yes → plus-one screen ──
  document.getElementById('btn-yes').addEventListener('click', () => {
    showScreen('screen-plus-one');
  });

  // ── Attending: No ──
  document.getElementById('btn-no').addEventListener('click', () => {
    state.plusOne = false;
    submitRSVP(false);
  });

  // ── Plus-one: yes ──
  document.getElementById('btn-plus-one-yes').addEventListener('click', () => {
    state.plusOne = true;
    showPlusOneDietarySection(true);
    showScreen('screen-dietary');
  });

  // ── Plus-one: no ──
  document.getElementById('btn-plus-one-no').addEventListener('click', () => {
    state.plusOne = false;
    showPlusOneDietarySection(false);
    showScreen('screen-dietary');
  });

  // ── Dietary: submit ──
  document.getElementById('btn-dietary-submit').addEventListener('click', () => {
    submitRSVP(true);
  });

  // ── Update response ──
  document.querySelectorAll('.btn-update').forEach(el => {
    el.addEventListener('click', () => showScreen('screen-question'));
  });

  // ── Error: retry ──
  document.getElementById('btn-retry').addEventListener('click', () => {
    if (state.key) fetchInvite(state.key);
    else           showScreen('screen-key');
  });
});
