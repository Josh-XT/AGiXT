/* Desktop session guard.
 *
 * The web client validates JWTs in middleware before protected routes
 * render and redirects to auth on 401/403. Desktop has no NextJS
 * middleware layer, so this module provides the same centralized
 * behavior for boot checks, core API calls, and desktop extensions.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;

  function appContext() {
    return typeof window.AgixtAppContext === 'function'
      ? window.AgixtAppContext()
      : null;
  }

  function baseUrl() {
    const ctx = appContext();
    return ctx && ctx.serverUrl ? String(ctx.serverUrl).replace(/\/+$/, '') : '';
  }

  function authHeader() {
    const ctx = appContext();
    return ctx && ctx.jwt ? 'Bearer ' + ctx.jwt : '';
  }

  async function parseBody(resp) {
    const text = await resp.text().catch(() => '');
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  function errorMessage(body, status) {
    if (body && typeof body === 'object') {
      const detail = body.detail != null ? body.detail : body.error != null ? body.error : body.message;
      if (detail != null) {
        if (typeof detail === 'string') return detail;
        try { return JSON.stringify(detail); } catch (_) { return String(detail); }
      }
    }
    if (typeof body === 'string' && body.trim()) return body.trim();
    return 'HTTP ' + status;
  }

  async function handleStatus(status, body) {
    if ((status === 401 || status === 403)
        && window.AgixtApp
        && typeof window.AgixtApp.handleAuthExpired === 'function') {
      await window.AgixtApp.handleAuthExpired({ status, body });
      return;
    }
    if (status === 402
        && window.AgixtApp
        && typeof window.AgixtApp.handlePaymentRequired === 'function') {
      await window.AgixtApp.handlePaymentRequired({ status, body });
      return;
    }
    if ((status === 502 || status >= 500)
        && window.AgixtApp
        && typeof window.AgixtApp.handleServerIssue === 'function') {
      await window.AgixtApp.handleServerIssue({ status, body });
    }
  }

  async function request(path, opts) {
    opts = opts || {};
    const resp = await fetchWithSession(path, opts);
    if (resp.status === 204) return null;
    return parseBody(resp);
  }

  async function fetchWithSession(path, opts) {
    opts = opts || {};
    const base = baseUrl();
    if (!base) throw new Error('No AGiXT server URL configured.');
    const url = /^https?:\/\//i.test(path) ? path : base + path;
    const headers = Object.assign({}, opts.headers || {});
    if (!headers.Authorization && authHeader()) headers.Authorization = authHeader();
    const init = {
      method: opts.method || 'GET',
      headers,
      signal: opts.signal,
    };
    if (opts.body !== undefined) {
      init.body = opts.body;
    } else if (opts.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.json);
    }
    const resp = await fetch(url, init);
    const allowed = Array.isArray(opts.allowedStatuses) ? opts.allowedStatuses : [];
    if (!resp.ok && !allowed.includes(resp.status)) {
      const body = await parseBody(resp.clone());
      await handleStatus(resp.status, body);
      const err = new Error(errorMessage(body, resp.status));
      err.status = resp.status;
      err.detail = body;
      throw err;
    }
    return resp;
  }

  async function verifyCurrentSession() {
    const ctx = appContext();
    if (!ctx || !ctx.jwt || !ctx.serverUrl) return false;
    try {
      await request('/v1/user/minimal');
      return true;
    } catch (err) {
      if (err && (err.status === 401 || err.status === 403 || err.status === 402)) {
        return false;
      }
      if (err && err.status >= 500) return true;
      console.warn('desktop-session: verification failed', err);
      return true;
    }
  }

  // Exposed for extensions that must keep their own raw `fetch` for
  // binary downloads, multipart uploads, websocket negotiation, etc.
  // After the response comes back they should call this with the status
  // and (optional) parsed body so the centralized 401/402/5xx handlers
  // still run. Returns true if the response status was handled (so the
  // caller can avoid surfacing a duplicate error toast).
  async function routeFailureStatus(status, body) {
    if (status >= 400 && status !== 404) {
      await handleStatus(status, body);
      return status === 401 || status === 402 || status === 403
        || status === 502 || status >= 500;
    }
    return false;
  }

  window.AgixtSession = {
    request,
    fetch: fetchWithSession,
    fetchJson: request,
    verifyCurrentSession,
    routeFailureStatus,
  };
})();
