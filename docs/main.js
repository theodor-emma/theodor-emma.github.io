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

function initCalendar() {
  const container = document.getElementById('calendar-container');
  if (!container) return;

  const labels = window.WEDDING_CONFIG?.labels || {};

  const eventTitle    = 'Mariage — Theodor Moroianu & Emma Chirlomez';
  const eventDetails  = labels.calendarDetails || 'Wedding of Theodor Moroianu & Emma Chirlomez';
  const eventLocation = 'Château de Beauvoir, Bourbonnais, France';

  const googleUrl = 'https://calendar.google.com/calendar/render?action=TEMPLATE'
    + '&text='     + encodeURIComponent(eventTitle)
    + '&dates=20270807T140000/20270807T230000'
    + '&details='  + encodeURIComponent(eventDetails)
    + '&location=' + encodeURIComponent(eventLocation);

  const icsLines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Theodor & Emma//Wedding//EN',
    'BEGIN:VEVENT',
    'DTSTART;TZID=Europe/Paris:20270807T140000',
    'DTEND;TZID=Europe/Paris:20270807T230000',
    'SUMMARY:Mariage — Theodor Moroianu & Emma Chirlomez',
    'LOCATION:Château de Beauvoir\\, Bourbonnais\\, France',
    'URL:https://www.beauvoir-bourbonnais.fr/accs',
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  const icsBlob = new Blob([icsLines.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
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
