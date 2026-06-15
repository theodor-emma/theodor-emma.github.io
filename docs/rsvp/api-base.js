// Resolves the backend API base URL from the current hostname.
//   localhost / 127.0.0.1   → http://localhost:8000
//   private LAN IP          → http://<same-host>:8000   (dev on another device)
//   anything else (domain)  → https://api-rsvp.theodor-emma.fr
window.API_BASE = (function () {
  const h = window.location.hostname;

  if (h === 'localhost' || h === '127.0.0.1') {
    return 'http://localhost:8000';
  }

  const isPrivateIP =
    /^10\./.test(h) ||
    /^192\.168\./.test(h) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(h);

  if (isPrivateIP) {
    return 'http://' + h + ':8000';
  }

  return 'https://api-rsvp.theodor-emma.fr';
})();
