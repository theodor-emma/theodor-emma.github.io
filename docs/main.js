const WEDDING_DATE = new Date('2027-08-07T14:00:00');

function pad(n) { return String(n).padStart(2, '0'); }

// ── Countdown ────────────────────────────────────────────────────────────────

function initCountdown() {
  const el = document.getElementById('countdown');
  if (!el) return;

  const today = window.WEDDING_CONFIG?.labels?.today || 'Today is the day! ✦';

  function tick() {
    const now  = new Date();
    const diff = WEDDING_DATE - now;
    if (diff <= 0) {
      el.innerHTML = `<p style="font-style:italic;color:var(--gold)">${today}</p>`;
      return;
    }

    const days    = Math.floor(diff / 86400000);
    const hours   = Math.floor((diff % 86400000) / 3600000);
    const minutes = Math.floor((diff % 3600000)  / 60000);
    const seconds = Math.floor((diff % 60000)    / 1000);

    document.getElementById('cd-days').textContent    = days;
    document.getElementById('cd-hours').textContent   = pad(hours);
    document.getElementById('cd-minutes').textContent = pad(minutes);
    document.getElementById('cd-seconds').textContent = pad(seconds);
  }

  tick();
  setInterval(tick, 1000);
}

// ── Add to Calendar ───────────────────────────────────────────────────────────

/** Escape a text value for an .ics file (RFC 5545). */
function icsText(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n');
}

function icsStamp(date) {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '');
}

/**
 * Fold a line to 75 octets, as the spec asks. Accented characters take two
 * octets, and a cut must never fall between a backslash and what it escapes.
 */
function icsFold(line) {
  const bytes = text => new TextEncoder().encode(text).length;
  const parts = [];
  let rest = line;

  while (bytes(rest) > 75) {
    let cut = 75;
    while (cut > 1 && (bytes(rest.slice(0, cut)) > 75 || rest[cut - 1] === '\\')) cut--;
    parts.push(rest.slice(0, cut));
    rest = ' ' + rest.slice(cut);   // continuation lines begin with a space
  }
  parts.push(rest);
  return parts.join('\r\n');
}


function initCalendar() {
  const container = document.getElementById('calendar-container');
  if (!container) return;

  const labels = window.WEDDING_CONFIG?.labels || {};

  // Everything the guest will read comes from the page's own labels
  const eventTitle    = labels.calendarTitle   || 'Wedding of Emma Chirlomez & Theodor Moroianu';
  const eventDetails  = labels.calendarDetails || eventTitle;
  const eventLocation = 'Château de Beauvoir, Bourbonnais, France';
  const eventUrl      = 'https://www.beauvoir-bourbonnais.fr/';

  const googleUrl = 'https://calendar.google.com/calendar/render?action=TEMPLATE'
    + '&text='     + encodeURIComponent(eventTitle)
    + '&dates=20270807/20270809'
    + '&details='  + encodeURIComponent(eventDetails)
    + '&location=' + encodeURIComponent(eventLocation);

  const icsLines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Theodor & Emma//Wedding//EN',
    'BEGIN:VEVENT',
    // A stable id, so re-importing updates the event instead of duplicating it
    'UID:emma-theodor-wedding-20270807@theodor-emma.fr',
    'DTSTAMP:' + icsStamp(new Date()),
    'DTSTART;VALUE=DATE:20270807',
    'DTEND;VALUE=DATE:20270809',
    'SUMMARY:' + icsText(eventTitle),
    'DESCRIPTION:' + icsText(eventDetails),
    'LOCATION:' + icsText(eventLocation),
    'URL:' + eventUrl,
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  const icsBlob = new Blob([icsLines.map(icsFold).join('\r\n')], { type: 'text/calendar;charset=utf-8' });
  const icsUrl  = URL.createObjectURL(icsBlob);

  container.innerHTML = `
    <div class="calendar-wrap">
      <button class="calendar-btn" id="cal-btn">${labels.addToCalendar || 'Add to Calendar'}</button>
      <div class="calendar-dropdown" id="cal-dropdown">
        <a href="${googleUrl}" target="_blank" rel="noopener">${labels.googleCalendar || 'Google Calendar'}</a>
        <a href="${icsUrl}" download="theodor-emma-wedding.ics">${labels.appleOutlook || 'Apple / Outlook (.ics)'}</a>
      </div>
    </div>
  `;

  const btn      = document.getElementById('cal-btn');
  const dropdown = document.getElementById('cal-dropdown');

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('open');
  });
  document.addEventListener('click', () => dropdown.classList.remove('open'));
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initCountdown();
  initCalendar();
});
