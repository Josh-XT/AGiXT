/* Auth screen logic.
 *
 * Handles service selection, email+password login, registration, magic
 * link, and OAuth-via-system-browser flows. Mirrors the field order
 * and method set of the AGiXT NextJS web client login page, adapted
 * for a desktop app with no cookie store — JWTs land in the Rust-side
 * SQLite via the `login_password` / `register_account` IPCs. Magic
 * links and OAuth callbacks return through `agixt://` deep links.
 *
 * Exposes `window.AgixtAuth.boot({onAuthenticated})` which the app shell
 * calls once on startup. When auth completes, `onAuthenticated(context)` fires
 * with the login/register response so the caller can handle limited billing
 * sessions.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const invoke = tauri.core.invoke;
  const opener = tauri.opener || (tauri.core && tauri.core.invoke ? null : null);

  const $ = (id) => document.getElementById(id);

  let brands = [];
  let currentBrand = null; // {slug, label, default_url}
  let mfaPending = false;
  let onAuthenticatedCb = null;
  let oauthRefreshSeq = 0;
  let invitationUnlisten = null;
  let pendingInvitation = null;
  const INVITATION_STORAGE_KEY = 'agixt.desktop.pendingInvitation.v1';

  function setStatus(text, cls) {
    const el = $('auth-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'auth-status' + (cls ? ` ${cls}` : '');
  }

  function activeServerUrl() {
    const v = $('server-url').value.trim();
    if (v) return v.replace(/\/+$/, '');
    return (currentBrand && currentBrand.default_url) || 'http://localhost:7437';
  }

  function activeWebUrl() {
    const v = $('web-url').value.trim();
    if (v) return v.replace(/\/+$/, '');
    return (currentBrand && currentBrand.default_web_url) || 'http://localhost:3437';
  }

  function normalizeInvitation(input) {
    if (!input) return null;
    let data = input;
    if (typeof input === 'string') {
      try {
        const u = new URL(input);
        data = Object.fromEntries(u.searchParams.entries());
      } catch (_) {
        try {
          data = Object.fromEntries(new URLSearchParams(input).entries());
        } catch (_) {
          data = {};
        }
      }
    }
    const id = data.invitation_id || data.invitationId || data.invitation || data.id;
    if (!id) return null;
    return {
      invitation_id: String(id),
      email: data.email ? String(data.email) : '',
      company: data.company || data.company_name ? String(data.company || data.company_name) : '',
    };
  }

  function loadPendingInvitation() {
    if (pendingInvitation) return pendingInvitation;
    try {
      pendingInvitation = normalizeInvitation(JSON.parse(localStorage.getItem(INVITATION_STORAGE_KEY) || 'null'));
    } catch (_) {
      pendingInvitation = null;
    }
    return pendingInvitation;
  }

  function applyPendingInvitationToUi() {
    const inv = loadPendingInvitation();
    const banner = $('auth-invite');
    const body = $('auth-invite-body');
    if (!banner || !body) return;
    if (!inv) {
      banner.hidden = true;
      body.textContent = '';
      return;
    }
    const company = inv.company ? ` for ${inv.company}` : '';
    const email = inv.email ? ` as ${inv.email}` : '';
    body.textContent = `Sign in or create an account${email} to accept this invitation${company}.`;
    banner.hidden = false;
    if (inv.email) {
      if ($('login-email') && !$('login-email').value) $('login-email').value = inv.email;
      if ($('reg-email') && !$('reg-email').value) $('reg-email').value = inv.email;
    }
  }

  function setPendingInvitation(input) {
    const inv = normalizeInvitation(input);
    if (!inv) return false;
    pendingInvitation = inv;
    try { localStorage.setItem(INVITATION_STORAGE_KEY, JSON.stringify(inv)); } catch (_) {}
    applyPendingInvitationToUi();
    setStatus('Sign in or create an account to accept the invitation.', 'info');
    return true;
  }

  function clearPendingInvitation() {
    pendingInvitation = null;
    try { localStorage.removeItem(INVITATION_STORAGE_KEY); } catch (_) {}
    applyPendingInvitationToUi();
  }

  async function acceptPendingInvitation() {
    const inv = loadPendingInvitation();
    if (!inv) return null;
    // Existing users are added when the invite is created, and new/inactive
    // users are accepted by POST /v1/user with invitation_id during register.
    // Keep this helper as the desktop cleanup hook instead of calling a
    // separate accept endpoint.
    clearPendingInvitation();
    setStatus('Invitation handled by the existing account flow.', 'success');
    return { accepted: true, handled_by_existing_flow: true };
  }

  async function finishFromMagicLink(resp, fallbackMessage) {
    if (!resp || !resp.magic_link) return false;
    await persistBrand();
    await invoke('login_with_jwt', {
      serverUrl: activeServerUrl(),
      raw: resp.magic_link,
    });
    clearPendingInvitation();
    setStatus(fallbackMessage || resp.message || 'Signed in.', 'success');
    finish(resp);
    return true;
  }

  function bindInvitationListener() {
    if (invitationUnlisten || !tauri.event || typeof tauri.event.listen !== 'function') return;
    const listener = tauri.event.listen('agixt-invitation', (ev) => {
      setPendingInvitation(ev && ev.payload);
    });
    if (listener && typeof listener.then === 'function') {
      listener.then((unlisten) => { invitationUnlisten = unlisten; }).catch(() => {});
    } else {
      invitationUnlisten = listener;
    }
  }

  function setActiveBrand(slug) {
    currentBrand = brands.find((b) => b.slug === slug) || brands[brands.length - 1];
    $('service-brand').value = currentBrand.slug;
    $('server-url').value = currentBrand.default_url;
    $('web-url').value = currentBrand.default_web_url || '';
    // URL fields are only shown/editable in "custom" mode. Every other
    // brand has a known server+web pair, so exposing the fields would
    // just be noise — and "local" pins to localhost:7437 anyway.
    const isCustom = currentBrand.slug === 'custom';
    $('server-url').readOnly = !isCustom;
    $('web-url').readOnly = !isCustom;
    $('custom-server-field').classList.toggle('readonly', !isCustom);
    $('custom-web-field').classList.toggle('readonly', !isCustom);
    $('custom-server-field').hidden = !isCustom;
    $('custom-web-field').hidden = !isCustom;
    const isLocal = currentBrand.slug === 'local';
    $('local-pane').hidden = !isLocal;
    applyBrandIdentity(currentBrand.slug);
    if (isLocal) {
      refreshLocalStatus();
    } else {
      stopLocalStatusPoll();
    }
  }

  // Map brand slug to its top-bar mark + display title. We intentionally
  // keep the title and the chrome (font, colors) the same across brands —
  // only the logo and product name change so the chat experience stays
  // consistent regardless of which AGiXT-derived service the user is
  // signed in to.
  const BRAND_IDENTITY = {
    agixt:      { logo: 'assets/brands/agixt.svg',      title: 'AGiXT' },
    nursext:    { logo: 'assets/brands/nursext.svg',    title: 'NurseXT' },
    xtsystems:  { logo: 'assets/brands/xtsystems.svg',  title: 'XT Systems' },
    boltremote: { logo: 'assets/brands/boltremote.svg', title: 'BoltRemote' },
    local:      { logo: 'assets/brands/agixt.svg',      title: 'AGiXT' },
    custom:     { logo: 'assets/brands/agixt.svg',      title: 'AGiXT' },
  };

  function applyBrandIdentity(slug) {
    const id = BRAND_IDENTITY[slug] || BRAND_IDENTITY.custom;
    const img = $('brand-mark-img');
    const title = $('brand-title');
    const mark = $('brand-mark');
    if (img) img.src = id.logo;
    if (title) title.textContent = id.title;
    if (mark) mark.classList.remove('fallback');
    // Also paint the sidenav brand slot — it's the first item users see
    // in the activity bar after sign-in, so it has to track the active
    // service brand the same way the auth-screen mark does.
    const sideImg = $('sidenav-brand-mark-img');
    const sideMark = $('sidenav-brand-mark');
    if (sideImg) sideImg.src = id.logo;
    if (sideMark) {
      sideMark.classList.remove('fallback');
      const slot = sideMark.closest('.sidenav-brand');
      if (slot) slot.title = id.title;
    }
  }

  // Expose so app.js can apply the saved brand on boot — without this
  // the topbar logo always reverts to the AGiXT default after restart
  // even when the user picked a different service like BoltRemote.
  window.AgixtBranding = { apply: applyBrandIdentity, identities: BRAND_IDENTITY };

  // ----- Tab switching -----------------------------------------------------

  function showPane(which) {
    const isLogin = which === 'login';
    $('pane-login').hidden = !isLogin;
    $('pane-register').hidden = isLogin;
    $('tab-login').setAttribute('aria-selected', String(isLogin));
    $('tab-register').setAttribute('aria-selected', String(!isLogin));
    setStatus('');
    applyPendingInvitationToUi();
  }

  $('tab-login').addEventListener('click', () => showPane('login'));
  $('tab-register').addEventListener('click', () => showPane('register'));

  // ----- Brand / server selector ------------------------------------------

  async function loadBrands() {
    brands = await invoke('list_service_brands');
    const sel = $('service-brand');
    sel.innerHTML = '';
    brands.forEach((b) => {
      const opt = document.createElement('option');
      opt.value = b.slug;
      opt.textContent = b.label;
      sel.appendChild(opt);
    });
    // Default to whatever's saved, else "local" (the dedicated
    // localhost:7437 entry replaces the old "custom"-as-default).
    const settings = await invoke('get_settings');
    const initial = settings.service_brand || 'local';
    setActiveBrand(initial);
    if (initial === 'custom') {
      if (settings.server_url) $('server-url').value = settings.server_url;
      if (settings.web_url) $('web-url').value = settings.web_url;
    }
    if (settings.user_email) $('login-email').value = settings.user_email;
  }

  // ----- OAuth providers --------------------------------------------------

  async function refreshOAuthProviders() {
    const refreshSeq = ++oauthRefreshSeq;
    const row = $('oauth-row');
    const wrap = $('oauth-buttons');
    wrap.innerHTML = '';
    let providers = [];
    try {
      providers = await invoke('list_oauth_providers', { serverUrl: activeServerUrl() });
    } catch (e) {
      // Servers without /v1/oauth simply have no SSO buttons.
      console.debug('no oauth providers for', activeServerUrl(), e);
    }
    if (refreshSeq !== oauthRefreshSeq) return;
    if (!providers || providers.length === 0) {
      row.hidden = true;
      return;
    }
    providers.forEach((p) => {
      const btn = document.createElement('button');
      btn.className = 'btn btn-oauth';
      btn.dataset.provider = p.name;
      const iconNode = oauthIconNode(p.name);
      btn.appendChild(iconNode);
      const label = document.createElement('span');
      label.textContent = `Continue with ${prettyProviderName(p.name)}`;
      btn.appendChild(label);
      btn.addEventListener('click', () => startOAuth(p));
      wrap.appendChild(btn);
    });
    row.hidden = false;
  }

  /** Map a provider name to the local SVG asset. Strips `_sso` so the
   *  mark file lookups match `microsoft.svg`, `github.svg`, etc.  */
  function oauthIconAsset(name) {
    const slug = (name || '').toLowerCase().replace(/_sso$/, '');
    const known = new Set([
      'microsoft', 'github', 'discord', 'spotify', 'google', 'apple',
    ]);
    if (known.has(slug)) return `assets/oauth/${slug}.svg`;
    return null;
  }

  function oauthIconNode(name) {
    const wrap = document.createElement('span');
    wrap.className = 'oauth-icon';
    const asset = oauthIconAsset(name);
    if (asset) {
      const img = document.createElement('img');
      img.src = asset;
      img.alt = '';
      // Some marks (GitHub, Apple) are pure-white and would disappear on
      // the dark panel without a darker background tile.
      const slug = name.toLowerCase().replace(/_sso$/, '');
      if (slug === 'github' || slug === 'apple') {
        wrap.style.background = '#0d1117';
        wrap.style.padding = '2px';
      }
      wrap.appendChild(img);
    } else {
      wrap.classList.add('fallback');
      wrap.textContent = oauthGlyph(name);
    }
    return wrap;
  }

  function prettyProviderName(name) {
    const t = (name || '').replace(/_(sso|oauth|login)$/, '');
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  function oauthGlyph(name) {
    const k = (name || '').toLowerCase();
    if (k.includes('google')) return 'G';
    if (k.includes('microsoft') || k.includes('teams') || k.includes('office')) return 'M';
    if (k.includes('github')) return '⌥';
    if (k.includes('discord')) return 'D';
    if (k.includes('spotify')) return '♫';
    if (k.includes('apple')) return '';
    return '◯';
  }

  async function startOAuth(provider) {
    setStatus(`Opening ${prettyProviderName(provider.name)} sign-in in your browser…`);
    // OAuth completes via an `agixt://` deep-link callback handled in
    // Rust, which fires `agixt-authenticated` *without* round-tripping
    // through the auth-screen DOM. If we don't persist the brand here,
    // settings.service_brand stays unset and the topbar logo defaults
    // back to AGiXT after restart — even when the user signed in via
    // BoltRemote/NurseXT/etc. Persist before opening the browser so the
    // brand survives every login outcome.
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    let result;
    try {
      result = await invoke('build_oauth_login_url', {
        args: {
          server_url: activeServerUrl(),
          // The OAuth provider redirects here, *not* to the API. AGiXT
          // pre-registered `{web_url}/user/close/{provider}` with each
          // OAuth app, so we have to use that URL exactly or the
          // provider rejects with `redirect_uri_mismatch`.
          web_url: activeWebUrl(),
          provider,
        },
      });
    } catch (e) {
      setStatus(`Couldn't build OAuth URL: ${e.error || e}`, 'error');
      return;
    }
    try {
      // tauri-plugin-opener exposes openUrl as a JS helper; fall back to
      // window.open which Tauri intercepts as the system browser when the
      // origin doesn't match the app.
      if (window.__TAURI__.opener && window.__TAURI__.opener.openUrl) {
        await window.__TAURI__.opener.openUrl(result.url);
      } else {
        window.open(result.url, '_blank', 'noopener');
      }
    } catch (e) {
      console.warn('opener failed, falling back', e);
      window.open(result.url, '_blank', 'noopener');
    }
    setStatus(
      'After authorizing in your browser, you will be returned here automatically.',
      'info',
    );
  }

  $('service-brand').addEventListener('change', async () => {
    setActiveBrand($('service-brand').value);
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    await refreshOAuthProviders();
  });
  $('server-url').addEventListener('change', async () => {
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
    await refreshOAuthProviders();
  });
  $('web-url').addEventListener('change', async () => {
    try { await persistBrand(); } catch (e) { console.warn('persistBrand failed', e); }
  });

  // ----- Email + password login -------------------------------------------

  $('btn-login').addEventListener('click', async () => {
    const email = $('login-email').value.trim();
    const password = $('login-password').value;
    if (!email || !password) {
      setStatus('Email and password required.', 'error');
      return;
    }
    const args = {
      server_url: activeServerUrl(),
      email,
      password,
    };
    if (mfaPending) {
      const token = $('login-mfa').value.trim();
      if (!token) {
        setStatus('Enter the 6-digit authenticator code.', 'error');
        return;
      }
      args.mfa_token = token;
    }
    setStatus('Signing in…');
    try {
      const resp = await invoke('login_password', { args });
      if (resp.token) {
        await persistBrand();
        await acceptPendingInvitation();
        setStatus('Signed in.', 'success');
        finish(resp);
        return;
      }
      if (resp.mfa_required) {
        mfaPending = true;
        $('mfa-field').hidden = false;
        $('login-mfa').focus();
        setStatus('Enter your 6-digit authenticator code.', 'info');
        return;
      }
      setStatus(resp.detail || 'Login failed.', 'error');
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Magic link --------------------------------------------------------

  $('btn-magic-link').addEventListener('click', async () => {
    const email = $('login-email').value.trim();
    if (!email) {
      setStatus('Enter your email first, then click the magic-link button.', 'error');
      return;
    }
    setStatus('Sending magic link…');
    try {
      await persistBrand();
      await invoke('request_magic_link', { args: { server_url: activeServerUrl(), email } });
      setStatus(
        `Sent. Check ${email} for a sign-in link — clicking it will sign you in here.`,
        'success',
      );
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Registration ------------------------------------------------------

  $('btn-register').addEventListener('click', async () => {
    const args = {
      server_url: activeServerUrl(),
      email: $('reg-email').value.trim(),
      first_name: $('reg-first').value.trim(),
      last_name: $('reg-last').value.trim(),
      password: $('reg-password').value,
    };
    const inv = loadPendingInvitation();
    if (inv && inv.invitation_id) args.invitation_id = inv.invitation_id;
    if (!args.email || !args.first_name || !args.last_name || !args.password) {
      setStatus('All registration fields are required.', 'error');
      return;
    }
    setStatus('Creating account…');
    try {
      const resp = await invoke('register_account', { args });
      if (resp.token) {
        await persistBrand();
        await acceptPendingInvitation();
        setStatus('Account created. Welcome!', 'success');
        finish(resp);
        return;
      }
      if (await finishFromMagicLink(resp, resp.message || 'Invitation accepted.')) {
        return;
      }
      if (resp.added_to_company || resp.reactivated) {
        clearPendingInvitation();
        showPane('login');
        setStatus(resp.message || 'Invitation accepted. Sign in to continue.', 'success');
        return;
      }
      setStatus('Registration completed but no token returned. Try signing in.', 'info');
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Helpers -----------------------------------------------------------

  async function persistBrand() {
    if (!currentBrand) return;
    const settings = await invoke('get_settings');
    settings.service_brand = currentBrand.slug;
    settings.server_url = activeServerUrl();
    settings.web_url = activeWebUrl();
    await invoke('save_settings', { settings });
  }

  function finish(context) {
    if (typeof onAuthenticatedCb === 'function') onAuthenticatedCb(context || null);
  }

  function prettyError(e) {
    if (!e) return 'Unknown error';
    if (typeof e === 'string') return e;
    if (e.error) return e.error;
    if (e.message) return e.message;
    try { return JSON.stringify(e); } catch (_) { return String(e); }
  }

  // ----- Local mode (localhost:7437 detection + one-click installer) ----

  const LOCAL_POLL_MS = 4000;
  let localPollTimer = null;
  let localInstallActive = false;
  let localInstallUnlisten = null;
  let hardwareCache = null;

  function setLocalStatus(text, cls) {
    const el = $('local-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'local-status' + (cls ? ` ${cls}` : '');
  }

  function appendLocalLog(line, kind) {
    const log = $('local-install-log');
    if (!log) return;
    const div = document.createElement('div');
    div.className = `local-log-line${kind ? ` local-log-${kind}` : ''}`;
    div.textContent = line;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function clearLocalLog() {
    const log = $('local-install-log');
    if (log) log.innerHTML = '';
  }

  function showLocalInstallControls(running) {
    // When running, hide install button + show "Connect" CTA (the
    // login pane handles credentials once they hit Sign in / Magic
    // link). When not running, swap to the installer.
    $('local-install-row').hidden = running;
    $('local-connect-row').hidden = !running;
  }

  async function refreshLocalStatus() {
    setLocalStatus('Checking localhost:7437…');
    let status;
    try {
      status = await invoke('check_local_agixt');
    } catch (e) {
      setLocalStatus(`Probe failed: ${prettyError(e)}`, 'error');
      showLocalInstallControls(false);
      return;
    }
    if (status.running) {
      const v = status.version ? ` (v${status.version})` : '';
      setLocalStatus(`AGiXT is running on localhost:7437${v}.`, 'ok');
      showLocalInstallControls(true);
    } else {
      const detail = status.detail ? ` (${status.detail})` : '';
      setLocalStatus(`Nothing is running on localhost:7437${detail}.`, 'warn');
      showLocalInstallControls(false);
      // Pre-load hardware info on first detection so the install
      // dialog can show the recommended model immediately.
      if (!hardwareCache) {
        try {
          hardwareCache = await invoke('detect_hardware');
          renderHardwareSummary(hardwareCache);
        } catch (e) {
          console.warn('hardware probe failed', e);
        }
      }
    }
    schedulePoll();
  }

  function schedulePoll() {
    stopLocalStatusPoll();
    if (currentBrand && currentBrand.slug === 'local' && !localInstallActive) {
      localPollTimer = setTimeout(refreshLocalStatus, LOCAL_POLL_MS);
    }
  }

  function stopLocalStatusPoll() {
    if (localPollTimer) {
      clearTimeout(localPollTimer);
      localPollTimer = null;
    }
  }

  function fmtMib(mib) {
    if (!mib) return '—';
    if (mib >= 1024) return `${(mib / 1024).toFixed(1)} GiB`;
    return `${mib} MiB`;
  }

  function renderHardwareSummary(hw) {
    const wrap = $('local-hw-summary');
    if (!wrap) return;
    const gpus = (hw.gpus || []).map((g) => {
      const v = g.vram_mib ? fmtMib(g.vram_mib) : 'unknown VRAM';
      return `${g.name} — ${v}`;
    });
    const gpuLine = gpus.length ? gpus.join('; ') : 'No NVIDIA GPU detected';
    wrap.innerHTML = '';
    const lines = [
      ['CPU cores', String(hw.cpu_cores || '—')],
      ['RAM', `${fmtMib(hw.total_ram_mib)} total · ${fmtMib(hw.available_ram_mib)} available`],
      ['GPU', gpuLine],
      ['Recommended model', hw.recommended_model || '—'],
      ['Max tokens', hw.recommended_max_tokens ? String(hw.recommended_max_tokens) : '—'],
    ];
    for (const [label, value] of lines) {
      const row = document.createElement('div');
      row.className = 'local-hw-row';
      const k = document.createElement('span');
      k.className = 'local-hw-label';
      k.textContent = label;
      const v = document.createElement('span');
      v.className = 'local-hw-value';
      v.textContent = value;
      row.appendChild(k);
      row.appendChild(v);
      wrap.appendChild(row);
    }
    if (hw.recommendation_note) {
      const note = document.createElement('div');
      note.className = 'local-hw-note';
      note.textContent = hw.recommendation_note;
      wrap.appendChild(note);
    }
    // Sudo field is Linux-only — that's where AGiXT/ezLocalai shell
    // out to apt for Docker + the NVIDIA Container Toolkit.
    const sudoField = $('local-sudo-field');
    if (sudoField) sudoField.hidden = hw.os !== 'linux';
  }

  async function startLocalInstall() {
    if (localInstallActive) return;
    localInstallActive = true;
    stopLocalStatusPoll();
    clearLocalLog();
    $('local-install-progress').hidden = false;
    $('btn-local-install').disabled = true;
    setLocalStatus('Installing AGiXT locally…', 'info');

    // Subscribe to progress events *before* invoking so we don't miss
    // early lines emitted during preflight.
    try {
      const evt = window.__TAURI__.event;
      localInstallUnlisten = await evt.listen('local-install-progress', (msg) => {
        const p = msg.payload || {};
        if (p.kind === 'phase') {
          appendLocalLog(`▶ ${p.message}`, 'phase');
        } else if (p.kind === 'log') {
          appendLocalLog(p.line, p.stream && p.stream.endsWith('stderr') ? 'stderr' : 'stdout');
        } else if (p.kind === 'ok') {
          appendLocalLog(`✓ ${p.message}`, 'ok');
        } else if (p.kind === 'err') {
          appendLocalLog(`✗ ${p.message}`, 'err');
        }
      });
    } catch (e) {
      console.warn('listen failed', e);
    }

    let installPath = '';
    try {
      installPath = await invoke('default_install_path');
    } catch (_) { /* fall through with empty path; Rust will default */ }
    const pathInput = $('local-install-path');
    if (pathInput && pathInput.value.trim()) {
      installPath = pathInput.value.trim();
    } else if (pathInput) {
      pathInput.value = installPath;
    }

    // On Linux, AGiXT/ezLocalai may need to install Docker or the
    // NVIDIA Container Toolkit, which means sudo. Remember validated sudo
    // credentials first via the existing sudo_auth helper if the user provided
    // a password. If they leave it blank, proceed anyway — the install will
    // surface the missing-sudo failure in the log.
    if (hardwareCache && hardwareCache.os === 'linux') {
      const pwField = $('local-sudo-password');
      const pw = pwField ? pwField.value : '';
      if (pw) {
        try {
          await invoke('sudo_auth', { password: pw });
          appendLocalLog('▶ Sudo password remembered (Docker / toolkit installs covered).', 'phase');
        } catch (e) {
          appendLocalLog(`✗ sudo authentication failed: ${prettyError(e)}`, 'err');
        }
        if (pwField) pwField.value = '';
      }
    }

    const installArgs = {
      install_path: installPath,
      default_model: hardwareCache && hardwareCache.recommended_model
        ? hardwareCache.recommended_model
        : null,
      default_max_tokens: hardwareCache && hardwareCache.recommended_max_tokens
        ? hardwareCache.recommended_max_tokens
        : null,
    };
    let result;
    try {
      result = await invoke('install_agixt_local', { args: installArgs });
    } catch (e) {
      setLocalStatus(`Install failed: ${prettyError(e)}`, 'error');
      $('btn-local-install').disabled = false;
      localInstallActive = false;
      if (localInstallUnlisten) { try { localInstallUnlisten(); } catch (_) {} localInstallUnlisten = null; }
      schedulePoll();
      return;
    }
    if (localInstallUnlisten) { try { localInstallUnlisten(); } catch (_) {} localInstallUnlisten = null; }
    localInstallActive = false;
    if (result && result.success) {
      setLocalStatus(result.message || 'AGiXT is now running.', 'ok');
      showLocalInstallControls(true);
    } else {
      $('btn-local-install').disabled = false;
    }
    schedulePoll();
  }

  // Wire local-mode buttons. These elements are present in index.html
  // even when local mode isn't active (the pane is just `hidden`),
  // so binding once on boot is fine.
  function bindLocalControls() {
    const btnInstall = $('btn-local-install');
    if (btnInstall) btnInstall.addEventListener('click', startLocalInstall);
    const btnRefresh = $('btn-local-refresh');
    if (btnRefresh) btnRefresh.addEventListener('click', refreshLocalStatus);
  }

  async function boot({ onAuthenticated } = {}) {
    onAuthenticatedCb = onAuthenticated;
    bindLocalControls();
    bindInvitationListener();
    await loadBrands();
    loadPendingInvitation();
    if (typeof window !== 'undefined' && window.location) setPendingInvitation(window.location.href);
    applyPendingInvitationToUi();
    await refreshOAuthProviders();
    showPane('login');
  }

  window.AgixtAuth = {
    boot,
    refreshOAuthProviders,
    setPendingInvitation,
    acceptPendingInvitation,
    clearPendingInvitation,
  };
})();
