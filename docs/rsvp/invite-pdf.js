// Invitation → PDF, for the admin dashboard.
//
// Each invitation becomes one A5 page that mirrors the website's card, plus a
// QR code and the short link to the RSVP page in the invitees' language.
//
// Needs (loaded by admin.html): jsPDF, html2canvas, qrcode.

window.InvitePDF = (function () {
  const LANGUAGES = ['en', 'fr', 'ro'];

  const CHURCH_URL  = 'https://www.allier-auvergne-tourisme.com/xixe-sia-cle/dompierre-sur-besbre/eglise-saint-joseph/4685050';
  const CHATEAU_URL = 'https://www.beauvoir-bourbonnais.fr/accs';

  const STRINGS = {
    en: {
      eyebrow:      'Wedding Invitation',
      addressed:    'We joyfully invite',
      date:         'Saturday, 7 August 2027',
      dateLabel:    'The wedding of',
      ceremony:     { text: 'Ceremony · Église Saint-Joseph, Dompierre-sur-Besbre, France', url: CHURCH_URL },
      reception:    { text: 'Reception · Château de Beauvoir, Bourbonnais, France', url: CHATEAU_URL },
      rsvpTitle:    'Please reply',
      rsvpHint:     'Scan the code, or visit',
      codeLabel:    'Invitation code',
      plusOne:      'and the guest of your choice',
      extras:       n => 'and up to ' + NUMBERS.en[n] + ' ' + (n === 1 ? 'guest' : 'guests') + ' of your choice',
    },
    fr: {
      eyebrow:      'Faire-part de Mariage',
      addressed:    'Nous avons la joie d’inviter',
      date:         'Le samedi 7 août 2027',
      dateLabel:    'Mariage de',
      ceremony:     { text: 'Cérémonie · Église Saint-Joseph, Dompierre-sur-Besbre, France', url: CHURCH_URL },
      reception:    { text: 'Réception · Château de Beauvoir, Bourbonnais, France', url: CHATEAU_URL },
      rsvpTitle:    'Réponse souhaitée',
      rsvpHint:     'Scannez le code, ou rendez-vous sur',
      codeLabel:    'Code d’invitation',
      plusOne:      'et la personne de votre choix',
      extras:       n => 'et jusqu’à ' + NUMBERS.fr[n] + ' personne' + (n === 1 ? '' : 's') + ' de votre choix',
    },
    ro: {
      eyebrow:      'Invitație de Nuntă',
      addressed:    'Avem bucuria de a invita',
      date:         'Sâmbătă, 7 august 2027',
      dateLabel:    'Nunta lui',
      ceremony:     { text: 'Ceremonia · Église Saint-Joseph, Dompierre-sur-Besbre, France', url: CHURCH_URL },
      reception:    { text: 'Recepția · Château de Beauvoir, Bourbonnais, Franța', url: CHATEAU_URL },
      rsvpTitle:    'Vă rugăm să confirmați',
      rsvpHint:     'Scanați codul sau accesați',
      codeLabel:    'Codul invitației',
      plusOne:      'și persoana pe care o doriți',
      extras:       n => 'și încă ' + NUMBERS.ro[n] + ' ' + (n === 1 ? 'persoană' : 'persoane') + ' la alegerea dumneavoastră',
    },
  };

  // Spelled out — "and up to 3 guests" reads like a quota on an invitation
  const NUMBERS = {
    en: [ '', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight' ],
    fr: [ '', 'une', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit' ],
    ro: [ '', 'o', 'două', 'trei', 'patru', 'cinci', 'șase', 'șapte', 'opt' ],
  };

  // What the Email button pre-writes. mailto: cannot carry an attachment, so the
  // message stands on its own: the personal link and code are in the body.
  const EMAIL = {
    en: {
      subject: 'Emma & Theodor — our wedding on 7 August 2027',
      body: (to, url, key) => [
        `Dear ${to},`,
        '',
        'We would be delighted to have you with us on Saturday 7 August 2027,',
        'at the Église Saint-Joseph in Dompierre-sur-Besbre and then at the',
        'Château de Beauvoir. Our invitation is attached.',
        '',
        'Please let us know whether you can join us:',
        url,
        '',
        `Your invitation code is ${key}.`,
        '',
        'With love,',
        'Emma & Theodor',
      ].join('\r\n'),
    },
    fr: {
      subject: 'Emma & Theodor — notre mariage le 7 août 2027',
      body: (to, url, key) => [
        `Cher/Chère ${to},`,
        '',
        'Nous serions très heureux de vous compter parmi nous le samedi 7 août 2027,',
        'à l’Église Saint-Joseph de Dompierre-sur-Besbre puis au Château de Beauvoir.',
        'Vous trouverez notre faire-part en pièce jointe.',
        '',
        'Merci de nous indiquer si vous pourrez être des nôtres :',
        url,
        '',
        `Votre code d’invitation est ${key}.`,
        '',
        'Avec toute notre affection,',
        'Emma & Theodor',
      ].join('\r\n'),
    },
    ro: {
      subject: 'Emma & Theodor — nunta noastră, 7 august 2027',
      body: (to, url, key) => [
        `Dragă ${to},`,
        '',
        'Ne-ar face mare bucurie să fiți alături de noi sâmbătă, 7 august 2027,',
        'la Église Saint-Joseph din Dompierre-sur-Besbre și apoi la Château de Beauvoir.',
        'Invitația noastră este atașată.',
        '',
        'Vă rugăm să ne spuneți dacă puteți veni:',
        url,
        '',
        `Codul invitației dumneavoastră este ${key}.`,
        '',
        'Cu drag,',
        'Emma & Theodor',
      ].join('\r\n'),
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
      const list = el('div', 'ic-guest-list');
      listed.forEach(name => list.appendChild(el('p', 'ic-guest-name', name)));
      card.appendChild(list);
    }
    const note = extraNote(invite, s);
    if (note) card.appendChild(el('p', 'ic-extra-note', note));

    const details = el('div', 'ic-details');
    details.appendChild(el('p', 'ic-detail-value', s.date));
    [s.ceremony, s.reception].forEach(venue => {
      const line = el('p', 'ic-detail-value', venue.text);
      // Picked up after rasterising and turned into a PDF link annotation
      line.dataset.pdfLink = venue.url;
      details.appendChild(line);
    });
    card.appendChild(details);

    card.appendChild(el('div', 'ic-spacer'));
    card.appendChild(el('div', 'ic-divider', '✦'));

    const rsvp = el('div', 'ic-rsvp');
    rsvp.dataset.pdfLink = rsvpUrl(invite.key, lang, o.baseUrl);
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

  /**
   * A ready-to-send message for one invitation.
   * Returns { subject, body, mailto } — no attachment: mailto: has no way to
   * carry one, so the caller saves the PDF for the sender to attach.
   */
  function emailDraft(invite, opts) {
    const o    = opts || {};
    const lang = langOf(invite, o.lang);
    const text = EMAIL[lang];
    const url  = rsvpUrl(invite.key, lang, o.baseUrl);

    const subject = text.subject;
    const body    = text.body(addressee(invite), url, invite.key);
    const to      = (invite.email || '').trim();

    return {
      subject,
      body,
      mailto: 'mailto:' + encodeURIComponent(to)
        + '?subject=' + encodeURIComponent(subject)
        + '&body=' + encodeURIComponent(body),
    };
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

  /** Room left between the last block and the card's bottom padding, in px. */
  function contentSlack(card) {
    const box  = card.getBoundingClientRect();
    const last = card.querySelector('.ic-rsvp').getBoundingClientRect();
    return box.bottom - parseFloat(getComputedStyle(card).paddingBottom) - last.bottom;
  }

  /** A household of ten would run off the page — tighten it up until it fits. */
  function fitCard(card) {
    const list = card.querySelector('.ic-guest-list');
    if (list) {
      for (let size = 16; size >= 10 && contentSlack(card) < 0; size--) {
        list.style.fontSize = size + 'px';
        if (size <= 14) list.style.gap = '1px';
      }
    }
    const details = card.querySelector('.ic-details');
    if (details) {
      for (let gap = 14; gap >= 6 && contentSlack(card) < 0; gap -= 2) {
        details.style.gap = gap + 'px';
        details.style.marginTop = (gap + 6) + 'px';
      }
    }
  }

  /** Turn every [data-pdf-link] element into a clickable area on the current page. */
  function addLinks(doc, card, pageW, pageH) {
    const box = card.getBoundingClientRect();
    const toMmX = px => (px / box.width) * pageW;
    const toMmY = px => (px / box.height) * pageH;

    card.querySelectorAll('[data-pdf-link]').forEach(node => {
      const r = node.getBoundingClientRect();
      doc.link(
        toMmX(r.left - box.left),
        toMmY(r.top - box.top),
        toMmX(r.width),
        toMmY(r.height),
        { url: node.dataset.pdfLink }
      );
    });
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
        fitCard(card);              // needs layout, so only once it is on the page

        const canvas = await window.html2canvas(card, {
          scale: scale,
          backgroundColor: '#faf6ef',
          logging: false,
          width: card.offsetWidth,
          height: card.offsetHeight,
        });

        if (i > 0) doc.addPage();
        doc.addImage(canvas.toDataURL('image/jpeg', 0.94), 'JPEG', 0, 0, pageW, pageH);
        addLinks(doc, card, pageW, pageH);

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
    LANGUAGES, STRINGS, EMAIL, buildCard, fitCard, renderPdf, download, fileNameFor, emailDraft,
    rsvpUrl, prettyUrl, prettyBase, addressee,
  };
})();
