/* Agent Settings orchestrator.
 *
 * Loads the active agent (from desktop settings — chosen via the topbar in
 * the main window), wires the tab switcher, and lazy-initializes each tab's
 * module the first time it's activated. Keeps unused tabs from making API
 * calls until the user actually clicks them.
 *
 * Two host modes:
 *   - Standalone window (`agent-settings.html`, `body.as-body`): auto-boots
 *     on DOMContentLoaded.
 *   - Embedded side pane in the main window (`view-pane[data-view=
 *     "agent-settings"]` inside `index.html`): waits for the host to call
 *     `window.AgentSettings.mount()` the first time the user activates the
 *     pane, so the API calls don't fire until they're actually needed.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    if (document.body && document.body.classList.contains('as-body')) {
      document.body.innerHTML = '<div style="padding: 40px; color: #ff8585;">Tauri IPC unavailable.</div>';
    }
    return;
  }
  const invoke = tauri.core.invoke;
  const event = tauri.event;
  const frontendLog = window.AgixtFrontendLog || function () {};

  // Standalone window puts `.as-body` on <body>; the embedded pane in the
  // main window does not. Several behaviors only make sense in the
  // standalone host (auto-boot, full-window auth gate, focus-based
  // refresh) — we branch on this flag instead of duplicating the file.
  const isStandalone = document.body && document.body.classList.contains('as-body');
  let booted = false;

  // Connections aren't a separate tab anymore — OAuth providers are
  // surfaced as cards inside their proper Extension category. We still
  // init the connections helper at boot so its deep-link event listeners
  // are wired up to refresh the extensions tab after an OAuth round-trip.
  const tabs = ['extensions', 'training'];
  const initialized = { extensions: false, training: false };
  let agentId = null;
  let agentName = null;

  let toastTimer = null;
  function toast(message, kind) {
    const el = document.getElementById('as-toast');
    if (!el) return;
    el.textContent = message;
    el.className = 'as-toast' + (kind ? ' ' + kind : '');
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, kind === 'error' ? 6000 : 3500);
  }

  const TAB_TITLES = { extensions: 'Extensions', training: 'Training' };
  function setActive(name) {
    tabs.forEach((t) => {
      const btn = document.getElementById('as-tab-' + t);
      const panel = document.getElementById('as-panel-' + t);
      const active = t === name;
      if (btn) {
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      }
      if (panel) {
        panel.classList.toggle('is-active', active);
        panel.hidden = !active;
      }
    });
    // Embedded mode hides the tab nav and uses the title bar to indicate
    // which view the user landed on (Extensions vs Training); keep it in
    // sync with whichever tab is active.
    const titleEl = document.getElementById('as-title');
    if (titleEl && TAB_TITLES[name]) titleEl.textContent = TAB_TITLES[name];
    if (!initialized[name] && agentId) {
      initialized[name] = true;
      try {
        if (name === 'extensions') window.AgentSettingsExtensions.init({ agentId, agentName });
        if (name === 'training') window.AgentSettingsTraining.init({ agentId, agentName });
      } catch (e) {
        toast('Failed to load ' + name + ': ' + (e.message || e), 'error');
      }
    }
  }

  function bindTabs() {
    tabs.forEach((t) => {
      const btn = document.getElementById('as-tab-' + t);
      if (btn) btn.addEventListener('click', () => setActive(t));
    });
  }

  async function reloadActive() {
    // Re-fetch the agent + reinitialize. Used after `agent-changed` events
    // from the main window.
    await window.AgixtApi.refreshSettings();
    const settings = await window.AgixtApi.getSettings();
    agentId = settings.agent_id || null;
    agentName = settings.agent_name || null;
    paintHeader(settings);
    if (!agentId) {
      ['ext-body', 'conn-body'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="as-empty">Pick an agent in the main window to configure it.</div>';
      });
      return;
    }
    if (window.AgentSettingsExtensions && initialized.extensions) {
      window.AgentSettingsExtensions.setAgent(agentId, agentName);
      window.AgentSettingsExtensions.reload();
    }
    if (window.AgentSettingsTraining && initialized.training) {
      window.AgentSettingsTraining.setAgent(agentId, agentName);
      window.AgentSettingsTraining.reload();
    }
    if (window.AgentSettingsConnections && initialized.connections) {
      window.AgentSettingsConnections.reload();
    }
  }

  function paintHeader(settings) {
    const sub = document.getElementById('as-subtitle');
    if (!sub) return;
    if (settings && settings.agent_name) {
      const company = settings.company_name ? ` @ ${settings.company_name}` : '';
      sub.textContent = `Configuring ${settings.agent_name}${company} · ${settings.user_email || 'unknown user'}`;
    } else {
      sub.textContent = 'No agent selected — pick one in the main window first.';
    }
  }

  function renderSignedOut() {
    document.body.classList.add('as-signed-out');
    const title = document.querySelector('.as-title');
    if (title) title.textContent = 'AGiXT';
    const sub = document.getElementById('as-subtitle');
    if (sub) sub.textContent = 'Sign in to configure an agent.';
    const tabsEl = document.querySelector('.as-tabs');
    if (tabsEl) tabsEl.hidden = true;
    const main = document.querySelector('.as-main');
    if (!main) return;
    main.innerHTML = '';
    const wrap = document.createElement('section');
    wrap.className = 'as-auth-gate';
    const heading = document.createElement('h2');
    heading.textContent = 'Sign in to continue';
    const body = document.createElement('p');
    body.textContent = 'Agent settings are available after the desktop client is connected to an AGiXT account.';
    const button = document.createElement('button');
    button.className = 'btn btn-primary';
    button.type = 'button';
    button.textContent = 'Open sign in';
    button.addEventListener('click', async () => {
      try {
        await invoke('show_chat');
      } catch (_) {
        // Navigating below is the important fallback when this page was
        // opened as the only mobile WebView.
      }
      window.location.href = 'index.html';
    });
    wrap.appendChild(heading);
    wrap.appendChild(body);
    wrap.appendChild(button);
    main.appendChild(wrap);
  }

  async function boot(opts) {
    const requestedTab = (opts && tabs.indexOf(opts.tab) !== -1) ? opts.tab : null;
    if (booted) {
      // Subsequent mount() calls (e.g. user toggling between the
      // sidenav Extensions button and the topbar Training button)
      // just need to switch the active tab.
      if (requestedTab) setActive(requestedTab);
      return;
    }
    booted = true;
    bindTabs();
    try {
      // Embedded mode shares cached settings with app.js — refresh once at
      // mount so we pick up the latest agent the user may have chosen in
      // the topbar before opening this pane.
      if (!isStandalone) await window.AgixtApi.refreshSettings();
      const settings = await window.AgixtApi.getSettings();
      if (!settings || !settings.jwt) {
        if (isStandalone) {
          renderSignedOut();
        } else {
          // The host (main window) already gates on auth — if we got
          // here without a JWT something is off, but rendering an
          // auth-gate inside the side pane would be redundant.
          paintHeader(null);
        }
        return;
      }
      agentId = settings.agent_id || null;
      agentName = settings.agent_name || null;
      paintHeader(settings);
      if (!agentId) {
        toast('No agent selected. Pick an agent in the topbar first.', 'error');
        ['ext-body', 'conn-body'].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.innerHTML = '<div class="as-empty">Pick an agent to configure it.</div>';
        });
        return;
      }
      // Default to the requested tab when one was passed (Extensions or
      // Training entry points), otherwise Extensions for the standalone
      // window.
      setActive(requestedTab || 'extensions');
      // Wire up cross-window OAuth callback listeners regardless of tab so
      // the Extensions tab can refresh after `agixt://oauth-connect`
      // round-trips, even if the user is on the Training tab when it
      // returns.
      if (window.AgentSettingsConnections && window.AgentSettingsConnections.initListeners) {
        window.AgentSettingsConnections.initListeners();
      }
    } catch (e) {
      toast('Failed to load settings: ' + (e.message || e), 'error');
    }

    // The agent switcher lives in the topbar (same window when embedded,
    // a peer window when standalone). Either way, it broadcasts
    // `agixt-agent-changed` and we re-fetch.
    if (event && event.listen) {
      event.listen('agixt-agent-changed', async () => {
        try { await reloadActive(); } catch (e) { console.warn('reloadActive', e); }
      });
    }

    // Standalone window only — refresh whenever it regains focus. Covers
    // the case where the user changed agents in the main window without
    // us getting an event. The embedded pane shares the same window so
    // a focus event there means nothing useful.
    if (isStandalone) {
      window.addEventListener('focus', () => {
        window.AgixtApi.refreshSettings().then(async () => {
          const s = await window.AgixtApi.getSettings();
          if ((s.agent_id || null) !== agentId) {
            await reloadActive();
          }
        }).catch(() => { /* ignore */ });
      });
    }
  }

  window.AgentSettings = {
    toast,
    setActive,
    reload: reloadActive,
    // Host-callable mount — idempotent. The main window calls this the
    // first time the user activates the agent-settings pane.
    mount: boot,
  };

  if (isStandalone) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  }

  frontendLog('info', 'agent-settings.js loaded (' + (isStandalone ? 'standalone' : 'embedded') + ')');
})();
