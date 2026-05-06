/* Thin AGiXT REST helper used by the agent-settings window.
 *
 * All calls hit `${settings.server_url}/v1/...` with `Authorization: Bearer
 * ${settings.jwt}`. Settings are loaded once via `invoke('get_settings')` and
 * cached for the lifetime of the window — the user's chosen agent comes from
 * `settings.agent_id` set by the topbar agent switcher in the main window.
 *
 * Decisions to call out for future maintainers:
 *   - We use `Bearer` prefix everywhere (matches existing chat.js + voice
 *     code). The web client uses raw JWT in some places; AGiXT accepts both.
 *   - When the server returns `{detail: "..."}` for a 4xx we surface
 *     `detail`; otherwise we surface the body text or status.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    console.error('agixt-api.js: Tauri IPC unavailable');
    return;
  }
  const invoke = tauri.core.invoke;

  let cachedSettings = null;
  let settingsPromise = null;

  async function getSettings() {
    if (cachedSettings) return cachedSettings;
    if (!settingsPromise) {
      settingsPromise = invoke('get_settings').then((s) => {
        cachedSettings = s;
        return s;
      });
    }
    return settingsPromise;
  }

  /** Force a refresh from disk — call this when settings might've changed
   *  (e.g. after the user switched agents in the main window). */
  async function refreshSettings() {
    cachedSettings = null;
    settingsPromise = null;
    return getSettings();
  }

  function trimSlashes(url) {
    return (url || '').replace(/\/+$/, '');
  }

  async function authHeaders(extra) {
    const s = await getSettings();
    const headers = { Authorization: 'Bearer ' + (s.jwt || '') };
    if (extra) Object.assign(headers, extra);
    return headers;
  }

  async function apiBase() {
    const s = await getSettings();
    return trimSlashes(s.server_url);
  }

  async function parseError(resp) {
    let detail = '';
    try {
      const body = await resp.text();
      try {
        const j = JSON.parse(body);
        detail = j.detail || j.error || j.message || body;
      } catch (_) {
        detail = body;
      }
    } catch (_) {
      detail = '';
    }
    const msg = detail || `HTTP ${resp.status}`;
    const err = new Error(msg);
    err.status = resp.status;
    err.detail = detail;
    return err;
  }

  async function request(method, path, opts) {
    opts = opts || {};
    const base = await apiBase();
    const url = base + path;
    const headers = await authHeaders(opts.headers);
    const init = { method, headers };
    if (opts.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    }
    const resp = await fetch(url, init);
    if (!resp.ok) throw await parseError(resp);
    if (resp.status === 204) return null;
    const text = await resp.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  // ----- Agent + extensions ------------------------------------------------

  /** GET /v1/agent/{id}/extensions
   *  Returns: { extensions: [{ extension_name, friendly_name, description,
   *    settings: [...], commands: [{ command_name, friendly_name, enabled, ... }],
   *    category, category_description }, ...] }
   */
  async function getAgentExtensions(agentId) {
    const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/extensions');
    const arr = (data && (data.extensions || data)) || [];
    return Array.isArray(arr) ? arr : [];
  }

  /** PATCH /v1/agent/{id}/command — enable/disable one command. */
  async function toggleCommand(agentId, commandName, enable) {
    return request('PATCH', '/v1/agent/' + encodeURIComponent(agentId) + '/command', {
      body: { command_name: commandName, enable: !!enable },
    });
  }

  /** PATCH /v1/agent/{id}/extension/commands — bulk enable/disable every
   *  command in an extension. */
  async function bulkToggleExtension(agentId, extensionName, enable) {
    return request(
      'PATCH',
      '/v1/agent/' + encodeURIComponent(agentId) + '/extension/commands',
      { body: { extension_name: extensionName, enable: !!enable } },
    );
  }

  /** PUT /v1/agent/{id} — update agent settings (key/value map). */
  async function updateAgentSettings(agentId, settingsMap) {
    return request('PUT', '/v1/agent/' + encodeURIComponent(agentId), {
      body: { settings: settingsMap },
    });
  }

  // ----- OAuth providers ---------------------------------------------------

  /** GET /v1/oauth — list of configured OAuth providers, with `client_id`
   *  populated only for providers the server has credentials for. */
  async function getOAuthProviders() {
    const data = await request('GET', '/v1/oauth');
    const arr = (data && (data.providers || data)) || [];
    return Array.isArray(arr) ? arr : [];
  }

  /** GET /v1/oauth2 — same shape as /v1/oauth but used for connection state
   *  (which providers the *user* is currently connected to). The two paths
   *  return the same payload — the only thing that differs is that
   *  authenticated /v1/oauth2 attaches per-provider connection metadata if
   *  the backend exposes it. We treat them as interchangeable. */
  async function getUserOAuthConnections() {
    try {
      return await request('GET', '/v1/oauth2');
    } catch (_) {
      return null;
    }
  }

  /** DELETE /v1/oauth2/{provider} — disconnect a provider. */
  async function disconnectOAuth(providerSlug) {
    return request('DELETE', '/v1/oauth2/' + encodeURIComponent(providerSlug));
  }

  // ----- Training ----------------------------------------------------------

  /** GET /v1/agent/{id}/persona → { message: "..." }  ("None" → empty). */
  async function getPersona(agentId) {
    try {
      const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/persona');
      const msg = (data && data.message) || '';
      return msg === 'None' ? '' : msg;
    } catch (e) {
      // 404 etc — treat as empty so the editor still works.
      return '';
    }
  }

  /** PUT /v1/agent/{id}/persona — set the mandatory context. */
  async function setPersona(agentId, persona) {
    return request('PUT', '/v1/agent/' + encodeURIComponent(agentId) + '/persona', {
      body: { persona: persona || '' },
    });
  }

  /** GET /v1/agent/{id}/memory/external_sources/0 → { external_sources: [...] }. */
  async function listTrainingSources(agentId) {
    try {
      const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/memory/external_sources/0');
      const arr = (data && data.external_sources) || [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  /** POST /v1/agent/{id}/learn/file — upload a base64-encoded file. */
  async function learnFile(agentId, fileName, base64Content) {
    return request('POST', '/v1/agent/' + encodeURIComponent(agentId) + '/learn/file', {
      body: {
        file_name: fileName,
        file_content: base64Content,
        collection_number: '0',
      },
    });
  }

  /** POST /v1/agent/{id}/learn/url. */
  async function learnUrl(agentId, url) {
    return request('POST', '/v1/agent/' + encodeURIComponent(agentId) + '/learn/url', {
      body: { url },
    });
  }

  /** DELETE /v1/agent/{id}/memories/external_source — remove a source. */
  async function deleteSource(agentId, source) {
    const base = await apiBase();
    const url = base + '/v1/agent/' + encodeURIComponent(agentId) + '/memories/external_source';
    const headers = await authHeaders({ 'Content-Type': 'application/json' });
    const resp = await fetch(url, {
      method: 'DELETE',
      headers,
      body: JSON.stringify({
        external_source: source,
        collection_number: '0',
      }),
    });
    if (!resp.ok) throw await parseError(resp);
    return null;
  }

  // ----- Helpers exported for the tab modules ------------------------------

  /** Read a File object as base64 (without the data: prefix). Reports
   *  load progress 0-100 via onProgress. */
  function readFileAsBase64(file, onProgress) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const r = reader.result;
        const idx = typeof r === 'string' ? r.indexOf(',') : -1;
        resolve(idx >= 0 ? r.slice(idx + 1) : r);
      };
      reader.onerror = () => reject(reader.error || new Error('file read failed'));
      reader.onprogress = (ev) => {
        if (ev.lengthComputable && typeof onProgress === 'function') {
          onProgress(Math.round((ev.loaded * 100) / ev.total));
        }
      };
      reader.readAsDataURL(file);
    });
  }

  /** Slug a provider name the way AGiXT's OAuth apps were registered:
   *  strip trailing _sso, lowercase, replace _/./ space with - . Mirrors
   *  the Rust side `redirect_slug_for` and the web's OAuth.tsx. */
  function redirectSlug(name) {
    if (!name) return '';
    let s = String(name).toLowerCase();
    if (s.endsWith('_sso')) s = s.slice(0, -4);
    return s.replace(/_/g, '-').replace(/\./g, '-').replace(/\s+/g, '-');
  }

  window.AgixtApi = {
    getSettings,
    refreshSettings,
    getAgentExtensions,
    toggleCommand,
    bulkToggleExtension,
    updateAgentSettings,
    getOAuthProviders,
    getUserOAuthConnections,
    disconnectOAuth,
    getPersona,
    setPersona,
    listTrainingSources,
    learnFile,
    learnUrl,
    deleteSource,
    readFileAsBase64,
    redirectSlug,
  };
})();
