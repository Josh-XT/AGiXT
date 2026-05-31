/* App orchestrator. Decides whether to show the auth screen or the chat
 * screen, then wires the chat screen up the way it always did once we
 * have a JWT.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    const dot = document.getElementById('connection-state');
    if (dot) {
      dot.className = 'brand-conn error';
      dot.title = 'Tauri IPC unavailable';
    }
    return;
  }
  const invoke = tauri.core.invoke;
  const event = tauri.event;
  const frontendLog = window.AgixtFrontendLog || function () {};

  let settings = null;
  let companies = [];
  let agents = [];
  let conversationName = null;
  let childMode = false;
  let childControl = null;
  let teamChatAvailable = false;
  let teamChatAvailabilityRequest = 0;
  const rememberedAgentConversations = new Map();

  // ----- DOM -----
  const $ = (id) => document.getElementById(id);
  const composerInput = $('composer-input');
  const sendBtn = $('btn-send');
  const stopBtn = $('btn-stop');
  const newConvoBtn = $('btn-new-conversation');
  const settingsBtn = $('btn-settings');
  const collapseBtn = $('btn-collapse');
  const micBtn = $('btn-mic');
  const attachBtn = $('btn-attach');
  const attachmentsEl = $('attachments');
  // Legacy gear-button modal references — the modal was replaced by the
  // `data-view="user-settings"` side pane (user-settings.js). These names
  // stay defined as `null` so the downstream auto-update + sudo helpers
  // keep working without sprinkling null checks across every call site;
  // each helper either no-ops when its DOM target is missing, or routes
  // to the new pane via `setActiveView('user-settings')`.
  const settingsModal = null;
  const settingsClose = null;
  const saveSettingsBtn = null;
  const logoutBtn = null;
  const settingsStatus = null;
  const settingsUser = null;
  const sudoPasswordInput = null;
  const sudoAuthBtn = null;
  const sudoClearBtn = null;
  const sudoSessionStatus = null;
  const desktopAutoUpdateInput = null;
  const desktopUpdateStatus = null;
  const desktopUpdateCheckBtn = null;
  const desktopUpdateInstallBtn = null;
  const agentBtn = $('agent-switcher-btn');
  const agentLabel = $('agent-switcher-label');
  const agentMenu = $('agent-menu');
  const agentMenuList = $('agent-menu-list');
  const convoBtn = $('convo-switcher-btn');
  const convoLabel = $('convo-switcher-label');
  const convoMenu = $('convo-menu');
  const convoMenuList = $('convo-menu-list');
  const convoNewBtn = $('convo-new-btn');
  let lastDesktopUpdateStatus = null;
  let desktopUpdateBusyMode = '';
  let desktopAutoUpdateTimer = null;
  let trialLifecycleTimer = null;
  let pendingDesktopUpdateInstall = false;

  function installBrandFallback(markId, imgId, label) {
    const mark = $(markId);
    const img = $(imgId);
    if (!mark || !img) return;
    const showFallback = () => {
      mark.classList.add('fallback');
      mark.dataset.fallback = label || 'XT';
      img.hidden = true;
    };
    img.addEventListener('error', showFallback);
    if (img.complete && img.naturalWidth === 0) showFallback();
  }

  installBrandFallback('brand-mark', 'brand-mark-img', 'XT');
  installBrandFallback('sidenav-brand-mark', 'sidenav-brand-mark-img', 'XT');

  function setSettingsStatus(text, cls) {
    if (!settingsStatus) return;
    settingsStatus.textContent = text || '';
    settingsStatus.className = 'settings-status' + (cls ? ' ' + cls : '');
  }

  function setSudoSessionStatus(text, cls) {
    if (!sudoSessionStatus) return;
    sudoSessionStatus.textContent = text || '';
    sudoSessionStatus.className = 'sudo-session-status' + (cls ? ' ' + cls : '');
  }

  function setDesktopUpdateStatus(text, cls) {
    if (!desktopUpdateStatus) return;
    desktopUpdateStatus.textContent = text || '';
    desktopUpdateStatus.className = 'sudo-session-status' + (cls ? ' ' + cls : '');
  }

  function desktopUpdateIsReady(status = lastDesktopUpdateStatus) {
    return !!(status && status.update_available && status.ready);
  }

  function setDesktopUpdateControls(updateReady = desktopUpdateIsReady()) {
    const busy = !!desktopUpdateBusyMode;
    const installing = desktopUpdateBusyMode === 'installing';
    if (desktopUpdateCheckBtn) {
      desktopUpdateCheckBtn.disabled = busy;
      desktopUpdateCheckBtn.hidden = installing;
      desktopUpdateCheckBtn.setAttribute('aria-busy', busy ? 'true' : 'false');
    }
    if (desktopUpdateInstallBtn) {
      desktopUpdateInstallBtn.disabled = busy;
      desktopUpdateInstallBtn.hidden = busy || !updateReady;
      desktopUpdateInstallBtn.setAttribute('aria-busy', busy ? 'true' : 'false');
    }
  }

  function setDesktopUpdateBusy(mode) {
    desktopUpdateBusyMode = mode || '';
    setDesktopUpdateControls();
  }

  function desktopUpdateErrorText(err) {
    if (err && err.error) return String(err.error);
    if (err && err.message) return String(err.message);
    return String(err || '');
  }

  function isSudoAuthRequired(message) {
    return /SUDO_AUTH_REQUIRED|sudo.*password.*required|authenticate.*Privileged Commands/i.test(message || '');
  }

  function requestSudoForDesktopUpdate(auto) {
    pendingDesktopUpdateInstall = true;
    setDesktopUpdateBusy('');
    setDesktopUpdateStatus('Authenticate Privileged Commands to install this update.', 'error');
    setDesktopUpdateControls(true);
    markSettingsBtnPending(true);
    if (auto) {
      // Auto-update path: don't yank the user into settings on every
      // boot. Mark the gear so they can authenticate when ready.
      return;
    }
    // Surface the side pane on the App tab — that's where the sudo
    // password field lives now (was the legacy modal).
    if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      window.AgixtSidenav.setActiveView('user-settings');
    }
  }

  function markSettingsBtnPending(pending) {
    if (!settingsBtn) return;
    settingsBtn.classList.toggle('has-pending', !!pending);
  }

  // ----- Screen switching --------------------------------------------------

  // Remove the boot splash once a real screen is on-screen. Idempotent —
  // the first terminal boot state (chat / auth / landing) clears it and
  // any later call is a no-op. The 250ms timeout matches the CSS fade so
  // the splash element can be left in the DOM without trapping clicks.
  let _bootFinished = false;
  function finishBoot() {
    if (_bootFinished) return;
    _bootFinished = true;
    try { document.body.classList.remove('app-booting'); } catch (_) {}
  }

  function showScreen(which) {
    const auth = which === 'auth';
    const landing = which === 'landing';
    const chat = which === 'chat';
    const landingScreen = $('landing-screen');
    if (landingScreen) landingScreen.hidden = !landing;
    $('auth-screen').hidden = !auth;
    $('chat-screen').hidden = !chat;
    // The auth-mode body class controls topbar chip styling. Treat the
    // landing screen the same — neither has chat chrome.
    document.body.classList.toggle('auth-mode', auth || landing);
    // While not on chat, disable the chat-only chrome controls.
    [
      newConvoBtn,
      agentBtn,
      convoBtn,
      agentTrainingBtn,
    ].forEach((b) => { if (b) b.disabled = !chat; });
    closeMenus();
    // The sidenav has zero height while #chat-screen is hidden, so any
    // overflow measurement made before login is meaningless. Re-run it
    // once the chat screen becomes visible so the More button appears
    // correctly on first paint.
    if (chat
        && window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.reflowSidenav === 'function') {
      setTimeout(() => {
        try { window.AgixtDesktopExtensions.reflowSidenav(); } catch (_) {}
      }, 0);
    }
    if (!chat) {
      removeTrialBanner();
      clearTrialLifecycleChecks();
    }
    // Auth and chat are terminal boot states — clear the splash now. The
    // landing screen is special-cased in showLanding(): it keeps the
    // splash up until the iframe finishes loading so the user never sees
    // a blank frame.
    if (!landing) {
      finishBoot();
    }
  }

  // ----- Landing screen (pre-auth marketing) -------------------------------

  // Track which landing site the iframe is currently showing so we don't
  // reload it on every showScreen('landing') call (e.g. logout retains
  // the prior load).
  let _activeLandingSiteId = null;
  let _landingMessageHandler = null;

  function landingServerBase() {
    if (settings && typeof settings.server_url === 'string' && settings.server_url) {
      return settings.server_url.replace(/\/+$/, '');
    }
    return 'http://localhost:7437';
  }

  async function fetchLandingManifest() {
    try {
      const res = await fetch(`${landingServerBase()}/v1/landing`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) return null;
      const data = await res.json();
      return (data && data.landing) ? data.landing : null;
    } catch (err) {
      console.warn('landing fetch failed', err);
      return null;
    }
  }

  function showLanding(landing) {
    const frame = $('landing-frame');
    if (!frame || !landing || !landing.id) return false;
    const desiredUrl = `${landingServerBase()}${landing.index_url || landing.entry_url}`;
    const alreadyLoaded = _activeLandingSiteId === landing.id && frame.src === desiredUrl;
    if (!alreadyLoaded) {
      frame.src = desiredUrl;
      _activeLandingSiteId = landing.id;
    }
    showScreen('landing');
    // Hold the boot splash over the (still-blank) iframe until it has
    // painted, then fade it out. A timeout guarantees we never strand the
    // user behind the splash if the load event is missed (cache hits,
    // cross-origin quirks, etc.). If the frame was already loaded from a
    // prior showLanding() call, clear immediately.
    if (alreadyLoaded) {
      finishBoot();
    } else if (!_bootFinished) {
      let cleared = false;
      const clearOnce = () => {
        if (cleared) return;
        cleared = true;
        frame.removeEventListener('load', clearOnce);
        finishBoot();
      };
      frame.addEventListener('load', clearOnce);
      setTimeout(clearOnce, 4000);
    }
    if (!_landingMessageHandler) {
      _landingMessageHandler = (event) => {
        const data = event && event.data;
        if (!data || typeof data !== 'object') return;
        if (data.type !== 'landing-action') return;
        if (data.action === 'signin' || data.action === 'register' || data.action === 'auth') {
          showScreen('auth');
          if (window.AgixtAuth && typeof window.AgixtAuth.boot === 'function') {
            window.AgixtAuth.boot({ onAuthenticated });
          }
        }
      };
      window.addEventListener('message', _landingMessageHandler);
    }
    return true;
  }

  // ----- Settings load / save ---------------------------------------------

  async function loadSettings() {
    settings = await invoke('get_settings');
    // The modal-era checkboxes (allow-commands, voice, auto-update, theme
    // <select>, signed-in label) are now rendered by user-settings.js
    // when the user opens the side pane — no boot-time DOM updates needed.
    // Theme: the inline bootstrap script in index.html already applied
    // a theme based on localStorage / OS prefers-color-scheme before the
    // first paint. Now that we have the user's persisted setting from
    // the Tauri DB, reconcile: backfill localStorage so the bootstrap
    // is correct on the next launch, and reapply if the persisted
    // pref disagrees with what we resolved at boot.
    //
    // XT School (kids tablets) is a locked-down kiosk: the content UI is
    // designed dark and the Fire tablets report a light OS preference, so
    // "system" would resolve to light and look wrong. Force dark ("gray")
    // for that brand regardless of the saved/OS preference. Persisting it
    // also fixes the index.html bootstrap on the next launch (it reads the
    // cached pref), so there's no light flash after the first run.
    const themePref = isKidsBrand(settings.service_brand)
      ? 'gray'
      : (settings.theme || 'system');
    applyTheme(themePref, { persist: true });
    if (settingsUser) {
      settingsUser.textContent = settings.user_email
        ? `${settings.user_email} @ ${settings.server_url}`
        : `not signed in`;
    }
    // Apply the saved service branding to the topbar logo. Without this,
    // returning users always see the default AGiXT mark even when they
    // picked a different brand (e.g. BoltRemote) on first login.
    if (window.AgixtBranding && settings.service_brand) {
      window.AgixtBranding.apply(settings.service_brand);
    }
  }

  // The XT School brand runs on locked-down kids tablets where the theme
  // is forced dark (see loadSettings) and the theme picker is hidden.
  function isKidsBrand(brand) {
    return brand === 'xtschool';
  }

  // Stamp the resolved theme on <html data-theme> so the CSS variables
  // switch (and propagate to every desktop extension that uses them).
  // `pref` is the user's intent: "system" | "light" | "dark"; "system"
  // resolves via the OS prefers-color-scheme media query. We also fire
  // an `agixt-theme-changed` window event so any extension that wants
  // to react beyond CSS (e.g. swap an icon set, redraw a chart) can.
  function applyTheme(pref, { persist = true } = {}) {
    const KNOWN = ['light', 'dark', 'gray', 'system'];
    const choice = KNOWN.indexOf(pref) >= 0 ? pref : 'system';
    const resolved = choice === 'system'
      ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'gray'
          : 'light')
      : choice;
    document.documentElement.setAttribute('data-theme', resolved);
    if (persist) {
      try { window.localStorage.setItem('agixt.theme', choice); } catch (_) {}
    }
    window.dispatchEvent(new CustomEvent('agixt-theme-changed', {
      detail: { theme: choice, resolved },
    }));
  }

  async function persistSettings(patch) {
    settings = { ...settings, ...patch };
    settings = await invoke('save_settings', { settings });
  }

  async function onSaveSettings() {
    // The modal-era save handler is unreachable now that user-settings.js
    // owns the form and persists directly via `invoke('save_settings')`.
    // Kept as a no-op so any lingering callers don't crash.
    setSettingsStatus('Saved.', 'success');
  }

  async function refreshSudoStatus() {
    if (!settings || !sudoSessionStatus) return;
    if (!settings.allow_client_commands) {
      setSudoSessionStatus('Client commands disabled.', 'error');
      return;
    }
    setSudoSessionStatus('Checking…');
    try {
      const result = await invoke('sudo_status');
      if (result && result.authenticated) {
        setSudoSessionStatus(
          result.remembered ? 'Authenticated and remembered.' : 'Authenticated for this session.',
          'success',
        );
      } else if (result && result.remembered) {
        setSudoSessionStatus('Remembered password needs re-authentication.', 'error');
      } else {
        setSudoSessionStatus('Needs authentication.');
      }
    } catch (err) {
      const message = err && err.error ? err.error : String(err);
      if (/client commands are disabled/i.test(message)) {
        setSudoSessionStatus('Client commands disabled.', 'error');
      } else {
        setSudoSessionStatus('Needs authentication.');
      }
    }
  }

  async function refreshDesktopUpdateStatus(opts = {}) {
    // No longer bails on `!desktopUpdateStatus`: the legacy DOM is gone
    // but the IPC + auto-install chain still needs to run. The status-text
    // setters no-op safely when their targets are null.
    if (desktopUpdateBusyMode) return lastDesktopUpdateStatus;
    const autoInstall = !!opts.autoInstall;
    setDesktopUpdateBusy('checking');
    setDesktopUpdateStatus('Checking…');
    try {
      const status = await invoke('desktop_update_check');
      lastDesktopUpdateStatus = status;
      const current = status.current_build_id || status.app_version || 'current';
      const latest = status.latest_build_id || 'unknown';
      if (!status.update_available) {
        setDesktopUpdateStatus(`Up to date (${current}).`, 'success');
      } else if (status.ready) {
        setDesktopUpdateStatus(`Update ready: ${current} → ${latest}.`);
        if (autoInstall && settings && settings.desktop_auto_update) {
          if (desktopUpdateBusyMode === 'checking') setDesktopUpdateBusy('');
          await installDesktopUpdate(true);
          return status;
        }
      } else {
        setDesktopUpdateStatus(`Update ${latest} is still building.`);
        if (autoInstall && settings && settings.desktop_auto_update) {
          scheduleDesktopAutoUpdateCheck(300000);
        }
      }
      if (desktopUpdateBusyMode === 'checking') setDesktopUpdateBusy('');
      setDesktopUpdateControls(desktopUpdateIsReady(status));
      return status;
    } catch (err) {
      const message = desktopUpdateErrorText(err);
      setDesktopUpdateStatus(message, 'error');
      if (autoInstall && settings && settings.desktop_auto_update) {
        scheduleDesktopAutoUpdateCheck(600000);
      }
      if (desktopUpdateBusyMode === 'checking') setDesktopUpdateBusy('');
      setDesktopUpdateControls(false);
      return null;
    }
  }

  async function installDesktopUpdate(auto) {
    // The legacy DOM elements are gone — user-settings.js owns the
    // controls now — so we no longer bail on `!desktopUpdateStatus`.
    // setDesktopUpdateStatus / setDesktopUpdateControls are safe no-ops
    // when the targets are null, and the IPC + retry flow still need to
    // run for the boot-time auto-update path.
    if (desktopUpdateBusyMode) return;
    pendingDesktopUpdateInstall = false;
    setDesktopUpdateBusy('installing');
    setDesktopUpdateStatus(auto ? 'Installing update…' : 'Downloading update…');
    try {
      const result = await invoke('desktop_update_install');
      if (result.installed && result.restart_required) {
        setDesktopUpdateStatus('Update installed. Restarting AGiXT Desktop…', 'success');
        if (desktopUpdateBusyMode === 'installing') setDesktopUpdateBusy('');
        setDesktopUpdateControls(false);
        markSettingsBtnPending(false);
        window.setTimeout(() => {
          invoke('desktop_restart_app').catch((e) => {
            setDesktopUpdateStatus('Update installed. Please restart AGiXT Desktop to finish.', 'success');
            console.error('desktop_restart_app failed', e);
          });
        }, 1500);
        return;
      }
      setDesktopUpdateStatus(result.message || 'Update installed.', result.installed ? 'success' : '');
      if (desktopUpdateBusyMode === 'installing') setDesktopUpdateBusy('');
      if (result.installed) {
        setDesktopUpdateControls(false);
        markSettingsBtnPending(false);
      } else {
        setDesktopUpdateControls(desktopUpdateIsReady());
      }
    } catch (err) {
      const message = desktopUpdateErrorText(err);
      if (isSudoAuthRequired(message)) {
        requestSudoForDesktopUpdate(auto);
        return;
      }
      setDesktopUpdateStatus(message, 'error');
      if (desktopUpdateBusyMode === 'installing') setDesktopUpdateBusy('');
      setDesktopUpdateControls(desktopUpdateIsReady());
    }
  }

  function scheduleDesktopAutoUpdateCheck(delayMs = 2500) {
    if (desktopAutoUpdateTimer) {
      window.clearTimeout(desktopAutoUpdateTimer);
      desktopAutoUpdateTimer = null;
    }
    if (!settings || !settings.desktop_auto_update) return;
    desktopAutoUpdateTimer = window.setTimeout(() => {
      desktopAutoUpdateTimer = null;
      refreshDesktopUpdateStatus({ autoInstall: true });
    }, delayMs);
  }

  // Public hook so user-settings.js can re-arm the auto-update timer after
  // the user toggles "Automatically install updates" + clicks Save in the
  // App tab. Without this the new pref only takes effect on the next boot.
  window.AgixtDesktopUpdates = {
    scheduleAutoCheck: scheduleDesktopAutoUpdateCheck,
    refresh: refreshDesktopUpdateStatus,
    install: installDesktopUpdate,
    syncSettings: (next) => { if (next) settings = next; },
  };

  async function onSudoAuth() {
    if (!sudoPasswordInput) return;
    const password = sudoPasswordInput.value;
    if (!password) {
      setSudoSessionStatus('Enter your sudo password.', 'error');
      sudoPasswordInput.focus();
      return;
    }
    setSudoSessionStatus('Authenticating…');
    try {
      await invoke('sudo_auth', { password });
      sudoPasswordInput.value = '';
      setSudoSessionStatus('Authenticated and remembered.', 'success');
      if (pendingDesktopUpdateInstall) {
        pendingDesktopUpdateInstall = false;
        await installDesktopUpdate(true);
      } else if (settings && settings.desktop_auto_update) {
        await refreshDesktopUpdateStatus({ autoInstall: true });
      }
    } catch (err) {
      setSudoSessionStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  async function onSudoClear() {
    setSudoSessionStatus('Forgetting…');
    try {
      await invoke('sudo_clear');
      if (sudoPasswordInput) sudoPasswordInput.value = '';
      setSudoSessionStatus('Forgotten.');
    } catch (err) {
      setSudoSessionStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  async function onLogout() {
    setSettingsStatus('Logging out…');
    try {
      await invoke('logout');
      window.AgixtChat.disconnect();
      window.AgixtChat.clear();
      if (window.AgixtNotifications) window.AgixtNotifications.stop();
      companies = [];
      agents = [];
      setTeamChatAvailable(false);
      renderSelectors();
      setSettingsStatus('Logged out.', 'success');
      showScreen('auth');
      await loadSettings();
      if (window.AgixtAuth) {
        window.AgixtAuth.boot({ onAuthenticated });
      }
    } catch (err) {
      setSettingsStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  let authRecoveryInFlight = null;
  async function handleAuthExpired(reason) {
    if (authRecoveryInFlight) return authRecoveryInFlight;
    authRecoveryInFlight = (async () => {
      try {
        console.warn('AGiXT session expired; returning to auth.', reason || {});
        await invoke('logout');
      } catch (_) {
        // Best-effort. The UI must still leave the protected shell.
      }
      try { window.AgixtChat.disconnect(); } catch (_) {}
      try { window.AgixtChat.clear(); } catch (_) {}
      try { if (window.AgixtNotifications) window.AgixtNotifications.stop(); } catch (_) {}
      companies = [];
      agents = [];
      setTeamChatAvailable(false);
      renderSelectors();
      showScreen('auth');
      await loadSettings().catch(() => {});
      if (window.AgixtAuth) {
        await window.AgixtAuth.boot({ onAuthenticated });
      }
    })().finally(() => { authRecoveryInFlight = null; });
    return authRecoveryInFlight;
  }

  async function handlePaymentRequired(reason) {
    console.warn('AGiXT billing action required.', reason || {});
    const detail = (reason && reason.body && (reason.body.detail || reason.body.error || reason.body.message))
      || 'This account needs a billing top-up or active subscription to continue.';
    openBillingPane();
    showSessionOverlay({
      kind: 'payment',
      title: 'Billing Action Required',
      body: detail,
      hint: "We'll take you to Billing so you can resolve it.",
      actions: [
        {
          label: 'Open Billing',
          primary: true,
          onClick() { openBillingPane(); },
        },
        { label: 'Dismiss' },
      ],
    });
  }

  function openBillingPane() {
    try {
      showScreen('chat');
      if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        window.AgixtSidenav.setActiveView('user-settings');
      }
      if (window.UserSettings && typeof window.UserSettings.setActiveTab === 'function') {
        window.UserSettings.setActiveTab('billing');
      }
    } catch (_) {}
  }

  const TRIAL_BANNER_ID = 'agixt-trial-banner';
  const TRIAL_BANNER_DISMISS_PREFIX = 'agixt.billingBanner.dismissed.v1';
  const TRIAL_BANNER_DISMISS_MS = 12 * 60 * 60 * 1000;
  const TRIAL_BANNER_WARNING_DAYS = 14;
  const SUBSCRIPTION_RENEWAL_WARNING_DAYS = 14;

  function billingCompanyForTrial() {
    if (!Array.isArray(companies) || !companies.length) {
      return settings && settings.company_id
        ? { id: settings.company_id, name: settings.company_name || 'your company' }
        : null;
    }
    return (settings && settings.company_id
      ? companies.find((company) => company.id === settings.company_id)
      : null) || companies.find((company) => company.primary) || companies[0];
  }

  function activeCompany() {
    if (!settings || !Array.isArray(companies)) return null;
    return (settings.company_id
      ? companies.find((company) => company.id === settings.company_id)
      : null) || companies.find((company) => company.primary) || companies[0] || null;
  }

  function isChildCompanyRole(company) {
    if (!company) return false;
    if (Number(company.role_id) === 4) return true;
    const role = String(company.role || company.role_name || '').trim().toLowerCase();
    return role === 'child';
  }

  function childAllowedView(viewId) {
    if (!viewId) return false;
    // xtschool was split into per-section sidenav buttons (xtschool,
    // xtschool_videos, _music, _audiobooks, _games, _creations,
    // _calendar). Kids see all of them through the same allow-list.
    if (viewId === 'xtschool' || viewId.startsWith('xtschool_')) return true;
    return viewId === 'chat' || viewId === 'audible';
  }

  function childChatLockState() {
    const access = childControl && childControl.access;
    const app = access && access.app;
    const chat = access && access.features && access.features.chat;
    if (app && app.locked) return app.reason || 'app_locked';
    if (chat && chat.locked) return chat.reason || 'chat_locked';
    return '';
  }

  function childMandatoryContext() {
    if (!childMode || !childControl) return '';
    const context = (childControl.mandatory_context || childControl.ai_context || '').trim();
    if (!context) return '';
    return [
      'Mandatory child context from the company admin/parent.',
      'This context is required for every response to this child and must be followed unless it conflicts with safety requirements.',
      '',
      context,
    ].join('\n');
  }

  function childLockMessage(reason) {
    switch (reason) {
      case 'disabled': return 'Chat is paused right now.';
      case 'scheduled': return 'Chat is resting until the next allowed time.';
      case 'app_locked': return 'This app is paused right now.';
      default: return 'Chat is paused right now.';
    }
  }

  function applyChildMode(next, control) {
    childMode = !!next;
    childControl = control || null;
    document.body.classList.toggle('child-mode', childMode);
    const lockedReason = childMode ? childChatLockState() : '';
    if (micBtn) micBtn.disabled = !!lockedReason;
    if (sendBtn) sendBtn.disabled = !!lockedReason;
    if (attachBtn) attachBtn.disabled = childMode || !!lockedReason;
    const workspaceBtn = $('btn-workspace');
    if (workspaceBtn) workspaceBtn.disabled = childMode || !!lockedReason;
    if (composerInput) {
      composerInput.placeholder = childMode ? 'Tap the microphone and talk to AGiXT' : 'Ask AGiXT…';
      composerInput.disabled = !!lockedReason;
      composerInput.setAttribute('aria-hidden', childMode ? 'true' : 'false');
    }
    document.querySelectorAll('.sidenav-btn[data-view]').forEach((btn) => {
      const allowed = !childMode
        || childAllowedView(btn.dataset.view);
      btn.disabled = !allowed;
      btn.setAttribute('aria-hidden', allowed ? 'false' : 'true');
    });
    ['agent-switcher-btn', 'btn-agent-training', 'btn-share', 'btn-delete-conversation'].forEach((id) => {
      const btn = $(id);
      if (btn) {
        btn.disabled = childMode;
        btn.setAttribute('aria-hidden', childMode ? 'true' : 'false');
      }
    });
    if (childMode && window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      const active = typeof window.AgixtSidenav.getActiveView === 'function'
        ? window.AgixtSidenav.getActiveView()
        : null;
      if (!active || !childAllowedView(active)) {
        window.AgixtSidenav.setActiveView('chat');
      }
    }
    applyTeamChatNavVisibility();
    if (window.AgixtChat && typeof window.AgixtChat.setComposerStatus === 'function') {
      window.AgixtChat.setComposerStatus(lockedReason ? childLockMessage(lockedReason) : '');
    }
  }

  async function refreshChildMode() {
    if (!settings || !settings.jwt || !settings.company_id) {
      applyChildMode(false, null);
      return;
    }
    let company = activeCompany();
    if (!company || company.role_id == null) {
      const canFetchUser = !!(window.AgixtSession && typeof window.AgixtSession.request === 'function')
        || (typeof window.fetch === 'function')
        || (typeof fetch === 'function');
      if (canFetchUser) {
        try {
          const user = await desktopJson('/v1/user');
          const userCompanies = Array.isArray(user && user.companies) ? user.companies : [];
          if (userCompanies.length) {
            const byId = new Map(userCompanies.map((c) => [c.id, c]));
            const sourceCompanies = Array.isArray(companies) && companies.length ? companies : userCompanies;
            companies = sourceCompanies.map((c) => Object.assign({}, byId.get(c.id) || {}, c, {
              role_id: (byId.get(c.id) && byId.get(c.id).role_id) != null ? byId.get(c.id).role_id : c.role_id,
              scopes: (byId.get(c.id) && byId.get(c.id).scopes) || c.scopes,
            }));
            company = byId.get(settings.company_id) || company;
          }
        } catch (err) {
          console.warn('child role refresh failed', err);
        }
      }
    }
    if (!isChildCompanyRole(company)) {
      applyChildMode(false, null);
      return;
    }
    try {
      const data = await desktopJson('/v1/companies/' + encodeURIComponent(settings.company_id) + '/child-controls/me');
      const child = data && Array.isArray(data.children) ? data.children[0] : null;
      applyChildMode(true, child || null);
    } catch (err) {
      console.warn('child controls refresh failed', err);
      applyChildMode(true, null);
    }
  }

  function billingRoleIsAdmin(role) {
    if (role == null || role === '') return null;
    if (typeof role === 'number') return role >= 0 && role <= 2;
    const numeric = Number(role);
    if (Number.isFinite(numeric)) return numeric >= 0 && numeric <= 2;
    const text = String(role).toLowerCase();
    if (/(owner|admin|billing)/.test(text)) return true;
    if (/(member|viewer|user)/.test(text)) return false;
    return null;
  }

  function billingCompanyHasAdminRole(company) {
    if (!company) return false;
    const explicit = company.is_admin ?? company.admin ?? company.can_manage_billing;
    if (explicit != null) return !!explicit;
    const role = billingRoleIsAdmin(company.role_id ?? company.roleId ?? company.role ?? company.role_name);
    // Older desktop IPC builds did not include role metadata in list_companies.
    // If the role is absent, let the billing API decide access instead of
    // hiding a critical renewal/limit warning from a real company admin.
    return role == null ? true : role;
  }

  function billingUserCanAdminCompany(user, companyId, fallbackCompany) {
    if (!companyId) return false;
    if (user && user.admin) return true;
    const userCompany = user && Array.isArray(user.companies)
      ? user.companies.find((company) => company.id === companyId)
      : null;
    if (userCompany) return billingCompanyHasAdminRole(userCompany);
    return billingCompanyHasAdminRole(fallbackCompany);
  }

  async function billingApiRequest(path) {
    if (!settings || !settings.jwt || !settings.server_url) {
      throw new Error('Billing requires an authenticated session.');
    }
    const base = settings.server_url.replace(/\/+$/, '');
    const resp = await fetch(base + path, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: 'Bearer ' + settings.jwt,
      },
    });
    if (!resp.ok) throw new Error('Billing request failed: HTTP ' + resp.status);
    const text = await resp.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  async function fetchTrialBillingSnapshot(companyId) {
    const api = window.AgixtApi || {};
    const pricingPromise = typeof api.getPricingConfig === 'function'
      ? api.getPricingConfig().catch(() => null)
      : billingApiRequest('/v1/billing/pricing').catch(() => null);
    const statusPromise = typeof api.getAutoTopupStatus === 'function'
      ? api.getAutoTopupStatus(companyId).catch(() => null)
      : billingApiRequest('/v1/billing/auto-topup?company_id=' + encodeURIComponent(companyId)).catch(() => null);
    const limitsPromise = typeof api.getPlanLimits === 'function'
      ? api.getPlanLimits(companyId).catch(() => null)
      : billingApiRequest('/v1/billing/plan/limits?company_id=' + encodeURIComponent(companyId)).catch(() => null);
    const userPromise = typeof api.getUser === 'function'
      ? api.getUser().catch(() => null)
      : billingApiRequest('/v1/user').catch(() => null);
    const [pricing, status, limits, user] = await Promise.all([
      pricingPromise,
      statusPromise,
      limitsPromise,
      userPromise,
    ]);
    return { pricing, status, limits, user };
  }

  function trialIsCoveredBySubscription(status) {
    if (!status) return false;
    const subscriptionStatus = String(status.subscription_status || '').toLowerCase();
    return !!status.subscription_id
      || !!status.enabled
      || ['active', 'trialing'].includes(subscriptionStatus);
  }

  function trialDaysRemaining(trial) {
    if (!trial) return null;
    if (trial.days_remaining != null && !Number.isNaN(Number(trial.days_remaining))) {
      return Math.max(0, Number(trial.days_remaining));
    }
    if (trial.trial_end) {
      const end = new Date(trial.trial_end);
      if (!Number.isNaN(end.getTime())) {
        return Math.max(0, Math.ceil((end.getTime() - Date.now()) / 86400000));
      }
    }
    return null;
  }

  function daysUntilDate(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return Math.max(0, Math.ceil((date.getTime() - Date.now()) / 86400000));
  }

  function billingDayText(days) {
    if (days == null) return '';
    if (days <= 0) return 'today';
    return days === 1 ? 'in 1 day' : 'in ' + days + ' days';
  }

  function billingDateText(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    try {
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch (_) {
      return '';
    }
  }

  function billingDismissKey(companyId, marker) {
    return TRIAL_BANNER_DISMISS_PREFIX + '.' + companyId + '.' + String(marker || 'active');
  }

  function billingDismissedRecently(companyId, marker) {
    try {
      const raw = window.localStorage.getItem(billingDismissKey(companyId, marker));
      if (!raw) return false;
      const lastDismissed = Number(raw);
      return lastDismissed && (Date.now() - lastDismissed) < TRIAL_BANNER_DISMISS_MS;
    } catch (_) {
      return false;
    }
  }

  function dismissBillingBanner(companyId, marker) {
    try {
      window.localStorage.setItem(billingDismissKey(companyId, marker), String(Date.now()));
    } catch (_) {}
    removeTrialBanner();
  }

  function trialDismissKey(companyId, trial) {
    const marker = (trial && (trial.trial_end || trial.granted_at || trial.domain)) || 'active';
    return billingDismissKey(companyId, 'trial.' + marker);
  }

  function trialDismissedRecently(companyId, trial) {
    const marker = (trial && (trial.trial_end || trial.granted_at || trial.domain)) || 'active';
    return billingDismissedRecently(companyId, 'trial.' + marker);
  }

  function dismissTrialBanner(companyId, trial) {
    const marker = (trial && (trial.trial_end || trial.granted_at || trial.domain)) || 'active';
    dismissBillingBanner(companyId, 'trial.' + marker);
  }

  function removeTrialBanner() {
    const existing = document.getElementById(TRIAL_BANNER_ID);
    if (existing) existing.remove();
  }

  function formatPlanMoney(amount) {
    const value = Number(amount);
    if (!Number.isFinite(value)) return '';
    return '$' + value.toLocaleString(undefined, {
      minimumFractionDigits: value % 1 === 0 ? 0 : 2,
      maximumFractionDigits: 2,
    });
  }

  function trialPlanSummary(pricing) {
    if (!pricing || !Array.isArray(pricing.tiers) || !pricing.tiers.length) return '';
    const monthlyPrices = pricing.tiers
      .map((tier) => Number(tier.price || tier.price_per_unit || tier.monthly_price || 0))
      .filter((value) => value > 0);
    if (!monthlyPrices.length) return '';
    const monthly = Math.min(...monthlyPrices);
    const contracts = pricing.contracts || {};
    if (contracts.annual) {
      const discount = Number(contracts.annual_discount_percent || 0);
      const annual = monthly * 12 * (1 - Math.max(0, Math.min(discount, 100)) / 100);
      const annualText = formatPlanMoney(annual) + '/yr';
      const savings = discount > 0 ? ' with ' + discount + '% annual savings' : '';
      return 'Plans start at ' + formatPlanMoney(monthly) + '/mo or ' + annualText + savings + '.';
    }
    return 'Plans start at ' + formatPlanMoney(monthly) + '/mo.';
  }

  function showBillingLifecycleBanner(notice) {
    if (!notice || !notice.company || !notice.company.id || !notice.title || !notice.copy) return;
    removeTrialBanner();
    const banner = document.createElement('section');
    banner.id = TRIAL_BANNER_ID;
    banner.className = 'trial-banner trial-banner-' + (notice.variant || 'warn');
    banner.setAttribute('role', 'status');
    banner.innerHTML = [
      '<div class="trial-banner-icon" aria-hidden="true">',
      notice.icon || '  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/></svg>',
      '</div>',
      '<div class="trial-banner-body">',
      '  <div class="trial-banner-title">' + escapeHtml(notice.title) + '</div>',
      '  <div class="trial-banner-copy">' + escapeHtml(notice.copy) + '</div>',
      '</div>',
      '<div class="trial-banner-actions">',
      '  <button type="button" class="trial-banner-primary" data-billing-action="primary">' + escapeHtml(notice.primaryText || 'View billing') + '</button>',
      '  <button type="button" class="trial-banner-btn" data-billing-action="billing">' + escapeHtml(notice.secondaryText || 'View billing') + '</button>',
      '  <button type="button" class="trial-banner-close" data-billing-action="dismiss" aria-label="Dismiss billing reminder">×</button>',
      '</div>',
    ].join('');
    banner.addEventListener('click', (event) => {
      const actionEl = event.target && typeof event.target.closest === 'function'
        ? event.target.closest('[data-billing-action]')
        : null;
      if (!actionEl) return;
      const action = actionEl.dataset.billingAction;
      if (action === 'dismiss') {
        dismissBillingBanner(notice.company.id, notice.marker);
      } else if (action === 'primary' || action === 'billing') {
        openBillingPane();
      }
    });
    const dockPanel = document.getElementById('dock-panel');
    const topbar = dockPanel ? dockPanel.querySelector('.topbar') : null;
    if (dockPanel && topbar && topbar.parentNode === dockPanel) {
      dockPanel.insertBefore(banner, topbar.nextSibling);
    } else if (dockPanel) {
      dockPanel.insertBefore(banner, dockPanel.firstChild);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }
  }

  function showTrialBanner({ company, pricing, status }) {
    if (!company || !status || !status.trial) return;
    const trial = status.trial;
    const days = trialDaysRemaining(trial);
    if (days == null || days > TRIAL_BANNER_WARNING_DAYS || days <= 0) return;
    const dayText = days === 1 ? '1 day' : days + ' days';
    const planText = trialPlanSummary(pricing);
    const marker = 'trial.' + ((trial && (trial.trial_end || trial.granted_at || trial.domain)) || 'active');
    showBillingLifecycleBanner({
      company,
      marker,
      variant: 'warn',
      title: 'Your ' + ((pricing && pricing.app_name) || 'AGiXT') + ' trial has ' + dayText + ' left',
      copy: 'Subscribe now to keep agents, machines, workspace files, and team chat running without interruption. ' + planText,
      primaryText: 'Subscribe now',
      secondaryText: 'View billing',
    });
  }

  function subscriptionRenewalNotice(company, pricing, status) {
    const nextBillingDate = status && (status.next_billing_date || status.current_period_end);
    const days = daysUntilDate(nextBillingDate);
    if (days == null || days > SUBSCRIPTION_RENEWAL_WARNING_DAYS) return null;
    const appName = (pricing && pricing.app_name) || 'AGiXT';
    const renewalDate = billingDateText(nextBillingDate);
    const amount = status && status.amount_usd ? formatPlanMoney(status.amount_usd) : '';
    return {
      company,
      marker: 'subscription-renewal.' + String(nextBillingDate || 'active'),
      variant: days <= 3 ? 'warn' : 'info',
      title: appName + ' subscription renews ' + billingDayText(days),
      copy: 'Your next subscription payment'
        + (amount ? ' of ' + amount : '')
        + (renewalDate ? ' is scheduled for ' + renewalDate : ' is coming up')
        + '. Review billing now to avoid interruption.',
      primaryText: 'Review billing',
      secondaryText: 'View billing',
      icon: '  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/></svg>',
    };
  }

  function highestPriorityBillingWarning(warnings) {
    if (!Array.isArray(warnings) || !warnings.length) return null;
    warnings = warnings.filter((warning) => {
      const type = String((warning && warning.type) || '');
      return !type.includes('user_limit');
    });
    if (!warnings.length) return null;
    const priority = {
      token_limit_reached: 0,
      device_limit_reached: 1,
      storage_limit_reached: 2,
      token_limit_approaching: 3,
      device_limit_approaching: 4,
      storage_limit_approaching: 5,
    };
    return warnings.slice().sort((a, b) => {
      const aType = a && a.type;
      const bType = b && b.type;
      const aScore = priority[aType] ?? (a && a.severity === 'error' ? 10 : 20);
      const bScore = priority[bType] ?? (b && b.severity === 'error' ? 10 : 20);
      return aScore - bScore;
    })[0];
  }

  function limitWarningNotice(company, limits) {
    const warnings = Array.isArray(limits && limits.warnings)
      ? limits.warnings.filter((warning) => {
          const type = String((warning && warning.type) || '');
          return !type.includes('user_limit');
        })
      : [];
    const warning = highestPriorityBillingWarning(warnings);
    if (!warning) return null;
    const type = String(warning.type || 'limit');
    const tokenWarning = type.includes('token');
    const reached = type.includes('reached') || warning.severity === 'error';
    const extraCount = Math.max(0, warnings.length - 1);
    const title = tokenWarning
      ? (reached ? 'Monthly token limit reached' : 'Monthly token limit is getting close')
      : (reached ? 'Company plan limit reached' : 'Company plan limit is getting close');
    const copy = String(warning.message || 'Review your billing usage.')
      + (extraCount ? ' There ' + (extraCount === 1 ? 'is 1 other limit' : 'are ' + extraCount + ' other limits') + ' also close.' : '');
    return {
      company,
      marker: 'limit.' + type + '.' + String((limits && limits.period_start) || 'active'),
      variant: reached ? 'warn' : 'info',
      title,
      copy,
      primaryText: tokenWarning ? 'Buy token top-up' : 'Upgrade plan',
      secondaryText: 'View usage',
      icon: tokenWarning
        ? '  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 7v10"/><path d="M8 12h8"/></svg>'
        : '  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>',
    };
  }

  async function maybeShowTrialLifecycle() {
    if (!settings || !settings.jwt) return false;
    const company = billingCompanyForTrial();
    if (!company || !company.id) return false;
    let pricing = null;
    let status = null;
    let limits = null;
    let user = null;
    try {
      const snapshot = await fetchTrialBillingSnapshot(company.id);
      pricing = snapshot.pricing;
      status = snapshot.status;
      limits = snapshot.limits;
      user = snapshot.user;
    } catch (err) {
      console.warn('trial lifecycle check failed', err);
      return false;
    }
    if (!pricing || !status) {
      removeTrialBanner();
      return false;
    }
    const canAdminBilling = billingUserCanAdminCompany(user, company.id, company);
    const hasSubscription = trialIsCoveredBySubscription(status);
    if (status.trial && !hasSubscription) {
      const trial = status.trial;
      const days = trialDaysRemaining(trial);
      const active = trial.is_active !== false && (days == null || days > 0);
      if (!active) {
        removeTrialBanner();
        await handlePaymentRequired({
          status: 402,
          body: {
            detail: 'Your trial has ended. Choose a monthly or annual plan to continue using ' + ((pricing && pricing.app_name) || 'AGiXT') + '.',
            pricing_model: pricing && pricing.pricing_model,
            company_id: company.id,
          },
        });
        return true;
      }
      if (canAdminBilling
          && days != null
          && days <= TRIAL_BANNER_WARNING_DAYS
          && !trialDismissedRecently(company.id, trial)) {
        showTrialBanner({ company, pricing, status });
        return false;
      }
    }
    if (!canAdminBilling) {
      removeTrialBanner();
      return false;
    }
    const renewalNotice = subscriptionRenewalNotice(company, pricing, status);
    if (renewalNotice && !billingDismissedRecently(company.id, renewalNotice.marker)) {
      showBillingLifecycleBanner(renewalNotice);
      return false;
    }
    const quotaNotice = limitWarningNotice(company, limits);
    if (quotaNotice && !billingDismissedRecently(company.id, quotaNotice.marker)) {
      showBillingLifecycleBanner(quotaNotice);
      return false;
    }
    removeTrialBanner();
    return false;
  }

  function clearTrialLifecycleChecks() {
    if (trialLifecycleTimer) {
      clearInterval(trialLifecycleTimer);
      trialLifecycleTimer = null;
    }
  }

  function scheduleTrialLifecycleChecks() {
    clearTrialLifecycleChecks();
    trialLifecycleTimer = setInterval(() => {
      maybeShowTrialLifecycle().catch((err) => {
        console.warn('scheduled trial lifecycle check failed', err);
      });
    }, 30 * 60 * 1000);
  }

  async function handleServerIssue(reason) {
    console.warn('AGiXT server returned an outage/error status.', reason || {});
    const detail = (reason && reason.body && (reason.body.detail || reason.body.error || reason.body.message))
      || 'AGiXT server is temporarily unavailable. Please try again shortly.';
    const status = reason && reason.status;
    showSessionOverlay({
      kind: 'server-issue',
      title: status ? `Server Error · ${status}` : 'Connection Issue',
      body: typeof detail === 'string' ? detail : 'AGiXT server returned an unexpected response.',
      hint: 'Your work is saved. The connection indicator will turn green when the server recovers.',
      actions: [
        { label: 'Retry', primary: true, onClick() { try { window.location.reload(); } catch (_) {} } },
        { label: 'Dismiss' },
      ],
    });
    if (typeof setSettingsStatus === 'function') {
      setSettingsStatus(detail, 'error');
    }
  }

  function showSessionOverlay(opts) {
    const id = 'agixt-session-overlay';
    const existing = document.getElementById(id);
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.id = id;
    overlay.className = 'session-overlay';
    overlay.dataset.kind = opts.kind || 'info';
    const iconHtml = {
      payment: '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
      'server-issue': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.73 18l-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      auth: '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    }[opts.kind] || '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
    const actions = (opts.actions || []).map((a, i) => (
      `<button class="${a.primary ? 'session-overlay-primary' : 'session-overlay-btn'}" data-overlay-idx="${i}">${escapeHtml(a.label || 'OK')}</button>`
    )).join('');
    overlay.innerHTML = [
      '<div class="session-overlay-card" role="alertdialog" aria-modal="true">',
      '  <div class="session-overlay-icon">' + iconHtml + '</div>',
      '  <h2 class="session-overlay-title">' + escapeHtml(opts.title || '') + '</h2>',
      '  <p class="session-overlay-body">' + escapeHtml(opts.body || '') + '</p>',
      opts.hint ? '  <p class="session-overlay-hint">' + escapeHtml(opts.hint) + '</p>' : '',
      '  <div class="session-overlay-actions">' + actions + '</div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    overlay.querySelectorAll('[data-overlay-idx]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const action = (opts.actions || [])[Number(btn.dataset.overlayIdx)];
        try { if (action && typeof action.onClick === 'function') action.onClick(); } catch (_) {}
        close();
      });
    });
    requestAnimationFrame(() => overlay.classList.add('is-open'));
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ----- Agent & company selectors ----------------------------------------

  function companyName(companyId) {
    if (!companyId) return '';
    const c = companies.find((x) => x.id === companyId);
    return (c && c.name) || '';
  }

  function renderSelectors() {
    // Header chip: "Agent @ Company".
    const aname = settings.agent_name || '—';
    const cname = companyName(settings.company_id) || settings.company_name || '';
    agentLabel.textContent = cname ? `${aname} @ ${cname}` : aname;
    // Composer placeholder mirrors the active agent so the user knows
    // which agent picks up their next prompt.
    if (composerInput) {
      composerInput.placeholder = aname && aname !== '—'
        ? `Ask ${aname}…`
        : 'Ask the agent…';
    }

    // Build the dropdown listing every reachable agent, grouped by company.
    agentMenuList.innerHTML = '';
    const everyAgent = agentEntriesAcrossCompanies();
    if (!everyAgent.length) {
      const empty = document.createElement('div');
      empty.className = 'popover-menu-item';
      empty.style.color = 'var(--text-faint)';
      empty.textContent = 'No agents available';
      agentMenuList.appendChild(empty);
    } else {
      everyAgent.forEach((entry) => {
        const item = document.createElement('button');
        item.className = 'popover-menu-item';
        item.type = 'button';
        const isSelected = entry.agent.id === settings.agent_id;
        if (isSelected) item.classList.add('is-selected');
        item.innerHTML =
          `<span class="popover-menu-check">${isSelected ? '✓' : ''}</span>` +
          `<span class="agent-name"></span>` +
          `<span class="agent-company"></span>`;
        item.querySelector('.agent-name').textContent = entry.agent.name || entry.agent.id;
        item.querySelector('.agent-company').textContent =
          entry.company ? `@${entry.company.name}` : '';
        item.addEventListener('click', () => onPickAgent(entry));
        agentMenuList.appendChild(item);
      });
    }
  }

  // Returns every (agent, company) pair the user can reach. AGiXT's
  // /v1/companies response on the desktop does NOT include a nested
  // `agents` list per company — that was only true for older API
  // shapes — so we resolve the company for each agent by matching
  // agent.company_id against the companies list. Falls back to
  // company-less entries when no match exists (shouldn't happen for
  // properly-scoped agents, but keeps the dropdown populated).
  function agentEntriesAcrossCompanies() {
    const out = [];
    if (agents.length) {
      agents.forEach((a) => {
        const c = a.company_id
          ? companies.find((co) => co.id === a.company_id) || null
          : null;
        out.push({ agent: a, company: c });
      });
    } else if (companies.length) {
      companies.forEach((c) => {
        (c.agents || []).forEach((a) => out.push({ agent: a, company: c }));
      });
    }
    return out;
  }

  async function onPickAgent(entry) {
    closeMenus();
    const a = entry.agent;
    const c = entry.company;
    const priorAgentId = settings.agent_id;
    if (priorAgentId && priorAgentId !== a.id && settings.conversation_id) {
      rememberAgentConversation(priorAgentId, settings.conversation_id);
    }
    await persistSettings({
      agent_id: a.id,
      agent_name: a.name,
      company_id: c ? c.id : settings.company_id,
      company_name: c ? c.name : settings.company_name,
    });
    renderSelectors();
    await refreshConversations();
    await ensureConversationForActiveAgent({ loadHistory: true });
    // Selected agent / company drives the desktop-extensions manifest
    // (an agent_extension or company_scope gate may now resolve
    // differently). Refresh so any newly-eligible page appears in the
    // sidenav and any newly-ineligible one drops out.
    if (window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.refresh === 'function') {
      window.AgixtDesktopExtensions.refresh();
    }
    // Notify peer windows (Agent Settings) so they can re-fetch for the
    // newly active agent without requiring a manual reload.
    if (event && event.emit) {
      try { await event.emit('agixt-agent-changed', { agent_id: a.id, agent_name: a.name }); }
      catch (e) { /* ignore — best-effort cross-window sync */ }
    }
  }

  function filteredAgents() {
    // Used internally to pick a default agent when none is set yet.
    if (!agents.length) return [];
    if (!settings.company_id) return agents;
    const company = companies.find((c) => c.id === settings.company_id);
    if (company && Array.isArray(company.agents) && company.agents.length) {
      return company.agents;
    }
    return agents.filter((a) => !a.company_id || a.company_id === settings.company_id);
  }

  function eligibleAgentsForCompany(companyId) {
    if (!agents.length) return [];
    if (!companyId) return agents;
    const company = companies.find((c) => c.id === companyId);
    if (company && Array.isArray(company.agents) && company.agents.length) {
      return company.agents;
    }
    return agents.filter((a) => !a.company_id || a.company_id === companyId);
  }

  async function refreshAgentsAndCompanies() {
    if (!settings.jwt) {
      companies = [];
      agents = [];
      setTeamChatAvailable(false);
      renderSelectors();
      return;
    }
    let companiesLoaded = false;
    let agentsLoaded = false;
    try {
      companies = await invoke('list_companies');
      companiesLoaded = true;
    } catch (err) {
      console.warn('list_companies failed', err);
      companies = [];
    }
    try {
      agents = await invoke('list_agents');
      agentsLoaded = true;
    } catch (err) {
      console.warn('list_agents failed', err);
      agents = [];
    }

    const priorCompanyId = settings.company_id || null;
    const priorAgentId = settings.agent_id || null;
    const nextSettings = { ...settings };
    const patch = {};
    const stageSetting = (key, value) => {
      if ((nextSettings[key] || null) === (value || null)) return;
      nextSettings[key] = value;
      patch[key] = value;
    };

    if (companiesLoaded) {
      const selectedCompany = nextSettings.company_id
        ? companies.find((c) => c.id === nextSettings.company_id)
        : null;
      if (companies.length && !selectedCompany) {
        const primary = companies.find((c) => c.primary) || companies[0];
        stageSetting('company_id', primary.id);
        stageSetting('company_name', primary.name);
      } else if (selectedCompany) {
        stageSetting('company_name', selectedCompany.name);
      } else {
        stageSetting('company_id', null);
        stageSetting('company_name', null);
      }
    }

    if (agentsLoaded) {
      const eligible = eligibleAgentsForCompany(nextSettings.company_id);
      const selectedAgent = nextSettings.agent_id
        ? eligible.find((a) => a.id === nextSettings.agent_id)
        : null;
      if (eligible.length && !selectedAgent) {
        const def = eligible.find((a) => a.default) || eligible[0];
        stageSetting('agent_id', def.id);
        stageSetting('agent_name', def.name);
      } else if (selectedAgent) {
        stageSetting('agent_name', selectedAgent.name);
      } else {
        stageSetting('agent_id', null);
        stageSetting('agent_name', null);
      }
    } else if (priorCompanyId !== (nextSettings.company_id || null)) {
      stageSetting('agent_id', null);
      stageSetting('agent_name', null);
    }

    const contextChanged = priorCompanyId !== (nextSettings.company_id || null)
      || priorAgentId !== (nextSettings.agent_id || null);
    if (contextChanged) {
      stageSetting('conversation_id', null);
      stageSetting('conversation_name', null);
      conversationName = null;
    }
    if (Object.keys(patch).length) {
      await persistSettings(patch);
    }
    renderSelectors();
    await refreshChildMode();
    await refreshTeamChatAvailability();
    if (contextChanged
        && window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.refresh === 'function') {
      window.AgixtDesktopExtensions.refresh();
    }
  }

  // ----- Popover menus (agent + conversation) -----

  function openMenu(which) {
    closeMenus();
    if (which === 'agent') {
      agentMenu.hidden = false;
      agentBtn.setAttribute('aria-expanded', 'true');
    } else if (which === 'convo') {
      convoMenu.hidden = false;
      convoBtn.setAttribute('aria-expanded', 'true');
      // Autofocus the search field so the user can start typing
      // immediately. Reset prior search so the full list shows first.
      if (convoSearchInput) {
        convoSearchInput.value = '';
        convoSearchTerm = '';
        setTimeout(() => convoSearchInput.focus(), 0);
      }
      refreshConversations();
    }
  }
  function closeMenus() {
    agentMenu.hidden = true;
    convoMenu.hidden = true;
    agentBtn.setAttribute('aria-expanded', 'false');
    convoBtn.setAttribute('aria-expanded', 'false');
  }
  agentBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (agentMenu.hidden) openMenu('agent'); else closeMenus();
  });
  convoBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (convoMenu.hidden) openMenu('convo'); else closeMenus();
  });
  document.addEventListener('click', (e) => {
    if (!agentMenu.hidden && !agentMenu.contains(e.target) && e.target !== agentBtn) closeMenus();
    if (!convoMenu.hidden && !convoMenu.contains(e.target) && e.target !== convoBtn) closeMenus();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (!agentMenu.hidden || !convoMenu.hidden)) closeMenus();
  });

  // ----- Conversation switcher -----

  let conversations = [];
  let convoSearchTerm = '';

  function normalizedName(value) {
    return String(value || '').trim().toLowerCase();
  }

  function activeAgent() {
    const id = settings && settings.agent_id;
    if (id) {
      const direct = agents.find((a) => a.id === id);
      if (direct) return direct;
      const nested = agentEntriesAcrossCompanies().find((entry) => entry.agent.id === id);
      if (nested) return nested.agent;
    }
    if (settings && (settings.agent_id || settings.agent_name)) {
      return {
        id: settings.agent_id || '',
        name: settings.agent_name || '',
        default: false,
      };
    }
    return null;
  }

  function isDefaultAgent(agent) {
    if (!agent) return false;
    if (agent.default) return true;
    const eligible = filteredAgents();
    return !!(eligible.length && eligible[0].id === agent.id);
  }

  function conversationMap() {
    return new Map(conversations.map((conv) => [conv.id, conv]));
  }

  function conversationMatchesAgent(conv, agent = activeAgent(), seen = new Set()) {
    if (!conv || !agent) return true;
    if (seen.has(conv.id)) return false;
    seen.add(conv.id);
    const type = normalizedName(conv.conversation_type);
    if (type === 'group') return false;
    if (type === 'thread') {
      const parentId = conv.parent_id || conv.parentId;
      const parent = parentId ? conversationMap().get(parentId) : null;
      return parent ? conversationMatchesAgent(parent, agent, seen) : false;
    }

    const agentName = normalizedName(agent.name || settings.agent_name);
    if (!agentName) return true;
    const convAgent = normalizedName(conv.agent_name || conv.agentName);
    if (convAgent) return convAgent === agentName;

    const display = normalizedName(conv.display_name || conv.displayName);
    const name = normalizedName(conv.name);
    if (type === 'dm') {
      return display === agentName || name === agentName;
    }
    if (display === agentName || name === agentName) return true;

    // Old private conversations may not have `agent_name` metadata until
    // their first assistant reply. Keep those visible under the default agent
    // so legacy desktop history does not disappear.
    return (!type || type === 'private') && isDefaultAgent(agent);
  }

  function activeAgentConversations() {
    return conversations.filter((conv) => conversationMatchesAgent(conv));
  }

  function agentConversationStorageKey(agentId = settings && settings.agent_id) {
    if (!agentId) return '';
    const user = (settings && (settings.user_email || settings.server_url)) || 'default';
    return `agixt-desktop-last-conversation:${user}:${agentId}`;
  }

  function rememberAgentConversation(agentId = settings && settings.agent_id, conversationId = settings && settings.conversation_id) {
    const key = agentConversationStorageKey(agentId);
    if (!key || !conversationId) return;
    rememberedAgentConversations.set(key, conversationId);
  }

  function rememberedAgentConversation(agentId = settings && settings.agent_id) {
    const key = agentConversationStorageKey(agentId);
    if (!key) return '';
    return rememberedAgentConversations.get(key) || '';
  }

  async function refreshConversations() {
    if (!settings.jwt) {
      convoMenuList.innerHTML = '<div class="popover-menu-item" style="color:var(--text-faint)">Sign in to see conversations</div>';
      return;
    }
    try {
      conversations = await invoke('list_conversations');
    } catch (e) {
      console.warn('list_conversations failed', e);
      conversations = [];
    }
    renderConversationList();
  }

  function renderConversationList() {
    convoMenuList.innerHTML = '';
    const term = convoSearchTerm.trim().toLowerCase();
    const scoped = activeAgentConversations();
    const filtered = term
      ? scoped.filter((c) => {
          const label = [c.display_name, c.displayName, c.name, c.summary]
            .filter(Boolean)
            .join(' ');
          return label.toLowerCase().includes(term);
        })
      : scoped;
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'popover-menu-item';
      empty.style.color = 'var(--text-faint)';
      const aname = settings.agent_name || 'this agent';
      empty.textContent = term ? 'No matching conversations' : `No conversations for ${aname}`;
      convoMenuList.appendChild(empty);
      return;
    }
    filtered.slice(0, 200).forEach((conv) => {
      const item = document.createElement('button');
      item.className = 'popover-menu-item';
      item.type = 'button';
      const isSelected = conv.id === settings.conversation_id;
      if (isSelected) item.classList.add('is-selected');
      item.innerHTML =
        `<span class="popover-menu-check">${isSelected ? '✓' : ''}</span>` +
        `<span class="convo-meta">` +
          `<span class="convo-name"></span>` +
          (conv.updated_at ? `<span class="convo-time"></span>` : '') +
        `</span>`;
      item.querySelector('.convo-name').textContent = prettyConvoName(conv);
      const t = item.querySelector('.convo-time');
      if (t && conv.updated_at) t.textContent = formatRelative(conv.updated_at);
      item.addEventListener('click', () => onPickConversation(conv));
      convoMenuList.appendChild(item);
    });
  }

  // Live-filter as the user types in the search box.
  const convoSearchInput = $('convo-search');
  if (convoSearchInput) {
    convoSearchInput.addEventListener('input', () => {
      convoSearchTerm = convoSearchInput.value;
      renderConversationList();
    });
  }

  function formatRelative(iso) {
    const ms = Date.parse(iso);
    if (!isFinite(ms)) return '';
    const diff = Date.now() - ms;
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
    return `${Math.round(diff / 86_400_000)}d ago`;
  }

  async function onPickConversation(conv) {
    closeMenus();
    if (conv.id === settings.conversation_id) return;
    await activateConversation(conv, { loadHistory: true });
  }

  async function activateConversation(conv, options = {}) {
    if (!conv || !conv.id) return;
    try {
      await invoke('select_conversation', { id: conv.id, name: prettyConvoName(conv) });
      settings = await invoke('get_settings');
      conversationName = conv.name || conv.display_name || conv.displayName || settings.conversation_name || '-';
      rememberAgentConversation(settings.agent_id, conv.id);
      updateConvoLabel();
      // Reconnect the WebSocket FIRST (it uses the new conversation_id)
      // so any concurrent live messages funnel into the right thread,
      // then replay the historical messages through the same ingest()
      // path. The clear() that loadHistory does is safe because the
      // chat panel's previous content was for a different conversation.
      reconnectChat();
      if (options.loadHistory !== false) {
        await window.AgixtChat.loadHistory(conv.id);
      }
      // If the workspace is open, point it at the new conversation
      // so the file list refreshes instead of showing stale entries
      // from the previous thread.
      reloadWorkspaceForActiveConversation({ conversationId: conv.id });
    } catch (e) {
      console.warn('select_conversation failed', e);
    }
  }

  function prettyConvoName(conv) {
    if (!conv) return 'New conversation';
    const raw = (conv.display_name || conv.displayName || conv.name || '').trim();
    if (!raw || raw === '-') return 'New conversation';
    return raw;
  }

  function updateConvoLabel() {
    // Prefer the freshly fetched list when available so agent switches do not
    // keep showing the previous agent's persisted conversation name.
    const cur = conversations.find((c) => c.id === settings.conversation_id);
    if (cur) {
      convoLabel.textContent = prettyConvoName(cur);
      return;
    }
    const persisted = (settings.conversation_name || '').trim();
    if (persisted && persisted !== '-') {
      convoLabel.textContent = persisted;
      return;
    }
    convoLabel.textContent = 'New conversation';
  }

  if (convoNewBtn) {
    convoNewBtn.addEventListener('click', async () => {
      closeMenus();
      await startNewConversation();
    });
  }

  // ----- Conversation lifecycle -------------------------------------------

  function newConversationName(forceNew) {
    const aname = settings.agent_name || 'XT';
    if (!forceNew) return aname;
    const day = new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const time = new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    return `${aname} - ${day}, ${time}`;
  }

  async function ensureConversation(options = {}) {
    if (!settings.jwt) return;
    if (settings.conversation_id && !options.forceNew) {
      conversationName = settings.conversation_name || '-';
      reconnectChat();
      reloadWorkspaceForActiveConversation();
      return;
    }
    try {
      // Match the web app's agent-DM convention. AGiXT auto-renames
      // conversations whose name is the agent name, or "{agent} - date".
      const forceNew = !!options.forceNew;
      const name = newConversationName(forceNew);
      const resp = await invoke('new_conversation', { name, forceNew });
      settings = await invoke('get_settings');
      conversationName = (resp && (resp.display_name || resp.name)) || name;
      rememberAgentConversation(settings.agent_id, settings.conversation_id);
      reconnectChat();
      reloadWorkspaceForActiveConversation();
    } catch (err) {
      console.warn('new_conversation failed', err);
    }
  }

  function reloadWorkspaceForActiveConversation(options = {}) {
    const targetConversationId = options.conversationId || (settings && settings.conversation_id);
    if (!window.AgixtWorkspace
        || typeof window.AgixtWorkspace.isOpen !== 'function'
        || !window.AgixtWorkspace.isOpen()
        || typeof window.AgixtWorkspace.reload !== 'function'
        || !settings
        || !targetConversationId) {
      return;
    }
    window.AgixtWorkspace.reload({
      serverUrl: settings.server_url,
      jwt: settings.jwt,
      agentName: settings.agent_name || (agents && agents[0] && agents[0].name) || 'XT',
      conversationId: targetConversationId,
      silent: options.silent !== false,
      burst: options.burst !== false,
    });
  }

  async function ensureConversationForActiveAgent(options = {}) {
    if (!settings.jwt) return;
    const current = conversations.find((c) => c.id === settings.conversation_id);
    if (current && conversationMatchesAgent(current)) {
      rememberAgentConversation(settings.agent_id, current.id);
      reconnectChat();
      updateConvoLabel();
      if (options.loadHistory) await window.AgixtChat.loadHistory(current.id);
      return;
    }

    const scoped = activeAgentConversations();
    const rememberedId = rememberedAgentConversation();
    const remembered = rememberedId ? scoped.find((c) => c.id === rememberedId) : null;
    const next = remembered || scoped[0];
    if (next) {
      await activateConversation(next, { loadHistory: !!options.loadHistory });
      return;
    }
    await startNewConversation({ forceNew: false, loadHistory: !!options.loadHistory });
  }

  async function startNewConversation(options = {}) {
    window.AgixtChat.clear();
    const forceNew = options.forceNew != null
      ? !!options.forceNew
      : activeAgentConversations().length > 0;
    settings = { ...settings, conversation_id: null, conversation_name: null };
    await invoke('save_settings', { settings });
    await ensureConversation({ forceNew });
    reconnectChat();
    reloadWorkspaceForActiveConversation();
    await refreshConversations();
    // The toolbar `+` button used to leave the chip showing the previous
    // conversation's name. Refresh from inside startNewConversation so
    // every caller (toolbar `+`, dropdown's "+ New conversation", auth
    // boot) ends up with the chip in sync — and the label snaps to
    // "New conversation" until AGiXT auto-renames the "-" placeholder.
    updateConvoLabel();
    if (options.loadHistory && settings.conversation_id) {
      await window.AgixtChat.loadHistory(settings.conversation_id);
    }
  }

  function reconnectChat() {
    if (!settings.jwt || !settings.conversation_id) return;
    window.AgixtChat.configure({
      serverUrl: settings.server_url,
      jwt: settings.jwt,
      conversationId: settings.conversation_id,
    });
  }

  // Open (or re-auth) the user-level notifications WebSocket. Mirrors
  // web/components/providers/BrowserNotificationProvider — the singleton
  // inside notifications.js dedupes calls, so it's safe to invoke from
  // both the boot path and onAuthenticated.
  function startNotifications() {
    if (!window.AgixtNotifications) return;
    if (!settings || !settings.jwt || !settings.server_url) return;
    window.AgixtNotifications.start({
      serverUrl: settings.server_url,
      jwt: settings.jwt,
      getActiveConversationId: () => (settings && settings.conversation_id) || null,
    });
  }

  // ----- Composer ---------------------------------------------------------

  function autoResize() {
    composerInput.style.height = 'auto';
    composerInput.style.height = Math.min(composerInput.scrollHeight, 160) + 'px';
  }
  composerInput.addEventListener('input', autoResize);
  composerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      frontendLog('info', 'composer enter pressed');
      e.preventDefault();
      sendCurrent();
    }
  });

  // ----- Attachments -------------------------------------------------------
  // Attachments selected in the desktop shell are uploaded to the active
  // conversation workspace before the turn is sent. The model still gets the
  // original desktop path as provenance, but the durable artifact it should
  // use is the workspace-relative path returned by the backend.
  let attachedFiles = [];

  function basename(p) {
    if (!p) return '';
    const m = String(p).match(/[^\\\/]+$/);
    return m ? m[0] : String(p);
  }

  function renderAttachments() {
    if (!attachmentsEl) return;
    attachmentsEl.innerHTML = '';
    if (!attachedFiles.length) {
      attachmentsEl.hidden = true;
      return;
    }
    attachedFiles.forEach((path, idx) => {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      chip.title = path;
      const name = document.createElement('span');
      name.className = 'attachment-name';
      name.textContent = basename(path);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'attachment-remove';
      remove.setAttribute('aria-label', `Remove ${basename(path)}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        attachedFiles.splice(idx, 1);
        renderAttachments();
      });
      chip.appendChild(name);
      chip.appendChild(remove);
      attachmentsEl.appendChild(chip);
    });
    attachmentsEl.hidden = false;
  }

  async function pickAttachments() {
    const dlg = tauri && tauri.dialog && tauri.dialog.open;
    if (!dlg) {
      window.AgixtChat.setComposerStatus('File picker unavailable', 'error');
      return;
    }
    let result;
    try {
      result = await tauri.dialog.open({
        multiple: true,
        directory: false,
        title: 'Attach files to send to the agent',
      });
    } catch (err) {
      window.AgixtChat.setComposerStatus(String((err && err.message) || err), 'error');
      return;
    }
    if (!result) return;
    const picks = Array.isArray(result) ? result : [result];
    for (const p of picks) {
      const path = typeof p === 'string' ? p : (p && p.path) || '';
      if (!path) continue;
      if (!attachedFiles.includes(path)) attachedFiles.push(path);
    }
    renderAttachments();
  }

  if (attachBtn) attachBtn.addEventListener('click', pickAttachments);

  // Workspace toggle — opens the conversation workspace editor (1:1
  // port of the web /chat?file=… view). Requires JWT + an active
  // conversation; both are surfaced by `settings`.
  const workspaceBtn = $('btn-workspace');
  if (workspaceBtn) {
    workspaceBtn.addEventListener('click', () => {
      if (!window.AgixtWorkspace) return;
      if (!settings || !settings.jwt) {
        if (window.AgixtChat && window.AgixtChat.setComposerStatus) {
          window.AgixtChat.setComposerStatus('Sign in first.', 'error');
        }
        return;
      }
      const conversationId = (window.AgixtChat && typeof window.AgixtChat.getConversationId === 'function')
        ? window.AgixtChat.getConversationId()
        : (settings && settings.conversation_id);
      if (!conversationId || conversationId === '-') {
        if (window.AgixtChat && window.AgixtChat.setComposerStatus) {
          window.AgixtChat.setComposerStatus('Send a message first to create a conversation.', 'error');
        }
        return;
      }
      window.AgixtWorkspace.toggle({
        serverUrl: settings.server_url,
        jwt: settings.jwt,
        agentName: (agents && agents[0] && agents[0].name) || 'XT',
        conversationId,
      });
    });
  }

  const shareBtn = $('btn-share');
  function activeConversationId() {
    return (window.AgixtChat && typeof window.AgixtChat.getConversationId === 'function')
      ? window.AgixtChat.getConversationId()
      : (settings && settings.conversation_id);
  }

  function notifyShare(message, kind) {
    if (window.AgixtToast && typeof window.AgixtToast.show === 'function') {
      window.AgixtToast.show(message, kind || 'success');
      return;
    }
    if (window.AgixtChat && window.AgixtChat.setComposerStatus) {
      window.AgixtChat.setComposerStatus(message, kind === 'error' ? 'error' : 'success');
    }
  }

  function errText(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    return err.detail || err.message || err.error || String(err);
  }

  async function desktopJson(path, opts) {
    const server = settings && settings.server_url;
    if (!server) throw new Error('Server URL is not configured.');
    if (window.AgixtSession && typeof window.AgixtSession.request === 'function') {
      return window.AgixtSession.request(path, {
        method: (opts && opts.method) || 'GET',
        json: opts && opts.json,
      });
    }
    const init = {
      method: (opts && opts.method) || 'GET',
      headers: Object.assign(
        { Authorization: 'Bearer ' + settings.jwt },
        opts && opts.json != null ? { 'Content-Type': 'application/json' } : {},
      ),
    };
    if (opts && opts.json != null) init.body = JSON.stringify(opts.json);
    const resp = await fetch(new URL(path, server).toString(), init);
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) {}
    if (!resp.ok) {
      if (window.AgixtSession && typeof window.AgixtSession.routeFailureStatus === 'function') {
        try { await window.AgixtSession.routeFailureStatus(resp.status, data); } catch (_) {}
      }
      const err = new Error((data && (data.detail || data.message)) || ('HTTP ' + resp.status));
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function downloadJsonFile(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function safeFilename(value) {
    return String(value || 'conversation').replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '') || 'conversation';
  }

  async function exportCurrentConversation() {
    if (!settings) await loadSettings();
    if (!settings || !settings.jwt) throw new Error('Sign in first.');
    const conversationId = activeConversationId();
    if (!conversationId || conversationId === '-') {
      throw new Error('Send a message first to create a conversation.');
    }
    const data = await desktopJson('/v1/conversation/' + encodeURIComponent(conversationId) + '?limit=1000&page=1&format=tree');
    const name = conversationName || settings.conversation_name || conversationId;
    downloadJsonFile(safeFilename(name) + '_' + new Date().toISOString().slice(0, 10) + '.json', {
      conversation_id: conversationId,
      conversation_name: name,
      exported_at: new Date().toISOString(),
      messages: (data && data.conversation_history) || [],
    });
    notifyShare('Conversation exported.');
  }

  function openShareDialog() {
    const conversationId = activeConversationId();
    if (!settings || !settings.jwt) {
      notifyShare('Sign in first.', 'error');
      return;
    }
    if (!conversationId || conversationId === '-') {
      notifyShare('Send a message first to create a conversation.', 'error');
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'modal open';
    modal.innerHTML = [
      '<div class="modal-card share-modal-card" role="dialog" aria-modal="true" aria-labelledby="share-modal-title">',
      '  <div class="modal-header">',
      '    <div>',
      '      <h2 id="share-modal-title">Share Conversation</h2>',
      '      <p class="share-modal-sub">Generate a link or download the transcript.</p>',
      '    </div>',
      '    <button class="modal-close" type="button" aria-label="Close">',
      '      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
      '    </button>',
      '  </div>',
      '  <div class="modal-body share-modal-body">',
      '    <label class="field"><span>Share Type</span><select id="share-type"><option value="public">Anyone with the link</option><option value="email">A specific user by email</option></select></label>',
      '    <label class="field" id="share-email-wrap" hidden><span>Recipient Email</span><input type="email" id="share-email" placeholder="user@example.com"></label>',
      '    <label class="field check"><input type="checkbox" id="share-workspace"><span>Include workspace files in the share</span></label>',
      '    <label class="field"><span>Expires (optional)</span><input type="datetime-local" id="share-expiry"></label>',
      '    <div class="settings-status" id="share-status"></div>',
      '    <label class="field" id="share-result-wrap" hidden><span>Share Link</span><input type="text" id="share-result" readonly></label>',
      '    <div class="field-actions">',
      '      <button class="btn" id="share-export" type="button">Export JSON</button>',
      '      <div><button class="btn" id="share-cancel" type="button">Cancel</button> <button class="btn btn-primary" id="share-create" type="button">Create Link</button></div>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(modal);
    const close = () => modal.remove();
    const status = modal.querySelector('#share-status');
    const type = modal.querySelector('#share-type');
    const emailWrap = modal.querySelector('#share-email-wrap');
    const email = modal.querySelector('#share-email');
    const workspace = modal.querySelector('#share-workspace');
    const expiry = modal.querySelector('#share-expiry');
    const resultWrap = modal.querySelector('#share-result-wrap');
    const resultInput = modal.querySelector('#share-result');
    const createBtn = modal.querySelector('#share-create');
    const setStatus = (text, cls) => {
      status.textContent = text || '';
      status.className = 'settings-status' + (cls ? ' ' + cls : '');
    };
    type.addEventListener('change', () => { emailWrap.hidden = type.value !== 'email'; });
    modal.querySelector('.modal-close').addEventListener('click', close);
    modal.querySelector('#share-cancel').addEventListener('click', close);
    modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
    resultInput.addEventListener('click', () => resultInput.select());
    resultInput.addEventListener('focus', () => resultInput.select());
    modal.querySelector('#share-export').addEventListener('click', async () => {
      try {
        await exportCurrentConversation();
        close();
      } catch (err) {
        setStatus(errText(err), 'error');
      }
    });
    createBtn.addEventListener('click', async () => {
      if (type.value === 'email' && !email.value.trim()) {
        setStatus('Email is required for email shares.', 'error');
        return;
      }
      createBtn.disabled = true;
      setStatus('Creating share link...');
      try {
        const payload = {
          share_type: type.value,
          email: type.value === 'email' ? email.value.trim() : undefined,
          include_workspace: !!workspace.checked,
          expires_at: expiry.value ? new Date(expiry.value).toISOString() : undefined,
        };
        const data = await desktopJson('/v1/conversation/' + encodeURIComponent(conversationId) + '/share', {
          method: 'POST',
          json: payload,
        });
        resultInput.value = data && data.share_url ? data.share_url : '';
        resultWrap.hidden = false;
        if (resultInput.value && navigator.clipboard) {
          try { await navigator.clipboard.writeText(resultInput.value); } catch (_) {}
        }
        setStatus('Share link created and copied.', 'success');
      } catch (err) {
        setStatus(errText(err), 'error');
      } finally {
        createBtn.disabled = false;
      }
    });
  }

  if (shareBtn) shareBtn.addEventListener('click', openShareDialog);

  const deleteConvoBtn = $('btn-delete-conversation');
  async function deleteActiveConversation() {
    if (childMode) {
      notifyShare('Child profiles can start and switch conversations, but deletion is for parents.', 'error');
      return;
    }
    const conversationId = activeConversationId();
    if (!conversationId || conversationId === '-') {
      notifyShare('No conversation to delete.', 'error');
      return;
    }
    const cName = (settings && settings.conversation_name) || 'this conversation';
    if (!window.confirm('Delete "' + cName + '"? This cannot be undone.')) return;
    try {
      await window.AgixtApi.deleteConversation(conversationId);
      notifyShare('Conversation deleted.');
      await startNewConversation();
    } catch (err) {
      notifyShare('Failed to delete conversation: ' + errText(err), 'error');
    }
  }
  if (deleteConvoBtn) deleteConvoBtn.addEventListener('click', deleteActiveConversation);

  function collectWorkspaceFiles(value, into) {
    if (!value || typeof value !== 'object') return into;
    const candidates = [];
    if (Array.isArray(value)) candidates.push(...value);
    if (Array.isArray(value.items)) candidates.push(...value.items);
    if (Array.isArray(value.children)) candidates.push(...value.children);
    if (Array.isArray(value.files)) candidates.push(...value.files);
    for (const item of candidates) {
      if (!item || typeof item !== 'object') continue;
      if (!item.type || item.type === 'file') {
        const path = item.path || item.name || item.file_name || item.filename;
        if (path) into.push({
          name: item.name || basename(path),
          path,
          type: item.type || 'file',
        });
      }
      collectWorkspaceFiles(item, into);
    }
    return into;
  }

  function uploadedWorkspacePath(localPath, result) {
    const localName = basename(localPath);
    const files = collectWorkspaceFiles(result && result.server_response, []);
    const exact = files.find((item) => item.name === localName && item.path);
    if (exact) return exact.path;
    const byPath = files.find((item) => basename(item.path) === localName && item.path);
    if (byPath) return byPath.path;
    return (result && result.workspace_path) || localName;
  }

  async function uploadAttachmentsToWorkspace(files) {
    if (!files || !files.length) return [];
    if (!invoke) throw new Error('Desktop attachment upload is unavailable.');

    const uploaded = [];
    for (let i = 0; i < files.length; i += 1) {
      const localPath = files[i];
      const label = basename(localPath);
      window.AgixtChat.setComposerStatus(
        `Uploading ${i + 1}/${files.length}: ${label}`,
        'info',
      );
      let result;
      try {
        result = await invoke('workspace_upload_local', {
          localPath,
          workspacePath: null,
        });
      } catch (err) {
        const message = errText(err);
        if (message.toLowerCase().includes('client commands are disabled')) {
          throw new Error('Enable client commands in Settings to upload local file attachments.');
        }
        throw err;
      }
      uploaded.push({
        local_path: localPath,
        workspace_path: uploadedWorkspacePath(localPath, result),
        bytes: result && result.bytes ? result.bytes : 0,
      });
    }
    window.AgixtChat.setComposerStatus(
      `Uploaded ${uploaded.length} file${uploaded.length === 1 ? '' : 's'} to workspace.`,
      'success',
    );
    try {
      window.dispatchEvent(new CustomEvent('agixt-workspace-mutated', {
        detail: { source: 'attachment-upload', conversationId: settings && settings.conversation_id },
      }));
    } catch (_) {}
    return uploaded;
  }

  // Build the hidden context block sent to the agent for attached files.
  // The workspace paths are authoritative because the upload has already
  // happened before the chat completion request starts.
  function buildAttachmentsContext(files, uploadedFiles) {
    if (!files || !files.length) return '';
    const uploaded = Array.isArray(uploadedFiles) ? uploadedFiles : [];
    const rows = files.map((p) => {
      const match = uploaded.find((u) => u.local_path === p);
      if (match) {
        return `- Workspace: \`${match.workspace_path}\` (${match.bytes || 0} bytes, original desktop path: ${p})`;
      }
      return `- ${p}`;
    });
    return [
      'The user attached the following file(s) to this message. They have',
      'already been uploaded into the active conversation workspace before',
      'this turn started. Use the workspace file tools (Read File, Search',
      'Files, List Directory, Execute Python Code, Use Terminal in Workspace,',
      'etc.) with the workspace-relative paths below. Do not try to read the',
      'original desktop paths unless the user explicitly asks you to work on',
      'their local machine copy.',
      '',
      rows.join('\n'),
      '',
    ].join('\n');
  }

  // When the workspace editor is open with a file selected, prepend a
  // small hidden context block so the agent knows what the user is
  // looking at (and which selection, if any, they want help with).
  // Mirrors the attachments context in tone — primes the agent to use
  // its workspace tools (workspace_read / workspace_write) for the
  // active conversation rather than guessing.
  function buildWorkspaceContext(ctx) {
    if (!ctx) return '';
    const lines = [
      `The user has \`${ctx.path}\` open in the workspace editor for this conversation.`,
      `Use the workspace tools (workspace_read, workspace_write, etc.) to inspect or modify the file when relevant.`,
    ];
    if (ctx.selection) {
      const MAX = 4000;
      const trimmed = ctx.selection.length > MAX
        ? ctx.selection.slice(0, MAX) + '\n…(selection truncated)'
        : ctx.selection;
      lines.push('');
      lines.push('Selected text in the editor:');
      lines.push('```');
      lines.push(trimmed);
      lines.push('```');
    }
    return lines.join('\n');
  }

  function buildExtensionContext() {
    const ext = window.AgixtDesktopExtensions;
    if (!ext || typeof ext.getActiveContext !== 'function') return '';
    try {
      return ext.getActiveContext() || '';
    } catch (err) {
      console.warn('extension context failed', err);
      return '';
    }
  }

  function buildTurnContext(parts) {
    return (parts || [])
      .map((p) => (p == null ? '' : String(p).trim()))
      .filter(Boolean)
      .join('\n\n---\n\n');
  }

  async function sendCurrent() {
    frontendLog('info', 'sendCurrent invoked');
    try {
      if (!settings) await loadSettings();
      const text = composerInput.value;
      if (!text || !text.trim()) {
        frontendLog('info', 'sendCurrent ignored empty text');
        return;
      }
      if (!settings.jwt) {
        window.AgixtChat.setComposerStatus('Sign in first.', 'error');
        frontendLog('warn', 'sendCurrent blocked: missing jwt');
        return;
      }
      const childLock = childMode ? childChatLockState() : '';
      if (childLock) {
        window.AgixtChat.setComposerStatus(childLockMessage(childLock), 'error');
        frontendLog('warn', 'sendCurrent blocked: child chat locked');
        return;
      }
      if (!settings.conversation_id) await ensureConversation();
      const filesForTurn = attachedFiles.slice();
      let uploadedFiles = [];
      if (filesForTurn.length) {
        uploadedFiles = await uploadAttachmentsToWorkspace(filesForTurn);
      }
      const wsCtx = (window.AgixtWorkspace && typeof window.AgixtWorkspace.getContext === 'function')
        ? window.AgixtWorkspace.getContext()
        : null;
      const turnContext = buildTurnContext([
        childMandatoryContext(),
        buildWorkspaceContext(wsCtx),
        filesForTurn.length ? buildAttachmentsContext(filesForTurn, uploadedFiles) : '',
        buildExtensionContext(),
      ]);
      composerInput.value = '';
      autoResize();
      // Clear chips before the await so a follow-up keystroke can't
      // accidentally re-include the same attachments on the next turn.
      attachedFiles = [];
      renderAttachments();
      frontendLog('info', `sendCurrent sending chat (attachments=${filesForTurn.length})`);
      await window.AgixtChat.send(
        text,
        conversationName || settings.conversation_name || '-',
        turnContext,
      );
    } catch (err) {
      const message = err && err.error ? err.error : String(err);
      window.AgixtChat.setComposerStatus(message, 'error');
      frontendLog('error', 'sendCurrent failed', message);
      console.warn('sendCurrent failed', err);
    }
  }

  sendBtn.addEventListener('click', () => {
    frontendLog('info', 'send button clicked');
    sendCurrent();
  });
  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      frontendLog('info', 'stop button clicked');
      try { await window.AgixtChat.stop(); }
      catch (e) { console.warn('stop failed', e); }
    });
  }
  // Subscribe to chat.js's generating signal so we can swap the
  // send/stop affordance in the same composer slot, mirroring the web
  // app's behavior.
  if (window.AgixtChat && typeof window.AgixtChat.onGeneratingChange === 'function') {
    window.AgixtChat.onGeneratingChange((on) => {
      // Keep the send button hidden if a recording is in progress, so the
      // red mic button stays the lone send-the-recording target.
      if (sendBtn) sendBtn.hidden = !!on || micState.state === 'recording';
      if (stopBtn) stopBtn.hidden = !on;
    });
  }
  newConvoBtn.addEventListener('click', startNewConversation);

  // ----- Voice input (mic) -------------------------------------------------
  // Tap-to-record / tap-to-stop. The recorded audio is POSTed to AGiXT's
  // /v1/audio/transcriptions (OpenAI-compatible), and the returned text
  // is sent through the normal compose path so all the activity/render
  // plumbing fires the same way as a typed message. Esc cancels.
  const micState = {
    recorder: null,
    stream: null,
    chunks: [],
    native: false,
    state: 'idle', // 'idle' | 'recording' | 'busy'
    mode: 'voice', // 'voice' | 'conversation'
  };

  function setMicState(state) {
    micState.state = state;
    if (micBtn) {
      micBtn.setAttribute('data-state', state);
      if (state === 'recording') {
        const isConversation = micState.mode === 'conversation';
        micBtn.title = isConversation
          ? 'Send conversation recording (Esc to cancel)'
          : 'Send recording (Esc to cancel)';
        micBtn.setAttribute('aria-label', isConversation ? 'Send conversation recording' : 'Send recording');
      } else if (state === 'busy') {
        micBtn.title = 'Transcribing…';
        micBtn.setAttribute('aria-label', 'Transcribing');
      } else {
        micBtn.title = 'Record voice message (Esc to cancel)';
        micBtn.setAttribute('aria-label', 'Record voice message');
      }
    }
    // Hide the regular send button while recording so the red stop/send
    // button (mic-btn in its recording state) is the only call-to-action.
    // Don't fight the generating-state swap: only touch send/stop when
    // the agent isn't generating a response.
    if (sendBtn && stopBtn && stopBtn.hidden) {
      sendBtn.hidden = state === 'recording';
    }
    try {
      window.dispatchEvent(new CustomEvent('agixt-voice-state-change', {
        detail: { state, mode: micState.mode || 'voice' },
      }));
    } catch (_) {}
  }

  function pickRecorderMime() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    for (const c of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) return c;
    }
    return '';
  }

  function micErrorMessage(err) {
    const message = err && err.error ? err.error : (err && err.message ? err.message : String(err || ''));
    const name = err && err.name ? err.name : '';
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return 'Microphone access denied — allow it in system settings';
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone detected';
    if (name === 'NotReadableError') return 'Microphone is already in use by another app';
    return message ? `Mic error: ${message}` : 'Microphone unavailable';
  }

  function blobFromBase64(b64, mime) {
    const bin = atob(b64 || '');
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime || 'audio/wav' });
  }

  function audioExtension(mime) {
    const clean = (mime || 'audio/wav').split(';')[0].toLowerCase();
    if (clean.includes('wav')) return 'wav';
    if (clean.includes('mpeg') || clean.includes('mp3')) return 'mp3';
    if (clean.includes('mp4') || clean.includes('m4a') || clean.includes('aac')) return 'm4a';
    if (clean.includes('ogg')) return 'ogg';
    if (clean.includes('webm')) return 'webm';
    return (clean.split('/')[1] || 'wav').replace(/[^a-z0-9]/g, '') || 'wav';
  }

  function buildConversationPrompt(transcript) {
    return [
      'The following is a transcription of a live conversation captured from my desktop app.',
      '',
      'Please summarize the conversation, identify decisions, action items, names, dates, and any follow-up questions I should ask.',
      '',
      'Transcript:',
      transcript,
    ].join('\n');
  }

  async function transcribeAndSendBlob(blob, mime) {
    const recordingMode = micState.mode || 'voice';
    if (!blob.size) {
      setMicState('idle');
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus('No audio captured', 'error');
      return;
    }

    setMicState('busy');
    window.AgixtChat.setComposerStatus('Transcribing…');
    let transcript = '';
    try {
      const fd = new FormData();
      fd.append('file', blob, `recording.${audioExtension(mime)}`);
      // AGiXT keys the transcription to the active agent via the `model`
      // form field — same convention as /v1/chat/completions.
      fd.append('model', settings.agent_name || 'XT');
      const url = (settings.server_url || '').replace(/\/+$/, '') + '/v1/audio/transcriptions';
      const fetcher = window.AgixtSession && typeof window.AgixtSession.fetch === 'function'
        ? window.AgixtSession.fetch(url, {
          method: 'POST',
          headers: { Authorization: `Bearer ${settings.jwt}` },
          body: fd,
        })
        : fetch(url, {
          method: 'POST',
          headers: { Authorization: `Bearer ${settings.jwt}` },
          body: fd,
        });
      const resp = await fetcher;
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}${text ? `: ${text.slice(0, 160)}` : ''}`);
      }
      const data = await resp.json().catch(() => ({}));
      transcript = (data && (data.text || data.transcript)) || '';
    } catch (err) {
      setMicState('idle');
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus(
        `Transcription failed: ${err && err.message ? err.message : err}`,
        'error',
      );
      return;
    }

    transcript = (transcript || '').trim();
    if (!transcript) {
      setMicState('idle');
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus("Couldn't hear anything", 'error');
      return;
    }

    try {
      window.dispatchEvent(new CustomEvent('agixt-voice-transcribed', {
        detail: { text: transcript, mode: recordingMode },
      }));
    } catch (_) {}

    composerInput.value = recordingMode === 'conversation'
      ? buildConversationPrompt(transcript)
      : transcript;
    autoResize();
    setMicState('idle');
    micState.mode = 'voice';
    window.AgixtChat.setComposerStatus(recordingMode === 'conversation' ? 'Conversation sent.' : 'Voice sent.');
    const sendPromise = sendCurrent();
    setTimeout(() => {
      if (micState.state === 'idle') window.AgixtChat.setComposerStatus('');
    }, 1400);
    await sendPromise;
  }

  async function startNativeRecording(mode) {
    try {
      const info = await invoke('voice_start_recording');
      micState.native = true;
      micState.cancelled = false;
      setMicState('recording');
      const label = info && info.device_name ? ` (${info.device_name})` : '';
      const prefix = mode === 'conversation' ? 'Recording conversation' : 'Listening';
      window.AgixtChat.setComposerStatus(`${prefix}${label} — tap the red button to send, Esc to cancel`);
      frontendLog('info', 'native voice recording started', JSON.stringify(info || {}));
      return true;
    } catch (err) {
      micState.native = false;
      frontendLog('warn', 'native voice recording unavailable', err && (err.error || err.message || String(err)));
      return false;
    }
  }

  async function startRecording(options) {
    if (micState.state !== 'idle') return;
    const mode = options && options.mode === 'conversation' ? 'conversation' : 'voice';
    micState.mode = mode;
    if (!settings) await loadSettings();
    const childLock = childMode ? childChatLockState() : '';
    if (childLock) {
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus(childLockMessage(childLock), 'error');
      return;
    }
    if (await startNativeRecording(mode)) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus('Microphone API unavailable in this webview', 'error');
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus(micErrorMessage(err), 'error');
      return;
    }
    const mime = pickRecorderMime();
    const recorder = mime
      ? new MediaRecorder(stream, { mimeType: mime })
      : new MediaRecorder(stream);
    micState.stream = stream;
    micState.recorder = recorder;
    micState.chunks = [];
    micState.native = false;
    micState.cancelled = false;
    recorder.addEventListener('dataavailable', (e) => {
      if (e.data && e.data.size > 0) micState.chunks.push(e.data);
    });
    recorder.addEventListener('stop', handleRecordingStopped);
    recorder.start(250);
    setMicState('recording');
    window.AgixtChat.setComposerStatus(
      mode === 'conversation'
        ? 'Recording conversation — tap the red button to send, Esc to cancel'
        : 'Listening — tap the red button to send, Esc to cancel',
    );
  }

  function teardownRecorderStream() {
    if (micState.stream) {
      micState.stream.getTracks().forEach((t) => t.stop());
      micState.stream = null;
    }
  }

  async function stopRecording() {
    if (micState.state !== 'recording') return;
    setMicState('busy');
    if (micState.native) {
      try {
        window.AgixtChat.setComposerStatus('Transcribing…');
        const result = await invoke('voice_stop_recording');
        micState.native = false;
        const blob = blobFromBase64(result.audio_base64, result.mime_type);
        await transcribeAndSendBlob(blob, result.mime_type);
      } catch (err) {
        micState.native = false;
        setMicState('idle');
        micState.mode = 'voice';
        window.AgixtChat.setComposerStatus(micErrorMessage(err), 'error');
        frontendLog('error', 'native voice stop failed', err && (err.error || err.message || String(err)));
      }
      return;
    }

    const r = micState.recorder;
    if (!r) {
      setMicState('idle');
      return;
    }
    try {
      if (r.state !== 'inactive') {
        if (typeof r.requestData === 'function') {
          try { r.requestData(); } catch (_) { /* optional */ }
        }
        r.stop();
      }
    } catch (e) {
      console.warn(e);
      setMicState('idle');
    }
  }

  async function cancelRecording() {
    if (micState.state !== 'recording') return;
    micState.cancelled = true;
    if (micState.native) {
      try { await invoke('voice_cancel_recording'); } catch (_) { /* ignore */ }
      micState.native = false;
      setMicState('idle');
      micState.mode = 'voice';
      window.AgixtChat.setComposerStatus('');
      return;
    }
    const r = micState.recorder;
    try { if (r && r.state !== 'inactive') r.stop(); } catch (_) { /* ignore */ }
    teardownRecorderStream();
    micState.recorder = null;
    micState.chunks = [];
    setMicState('idle');
    micState.mode = 'voice';
    window.AgixtChat.setComposerStatus('');
  }

  async function handleRecordingStopped() {
    teardownRecorderStream();
    const r = micState.recorder;
    micState.recorder = null;
    if (micState.cancelled) {
      micState.chunks = [];
      setMicState('idle');
      micState.mode = 'voice';
      return;
    }
    const mime = (r && r.mimeType) || 'audio/webm';
    const blob = new Blob(micState.chunks, { type: mime });
    micState.chunks = [];
    await transcribeAndSendBlob(blob, mime);
  }

  if (micBtn) {
    micBtn.addEventListener('click', async () => {
      if (micState.state === 'recording') await stopRecording();
      else if (micState.state === 'idle') await startRecording();
    });
  }

  window.AgixtVoiceInput = {
    start: () => startRecording({ mode: 'voice' }),
    stop: () => stopRecording(),
    cancel: () => cancelRecording(),
    toggle: async () => {
      if (micState.state === 'recording' && micState.mode !== 'conversation') {
        await stopRecording();
      } else if (micState.state === 'idle') {
        await startRecording({ mode: 'voice' });
      }
    },
    startConversation: () => startRecording({ mode: 'conversation' }),
    stopConversation: () => stopRecording(),
    transcribeBlob: (blob, mime, options) => {
      const mode = options && options.mode === 'conversation' ? 'conversation' : 'voice';
      micState.mode = mode;
      return transcribeAndSendBlob(blob, mime);
    },
    toggleConversation: async () => {
      if (micState.state === 'recording' && micState.mode === 'conversation') {
        await stopRecording();
      } else if (micState.state === 'idle') {
        await startRecording({ mode: 'conversation' });
      }
    },
    getState: () => ({ state: micState.state, mode: micState.mode || 'voice' }),
  };

  // Esc cancels an in-progress recording without sending. Doesn't
  // interfere when the user is just typing (recording state guards it).
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && micState.state === 'recording') {
      e.preventDefault();
      void cancelRecording();
    }
  });

  collapseBtn?.addEventListener('click', async () => {
    try { await invoke('set_sidebar_visible', { visible: false }); } catch (_) { /* ignore */ }
  });

  // ----- Sidenav (VSCode-style activity bar) ------------------------------
  // Each `.sidenav-btn[data-view=…]` toggles the matching
  // `.view-pane[data-view=…]`. The currently active button gets the
  // `.is-active` class. To add a new section, drop in a button + pane
  // pair sharing the same data-view value — no JS changes needed.
  //
  // Layout invariant: in window-mode, the chat pane is always visible
  // alongside whatever extension pane is active. The active view's
  // pane is the only *other* one shown; chat is special-cased to
  // never be hidden so the conversation stays accessible from any
  // page. `body.with-content-pane` flips the chat pane to its
  // 340px-wide side layout when something else is on the right.
  let activeView = 'chat';
  let hostedRoutingReady = false;
  let applyingHostedRoute = false;
  // Both 'extensions' and 'training' surface inside the shared
  // agent-settings pane. Sidenav/topbar buttons set the desired tab,
  // we map back to the underlying pane id when toggling visibility.
  const PANE_ALIASES = { extensions: 'agent-settings', training: 'agent-settings' };
  function paneIdFor(viewId) { return PANE_ALIASES[viewId] || viewId; }

  function teamChatButton() {
    return document.querySelector('.sidenav-btn[data-view="team-chat"]');
  }

  function applyTeamChatNavVisibility() {
    const available = !!teamChatAvailable;
    const btn = teamChatButton();
    if (btn) {
      btn.hidden = !available;
      btn.disabled = !available || (childMode && !childAllowedView('team-chat'));
      btn.setAttribute('aria-hidden', available ? 'false' : 'true');
    }
    if (!available) {
      const pane = document.querySelector('.view-pane-team-chat');
      if (pane) pane.hidden = true;
      if (activeView === 'team-chat') {
        setActiveView('chat');
      }
    }
    if (window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.reflowSidenav === 'function') {
      try { window.AgixtDesktopExtensions.reflowSidenav(); } catch (_) {}
    }
  }

  function setTeamChatAvailable(available) {
    teamChatAvailable = !!available;
    applyTeamChatNavVisibility();
  }

  function companyShapeHasTeammates(company) {
    if (!company) return false;
    if (Array.isArray(company.users)) return company.users.length > 1;
    const count = Number(
      company.user_count
      ?? company.users_count
      ?? company.member_count
      ?? company.members_count
      ?? 0,
    );
    return Number.isFinite(count) && count > 1;
  }

  function companyShapeHasKnownMemberCount(company) {
    if (!company) return true;
    if (Array.isArray(company.users)) return company.users.length > 0;
    return company.user_count != null
      || company.users_count != null
      || company.member_count != null
      || company.members_count != null;
  }

  async function refreshTeamChatAvailability() {
    const requestId = ++teamChatAvailabilityRequest;
    if (!settings || !settings.jwt || !Array.isArray(companies) || !companies.length) {
      setTeamChatAvailable(false);
      return false;
    }
    if (companies.some(companyShapeHasTeammates)) {
      setTeamChatAvailable(true);
      return true;
    }
    const unknownCompanies = companies.filter((company) => !companyShapeHasKnownMemberCount(company));
    if (!unknownCompanies.length) {
      setTeamChatAvailable(false);
      return false;
    }
    let available = false;
    if (window.AgixtApi && typeof window.AgixtApi.getCompanyMembers === 'function') {
      const results = await Promise.all(unknownCompanies.map((company) =>
        window.AgixtApi.getCompanyMembers(company.id)
          .then((members) => Array.isArray(members) && members.length > 1)
          .catch(() => false)));
      available = results.some(Boolean);
    }
    if (requestId !== teamChatAvailabilityRequest) return teamChatAvailable;
    setTeamChatAvailable(available);
    return available;
  }

  function setActiveView(viewId) {
    if (!viewId) return;
    if (viewId === 'team-chat' && !teamChatAvailable) viewId = 'chat';
    if (childMode && !childAllowedView(viewId)) viewId = 'chat';
    // Picking any section leaves the chat's full-window focus mode and
    // restores the side-by-side split with that page.
    if (document.body.classList.contains('chat-expanded')) {
      preserveChatScroll(() => document.body.classList.remove('chat-expanded'));
    }
    activeView = viewId;
    document.querySelectorAll('.sidenav-btn[data-view]').forEach((btn) => {
      const on = btn.dataset.view === viewId;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const targetPane = paneIdFor(viewId);
    document.querySelectorAll('.chat-screen-main .view-pane[data-view]').forEach((pane) => {
      if (pane.dataset.view === 'chat') {
        // Chat is always visible. Layout swaps via body.with-content-pane.
        pane.hidden = false;
      } else {
        pane.hidden = pane.dataset.view !== targetPane;
      }
    });
    // Switching to a non-chat extension closes any open workspace —
    // they share the right-side content slot, so showing both at once
    // would jam two panes into the same space.
    if (viewId !== 'chat'
        && window.AgixtWorkspace
        && typeof window.AgixtWorkspace.isOpen === 'function'
        && window.AgixtWorkspace.isOpen()) {
      window.AgixtWorkspace.close();
    }
    // Lazy-mount the embedded agent-settings module on first activation
    // so its API calls don't fire until the user actually opens the pane.
    // Pass the requested tab so the same pane can host both Extensions
    // (sidenav) and Training (topbar icon).
    if (targetPane === 'agent-settings'
        && window.AgentSettings
        && typeof window.AgentSettings.mount === 'function') {
      const tab = (viewId === 'training') ? 'training' : 'extensions';
      Promise.resolve(window.AgentSettings.mount({ tab })).catch((err) => {
        console.warn('AgentSettings.mount', err);
      });
    }
    // Same lazy-mount pattern for the user-settings pane (App / Account /
    // Settings / Developer / Billing / Companies / Teams). Subsequent
    // activations re-enter mount() which refreshes whichever sub-tab is
    // currently active without re-fetching everything.
    if (targetPane === 'user-settings'
        && window.UserSettings
        && typeof window.UserSettings.mount === 'function') {
      Promise.resolve(window.UserSettings.mount()).catch((err) => {
        console.warn('UserSettings.mount', err);
      });
    }
    // Automation Chains pane — vanilla-JS port of the web's
    // /settings/chains route. Lazy-mounted on first activation so the
    // chain/agent/prompt API calls don't fire until the pane is opened.
    if (targetPane === 'chains'
        && window.AgixtChains
        && typeof window.AgixtChains.mount === 'function') {
      Promise.resolve(window.AgixtChains.mount()).catch((err) => {
        console.warn('AgixtChains.mount', err);
      });
    }
    // Prompt Library pane — vanilla-JS port of the web's
    // /settings/prompts route. Same lazy-mount pattern as chains.
    if (targetPane === 'prompts'
        && window.AgixtPrompts
        && typeof window.AgixtPrompts.mount === 'function') {
      Promise.resolve(window.AgixtPrompts.mount()).catch((err) => {
        console.warn('AgixtPrompts.mount', err);
      });
    }
    // Team chat pane — Discord-style group chat. Lazy-mounted on first
    // activation so its API round-trips (companies / channels / members)
    // don't fire until the user actually opens the pane.
    if (targetPane === 'team-chat'
        && window.AgixtTeamChat
        && typeof window.AgixtTeamChat.mount === 'function') {
      Promise.resolve(window.AgixtTeamChat.mount()).catch((err) => {
        console.warn('AgixtTeamChat.mount', err);
      });
    }
    // Server-delivered desktop extensions are mounted by the extension
    // loader. Trigger it from the central view switcher too, so panes
    // opened programmatically or restored from overflow cannot become
    // visible without their module being evaluated.
    if (viewId !== 'chat'
        && targetPane === viewId
        && window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.activate === 'function') {
      Promise.resolve(window.AgixtDesktopExtensions.activate(viewId)).catch((err) => {
        console.warn('AgixtDesktopExtensions.activate', viewId, err);
      });
    }
    syncContentPaneClass();
    refreshWindowMode();
    // Let the overflow-aware sidenav re-stamp its "active hidden" dot
    // when the active view is one of the items currently behind the
    // More menu. No-op if the loader hasn't initialised yet.
    if (window.AgixtDesktopExtensions
        && typeof window.AgixtDesktopExtensions.reflowSidenav === 'function') {
      try { window.AgixtDesktopExtensions.reflowSidenav(); } catch (_) {}
    }
    // Notify the Prompt Guidance bar (and any future view-aware module)
    // so it can swap its per-page suggestions to match the page the
    // user just switched to.
    try {
      window.dispatchEvent(new CustomEvent('agixt-view-changed', {
        detail: { viewId },
      }));
    } catch (_) {}
    if (hostedRoutingReady && isHostedWebRuntime() && !applyingHostedRoute) {
      updateHostedRouteForView(viewId);
    }
  }
	  document.querySelectorAll('.sidenav-btn[data-view]').forEach((btn) => {
	    btn.addEventListener('click', () => setActiveView(btn.dataset.view));
	  });
	  // refreshWindowMode is a function declaration below, so setActiveView can
	  // call it during boot. Keep its guard outside the declaration's later block
	  // so test/jsdom startup does not hit the `let` temporal dead zone.
	  let _windowDecorated = false;
	  // Stamp the default active state on the Chat button so the rail shows
	  // the user where they are on first paint. activeView already defaults
	  // to 'chat' above; this just syncs the button visuals.
	  setActiveView(activeView);
  // Surface a tiny extension point so future modules can register their
  // own sections without touching this file directly.
  window.AgixtSidenav = { setActiveView, getActiveView: () => activeView };

  // True when something other than chat is occupying the right side
  // of the chat-screen-main row layout (an active extension OR the
  // workspace editor). Drives the chat pane's split-vs-fill CSS.
  function syncContentPaneClass() {
    const wsOpen = !!(window.AgixtWorkspace
      && typeof window.AgixtWorkspace.isOpen === 'function'
      && window.AgixtWorkspace.isOpen());
    const hasContent = wsOpen || (activeView && activeView !== 'chat');
    // Preserve the chat scroll position across layout transitions —
    // the chat pane's width changes when this class toggles, which
    // causes messages to reflow. Without this snapshot/restore, the
    // user feels the chat "jump" when they navigate between pages.
    preserveChatScroll(() => {
      document.body.classList.toggle('with-content-pane', hasContent);
      relocateTopbarStack();
    });
  }
  window.AgixtSidenav.syncContentPaneClass = syncContentPaneClass;

  // In window mode, physically move the agent / conversation chip
  // controls from the global topbar into the top of the chat pane so
  // they don't claim full window-width chrome. The OS title bar
  // already provides drag + min/max/close + app identity in that
  // mode, so the global topbar adds nothing useful and just steals
  // ~76px of vertical space from the content area.
  //
  // The topbar-stack element carries its own popover-menu children
  // (agent, conversation), so moving the wrapper relocates those too;
  // we set `position: relative` on `.topbar-stack` in CSS so the
  // popovers stay anchored regardless of which parent they're under.
  function relocateTopbarStack() {
    const stack = document.querySelector('.topbar-stack');
    const chatPane = document.querySelector('.view-pane[data-view="chat"]');
    const topbar = document.querySelector('.topbar');
    if (!stack || !chatPane || !topbar) return;
    const inWindow = document.body.classList.contains('window-mode');
    if (inWindow && stack.parentElement !== chatPane) {
      chatPane.insertBefore(stack, chatPane.firstChild);
      stack.classList.add('topbar-stack--in-chat');
    } else if (!inWindow && stack.parentElement !== topbar) {
      topbar.appendChild(stack);
      stack.classList.remove('topbar-stack--in-chat');
    }
  }

  // Run `mutate` while preserving the chat scroller's vertical
  // position. If the user was within ~30px of the bottom we keep them
  // pinned there (so live messages still auto-scroll into view);
  // otherwise we maintain the same scrollTop/scrollHeight ratio so
  // the message they were reading stays under their cursor.
  function preserveChatScroll(mutate) {
    const scroll = document.getElementById('chat-scroll');
    if (!scroll) { try { mutate(); } catch (_) {} return; }
    const wasAtBottom = (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < 30;
    const ratio = scroll.scrollHeight > 0 ? scroll.scrollTop / scroll.scrollHeight : 0;
    try { mutate(); } catch (_) {}
    // After the layout change settles (one frame later) put the
    // viewport back where it was.
    const raf = (typeof requestAnimationFrame === 'function')
      ? requestAnimationFrame
      : (cb) => setTimeout(cb, 0);
    raf(() => {
      if (!scroll.isConnected) return;
      if (wasAtBottom) {
        scroll.scrollTop = scroll.scrollHeight;
      } else {
        scroll.scrollTop = ratio * scroll.scrollHeight;
      }
    });
  }

  // CSS `overflow-anchor: auto` on `.chat` pins to *some* visible element
  // during reflow, but for a chat UI the desired anchor is almost always
  // the bottom. When the user drags the resize handle (or the OS window
  // resizes) the pane width changes, messages re-wrap, scrollHeight
  // shifts, and the anchored element ends up partway up the viewport —
  // i.e. the chat appears to scroll up. Track whether the user is pinned
  // to the bottom on scroll events, and re-pin them after every resize.
  (function installChatResizeAnchor() {
    const scroll = document.getElementById('chat-scroll');
    if (!scroll || typeof ResizeObserver !== 'function') return;
    const NEAR_BOTTOM_PX = 30;
    let pinnedToBottom = true;
    const updatePinned = () => {
      pinnedToBottom = (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < NEAR_BOTTOM_PX;
    };
    scroll.addEventListener('scroll', updatePinned, { passive: true });
    const ro = new ResizeObserver(() => {
      if (pinnedToBottom) scroll.scrollTop = scroll.scrollHeight;
    });
    ro.observe(scroll);
    // The messages list grows independently of the scroller (new
    // messages, expanded activity blocks); reflow there also needs the
    // same anchor-to-bottom behaviour when the user is parked there.
    const list = document.getElementById('messages');
    if (list) ro.observe(list);
  })();

  // ----- Chat pane: resizable + collapsible -------------------------------
  // Drag the seam between chat and content to set chat width. Persists
  // to localStorage so the user's choice sticks across sessions.
  const CHAT_WIDTH_KEY = 'agixt.desktop.chatPaneWidth.v1';
  const CHAT_COLLAPSED_KEY = 'agixt.desktop.chatPaneCollapsed.v1';
  const MIN_CHAT_WIDTH = 240;
  const MAX_CHAT_WIDTH = 720;
  const DEFAULT_CHAT_WIDTH = 340;

  function applyChatPaneWidth(w) {
    const n = Math.max(MIN_CHAT_WIDTH, Math.min(MAX_CHAT_WIDTH, Math.round(w || DEFAULT_CHAT_WIDTH)));
    document.documentElement.style.setProperty('--chat-pane-width', n + 'px');
    return n;
  }

  // Restore on boot.
  try {
    const stored = window.localStorage.getItem(CHAT_WIDTH_KEY);
    if (stored != null) applyChatPaneWidth(Number(stored));
    if (window.localStorage.getItem(CHAT_COLLAPSED_KEY) === '1') {
      // Defer until first content-pane appears — collapsing a hidden
      // pane is a no-op and we don't want to flash an empty state.
      _restoreCollapsedOnFirstContent = true;
    }
  } catch (_) {}
  let _restoreCollapsedOnFirstContent = false;

  const handleEl = document.querySelector('.chat-resize-handle');
  const collapseBtnEl = handleEl && handleEl.querySelector('.chat-collapse-btn');
  const expandBtnEl = handleEl && handleEl.querySelector('.chat-expand-btn');
  const collapsedStripEl = document.querySelector('.chat-collapsed-strip');

  if (handleEl) {
    let dragging = false;
    let startX = 0;
    let startWidth = 0;
    handleEl.addEventListener('pointerdown', (e) => {
      // Don't start a resize when the user clicks the collapse button.
      if (e.target.closest('.chat-handle-actions')) return;
      const chatPane = document.querySelector('.chat-screen-main .view-pane[data-view="chat"]');
      if (!chatPane) return;
      dragging = true;
      handleEl.classList.add('is-dragging');
      startX = e.clientX;
      startWidth = chatPane.getBoundingClientRect().width;
      handleEl.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    handleEl.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const next = applyChatPaneWidth(startWidth + (e.clientX - startX));
      try { window.localStorage.setItem(CHAT_WIDTH_KEY, String(next)); } catch (_) {}
    });
    const stop = (e) => {
      if (!dragging) return;
      dragging = false;
      handleEl.classList.remove('is-dragging');
      try { handleEl.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    handleEl.addEventListener('pointerup', stop);
    handleEl.addEventListener('pointercancel', stop);
    // Double-click to reset to default.
    handleEl.addEventListener('dblclick', (e) => {
      if (e.target.closest('.chat-handle-actions')) return;
      applyChatPaneWidth(DEFAULT_CHAT_WIDTH);
      try { window.localStorage.setItem(CHAT_WIDTH_KEY, String(DEFAULT_CHAT_WIDTH)); } catch (_) {}
    });
  }

  // Flip the chat-collapsed body class with scroll preservation but
  // WITHOUT touching localStorage. Used by the mobile-portrait layout,
  // whose collapse state is a transient consequence of the small
  // viewport — persisting it would corrupt the user's desktop split
  // preference (which `setChatCollapsed` owns).
  function setChatCollapsedTransient(collapsed) {
    preserveChatScroll(() => {
      document.body.classList.toggle('chat-collapsed', !!collapsed);
    });
  }
  // Expanded = chat fills the whole content area, hiding the open
  // content page. Transient (not persisted): it's a momentary focus
  // mode the user leaves by picking any sidenav section again. Mutually
  // exclusive with collapsed.
  function setChatExpanded(expanded) {
    preserveChatScroll(() => {
      if (expanded) document.body.classList.remove('chat-collapsed');
      document.body.classList.toggle('chat-expanded', !!expanded);
    });
  }
  function setChatCollapsed(collapsed) {
    preserveChatScroll(() => {
      if (collapsed) document.body.classList.remove('chat-expanded');
      document.body.classList.toggle('chat-collapsed', !!collapsed);
    });
    // On a phone the collapse state tracks navigation, not a deliberate
    // desktop preference — don't let it overwrite the persisted split.
    if (document.body.classList.contains('mobile-portrait')) return;
    try { window.localStorage.setItem(CHAT_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (_) {}
  }
  if (collapseBtnEl) {
    collapseBtnEl.addEventListener('click', (e) => { e.stopPropagation(); setChatCollapsed(true); });
  }
  if (expandBtnEl) {
    expandBtnEl.addEventListener('click', (e) => { e.stopPropagation(); setChatExpanded(true); });
  }
  if (collapsedStripEl) {
    collapsedStripEl.addEventListener('click', () => setChatCollapsed(false));
  }
  // Re-apply collapsed state after layout transitions so a returning
  // user with a content pane open lands on the saved chat state.
  const _origSync = syncContentPaneClass;
  syncContentPaneClass = function () {
    _origSync();
    if (_restoreCollapsedOnFirstContent && document.body.classList.contains('with-content-pane')) {
      _restoreCollapsedOnFirstContent = false;
      setChatCollapsed(true);
    }
  };
  window.AgixtSidenav.syncContentPaneClass = syncContentPaneClass;

  // ----- Mobile portrait: single-surface navigation ----------------------
  // On a phone in portrait the chat-beside-content split is too narrow,
  // so we present one surface at a time: selecting a section shows that
  // page full-width with the agent chat collapsed to the pop-open
  // "Chat" strip; tapping the strip overlays chat over the page; the
  // Back bar (mobile-only, see index.html / styles.css) returns to the
  // page. `body.mobile-portrait` gates ALL of this — desktop and
  // landscape never get the class so the split is byte-for-byte
  // unchanged there.
  const MOBILE_PORTRAIT_MQ = '(orientation: portrait) and (max-width: 820px)';
  const mpMql = window.matchMedia ? window.matchMedia(MOBILE_PORTRAIT_MQ) : null;

  // The Back bar collapses chat, revealing the content page it overlaid.
  const chatBackBtn = document.querySelector('.chat-mobile-back');
  if (chatBackBtn) {
    chatBackBtn.addEventListener('click', () => setChatCollapsed(true));
  }

  // When navigating between content sections in portrait, default to
  // showing the page (chat collapsed to the strip). We only force this
  // on an actual view *change* — not on every layout reconcile — so the
  // chat overlay the user explicitly popped open via the strip stays
  // open until they hit Back or pick a different section.
  let _mpLastView = activeView;
  const _syncBeforeMobile = syncContentPaneClass;
  syncContentPaneClass = function () {
    _syncBeforeMobile();
    if (document.body.classList.contains('mobile-portrait')) {
      const onContent = activeView && activeView !== 'chat'
        && document.body.classList.contains('with-content-pane');
      if (onContent && activeView !== _mpLastView) {
        setChatCollapsedTransient(true);
      }
    }
    _mpLastView = activeView;
  };
  window.AgixtSidenav.syncContentPaneClass = syncContentPaneClass;

  function applyMobilePortrait(isPortrait) {
    const had = document.body.classList.contains('mobile-portrait');
    document.body.classList.toggle('mobile-portrait', !!isPortrait);
    if (isPortrait === had) return;
    if (isPortrait) {
      // Entering portrait with a page already open: focus the page by
      // collapsing chat (transient — desktop's persisted split pref is
      // left intact).
      if (document.body.classList.contains('with-content-pane')
          && !document.body.classList.contains('chat-collapsed')) {
        setChatCollapsedTransient(true);
      }
    } else {
      // Back to desktop / landscape: restore the user's persisted
      // split-collapse preference so the side-by-side layout returns
      // exactly as they left it.
      let pref = false;
      try { pref = window.localStorage.getItem(CHAT_COLLAPSED_KEY) === '1'; } catch (_) {}
      setChatCollapsedTransient(pref);
    }
    // Team chat resolves its channel/member columns as inline columns
    // (desktop) vs slide-over drawers (portrait) off body.mobile-portrait;
    // nudge it to re-evaluate now that the class flipped.
    if (window.AgixtTeamChat
        && typeof window.AgixtTeamChat.applyCollapseState === 'function') {
      try { window.AgixtTeamChat.applyCollapseState(); } catch (_) {}
    }
    syncContentPaneClass();
  }
  if (mpMql) {
    const onMpChange = (e) => applyMobilePortrait(e.matches);
    if (typeof mpMql.addEventListener === 'function') {
      mpMql.addEventListener('change', onMpChange);
    } else if (typeof mpMql.addListener === 'function') {
      mpMql.addListener(onMpChange); // Safari < 14
    }
    applyMobilePortrait(mpMql.matches); // initial state
  }

  // ----- Window mode reconciler ------------------------------------------
  // The desktop window is always a regular full-app window now (decorated,
  // taskbar-visible, no longer always-on-top). The legacy popover mode
  // was retired, so this reconciler just stamps `body.window-mode` on
  // boot and keeps the topbar-stack relocation in sync. Kept callable
  // so workspace/extension transitions can re-run layout.
	  async function refreshWindowMode() {
    if (_windowDecorated) {
      syncContentPaneClass();
      relocateTopbarStack();
      return;
    }
    _windowDecorated = true;
    document.body.classList.add('window-mode');
    syncContentPaneClass();
    relocateTopbarStack();
    try { await invoke('set_workspace_window_mode', { enabled: true }); }
    catch (_) { /* best-effort — Rust no-ops in the new full-app model */ }
  }
  // Stamp window-mode on the body immediately so the boot frame doesn't
  // render with the legacy popover topbar. The full reconciler runs
  // asynchronously after first layout so syncContentPaneClass /
  // requestAnimationFrame plumbing has had a chance to settle.
  document.body.classList.add('window-mode');
  setTimeout(() => { refreshWindowMode(); }, 0);
  // Public entrypoint other modules call after they change state that
  // would affect the desired chrome (workspace open/close, OAuth
  // connections becoming live, etc).
  window.AgixtWindowMode = { refresh: refreshWindowMode };

  // The desktop-extensions loader (and any future module) needs the
  // current SDK handles + selected scopes to fetch and to pass into
  // each extension page's `mount(container, ctx)` call. Centralising
  // this lookup means we don't have to wire those modules into the
  // settings cache directly.
  window.AgixtAppContext = function () {
    if (!settings || !settings.jwt) return null;
    return {
      serverUrl: settings.server_url,
      webUrl: settings.web_url || null,
      jwt: settings.jwt,
      agentId: settings.agent_id || null,
      agentName: settings.agent_name || null,
      companyId: settings.company_id || null,
      companyName: settings.company_name || null,
      conversationId: settings.conversation_id || null,
      childMode,
      childControl,
      invoke: window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke,
      fetchJson: (path, opts) => {
        if (window.AgixtSession && typeof window.AgixtSession.request === 'function') {
          return window.AgixtSession.request(path, opts || {});
        }
        return Promise.reject(new Error('Desktop session helper is unavailable.'));
      },
      // The Tauri shell plugin's `open()` opens a URL in the user's
      // default browser. Extensions use it for "open in web app"
      // affordances while their desktop counterpart is still in
      // development.
      openExternal: (url) => {
        try {
          const sh = window.__TAURI__ && window.__TAURI__.opener;
          if (sh && typeof sh.openUrl === 'function') return sh.openUrl(url);
          const sh2 = window.__TAURI__ && window.__TAURI__.shell;
          if (sh2 && typeof sh2.open === 'function') return sh2.open(url);
        } catch (_) {}
        return null;
      },
    };
  };

  // Public switch-conversation entry point for desktop extensions. Wraps
  // the private activateConversation flow (Tauri select_conversation +
  // settings refresh + WS reconnect + history load), then refreshes the
  // cached conversation list and snaps the sidenav to chat. Used by the
  // Repos dashboard's Fix-vulns / Audit / Fix-issue / Review-PR buttons,
  // which create a new conversation server-side and hand the user off to
  // the existing chat UI for progress.
  window.AgixtApp = {
    handleAuthExpired,
    handlePaymentRequired,
    handleServerIssue,
    activateConversation: async (conv) => {
      if (!conv || !conv.id) return;
      await activateConversation(conv, { loadHistory: true });
      try { await refreshConversations(); } catch (_) {}
      try {
        if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
          window.AgixtSidenav.setActiveView('chat');
        }
      } catch (_) {}
    },
  };

  // The graduation-cap icon next to the agent selector activates the
  // embedded Agent Settings pane focused on the Training tab.
  // Extensions live in the sidenav button on the left activity bar.
  // App settings live on the pinned gear at the bottom of the sidenav.
  const agentTrainingBtn = $('btn-agent-training');
  if (agentTrainingBtn) {
    agentTrainingBtn.addEventListener('click', () => {
      if (!settings || !settings.jwt) {
        showScreen('auth');
        return;
      }
      setActiveView('training');
    });
  }

  // The gear button in the sidenav has `data-view="user-settings"`, so the
  // setActiveView wiring below already routes clicks to the new side pane.
  // openSettings/closeSettings remain as no-ops in case any other module
  // calls them; they used to drive the modal that's been removed.
  function openSettings(_opts) {
    if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      window.AgixtSidenav.setActiveView('user-settings');
    }
  }
  function closeSettings() { /* no-op — modal is gone */ }

  // ----- Hosted web route compatibility -------------------------------------

  function isHostedWebRuntime() {
    return !!window.__AGIXT_WEB_RUNTIME;
  }

  function routeParts() {
    if (!isHostedWebRuntime()) return [];
    return String(window.location.pathname || '/')
      .split('/')
      .filter(Boolean)
      .map((part) => {
        try { return decodeURIComponent(part); } catch (_) { return part; }
      });
  }

  function setHostedPath(path) {
    if (!isHostedWebRuntime() || !window.history || typeof window.history.replaceState !== 'function') {
      return;
    }
    const nextPath = path || '/chat';
    const current = String(window.location.pathname || '/') + String(window.location.search || '');
    if (current === nextPath) return;
    try { window.history.replaceState({}, '', nextPath); } catch (_) {}
  }

  function hostedSettingsPath(tab) {
    switch (tab) {
      case 'billing': return '/user/billing';
      case 'companies': return '/user/companies';
      case 'teams': return '/user/teams';
      case 'webhooks': return '/user/webhooks';
      case 'settings': return '/user/settings';
      case 'developer': return '/user/developer';
      case 'account': return '/user/manage';
      case 'app':
      case 'glasses':
      default: return '/user';
    }
  }

  function updateHostedRouteForView(viewId) {
    if (!isHostedWebRuntime()) return;
    if (!viewId || viewId === 'chat') {
      const conversationId = settings && settings.conversation_id;
      setHostedPath(conversationId ? '/chat/' + encodeURIComponent(conversationId) : '/chat');
      return;
    }
    if (viewId === 'user-settings') {
      setHostedPath('/user');
      return;
    }
    if (viewId === 'team-chat') {
      setHostedPath('/team');
      return;
    }
    if (viewId === 'chains') {
      setHostedPath('/settings/chains');
      return;
    }
    if (viewId === 'prompts') {
      setHostedPath('/settings/prompts');
      return;
    }
    setHostedPath('/' + encodeURIComponent(viewId));
  }

  window.AgixtAppRoutes = {
    setSettingsTab: (tab) => {
      if (!hostedRoutingReady || applyingHostedRoute) return;
      setHostedPath(hostedSettingsPath(tab));
    },
    cleanBillingReturn: () => setHostedPath('/user/billing'),
    setView: (viewId) => updateHostedRouteForView(viewId),
  };
  hostedRoutingReady = true;

  function isAuthRoute() {
    const parts = routeParts();
    return parts[0] === 'user' && parts[1] !== 'close';
  }

  function hasInvitationRoute() {
    if (!isHostedWebRuntime()) return false;
    try {
      const params = new URLSearchParams(window.location.search || '');
      return Boolean(params.get('invitation_id') || params.get('invitationId') || params.get('invitation') || params.get('invite'));
    } catch (_) {
      return false;
    }
  }

  async function acceptInvitationFromHostedRoute() {
    if (!hasInvitationRoute() || !window.AgixtAuth || typeof window.AgixtAuth.setPendingInvitation !== 'function') {
      return false;
    }
    const captured = window.AgixtAuth.setPendingInvitation(window.location.href);
    if (!captured) return false;
    if (typeof window.AgixtAuth.consumeInvitationUrl === 'function') {
      window.AgixtAuth.consumeInvitationUrl('/chat');
    }
    if (settings && settings.jwt && typeof window.AgixtAuth.acceptPendingInvitation === 'function') {
      await window.AgixtAuth.acceptPendingInvitation();
      await loadSettings();
    }
    return true;
  }

  function routedConversationId() {
    const parts = routeParts();
    if (parts[0] !== 'chat') return '';
    return parts[1] || '';
  }

  function routedUserSettingsTab() {
    const parts = routeParts();
    const first = parts[0] || '';
    const second = parts[1] || '';
    if (first === 'billing') return 'billing';
    if (first === 'companies') return 'companies';
    if (first === 'teams') return 'teams';
    if (first === 'webhooks') return 'webhooks';
    if (first !== 'user') return '';
    if (second === 'manage' || second === 'account') return 'account';
    if (second === 'settings') return 'settings';
    if (second === 'developer') return 'developer';
    if (second === 'billing') return 'billing';
    if (second === 'companies') return 'companies';
    if (second === 'teams') return 'teams';
    if (second === 'webhooks') return 'webhooks';
    return 'account';
  }

  function routedBillingReturn() {
    if (routedUserSettingsTab() !== 'billing') return null;
    let params = null;
    try {
      params = new URLSearchParams(window.location.search || '');
    } catch (_) {
      return null;
    }
    const sessionId = (params.get('session_id') || params.get('checkout_session_id') || '').trim();
    const success = params.get('success') === 'true';
    const canceled = params.get('canceled') === 'true' || params.get('cancelled') === 'true';
    if (!sessionId && !success && !canceled) return null;
    return {
      session_id: sessionId,
      success,
      canceled,
    };
  }

  function routedViewId() {
    const parts = routeParts();
    const first = parts[0] || '';
    const second = parts[1] || '';
    if (!first || first === 'chat') return 'chat';
    if (first === 'team' || first === 'team-chat') return 'team-chat';
    if (first === 'settings' && second === 'chains') return 'chains';
    if (first === 'settings' && second === 'prompts') return 'prompts';
    if (first === 'chains' || first === 'prompts') return first;
    if (first === 'extensions') return 'extensions';
    if (first === 'training') return 'training';
    if (routedUserSettingsTab()) return 'user-settings';
    if (/^[a-z0-9][a-z0-9_-]{0,63}$/.test(first)) return first;
    return 'chat';
  }

  async function activateRoutedConversationIfPresent() {
    const id = routedConversationId();
    if (!id || !settings || !settings.jwt) return false;
    const conv = conversations.find((c) => c.id === id) || {
      id,
      name: settings.conversation_name || 'Conversation',
    };
    await activateConversation(conv, { loadHistory: true });
    return !!(settings && settings.conversation_id === id);
  }

  function applyRoutedView() {
    const requestedViewId = routedViewId();
    const viewId = requestedViewId === 'team-chat' && !teamChatAvailable
      ? 'chat'
      : requestedViewId;
    if (!viewId || !window.AgixtSidenav || typeof window.AgixtSidenav.setActiveView !== 'function') {
      return;
    }
    applyingHostedRoute = true;
    try {
      window.AgixtSidenav.setActiveView(viewId);
    } finally {
      applyingHostedRoute = false;
    }
    if (viewId !== requestedViewId) {
      updateHostedRouteForView(viewId);
    }
    if (viewId === 'user-settings') {
      const tab = routedUserSettingsTab();
      const billingReturn = routedBillingReturn();
      const mountOrTab = () => {
        if (!window.UserSettings) return;
        if (billingReturn && typeof window.UserSettings.handleBillingReturn === 'function') {
          window.UserSettings.handleBillingReturn(billingReturn);
        }
        if (typeof window.UserSettings.mount === 'function') {
          const opts = tab ? { tab } : {};
          if (billingReturn) opts.billingReturn = billingReturn;
          window.UserSettings.mount(tab || billingReturn ? opts : undefined).catch((err) => {
            console.warn('UserSettings route mount failed', err);
          });
        } else if (tab && typeof window.UserSettings.setActiveTab === 'function') {
          window.UserSettings.setActiveTab(tab);
        }
      };
      setTimeout(mountOrTab, 0);
    }
  }

  if (isHostedWebRuntime()) {
    window.addEventListener('popstate', () => applyRoutedView());
  }

  async function startDesktopExtensionsForRoute() {
    if (!window.AgixtDesktopExtensions) return;
    if (typeof window.AgixtDesktopExtensions.start === 'function') {
      await Promise.resolve(window.AgixtDesktopExtensions.start());
    } else if (typeof window.AgixtDesktopExtensions.refresh === 'function') {
      await window.AgixtDesktopExtensions.refresh();
    }
  }

  // ----- Boot --------------------------------------------------------------

  async function onAuthenticated(authContext) {
    await loadSettings();
    if (window.AgixtAuth && typeof window.AgixtAuth.acceptPendingInvitation === 'function') {
      try {
        await window.AgixtAuth.acceptPendingInvitation();
        await loadSettings();
      } catch (err) {
        console.warn('accept pending invitation failed', err);
      }
    }
    const paymentRequired = !!(authContext && authContext.payment_required);
    if (!paymentRequired
        && window.AgixtSession
        && typeof window.AgixtSession.verifyCurrentSession === 'function') {
      const ok = await window.AgixtSession.verifyCurrentSession();
      if (!ok) return;
    }
    if (paymentRequired) {
      await handlePaymentRequired({
        status: 402,
        body: {
          detail: 'This account needs a billing top-up or active subscription to continue.',
          pricing_model: authContext.pricing_model,
          company_id: authContext.company_id,
        },
      });
      scheduleDesktopAutoUpdateCheck();
      return;
    }
    showScreen('chat');
    await refreshAgentsAndCompanies();
    const trialBlocked = await maybeShowTrialLifecycle();
    if (trialBlocked) {
      scheduleDesktopAutoUpdateCheck();
      await startDesktopExtensionsForRoute();
      return;
    }
    scheduleTrialLifecycleChecks();
    // Pre-populate the conversations list so the chip label can resolve
    // against the latest server-side names (e.g. an auto-rename that
    // happened since the last save), not just the persisted snapshot.
    await refreshConversations();
    const routedConversationLoaded = await activateRoutedConversationIfPresent();
    if (!routedConversationLoaded) {
      await ensureConversationForActiveAgent();
    }
    reconnectChat();
    updateConvoLabel();
    if (!routedConversationLoaded && settings.conversation_id) {
      await window.AgixtChat.loadHistory(settings.conversation_id);
    }
    startNotifications();
    scheduleDesktopAutoUpdateCheck();
    await startDesktopExtensionsForRoute();
    // Default landing surface = the agent AI chat, alone, filling the
    // whole content area (no with-content-pane split, no team chat
    // shown first). The user reaches team chat / other sections via the
    // sidenav when they want them.
    if (isHostedWebRuntime()) {
      applyRoutedView();
    } else if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
      window.AgixtSidenav.setActiveView('chat');
    }
  }

  (async () => {
    await loadSettings();
    if (settings.jwt) {
      if (window.AgixtSession && typeof window.AgixtSession.verifyCurrentSession === 'function') {
        const ok = await window.AgixtSession.verifyCurrentSession();
        if (!ok) {
          frontendLog('info', 'stored session rejected during boot');
          return;
        }
      }
      try {
        await acceptInvitationFromHostedRoute();
      } catch (err) {
        console.warn('accept invitation from hosted route failed', err);
      }
      // Returning user — straight into chat. We still let the user fix
      // anything via the settings modal.
      showScreen('chat');
      await refreshAgentsAndCompanies();
      const trialBlocked = await maybeShowTrialLifecycle();
      if (trialBlocked) {
        scheduleDesktopAutoUpdateCheck();
        await startDesktopExtensionsForRoute();
        return;
      }
      scheduleTrialLifecycleChecks();
      await refreshConversations();
      const routedConversationLoaded = await activateRoutedConversationIfPresent();
      if (!routedConversationLoaded) {
        await ensureConversationForActiveAgent();
      }
      reconnectChat();
      updateConvoLabel();
      if (!routedConversationLoaded && settings.conversation_id) {
        await window.AgixtChat.loadHistory(settings.conversation_id);
      }
      startNotifications();
      scheduleDesktopAutoUpdateCheck();
      await startDesktopExtensionsForRoute();
      // Default landing surface = the agent AI chat, alone, filling the
      // whole content area (no split, no team chat shown first).
      if (isHostedWebRuntime()) {
        setTimeout(() => applyRoutedView(), 0);
      } else if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        setTimeout(() => window.AgixtSidenav.setActiveView('chat'), 0);
      }
    } else {
      // No JWT. In web mode (no Tauri shell), show the configured
      // landing page first so first-time visitors see marketing instead
      // of a bare auth form. This is the default for *any* web route that
      // isn't an explicit auth route (/user...) or an invitation link —
      // the landing's own sign-in CTA flips us to the auth screen. In
      // native desktop/mobile mode, skip landing and jump straight to the
      // auth screen — the desktop user already chose to install the app
      // and needs the server picker, not a sales pitch. The browser shim
      // provides a Tauri-compatible surface, so use its explicit web
      // marker to distinguish hosted web from the real native shell.
      const invitationRoute = hasInvitationRoute();
      let landingShown = false;
      if (!invitationRoute && isHostedWebRuntime() && !isAuthRoute()) {
        try {
          const landing = await fetchLandingManifest();
          if (landing) landingShown = showLanding(landing);
        } catch (err) {
          console.warn('landing boot failed', err);
        }
      }
      if (!landingShown) {
        showScreen('auth');
      }
      if (window.AgixtAuth) {
        await window.AgixtAuth.boot({ onAuthenticated });
      }
    }
  })();

  // Refresh the cached conversations list when a conversation is created
  // or deleted on the server (e.g. from another window/device). Cheaper
  // than re-fetching on every dropdown open and keeps the chip label
  // accurate immediately.
  window.addEventListener('agixt-conversation-created', () => {
    refreshConversations().catch((e) => console.warn('refreshConversations after create failed', e));
  });
  window.addEventListener('agixt-conversation-deleted', (ev) => {
    const data = (ev && ev.detail) || {};
    const id = data.conversation_id || data.id;
    if (id) conversations = conversations.filter((c) => c.id !== id);
    if (id && id === settings.conversation_id) {
      // Active conversation was deleted out from under us — reset to a
      // fresh placeholder so the user isn't staring at a dead thread.
      startNewConversation().catch((e) => console.warn('reset after delete failed', e));
    } else {
      renderConversationList();
    }
  });

  // Live-update the conversation chip + cache when AGiXT renames a
  // conversation server-side. Chat.js forwards the WebSocket event as a
  // window CustomEvent so the chat module stays renderer-agnostic.
  window.addEventListener('agixt-conversation-renamed', (ev) => {
    const data = (ev && ev.detail) || {};
    const id = data.conversation_id || data.id;
    const newName = data.new_name || data.name || data.display_name;
    if (!id) return;
    const cached = conversations.find((c) => c.id === id);
    if (cached && newName) cached.name = newName;
    if (id === settings.conversation_id) {
      if (newName) {
        settings = { ...settings, conversation_name: newName };
        invoke('save_settings', { settings }).catch((err) => {
          console.warn('save renamed conversation failed', err);
        });
      }
      convoLabel.textContent = newName ? newName : 'New conversation';
    }
  });

  if (event && event.listen) {
    event.listen('sidebar-state', (ev) => { void ev; });
    // Fired by the Rust deep-link handler after `agixt://login?token=...`
    // arrives and has been verified against /v1/user. Swap the screen
    // automatically — no copy-paste needed.
    event.listen('agixt-authenticated', async () => {
      try { await onAuthenticated(); } catch (e) { console.warn('onAuthenticated', e); }
    });
    event.listen('agixt-invitation', async (ev) => {
      if (window.AgixtAuth && typeof window.AgixtAuth.setPendingInvitation === 'function') {
        window.AgixtAuth.setPendingInvitation(ev && ev.payload);
      }
      await loadSettings().catch(() => {});
      if (settings && settings.jwt) {
        try {
          if (window.AgixtAuth && typeof window.AgixtAuth.acceptPendingInvitation === 'function') {
            await window.AgixtAuth.acceptPendingInvitation();
          }
          await loadSettings();
          await refreshAgentsAndCompanies();
          if (window.AgixtDesktopExtensions
              && typeof window.AgixtDesktopExtensions.refresh === 'function') {
            window.AgixtDesktopExtensions.refresh();
          }
        } catch (err) {
          console.warn('accept invitation from deep link failed', err);
        }
      } else {
        showScreen('auth');
        if (window.AgixtAuth) {
          await window.AgixtAuth.boot({ onAuthenticated });
        }
      }
    });
    event.listen('agixt-shared-conversation', async (ev) => {
      const payload = (ev && ev.payload) || {};
      const token = payload.token || payload.share_token || payload.id || payload.url || '';
      if (!token) return;
      try {
        window.localStorage.setItem('agixt.desktop.pendingSharedConversationToken.v1', String(token));
      } catch (_) {}
      if (window.AgixtSidenav && typeof window.AgixtSidenav.setActiveView === 'function') {
        window.AgixtSidenav.setActiveView('shared-conversations');
      }
      window.dispatchEvent(new CustomEvent('agixt-shared-conversation-open', {
        detail: { token },
      }));
    });
    // Legacy popover mode has been retired — the desktop window is now
    // always a regular full-app window (see refreshWindowMode). The old
    // handler tore down `window-mode` and shoved the topbar-stack (with
    // its brand logo) back into the global topbar on every hide, which
    // on boot produced a duplicate logo + topbar that only corrected
    // once the next setActiveView re-asserted window mode. Hiding to the
    // tray and reopening must keep the full-app chrome stable, so we
    // just close any open menus and re-assert window mode (idempotent).
    event.listen('popover-visible', (ev) => {
      if (ev && ev.payload === false) {
        closeMenus();
        refreshWindowMode();
      }
    });
  }
})();
