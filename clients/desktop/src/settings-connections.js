/* Connections tab — OAuth provider list + per-provider connect/disconnect.
 *
 * Connect flow extends the existing login-OAuth pattern:
 *   1. JS calls invoke('build_oauth_connect_url', ...) — sibling to the
 *      build_oauth_login_url command; tags state with `desktop_connect=1`.
 *   2. JS opens the URL in the system browser via tauri-plugin-opener.
 *   3. Provider redirects to {web_url}/user/close/{provider} with the code.
 *   4. The web close page (modified to recognize desktop_connect=1) hops
 *      back to the desktop via `agixt://oauth-connect?provider=...&code=...`.
 *   5. Rust deep-link handler does the POST /v1/oauth2/{provider} server-side
 *      (the desktop has the JWT, the browser doesn't) and emits the event
 *      `agixt-extension-connected` so this page can refresh.
 */
(function () {
  const tauri = window.__TAURI__;
  const api = window.AgixtApi;
  if (!tauri || !api) {
    console.error('settings-connections.js: Tauri or AgixtApi missing');
    return;
  }
  const invoke = tauri.core.invoke;
  const event = tauri.event;

  let providers = [];          // GET /v1/oauth — server config (with client_id)
  let userConnections = null;  // GET /v1/oauth2 — per-user state, may be null
  let bodyEl = null;
  let initialized = false;

  function escape(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function prettyName(name) {
    if (!name) return '';
    let s = String(name).replace(/_(sso|oauth)$/i, '');
    return s.split(/[_\s]+/).map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
  }

  function providerIconUrl(name) {
    const k = (name || '').toLowerCase();
    const map = {
      google: 'assets/oauth/google.svg',
      microsoft: 'assets/oauth/microsoft.svg',
      github: 'assets/oauth/github.svg',
      discord: 'assets/oauth/discord.svg',
      apple: 'assets/oauth/apple.svg',
      spotify: 'assets/oauth/spotify.svg',
    };
    for (const key of Object.keys(map)) {
      if (k.includes(key)) return map[key];
    }
    return null;
  }

  function isConnected(provider) {
    if (!userConnections) return false;
    // The /v1/oauth2 response shape varies. Try a few likely fields.
    if (Array.isArray(userConnections.connected)) {
      return userConnections.connected.includes(provider.name) ||
             userConnections.connected.includes(api.redirectSlug(provider.name));
    }
    if (Array.isArray(userConnections.providers)) {
      // Each entry may have `connected: bool`
      const match = userConnections.providers.find((p) => (p.name || '').toLowerCase() === (provider.name || '').toLowerCase());
      return !!(match && match.connected);
    }
    if (userConnections[provider.name]) return true;
    return false;
  }

  function renderProvider(p) {
    const slug = api.redirectSlug(p.name);
    const connected = isConnected(p);
    const iconUrl = providerIconUrl(p.name);
    const iconHtml = iconUrl
      ? `<img src="${iconUrl}" alt="" />`
      : `<span class="conn-icon-letter">${escape((p.name || '?').charAt(0).toUpperCase())}</span>`;
    const action = connected
      ? `<button class="btn btn-secondary conn-disconnect" data-provider="${escape(p.name)}" type="button">Disconnect</button>`
      : `<button class="btn btn-primary conn-connect" data-provider="${escape(p.name)}" type="button">Connect</button>`;
    return `
      <div class="conn-card" data-slug="${escape(slug)}">
        <div class="conn-icon">${iconHtml}</div>
        <div class="conn-meta">
          <div class="conn-name">${escape(prettyName(p.name))}</div>
          <div class="conn-status ${connected ? 'connected' : ''}">${connected ? 'Connected' : 'Not connected'}</div>
        </div>
        <div class="conn-actions">${action}</div>
      </div>
    `;
  }

  function render() {
    if (!bodyEl) return;
    // Show only providers with a configured client_id (server has creds).
    // Drop SSO-only providers — they're for login, not extension connections.
    const list = providers.filter((p) => p && p.client_id && !p.sso_only);
    if (list.length === 0) {
      bodyEl.innerHTML = '<div class="as-empty">No OAuth providers configured on this server.</div>';
      return;
    }
    bodyEl.innerHTML = `<div class="conn-grid">${list.map(renderProvider).join('')}</div>`;
    bind();
  }

  function bind() {
    bodyEl.querySelectorAll('.conn-connect').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const name = btn.getAttribute('data-provider');
        await startConnect(name, btn);
      });
    });
    bodyEl.querySelectorAll('.conn-disconnect').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const name = btn.getAttribute('data-provider');
        await startDisconnect(name, btn);
      });
    });
  }

  async function startConnect(providerName, btn) {
    const provider = providers.find((p) => p.name === providerName);
    if (!provider) {
      window.AgentSettings.toast(`Provider "${providerName}" not found.`, 'error');
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Opening browser…'; }
    try {
      const settings = await api.getSettings();
      const result = await invoke('build_oauth_connect_url', {
        args: {
          server_url: settings.server_url,
          web_url: settings.web_url,
          provider,
        },
      });
      if (tauri.opener && tauri.opener.openUrl) {
        await tauri.opener.openUrl(result.url);
      } else {
        window.open(result.url, '_blank', 'noopener');
      }
      window.AgentSettings.toast(`Opened ${prettyName(providerName)} sign-in. Authorize in your browser, then return to this window.`, 'success');
    } catch (e) {
      window.AgentSettings.toast('Connect failed: ' + (e.error || e.message || e), 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Connect'; }
    }
  }

  async function startDisconnect(providerName, btn) {
    if (btn) { btn.disabled = true; btn.textContent = 'Disconnecting…'; }
    try {
      const slug = api.redirectSlug(providerName);
      await api.disconnectOAuth(slug);
      window.AgentSettings.toast(`${prettyName(providerName)} disconnected.`, 'success');
      await load();
      // Also refresh extensions so dots/labels update.
      if (window.AgentSettingsExtensions) {
        window.AgentSettingsExtensions.refreshConnectionState();
      }
    } catch (e) {
      window.AgentSettings.toast('Disconnect failed: ' + (e.message || e), 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Disconnect'; }
    }
  }

  async function load() {
    bodyEl = document.getElementById('conn-body');
    if (bodyEl) bodyEl.innerHTML = '<div class="as-empty">Loading providers…</div>';
    try {
      const [provs, conns] = await Promise.all([
        api.getOAuthProviders(),
        api.getUserOAuthConnections(),
      ]);
      providers = provs || [];
      userConnections = conns;
      render();
    } catch (e) {
      if (bodyEl) bodyEl.innerHTML = `<div class="as-empty">Failed to load: ${escape(e.message || e)}</div>`;
    }
  }

  function init() {
    if (!initialized && event && event.listen) {
      initialized = true;
      // Fired by the Rust deep-link handler after a successful POST to
      // /v1/oauth2/{provider} completes the connect.
      event.listen('agixt-extension-connected', async (ev) => {
        const provider = (ev && ev.payload && ev.payload.provider) || '';
        if (provider) {
          window.AgentSettings.toast(`${prettyName(provider)} connected.`, 'success');
        }
        await load();
        if (window.AgentSettingsExtensions) {
          window.AgentSettingsExtensions.refreshConnectionState();
        }
      });
      event.listen('agixt-extension-connect-failed', (ev) => {
        const detail = (ev && ev.payload && ev.payload.detail) || 'unknown error';
        window.AgentSettings.toast('OAuth callback failed: ' + detail, 'error');
      });
    }
    return load();
  }

  window.AgentSettingsConnections = {
    init,
    reload: load,
    startConnect,
  };
})();
