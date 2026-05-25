/* OAuth connect/disconnect helper used by the Extensions tab.
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
 *      `agixt-extension-connected` so the Extensions tab can refresh.
 *
 * Connections used to live in their own tab; the user feedback was that
 * OAuth providers should be sorted into their proper extension categories
 * instead. This module now exposes start/stop helpers + the deep-link
 * event listeners — the rendering is handled by settings-extensions.js.
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
  let listenersWired = false;

  function prettyName(name) {
    if (!name) return '';
    let s = String(name).replace(/_(sso|oauth)$/i, '');
    return s.split(/[_\s]+/).map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
  }

  /** Open the provider's authorize URL in the system browser. The actual
   *  code-for-token exchange happens in the Rust deep-link handler after
   *  the user authorizes. */
  async function startConnect(provider) {
    if (!provider || !provider.name) {
      window.AgentSettings.toast('No provider supplied to connect.', 'error');
      return;
    }
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
      window.AgentSettings.toast(
        `Opened ${prettyName(provider.name)} sign-in. Authorize in your browser, then return here.`,
        'success',
      );
    } catch (e) {
      window.AgentSettings.toast('Connect failed: ' + (e.error || e.message || e), 'error');
    }
  }

  /** DELETE /v1/oauth2/{slug} */
  async function startDisconnect(provider) {
    try {
      const slug = api.oauthEndpointSlug
        ? api.oauthEndpointSlug(provider.name)
        : api.redirectSlug(provider.name);
      await api.disconnectOAuth(slug);
      window.AgentSettings.toast(`${prettyName(provider.name)} disconnected.`, 'success');
      if (window.AgentSettingsExtensions) {
        await window.AgentSettingsExtensions.refreshConnectionState();
      }
    } catch (e) {
      window.AgentSettings.toast('Disconnect failed: ' + (e.message || e), 'error');
    }
  }

  /** Wire up the deep-link event listeners. Called once at boot. */
  function initListeners() {
    if (listenersWired || !event || !event.listen) return;
    listenersWired = true;
    event.listen('agixt-extension-connected', async (ev) => {
      const provider = (ev && ev.payload && ev.payload.provider) || '';
      if (provider) {
        window.AgentSettings.toast(`${prettyName(provider)} connected.`, 'success');
      }
      if (window.AgentSettingsExtensions) {
        await window.AgentSettingsExtensions.refreshConnectionState();
      }
    });
    event.listen('agixt-extension-connect-failed', (ev) => {
      const detail = (ev && ev.payload && ev.payload.detail) || 'unknown error';
      window.AgentSettings.toast('OAuth callback failed: ' + detail, 'error');
    });
  }

  window.AgentSettingsConnections = {
    initListeners,
    startConnect,
    startDisconnect,
    prettyName,
  };
})();
