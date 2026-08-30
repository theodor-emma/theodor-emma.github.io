// Invitation → PDF, for the admin dashboard.
//
// Each invitation becomes one A5 page that mirrors the website's card, plus a
// QR code and the short link to the RSVP page in the invitees' language.
//
// Needs (loaded by admin.html): jsPDF, html2canvas, qrcode.

window.InvitePDF = (function () {
  const LANGUAGES = ['en', 'fr', 'ro'];

  const STRINGS = {
    en: {
      eyebrow:      'Wedding Invitation',
      addressed:    'We joyfully invite',
      date:         'Saturday, 7 August 2027',
      dateLabel:    'The wedding of',
      ceremony:     'Ceremony · to be announced',
      reception:    'Reception · Château de Beauvoir, Bourbonnais, France',
      rsvpTitle:    'Please reply',
      rsvpHint:     'Scan the code, or visit',
      codeLabel:    'Invitation code',
      plusOne:      'You are welcome to bring a guest',
      extras:       n => `You may bring up to ${n} more ${n === 1 ? 'person' : 'people'}`,
    },
    fr: {
      eyebrow:      'Faire-part de Mariage',
      addressed:    'Nous avons la joie d’inviter',
      date:         'Le samedi 7 août 2027',
      dateLabel:    'Mariage de',
      ceremony:     'Cérémonie · à confirmer',
      reception:    'Réception · Château de Beauvoir, Bourbonnais, France',
      rsvpTitle:    'Réponse souhaitée',
      rsvpHint:     'Scannez le code, ou rendez-vous sur',
      codeLabel:    'Code d’invitation',
      plusOne:      'Vous pouvez venir accompagné(e)',
      extras:       n => `Vous pouvez venir avec ${n} personne${n === 1 ? '' : 's'} de plus`,
    },
    ro: {
      eyebrow:      'Invitație de Nuntă',
      addressed:    'Avem bucuria de a invita',
      date:         'Sâmbătă, 7 august 2027',
      dateLabel:    'Nunta lui',
      ceremony:     'Ceremonia · de confirmat',
      reception:    'Recepția · Château de Beauvoir, Bourbonnais, Franța',
      rsvpTitle:    'Vă rugăm să confirmați',
      rsvpHint:     'Scanați codul sau accesați',
      codeLabel:    'Codul invitației',
      plusOne:      'Puteți veni însoțit(ă)',
      extras:       n => `Puteți veni cu ${n} ${n === 1 ? 'persoană' : 'persoane'} în plus`,
    },
  };

  // ── Links ──────────────────────────────────────────────────────────────────

  function normalizeBase(baseUrl) {
    const base = (baseUrl || 'https://theodor-emma.fr/rsvp/').trim();
    return base.endsWith('/') ? base : base + '/';
  }

  function rsvpUrl(key, lang, baseUrl) {
    const page = lang === 'fr' ? 'fr.html' : lang === 'ro' ? 'ro.html' : '';
    return normalizeBase(baseUrl) + page + '?invite=' + encodeURIComponent(key);
  }

  function prettyUrl(key, lang, baseUrl) {
    return rsvpUrl(key, lang, baseUrl).replace(/^https?:\/\//, '');
  }

  /** Short address to print — guests type this and then enter their code. */
  function prettyBase(baseUrl) {
    return normalizeBase(baseUrl).replace(/^https?:\/\//, '').replace(/\/$/, '');
  }

  // ── Card ───────────────────────────────────────────────────────────────────

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function langOf(invite, override) {
    if (LANGUAGES.includes(override)) return override;
    return LANGUAGES.includes(invite.language) ? invite.language : 'en';
  }

  function hostGuestNames(invite) {
    return (invite.guests || [])
      .filter(g => g.source !== 'guest' && g.name)
      .map(g => g.name);
  }

  function addressee(invite) {
    if (invite.label) return invite.label;
    if (invite.display_label) return invite.display_label;
    const names = hostGuestNames(invite);
    if (!names.length) return '—';
    if (names.length === 1) return names[0];
    return names.slice(0, -1).join(', ') + ' & ' + names[names.length - 1];
  }

  function extraNote(invite, s) {
    const allowed = invite.extra_guests_allowed || 0;
    if (!allowed) return '';
    if (invite.invite_type === 'plus_one') return s.plusOne;
    return s.extras(allowed);
  }

  /** Build the invitation card element. `qrDataUrl` may be null (no QR drawn). */
  function buildCard(invite, opts) {
    const o    = opts || {};
    const lang = langOf(invite, o.lang);
    const s    = STRINGS[lang];

    const card = el('div', 'invite-card');
    card.setAttribute('lang', lang);
    card.appendChild(el('div', 'ic-frame'));
    ['tl', 'tr', 'bl', 'br'].forEach(c => card.appendChild(el('span', 'ic-corner ' + c)));

    card.appendChild(el('p', 'ic-eyebrow', s.eyebrow));
    card.appendChild(el('div', 'ic-divider', '✦'));

    card.appendChild(el('p', 'ic-label', s.dateLabel));
    const names = el('p', 'ic-names');
    names.appendChild(document.createTextNode('Emma Chirlomez'));
    names.appendChild(el('span', 'ic-amp', '&'));
    names.appendChild(document.createTextNode('Theodor Moroianu'));
    card.appendChild(names);

    card.appendChild(el('div', 'ic-divider', '✦'));
    card.appendChild(el('div', 'ic-spacer'));

    card.appendChild(el('p', 'ic-label', s.addressed));
    card.appendChild(el('p', 'ic-addressed', addressee(invite)));

    const listed = hostGuestNames(invite);
    if (invite.label && listed.length) {
      card.appendChild(el('p', 'ic-guest-list', listed.join(' · ')));
    }
    const note = extraNote(invite, s);
    if (note) card.appendChild(el('p', 'ic-extra-note', note));

    const details = el('div', 'ic-details');
    details.appendChild(el('p', 'ic-detail-value', s.date));
    details.appendChild(el('p', 'ic-detail-value', s.ceremony));
    details.appendChild(el('p', 'ic-detail-value', s.reception));
    card.appendChild(details);

    card.appendChild(el('div', 'ic-spacer'));
    card.appendChild(el('div', 'ic-divider', '✦'));

    const rsvp = el('div', 'ic-rsvp');
    if (o.qrDataUrl) {
      const img = document.createElement('img');
      img.className = 'ic-qr';
      img.src = o.qrDataUrl;
      img.alt = '';
      rsvp.appendChild(img);
    }
    const text = el('div', 'ic-rsvp-text');
    text.appendChild(el('p', 'ic-rsvp-title', s.rsvpTitle));
    text.appendChild(el('p', 'ic-rsvp-hint', s.rsvpHint));
    text.appendChild(el('p', 'ic-rsvp-url', prettyBase(o.baseUrl)));
    text.appendChild(el('p', 'ic-label', s.codeLabel));
    text.appendChild(el('p', 'ic-code', invite.key));
    rsvp.appendChild(text);
    card.appendChild(rsvp);

    return card;
  }

  // ── Rendering ──────────────────────────────────────────────────────────────

  function requireLibs() {
    const missing = [];
    if (!window.jspdf || !window.jspdf.jsPDF) missing.push('jsPDF');
    if (!window.html2canvas)                  missing.push('html2canvas');
    if (!window.QRCode)                       missing.push('qrcode');
    if (missing.length) throw new Error('Missing libraries: ' + missing.join(', '));
  }

  function qrFor(url) {
    return window.QRCode.toDataURL(url, {
      margin: 1,
      width: 480,
      errorCorrectionLevel: 'M',
      color: { dark: '#2c2416ff', light: '#faf6efff' },
    });
  }

  function stage() {
    let host = document.getElementById('invite-pdf-stage');
    if (!host) {
      host = document.createElement('div');
      host.id = 'invite-pdf-stage';
      host.setAttribute('aria-hidden', 'true');
      // Off-screen but laid out — html2canvas needs real geometry
      host.style.cssText = 'position:fixed;left:-20000px;top:0;width:720px;z-index:-1;';
      document.body.appendChild(host);
    }
    host.innerHTML = '';
    return host;
  }

  function slug(text) {
    return (text || '')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .toLowerCase()
      .slice(0, 40) || 'invitation';
  }

  function fileNameFor(invite) {
    return `invitation-${slug(addressee(invite))}-${invite.key}.pdf`;
  }

  /**
   * Render invitations into a single PDF (one A5 page each).
   * opts: { lang, baseUrl, scale, onProgress(done, total) }
   */
  async function renderPdf(invites, opts) {
    requireLibs();
    const o     = opts || {};
    const scale = o.scale || 2;
    const host  = stage();

    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (_) {}
    }

    const doc = new window.jspdf.jsPDF({ unit: 'mm', format: 'a5', orientation: 'portrait' });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();

    try {
      for (let i = 0; i < invites.length; i++) {
        const invite = invites[i];
        const lang   = langOf(invite, o.lang);
        const url    = rsvpUrl(invite.key, lang, o.baseUrl);
        const qr     = await qrFor(url);

        const card = buildCard(invite, { lang, baseUrl: o.baseUrl, qrDataUrl: qr });
        host.innerHTML = '';
        host.appendChild(card);

        const canvas = await window.html2canvas(card, {
          scale: scale,
          backgroundColor: '#faf6ef',
          logging: false,
          width: card.offsetWidth,
          height: card.offsetHeight,
        });

        if (i > 0) doc.addPage();
        doc.addImage(canvas.toDataURL('image/jpeg', 0.94), 'JPEG', 0, 0, pageW, pageH);
        // Keep the RSVP address clickable in the digital copy
        doc.link(0, pageH - 42, pageW, 42, { url: url });

        if (o.onProgress) o.onProgress(i + 1, invites.length);
      }
    } finally {
      host.innerHTML = '';
    }

    return doc;
  }

  /** Render and save. One invitation → named file; several → a single booklet. */
  async function download(invites, opts) {
    const list = Array.isArray(invites) ? invites : [invites];
    if (!list.length) return;
    const doc = await renderPdf(list, opts);
    doc.save(list.length === 1 ? fileNameFor(list[0]) : 'invitations.pdf');
  }

  return {
    LANGUAGES, STRINGS, buildCard, renderPdf, download, fileNameFor,
    rsvpUrl, prettyUrl, prettyBase, addressee,
  };
})();
