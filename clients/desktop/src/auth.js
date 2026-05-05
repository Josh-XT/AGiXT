/* Auth screen logic.
 *
 * Handles service selection, email+password login, registration, magic
 * link, paste-a-JWT, and OAuth-via-system-browser flows. Mirrors the
 * field order and method set of the AGiXT NextJS web client login page,
 * adapted for a desktop app with no cookie store — JWTs land in the
 * Rust-side SQLite via the `login_password` / `register_account` /
 * `login_with_jwt` IPCs.
 *
 * Exposes `window.AgixtAuth.boot({onAuthenticated})` which the app shell
 * calls once on startup. When auth completes, `onAuthenticated()` fires
 * with no args; the caller swaps the auth screen for the chat screen.
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

  function setActiveBrand(slug) {
    currentBrand = brands.find((b) => b.slug === slug) || brands[brands.length - 1];
    $('service-brand').value = currentBrand.slug;
    $('server-url').value = currentBrand.default_url;
    $('web-url').value = currentBrand.default_web_url || '';
    // URL fields are only editable in "custom" mode. "local" pins to
    // localhost:7437 because the install flow assumes that port.
    const editable = currentBrand.slug === 'custom';
    $('server-url').readOnly = !editable;
    $('web-url').readOnly = !editable;
    $('custom-server-field').classList.toggle('readonly', !editable);
    $('custom-web-field').classList.toggle('readonly', !editable);
    // Hide the URL inputs entirely for local mode — the user has no
    // dial to turn there; what they want is the install/connect button.
    const isLocal = currentBrand.slug === 'local';
    $('custom-server-field').hidden = isLocal;
    $('custom-web-field').hidden = isLocal;
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
      'After authorizing, copy the magic-link URL or JWT from the browser back here and paste it below.',
      'info',
    );
    // Auto-expand the paste section so the user sees where to put it.
    const det = document.querySelector('.auth-paste');
    if (det) det.open = true;
  }

  $('service-brand').addEventListener('change', async () => {
    setActiveBrand($('service-brand').value);
    await refreshOAuthProviders();
  });
  $('server-url').addEventListener('change', refreshOAuthProviders);
  $('web-url').addEventListener('change', () => { /* persisted on save */ });

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
        setStatus('Signed in.', 'success');
        finish();
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
      await invoke('request_magic_link', { args: { server_url: activeServerUrl(), email } });
      setStatus(
        `Sent. Check ${email} for a sign-in link, then paste the URL below.`,
        'success',
      );
      const det = document.querySelector('.auth-paste');
      if (det) det.open = true;
    } catch (e) {
      setStatus(prettyError(e), 'error');
    }
  });

  // ----- Paste-a-token fallback (covers magic links + OAuth callbacks) ----

  $('btn-paste-jwt').addEventListener('click', async () => {
    const raw = $('paste-jwt').value.trim();
    if (!raw) {
      setStatus('Paste a magic-link URL or JWT first.', 'error');
      return;
    }
    setStatus('Verifying token…');
    try {
      await invoke('login_with_jwt', { serverUrl: activeServerUrl(), raw });
      await persistBrand();
      setStatus('Signed in.', 'success');
      finish();
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
    if (!args.email || !args.first_name || !args.last_name || !args.password) {
      setStatus('All registration fields are required.', 'error');
      return;
    }
    setStatus('Creating account…');
    try {
      const resp = await invoke('register_account', { args });
      if (resp.token) {
        await persistBrand();
        setStatus('Account created. Welcome!', 'success');
        finish();
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

  function finish() {
    if (typeof onAuthenticatedCb === 'function') onAuthenticatedCb();
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
    // NVIDIA Container Toolkit, which means sudo. Cache creds first
    // via the existing sudo_auth helper if the user provided a
    // password. If they leave it blank, proceed anyway — the install
    // will surface the missing-sudo failure in the log.
    if (hardwareCache && hardwareCache.os === 'linux') {
      const pwField = $('local-sudo-password');
      const pw = pwField ? pwField.value : '';
      if (pw) {
        try {
          await invoke('sudo_auth', { password: pw });
          appendLocalLog('▶ Sudo session authenticated (Docker / toolkit installs covered).', 'phase');
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
    await loadBrands();
    await refreshOAuthProviders();
    showPane('login');
  }

  window.AgixtAuth = { boot, refreshOAuthProviders };
})();
