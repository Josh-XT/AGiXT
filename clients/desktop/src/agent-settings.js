/* Agent Settings window orchestrator.
 *
 * Loads the active agent (from desktop settings — chosen via the topbar in
 * the main window), wires the tab switcher, and lazy-initializes each tab's
 * module the first time it's activated. Keeps unused tabs from making API
 * calls until the user actually clicks them.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    document.body.innerHTML = '<div style="padding: 40px; color: #ff8585;">Tauri IPC unavailable.</div>';
    return;
  }
  const invoke = tauri.core.invoke;
  const event = tauri.event;
  const frontendLog = window.AgixtFrontendLog || function () {};

  const tabs = ['extensions', 'connections', 'training'];
  const initialized = { extensions: false, connections: false, training: false };
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
    if (!initialized[name] && agentId) {
      initialized[name] = true;
      try {
        if (name === 'extensions') window.AgentSettingsExtensions.init({ agentId, agentName });
        if (name === 'connections') window.AgentSettingsConnections.init();
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

  async function boot() {
    bindTabs();
    try {
      const settings = await window.AgixtApi.getSettings();
      agentId = settings.agent_id || null;
      agentName = settings.agent_name || null;
      paintHeader(settings);
      if (!agentId) {
        toast('No agent selected. Open the main window and pick an agent first.', 'error');
        ['ext-body', 'conn-body'].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.innerHTML = '<div class="as-empty">Pick an agent in the main window to configure it.</div>';
        });
        return;
      }
      // Default to the Extensions tab (already aria-selected in the HTML).
      setActive('extensions');
    } catch (e) {
      toast('Failed to load settings: ' + (e.message || e), 'error');
    }

    // The main window can broadcast that the user changed the active agent;
    // we listen so this window stays in sync without requiring a manual
    // close/reopen.
    if (event && event.listen) {
      event.listen('agixt-agent-changed', async () => {
        try { await reloadActive(); } catch (e) { console.warn('reloadActive', e); }
      });
    }

    // Refresh whenever the window regains focus — covers the case where the
    // user changed agents in the main window without us getting an event.
    window.addEventListener('focus', () => {
      // Cheap: re-read settings; only reload if agent changed.
      window.AgixtApi.refreshSettings().then(async () => {
        const s = await window.AgixtApi.getSettings();
        if ((s.agent_id || null) !== agentId) {
          await reloadActive();
        }
      }).catch(() => { /* ignore */ });
    });
  }

  window.AgentSettings = { toast, setActive, reload: reloadActive };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  frontendLog('info', 'agent-settings.js boot');
})();
