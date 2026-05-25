/* Extensions tab — Android-launcher-style tile grid + slide-in detail drawer.
 *
 * Renders extensions as icon tiles grouped into "Connected" and "Available"
 * sections, sorted alphabetically within each. Tapping a tile opens a
 * detail drawer with the description, connect/configure action, and the
 * per-command toggles. Categories are no longer the primary structure —
 * they're a chip filter row above the grid.
 *
 * OAuth extensions delegate the "Connect" action to settings-connections.js
 * so we have one code path for the OAuth handshake.
 */
(function () {
  const api = window.AgixtApi;
  const md = window.AgixtMarkdown;
  if (!api) {
    console.error('settings-extensions.js: AgixtApi missing');
    return;
  }

  const CODEX_AUTH_KEY = 'OPENAI_CODEX_AUTH_JSON_SECRET';
  const CODEX_MODEL_KEY = 'OPENAI_CODEX_MODEL';
  const CODEX_REASONING_KEY = 'OPENAI_CODEX_REASONING_EFFORT';
  const CODEX_DEFAULT_MODEL = 'gpt-5.5';
  const CODEX_DEFAULT_REASONING = 'xhigh';
  const CLAUDE_CREDENTIALS_KEY = 'CLAUDE_CODE_CREDENTIALS_JSON_SECRET';
  const CLAUDE_MODEL_KEY = 'CLAUDE_CODE_MODEL';
  const CLAUDE_EFFORT_KEY = 'CLAUDE_CODE_EFFORT';
  const CLAUDE_DEFAULT_MODEL = 'opus';
  const CLAUDE_DEFAULT_EFFORT = 'xhigh';
  const KIRO_API_KEY = 'KIRO_API_KEY';
  const KIRO_REFRESH_TOKEN_KEY = 'KIRO_REFRESH_TOKEN_SECRET';
  const KIRO_MODEL_KEY = 'KIRO_CODE_MODEL';
  const KIRO_TRUST_ALL_TOOLS_KEY = 'KIRO_TRUST_ALL_TOOLS';
  const KIRO_DEFAULT_MODEL = 'claude-opus-4.6';

  let agentId = null;
  let agentName = null;
  let extensions = [];
  let providers = [];           // GET /v1/oauth — server-configured providers
  let userConnections = null;   // GET /v1/oauth2 — per-user state
  let searchText = '';
  let onlyEnabled = false;
  let activeCategory = null;    // null = "All"
  let bodyEl = null;
  let drawerOpen = false;
  let drawerExt = null;
  let drawerEventsWired = false;

  // Brand SVGs we ship locally in assets/oauth/. Curated from Simple Icons
  // (colored variants) plus a handful of hand-authored ones for providers
  // Simple Icons declines to host (Microsoft, Apple, etc.).
  const LOCAL_BRAND_ICONS = new Set([
    'airtable', 'anthropic', 'apple', 'audible', 'azure', 'bitdefender',
    'confluence', 'datto', 'deepseek', 'discord', 'dji', 'dropbox',
    'elevenlabs', 'facebook', 'fitbit', 'garmin', 'github', 'gitlab',
    'gmail', 'google', 'googlecalendar', 'googledrive', 'googlegemini',
    'graphql', 'homeassistant', 'hubspot', 'huggingface', 'jira', 'meta',
    'microsoft', 'mongodb', 'mysql', 'notion', 'obsidian', 'okta',
    'openai', 'openrouter', 'pagerduty', 'paloaltonetworks', 'perplexity',
    'postgresql', 'producthunt', 'proxmox', 'reddit', 'sendgrid', 'solana',
    'spotify', 'sqlite', 'stripe', 'telegram', 'tesla', 'todoist',
    'trello', 'twilio', 'veeam', 'vmware', 'whatsapp', 'wordpress', 'x',
    'youtube', 'zapier', 'zendesk', 'zoho',
  ]);

  // Lucide stroke icons in assets/lucide/ — used when a brand icon doesn't
  // exist for a concept (assets, contacts, tickets, secrets, etc.). Pre-baked
  // with white stroke since <img> elements don't propagate CSS color.
  const LOCAL_LUCIDE_ICONS = new Set([
    'activity', 'book-open', 'bot', 'brain', 'briefcase', 'calendar',
    'camera', 'chart-column', 'code', 'cog', 'contact-round', 'cpu',
    'crosshair', 'database', 'drone', 'dumbbell', 'eye', 'file-text',
    'folder', 'globe', 'hard-drive', 'key', 'key-round', 'list-todo',
    'lock', 'mail', 'megaphone', 'monitor-smartphone', 'network', 'radar',
    'receipt', 'search', 'server', 'shield', 'shield-check', 'sticky-note',
    'target', 'terminal', 'ticket', 'wallet', 'watch', 'workflow', 'wrench',
    'zap',
  ]);

  // Brand-color tile backgrounds for providers we don't have an SVG for.
  // Renders the letter tile in the actual brand color so the launcher stays
  // recognizable (Slack purple "S", LinkedIn blue "in", OpenAI green "O").
  const BRAND_TILE_COLORS = {
    slack: '#4A154B',
    linkedin: '#0A66C2',
    openai: '#10A37F',
    chatgpt: '#10A37F',
    amazon: '#FF9900',
    alexa: '#00CAFF',
    walmart: '#0071CE',
    meta: '#0866FF',
    whatsapp: '#25D366',
    telegram: '#26A5E4',
    twilio: '#F22F46',
    sendgrid: '#1A82E2',
    azure: '#0078D4',
    teams: '#5059C9',
    outlook: '#0078D4',
    onedrive: '#0078D4',
    sharepoint: '#0078D4',
  };

  // Maps an extension's raw name (lowercase, snake_case) to an icon slug.
  // Lookup order in pickIconSlug: LOCAL_BRAND_ICONS (colored brand SVG),
  // BRAND_TILE_COLORS (letter tile in brand color), LOCAL_LUCIDE_ICONS
  // (white stroke concept icon).
  const EXTENSION_ICON_SLUGS = {
    // OAuth / brand providers
    google: 'google',
    google_sso: 'google',
    google_email: 'gmail',
    google_calendar: 'googlecalendar',
    google_marketing: 'google',
    google_search: 'google',
    google_drive: 'googledrive',
    microsoft: 'microsoft',
    microsoft_sso: 'microsoft',
    microsoft_email: 'microsoft',
    microsoft_calendar: 'microsoft',
    microsoft_onedrive: 'microsoft',
    microsoft_sharepoint: 'microsoft',
    teams: 'microsoft',
    outlook: 'microsoft',
    github: 'github',
    github_sso: 'github',
    github_copilot: 'github',
    gitlab: 'gitlab',
    linkedin: 'linkedin',
    linkedin_sso: 'linkedin',
    meta_ads: 'meta',
    meta_sso: 'meta',
    facebook: 'facebook',
    amazon: 'amazon',
    alexa: 'alexa',
    tesla: 'tesla',
    discord: 'discord',
    x: 'x',
    twitter: 'x',
    slack: 'slack',
    telegram: 'telegram',
    whatsapp: 'whatsapp',
    spotify: 'spotify',
    youtube: 'youtube',
    reddit: 'reddit',

    // Productivity / SaaS
    notion: 'notion',
    todoist: 'todoist',
    trello: 'trello',
    airtable: 'airtable',
    dropbox: 'dropbox',
    obsidian: 'obsidian',
    wordpress: 'wordpress',
    zapier_webhooks: 'zapier',

    // Finance / Crypto
    stripe_payments: 'stripe',
    stripe: 'stripe',
    walmart: 'walmart',
    solana_wallet: 'solana',
    bags_app: 'wallet',
    raydium: 'zap',
    wallet: 'wallet',

    // Health & Fitness
    fitbit: 'fitbit',
    garmin: 'garmin',
    oura: 'activity',
    workout_tracker: 'dumbbell',

    // AI Providers
    openai: 'openai',
    openai_codex: 'openai',
    claude_code: 'anthropic',
    kiro_code: 'code',
    chatgpt: 'chatgpt',
    anthropic: 'anthropic',
    claude: 'anthropic',
    perplexity: 'perplexity',
    gemini: 'googlegemini',
    google_gemini: 'googlegemini',
    huggingface: 'huggingface',
    elevenlabs: 'elevenlabs',
    azure: 'azure',
    azure_openai: 'azure',
    deepseek: 'deepseek',
    deepinfra: 'brain',
    openrouter: 'openrouter',
    chutes: 'cog',
    ezlocalai: 'cpu',
    xai: 'bot',

    // PSA & Ticketing
    jira: 'jira',
    confluence: 'confluence',
    zendesk: 'zendesk',
    hubspot_service_hub: 'hubspot',
    pagerduty: 'pagerduty',
    autotask_psa: 'ticket',
    halo_psa: 'ticket',
    kaseya_bms: 'ticket',
    servicenow: 'ticket',
    syncro: 'ticket',
    zoho_desk: 'zoho',
    connectwise_manage: 'ticket',

    // Remote Monitoring
    atera: 'monitor-smartphone',
    connectwise_automate: 'monitor-smartphone',
    datto_rmm: 'monitor-smartphone',
    domotz: 'network',
    kaseya_vsa: 'monitor-smartphone',
    meraki: 'network',
    nable_ncentral: 'monitor-smartphone',
    nable_rmm: 'monitor-smartphone',
    ninja_rmm: 'monitor-smartphone',
    pulseway: 'monitor-smartphone',
    auvik: 'network',

    // Security & Compliance
    activity_log: 'file-text',
    bitdefender: 'bitdefender',
    crowdstrike: 'shield-check',
    cybercns: 'shield',
    duo: 'key',
    huntress: 'crosshair',
    knowbe4: 'shield-check',
    okta: 'okta',
    palo_alto_networks: 'paloaltonetworks',
    phin: 'shield-check',
    sentinelone: 'shield-check',
    sophos: 'shield',
    webroot: 'shield',
    rocketcyber: 'radar',
    acronis: 'shield',
    secrets: 'lock',

    // Backup & Recovery
    datto_backup: 'datto',
    veeam: 'veeam',

    // Documentation & Knowledge
    it_glue: 'book-open',
    hudu: 'book-open',

    // Virtualization
    vmware_vsphere: 'vmware',
    proxmox: 'proxmox',

    // Smart Home / IoT
    home_assistant: 'homeassistant',
    axis_camera: 'camera',
    blink: 'camera',
    hikvision: 'camera',
    ring: 'camera',
    spypoint: 'camera',
    vivotek: 'camera',
    roomba: 'bot',
    tuya: 'bot',
    dji_tello: 'dji',
    find_my_devices: 'monitor-smartphone',

    // Communication
    sendgrid_email: 'sendgrid',
    twilio_sms: 'twilio',

    // Databases
    mssql_database: 'database',
    mysql_database: 'mysql',
    postgres_database: 'postgresql',
    sqlite_database: 'sqlite',

    // Development & Code
    automation_helpers: 'zap',
    custom_automation: 'workflow',
    graphql_server: 'graphql',
    microcontroller_development: 'cpu',
    safe_execute: 'terminal',
    code_execution: 'terminal',

    // Marketing & Growth
    content_repurpose: 'megaphone',
    lead_tracker: 'target',
    review_sites: 'chart-column',
    seo_research: 'search',
    social_monitor: 'eye',
    product_hunt: 'producthunt',

    // Core Abilities
    assets: 'briefcase',
    contacts: 'contact-round',
    essential_abilities: 'zap',
    grokipedia: 'book-open',
    invoices: 'receipt',
    machines: 'server',
    notes: 'sticky-note',
    tickets: 'ticket',
    web_browsing: 'globe',
    web_search: 'search',
    websearch: 'search',

    // Entertainment
    audible: 'audible',
  };

  function isKnownSlug(slug) {
    return LOCAL_BRAND_ICONS.has(slug) || LOCAL_LUCIDE_ICONS.has(slug) || !!BRAND_TILE_COLORS[slug];
  }

  function pickIconSlug(ext) {
    const raw = extensionRawName(ext);
    if (EXTENSION_ICON_SLUGS[raw]) return EXTENSION_ICON_SLUGS[raw];
    // If it's an OAuth extension, fall back to the provider slug — the
    // provider name often matches a brand we have an icon for.
    if (isOAuthExtension(ext)) {
      const provider = findProviderForExtension(ext);
      if (provider && provider.name) {
        const slug = api.redirectSlug(provider.name);
        if (EXTENSION_ICON_SLUGS[slug]) return EXTENSION_ICON_SLUGS[slug];
        if (isKnownSlug(slug)) return slug;
      }
    }
    // Last resort: if the raw name itself happens to match a known slug.
    if (isKnownSlug(raw)) return raw;
    // Try the prefix before the first underscore (e.g. google_marketing → google).
    const root = raw.split('_')[0];
    if (isKnownSlug(root)) return root;
    return null;
  }

  // Field-name → input type heuristics (mirrors web's
  // ExtensionSettingsDialog.getInputTypeAndDefaults).
  function classifySetting(fieldName) {
    const upper = (fieldName || '').toUpperCase();
    if (upper.includes('_API_KEY') || upper.includes('_PASSWORD') ||
        upper.includes('_SECRET') || upper.includes('_TOKEN')) {
      return { type: 'password' };
    }
    if (upper.includes('_TEMPERATURE')) return { type: 'number', step: '0.1', min: '0', max: '2' };
    if (upper.includes('_MAX_TOKENS')) return { type: 'number', step: '1', min: '1' };
    return { type: 'text' };
  }

  function formatExtensionName(name) {
    if (!name) return 'Unknown';
    return String(name).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function formatSettingLabel(key, extensionName) {
    if (!key) return '';
    let s = key;
    if (extensionName) {
      const re = new RegExp('^' + extensionName.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&') + '_', 'i');
      s = s.replace(re, '');
    }
    return s.split('_').map((w) => {
      const u = w.toUpperCase();
      if (['API', 'URL', 'URI', 'ID'].includes(u)) return u;
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    }).join(' ');
  }

  // OAuth provider slugs that map to extension names. Intentionally a small
  // hand-curated list; matches web/components/settings/ExtensionGrid.tsx.
  const OAUTH_EXT_NAMES = new Set([
    'google', 'google_email', 'google_calendar', 'google_marketing',
    'microsoft', 'microsoft_365', 'microsoft_email', 'microsoft_calendar', 'microsoft_onedrive', 'microsoft_sharepoint',
    'microsoft_teams',
    'github', 'linkedin', 'meta_ads', 'amazon', 'alexa', 'tesla', 'discord',
    'x', 'x_twitter', 'twitter', 'fitbit', 'garmin', 'walmart', 'stripe_payments', 'stripe',
    'notion',
    'todoist', 'spotify', 'trello', 'airtable', 'dropbox', 'youtube', 'reddit',
    'facebook', 'slack',
  ]);

  const OAUTH_PROVIDER_BY_EXTENSION = {
    microsoft_365: 'microsoft',
    microsoft_teams: 'teams',
    x_twitter: 'x',
    twitter: 'x',
    stripe: 'stripe_payments',
  };

  // Extensions whose "Connect" action is a custom flow we render inline
  // in the drawer (not an OAuth handshake against AGiXT's provider
  // table). Each entry has a `statusPath` for the connection probe and
  // a `renderInline(host, ctx, onConnected)` that paints the connect UI
  // into the drawer body. Connection state polling lives here too so
  // the tile reads "Connected" the moment the auth file lands.
  const CUSTOM_CONNECT_EXTENSIONS = {
    audible: {
      statusPath: '/v1/audible/auth/status',
      ctaLabel: 'Connect Audible',
      renderInline: renderAudibleConnect,
    },
  };
  const customConnectStatus = {};   // raw -> { loadable, configured } | null
  const customConnectInflight = {}; // raw -> Promise

  function customConnectFor(ext) {
    return CUSTOM_CONNECT_EXTENSIONS[extensionRawName(ext)] || null;
  }

  /** Append `agent_id=<ctx.agentId>` to a path if not already present.
   *  All audible auth endpoints store/read state on the requested
   *  agent so this needs to flow through every request. */
  function withAgentParam(path) {
    const ctx = window.AgixtAppContext && window.AgixtAppContext();
    if (!ctx || !ctx.agentId) return path;
    if (path.indexOf('agent_id=') !== -1) return path;
    return path + (path.indexOf('?') === -1 ? '?' : '&') + 'agent_id=' + encodeURIComponent(ctx.agentId);
  }

  function fetchCustomConnectStatus(raw, cfg) {
    if (customConnectInflight[raw]) return customConnectInflight[raw];
    const ctx = window.AgixtAppContext && window.AgixtAppContext();
    if (!ctx) return Promise.resolve(null);
    const requestPath = withAgentParam(cfg.statusPath);
    const url = (ctx.serverUrl || '').replace(/\/+$/, '') + withAgentParam(cfg.statusPath);
    const fetcher = window.AgixtSession && typeof window.AgixtSession.fetch === 'function'
      ? window.AgixtSession.fetch(requestPath, { headers: { Authorization: 'Bearer ' + ctx.jwt } })
      : fetch(url, { headers: { Authorization: 'Bearer ' + ctx.jwt } });
    const p = fetcher
      .then((r) => r.ok ? r.json() : null)
      .then((s) => { customConnectStatus[raw] = s || null; return s; })
      .catch(() => { customConnectStatus[raw] = null; return null; })
      .finally(() => { delete customConnectInflight[raw]; });
    customConnectInflight[raw] = p;
    return p;
  }

  // Audible marketplaces, in the order we surface them. Codes match the
  // `audible.localization.Locale` keys the server uses.
  const AUDIBLE_MARKETPLACES = [
    { code: 'us', label: 'US — audible.com' },
    { code: 'uk', label: 'UK — audible.co.uk' },
    { code: 'de', label: 'Germany — audible.de' },
    { code: 'fr', label: 'France — audible.fr' },
    { code: 'ca', label: 'Canada — audible.ca' },
    { code: 'au', label: 'Australia — audible.com.au' },
    { code: 'it', label: 'Italy — audible.it' },
    { code: 'es', label: 'Spain — audible.es' },
    { code: 'in', label: 'India — audible.in' },
    { code: 'jp', label: 'Japan — audible.co.jp' },
    { code: 'br', label: 'Brazil — audible.com.br' },
  ];
  const AUDIBLE_MARKETPLACE_LABELS = AUDIBLE_MARKETPLACES.reduce((m, x) => {
    m[x.code] = x.label;
    return m;
  }, {});

  // Map of timezone-region prefixes to Audible marketplace codes.
  // Timezone is a much better signal than navigator.language for an
  // English-speaking user in the UK (whose browser may still report
  // en-US) — but we fall back to language tag → store code afterward.
  const TIMEZONE_REGION_TO_MARKETPLACE = {
    'America/Toronto': 'ca', 'America/Vancouver': 'ca', 'America/Edmonton': 'ca',
    'America/Halifax': 'ca', 'America/St_Johns': 'ca', 'America/Winnipeg': 'ca',
    'America/Sao_Paulo': 'br', 'America/Fortaleza': 'br', 'America/Manaus': 'br',
    'Europe/London': 'uk', 'Europe/Belfast': 'uk', 'Europe/Dublin': 'uk',
    'Europe/Berlin': 'de', 'Europe/Vienna': 'de', 'Europe/Zurich': 'de',
    'Europe/Paris': 'fr', 'Europe/Brussels': 'fr', 'Europe/Luxembourg': 'fr',
    'Europe/Rome': 'it', 'Europe/Madrid': 'es', 'Europe/Lisbon': 'es',
    'Asia/Tokyo': 'jp',
    'Asia/Kolkata': 'in', 'Asia/Calcutta': 'in',
    'Australia/Sydney': 'au', 'Australia/Melbourne': 'au', 'Australia/Brisbane': 'au',
    'Australia/Perth': 'au', 'Australia/Adelaide': 'au',
  };

  // Region letters from a BCP-47 language tag → marketplace code.
  const LANGUAGE_REGION_TO_MARKETPLACE = {
    us: 'us', gb: 'uk', uk: 'uk',
    ca: 'ca', mx: 'us',
    de: 'de', at: 'de', ch: 'de',
    fr: 'fr', be: 'fr', lu: 'fr',
    it: 'it', es: 'es', pt: 'es',
    in: 'in', jp: 'jp',
    au: 'au', nz: 'au',
    br: 'br',
  };

  // Pure language tag → marketplace fallback for browsers that don't
  // include a region code.
  const LANGUAGE_BASE_TO_MARKETPLACE = {
    en: 'us', de: 'de', fr: 'fr', it: 'it',
    es: 'es', pt: 'br', ja: 'jp',
  };

  function detectAudibleMarketplace() {
    try {
      const tz = (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || '';
      if (tz && TIMEZONE_REGION_TO_MARKETPLACE[tz]) {
        return TIMEZONE_REGION_TO_MARKETPLACE[tz];
      }
      // Generic America/* timezones default to US — Mexico/Central
      // America also use audible.com per Amazon's marketplace mapping.
      if (tz.startsWith('America/')) return 'us';
    } catch (_) {}
    try {
      const lang = String(navigator.language || '').toLowerCase();
      const parts = lang.split('-');
      if (parts.length >= 2 && LANGUAGE_REGION_TO_MARKETPLACE[parts[1]]) {
        return LANGUAGE_REGION_TO_MARKETPLACE[parts[1]];
      }
      if (parts[0] && LANGUAGE_BASE_TO_MARKETPLACE[parts[0]]) {
        return LANGUAGE_BASE_TO_MARKETPLACE[parts[0]];
      }
    } catch (_) {}
    return 'us';
  }

  /** Open the system browser to the supplied URL, falling back through
   *  the Tauri opener plugin → shell.open → `window.open`. */
  function openExternal(url) {
    try {
      const t = window.__TAURI__;
      if (t && t.opener && typeof t.opener.openUrl === 'function') {
        return t.opener.openUrl(url);
      }
      if (t && t.shell && typeof t.shell.open === 'function') {
        return t.shell.open(url);
      }
    } catch (_) {}
    try { window.open(url, '_blank', 'noopener'); } catch (_) {}
    return null;
  }

  function tauriInvoke() {
    const t = window.__TAURI__;
    return t && t.core && typeof t.core.invoke === 'function' ? t.core.invoke : null;
  }

  /** POST/GET helper for the audible connect flow. We avoid api.* here
   *  because those helpers are scoped to extension/agent endpoints. */
  async function audibleFetch(path, init) {
    const ctx = window.AgixtAppContext && window.AgixtAppContext();
    if (!ctx) throw new Error('No AGiXT context available');
    const requestPath = withAgentParam(path);
    const url = (ctx.serverUrl || '').replace(/\/+$/, '') + requestPath;
    const opts = Object.assign({}, init || {});
    opts.headers = Object.assign(
      { Authorization: 'Bearer ' + ctx.jwt },
      (opts.body && !(opts.headers && opts.headers['Content-Type']))
        ? { 'Content-Type': 'application/json' }
      : {},
      opts.headers || {},
    );
    const r = window.AgixtSession && typeof window.AgixtSession.fetch === 'function'
      ? await window.AgixtSession.fetch(requestPath, opts)
      : await fetch(url, opts);
    if (!r.ok) {
      let detail = '';
      try { detail = JSON.stringify(await r.json()); }
      catch (_) { try { detail = await r.text(); } catch (_) {} }
      throw new Error(`${r.status} ${r.statusText}: ${detail.slice(0, 240)}`);
    }
    if (r.status === 204) return null;
    const ct = r.headers.get('content-type') || '';
    return ct.includes('application/json') ? r.json() : r.text();
  }

  /** Render the Audible connect form into a host element. `onConnected`
   *  is called once the auth file lands; the caller is responsible for
   *  refreshing the extensions list + closing the drawer. */
  function renderAudibleConnect(host, onConnected) {
    let pendingId = null;
    let pollTimer = null;

    function cleanupPoll() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    function setMsg(kind, text) {
      msgEl.className = 'ext-aud-msg ext-aud-msg-' + kind;
      msgEl.textContent = text;
    }

    // Pick a sensible marketplace default from the user's locale rather
    // than making them choose. Most signed-in Audible users will hit
    // their own store first, and we leave a "Different marketplace?"
    // disclosure for the rare case of an account in another region.
    const detected = detectAudibleMarketplace();
    const marketLabel = AUDIBLE_MARKETPLACE_LABELS[detected] || detected.toUpperCase();
    const marketOptions = AUDIBLE_MARKETPLACES.map(
      (m) => `<option value="${m.code}"${m.code === detected ? ' selected' : ''}>${m.label}</option>`,
    ).join('');

    host.innerHTML = `
      <p class="ext-aud-intro">
        Sign in with your Amazon account in your default browser.
        We'll capture the redirect once Amazon hands us a one-time code —
        no password is stored in AGiXT.
      </p>
      <details class="ext-aud-market">
        <summary class="ext-aud-market-summary">
          Marketplace: <b class="ext-aud-market-label">${escape(marketLabel)}</b>
          <span class="ext-aud-market-hint">— different marketplace?</span>
        </summary>
        <label class="ext-aud-row ext-aud-market-row">
          <span class="ext-aud-label">Audible store</span>
          <select class="ext-aud-input ext-aud-locale">${marketOptions}</select>
        </label>
      </details>
      <div class="ext-aud-actions">
        <button class="btn btn-primary ext-aud-open" type="button">Open Amazon login</button>
        <button class="btn ext-aud-cancel" type="button" hidden>Cancel</button>
      </div>
      <div class="ext-aud-paste" hidden>
        <p class="ext-aud-step">After signing in Amazon will land on a "page not found" screen — copy the FULL URL from the address bar and paste it here:</p>
        <input type="url" class="ext-aud-input ext-aud-redirect" placeholder="https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=…" />
        <button class="btn btn-primary ext-aud-verify" type="button">Verify &amp; connect</button>
      </div>
      <div class="ext-aud-msg" hidden></div>
    `;

    const localeEl = host.querySelector('.ext-aud-locale');
    const marketLabelEl = host.querySelector('.ext-aud-market-label');
    if (localeEl && marketLabelEl) {
      localeEl.addEventListener('change', () => {
        marketLabelEl.textContent = AUDIBLE_MARKETPLACE_LABELS[localeEl.value] || localeEl.value.toUpperCase();
      });
    }
    const openBtn = host.querySelector('.ext-aud-open');
    const cancelBtn = host.querySelector('.ext-aud-cancel');
    const pasteWrap = host.querySelector('.ext-aud-paste');
    const redirectInput = host.querySelector('.ext-aud-redirect');
    const verifyBtn = host.querySelector('.ext-aud-verify');
    const msgEl = host.querySelector('.ext-aud-msg');

    openBtn.addEventListener('click', async () => {
      openBtn.disabled = true;
      openBtn.textContent = 'Opening…';
      try {
        const r = await audibleFetch('/v1/audible/auth/url', {
          method: 'POST',
          body: JSON.stringify({ locale: localeEl.value }),
        });
        pendingId = r.pending_id;
        openExternal(r.login_url);
        pasteWrap.hidden = false;
        cancelBtn.hidden = false;
        msgEl.hidden = true;
        openBtn.textContent = 'Reopen Amazon login';
        redirectInput.focus();
        // Start polling — if Amazon's redirect lands somewhere our
        // helper script can catch it (e.g. the user already ran the
        // CLI in another terminal), the auth file appears and we can
        // skip the manual paste.
        cleanupPoll();
        pollTimer = setInterval(async () => {
          try {
            const s = await audibleFetch('/v1/audible/auth/status');
            if (s && s.loadable) {
              cleanupPoll();
              msgEl.hidden = false;
              setMsg('ok', `Connected as ${s.name || s.given_name || 'your Audible account'}.`);
              setTimeout(onConnected, 700);
            }
          } catch (_) { /* keep polling */ }
        }, 4000);
      } catch (err) {
        msgEl.hidden = false;
        setMsg('err', 'Could not start login: ' + (err.message || err));
      } finally {
        openBtn.disabled = false;
      }
    });

    cancelBtn.addEventListener('click', () => {
      cleanupPoll();
      pendingId = null;
      pasteWrap.hidden = true;
      cancelBtn.hidden = true;
      msgEl.hidden = true;
      openBtn.textContent = 'Open Amazon login';
    });

    verifyBtn.addEventListener('click', async () => {
      const url = (redirectInput.value || '').trim();
      if (!pendingId) {
        msgEl.hidden = false;
        setMsg('err', 'Click "Open Amazon login" first.');
        return;
      }
      if (!url) {
        msgEl.hidden = false;
        setMsg('err', 'Paste the redirected URL after signing in.');
        return;
      }
      verifyBtn.disabled = true;
      verifyBtn.textContent = 'Verifying…';
      try {
        const result = await audibleFetch('/v1/audible/auth/complete', {
          method: 'POST',
          body: JSON.stringify({ pending_id: pendingId, redirect_url: url }),
        });
        cleanupPoll();
        if (result && result.loadable) {
          msgEl.hidden = false;
          setMsg('ok', `Connected as ${result.name || result.given_name || 'your Audible account'}.`);
          setTimeout(onConnected, 700);
        } else {
          msgEl.hidden = false;
          setMsg('err', 'Verification finished but Amazon did not return a usable token. Try again.');
        }
      } catch (err) {
        msgEl.hidden = false;
        setMsg('err', String(err.message || err));
      } finally {
        verifyBtn.disabled = false;
        verifyBtn.textContent = 'Verify & connect';
      }
    });

    return cleanupPoll;
  }

  function extensionRawName(ext) {
    return (ext.extension_name || ext.friendly_name || '')
      .toLowerCase()
      .trim()
      .replace(/&/g, 'and')
      .replace(/[()]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  function isOAuthExtension(ext) {
    return OAUTH_EXT_NAMES.has(extensionRawName(ext));
  }

  function findProviderForExtension(ext) {
    if (!isOAuthExtension(ext)) return null;
    const raw = extensionRawName(ext);
    const providerName = OAUTH_PROVIDER_BY_EXTENSION[raw] || raw;
    let p = providers.find((p) => (p.name || '').toLowerCase() === providerName);
    if (!p) {
      const alt = providerName === 'twitter' ? 'x' : providerName === 'x' ? 'twitter' : null;
      if (alt) p = providers.find((p) => (p.name || '').toLowerCase() === alt);
    }
    return p || null;
  }

  function hasConfiguredOAuthProvider(ext) {
    return isOAuthExtension(ext) && !!findProviderForExtension(ext);
  }

  function oauthExtensionUnavailable(ext) {
    return isOAuthExtension(ext) && !hasConfiguredOAuthProvider(ext);
  }

  function commandsEnabled(ext) {
    // An ability that's flipped "enabled" in the database against an
    // extension that isn't actually connected can't run — surfacing it
    // as enabled in the UI is misleading. Treat enabled-but-not-
    // reachable as effectively zero so the launcher tile, the bulk
    // counter, and the section badges all reflect what the user can
    // actually use right now.
    if (extensionHasConnectionState(ext) && !extensionConnected(ext)) return 0;
    return (ext.commands || []).filter((c) => c.enabled).length;
  }

  /** Does the user have an active OAuth connection for this provider? */
  function isProviderConnected(provider) {
    if (!provider || !userConnections) return false;
    const targetName = (provider.name || '').toLowerCase();
    const targetSlug = api.redirectSlug(provider.name);
    const targetEndpointSlug = api.oauthEndpointSlug
      ? api.oauthEndpointSlug(provider.name)
      : targetSlug;
    if (Array.isArray(userConnections)) {
      return userConnections.some((entry) => {
        if (typeof entry === 'string') {
          const e = entry.toLowerCase();
          return e === targetName || e === targetSlug || e === targetEndpointSlug;
        }
        if (entry && typeof entry === 'object') {
          const n = (entry.name || entry.provider || '').toLowerCase();
          if (n !== targetName && n !== targetSlug && n !== targetEndpointSlug) return false;
          return !('connected' in entry) || !!entry.connected;
        }
        return false;
      });
    }
    if (Array.isArray(userConnections.connected)) {
      return userConnections.connected.includes(provider.name) ||
             userConnections.connected.includes(targetSlug) ||
             userConnections.connected.includes(targetEndpointSlug);
    }
    if (Array.isArray(userConnections.providers)) {
      const match = userConnections.providers.find((p) => {
        const n = (p.name || p.provider || '').toLowerCase();
        return n === targetName || n === targetSlug || n === targetEndpointSlug;
      });
      return !!(match && match.connected);
    }
    return !!(userConnections[provider.name] || userConnections[targetSlug] || userConnections[targetEndpointSlug]);
  }

  /** Mirrors web/app/settings/page.tsx getExtensionConnected. A setting
   *  counts as sensitive when the API marks it `is_sensitive` OR its name
   *  matches the API_KEY/PASSWORD/SECRET/TOKEN heuristic. Default values
   *  on non-sensitive fields (e.g. `_TEMPERATURE=0.7`) shouldn't make an
   *  extension look "connected" — that bug is what this guards against. */
  function isSensitiveSetting(s) {
    if (!s || typeof s === 'string') {
      return /_(api_key|password|secret|token)$/i.test(String(s || ''));
    }
    if (s.is_sensitive === true) return true;
    return /_(api_key|password|secret|token)$/i.test(String(s.setting_key || ''));
  }

  function isSensitiveKey(key) {
    return /(_api_key|_password|_secret|_token|private_key|auth_json|credentials_json)$/i.test(String(key || ''));
  }

  function looksMaskedSecretValue(value) {
    const v = String(value || '').trim();
    return v === '****' || v.startsWith('***');
  }

  function isOpenAiCodexExtension(ext) {
    return extensionRawName(ext) === 'openai_codex';
  }

  function isClaudeCodeExtension(ext) {
    return extensionRawName(ext) === 'claude_code';
  }

  function isKiroCodeExtension(ext) {
    return extensionRawName(ext) === 'kiro_code';
  }

  function extensionDefaultValue(ext, key, value) {
    const current = value == null ? '' : String(value);
    const upper = String(key || '').toUpperCase();
    if (isOpenAiCodexExtension(ext)) {
      if (current.trim()) return current;
      if (upper === CODEX_MODEL_KEY) return CODEX_DEFAULT_MODEL;
      if (upper === CODEX_REASONING_KEY) return CODEX_DEFAULT_REASONING;
    }
    if (isClaudeCodeExtension(ext)) {
      if (current.trim()) return current;
      if (upper === CLAUDE_MODEL_KEY) return CLAUDE_DEFAULT_MODEL;
      if (upper === CLAUDE_EFFORT_KEY || upper === 'CLAUDE_CODE_REASONING_EFFORT') return CLAUDE_DEFAULT_EFFORT;
    }
    if (isKiroCodeExtension(ext)) {
      if (current.trim()) return current;
      if (upper === KIRO_MODEL_KEY || upper === 'KIRO_MODEL') return KIRO_DEFAULT_MODEL;
      if (upper === KIRO_TRUST_ALL_TOOLS_KEY) return 'true';
    }
    return current;
  }

  function settingValue(s) {
    if (!s || typeof s === 'string') return '';
    return s.setting_value == null ? '' : String(s.setting_value);
  }

  function hasAnyValue(settings) {
    return settings.some((s) => settingValue(s).length > 0);
  }

  function extensionConnected(ext) {
    if (hasConfiguredOAuthProvider(ext)) {
      return isProviderConnected(findProviderForExtension(ext));
    }
    const custom = customConnectFor(ext);
    if (custom) {
      // Audible-style external auth — connection state lives on the
      // server (cached audible_auth.json) and is fetched on drawer
      // open. While the probe is in flight we treat it as not yet
      // connected to avoid flashing "Configured" first.
      const status = customConnectStatus[extensionRawName(ext)];
      return !!(status && status.loadable);
    }
    const settings = ext.settings || [];
    if (settings.length === 0) return true;   // always-on, no setup needed
    const sensitive = settings.filter(isSensitiveSetting);
    if (sensitive.length > 0) {
      // The extension declares secrets — those gate "connected".
      return hasAnyValue(sensitive);
    }
    // No sensitive fields — treat any populated setting OR an enabled
    // command as evidence the user has wired it up.
    const anyEnabled = (ext.commands || []).some((c) => c.enabled);
    return hasAnyValue(settings) || anyEnabled;
  }

  /** Plain extensions with no settings are always usable; we don't show a
   *  connection state for them so nothing reads as "broken". */
  function extensionHasConnectionState(ext) {
    return hasConfiguredOAuthProvider(ext) || !!customConnectFor(ext) || (ext.settings || []).length > 0;
  }

  function escape(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function prettyProviderName(name) {
    if (!name) return '';
    let s = String(name).replace(/_(sso|oauth)$/i, '');
    return s.split(/[_\s]+/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  }

  // Stable hue per name so each fallback letter tile keeps the same color
  // across reloads. 38% sat / 38% light keeps it muted on the dark theme.
  function colorForName(name) {
    let h = 0;
    const s = String(name || '');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return `hsl(${Math.abs(h) % 360}, 38%, 38%)`;
  }

  function letterFor(name) {
    const s = String(name || '').trim();
    return (s.charAt(0) || '?').toUpperCase();
  }

  function iconHtmlForExtension(ext) {
    const friendly = formatExtensionName(ext.friendly_name || ext.extension_name);
    const slug = pickIconSlug(ext);
    if (slug && LOCAL_BRAND_ICONS.has(slug)) {
      return `<div class="ext-tile-icon"><img src="assets/oauth/${escape(slug)}.svg" alt="" /></div>`;
    }
    // Lucide stroke icons sit on the neutral panel-2 tile — they're concept
    // icons (folder, ticket, etc.) so they don't carry brand color.
    if (slug && LOCAL_LUCIDE_ICONS.has(slug)) {
      return `<div class="ext-tile-icon ext-tile-icon-lucide"><img src="assets/lucide/${escape(slug)}.svg" alt="" /></div>`;
    }
    // No SVG, but we know the brand's color — render a colored letter tile
    // that still reads as that brand (e.g. Slack purple "S").
    if (slug && BRAND_TILE_COLORS[slug]) {
      const bg = BRAND_TILE_COLORS[slug];
      return `<div class="ext-tile-icon" style="background:${bg}"><span class="ext-tile-icon-letter">${escape(letterFor(friendly))}</span></div>`;
    }
    const bg = colorForName(friendly);
    return `<div class="ext-tile-icon" style="background:${bg}"><span class="ext-tile-icon-letter">${escape(letterFor(friendly))}</span></div>`;
  }

  function renderSwitch(checked, disabled) {
    const dis = disabled ? 'disabled' : '';
    const chk = checked ? 'checked' : '';
    return `<label class="as-switch"><input type="checkbox" ${chk} ${dis}><span class="as-switch-slider"></span></label>`;
  }

  function renderExtensionCommands(ext) {
    const cmds = ext.commands || [];
    if (cmds.length === 0) return '';
    const rows = cmds.map((cmd, idx) => {
      const fn = cmd.friendly_name || cmd.command_name || '(unnamed)';
      const tip = cmd.description ? cmd.description.replace(/"/g, '&quot;') : '';
      return `
        <div class="ext-cmd" data-cmd-idx="${idx}">
          ${renderSwitch(!!cmd.enabled, false)}
          <span class="ext-cmd-name ${tip ? 'ext-cmd-name-tooltip' : ''}" ${tip ? `title="${tip}"` : ''}>${escape(fn)}</span>
        </div>
      `;
    }).join('');
    return `<div class="ext-cmds">${rows}</div>`;
  }

  function renderExtensionSettingsForm(ext) {
    const settings = ext.settings || [];
    if (settings.length === 0) return '';
    if (hasConfiguredOAuthProvider(ext)) return '';   // OAuth handles its own creds

    // Codex / Claude Code authenticate from the local CLI's own login
    // file. When that file is present the one-click "Connect" is the
    // whole story — the raw JSON paste box plus the model/effort fields
    // are just noise, so for these extensions they collapse behind an
    // "Enter credentials manually" disclosure. The connect handler
    // (initialize*LocalConnect) auto-opens it only when no local login
    // is found, or we're in the browser where there is none. Kiro uses
    // the same treatment for refresh tokens imported from Kiro IDE's
    // AWS SSO cache, while still allowing a manual API key.
    const localAuth = isOpenAiCodexExtension(ext)
      ? { box: 'data-codex-local', btn: 'ext-codex-local-connect', status: 'data-codex-local-status',
          checking: 'Checking local Codex login…', looking: 'Looking for ~/.codex/auth.json…' }
      : isClaudeCodeExtension(ext)
      ? { box: 'data-claude-local', btn: 'ext-claude-local-connect', status: 'data-claude-local-status',
          checking: 'Checking local Claude Code login…', looking: 'Looking for ~/.claude/.credentials.json…' }
      : isKiroCodeExtension(ext)
      ? { box: 'data-kiro-local', btn: 'ext-kiro-local-connect', status: 'data-kiro-local-status',
          checking: 'Checking local Kiro IDE login…', looking: 'Looking for a Kiro token in ~/.aws/sso/cache…' }
      : null;

    const rows = settings.map((s, idx) => {
      const key = typeof s === 'string' ? s : s.setting_key;
      const val = extensionDefaultValue(
        ext,
        key,
        typeof s === 'string' ? '' : (s.setting_value == null ? '' : s.setting_value)
      );
      const meta = classifySetting(key);
      const label = formatSettingLabel(key, ext.extension_name);
      const sensitive = isSensitiveSetting(s) || isSensitiveKey(key);
      const isMasked = sensitive && looksMaskedSecretValue(val);
      const placeholder = sensitive && val ? 'Saved. Paste a new value to replace it.' : '';
      const numAttrs = meta.type === 'number' ? `step="${meta.step}" min="${meta.min || ''}" max="${meta.max || ''}"` : '';
      const domValue = isMasked ? '' : val;
      if ((key || '').toUpperCase().includes('AUTH_JSON') || (key || '').toUpperCase().includes('CREDENTIALS_JSON')) {
        return `
        <div class="ext-settings-row" data-setting-key="${escape(key)}">
          <label class="ext-settings-label" for="ext-set-${idx}-${escape(ext.extension_name)}">${escape(label)}</label>
          <textarea id="ext-set-${idx}-${escape(ext.extension_name)}" class="as-input" rows="4" placeholder="${escape(placeholder || 'Paste raw JSON credentials or a base64-encoded copy.')}">${escape(domValue)}</textarea>
        </div>
      `;
      }
      return `
        <div class="ext-settings-row" data-setting-key="${escape(key)}">
          <label class="ext-settings-label" for="ext-set-${idx}-${escape(ext.extension_name)}">${escape(label)}</label>
          <input id="ext-set-${idx}-${escape(ext.extension_name)}" class="as-input" type="${meta.type}" value="${escape(domValue)}" placeholder="${escape(placeholder)}" ${numAttrs} />
        </div>
      `;
    }).join('');

    if (localAuth) {
      return `
      <div class="ext-settings">
        <div class="ext-local-auth ext-local-auth-primary" ${localAuth.box} hidden>
          <button class="btn btn-primary ${localAuth.btn}" type="button" disabled>${localAuth.checking}</button>
          <div class="ext-local-auth-status" ${localAuth.status}>${localAuth.looking}</div>
        </div>
        <details class="ext-local-manual">
          <summary class="ext-local-manual-summary">Enter credentials manually</summary>
          <div class="ext-local-manual-body">
            ${rows}
            <div class="ext-settings-actions">
              <button class="btn btn-secondary ext-settings-save" type="button">Save settings</button>
            </div>
          </div>
        </details>
      </div>
    `;
    }

    return `
      <div class="ext-settings">
        ${rows}
        <div class="ext-settings-actions">
          <button class="btn btn-primary ext-settings-save" type="button">Save settings</button>
        </div>
      </div>
    `;
  }

  function renderTile(ext) {
    const friendly = formatExtensionName(ext.friendly_name || ext.extension_name);
    const connected = extensionConnected(ext);
    const hasConnState = extensionHasConnectionState(ext);
    const isOAuth = hasConfiguredOAuthProvider(ext);
    const needsSetup = hasConnState && !connected;
    const enabled = commandsEnabled(ext);
    // The green "is-connected" dot reads as "this integration is wired
    // up and ready". OAuth and custom-connect both qualify; pure
    // settings-driven extensions don't have an analogous binary state.
    const showDot = (isOAuth || !!customConnectFor(ext)) && connected;
    const showBadge = enabled > 0;
    const klass = needsSetup ? 'is-disconnected' : 'is-connected';
    return `
      <button class="ext-tile ${klass}" type="button" data-ext-name="${escape(ext.extension_name || '')}" title="${escape(friendly)}">
        ${iconHtmlForExtension(ext)}
        ${showDot ? '<span class="ext-tile-dot" aria-hidden="true"></span>' : ''}
        ${showBadge ? `<span class="ext-tile-badge" aria-label="${enabled} abilities enabled">${enabled}</span>` : ''}
        <span class="ext-tile-name">${escape(friendly)}</span>
      </button>
    `;
  }

  function filterExtensions(list) {
    const q = (searchText || '').trim().toLowerCase();
    return list.filter((ext) => {
      const cat = ext.category || 'Other';
      if (cat.toLowerCase() === 'authentication') return false;
      if (oauthExtensionUnavailable(ext)) return false;
      if (activeCategory && cat !== activeCategory) return false;
      if (onlyEnabled && commandsEnabled(ext) === 0) return false;
      if (!q) return true;
      const name = (ext.friendly_name || ext.extension_name || '').toLowerCase();
      const desc = (ext.description || '').toLowerCase();
      if (name.includes(q) || desc.includes(q)) return true;
      return (ext.commands || []).some((c) =>
        (c.command_name || '').toLowerCase().includes(q) ||
        (c.friendly_name || '').toLowerCase().includes(q),
      );
    });
  }

  function refreshStats() {
    const stats = document.getElementById('ext-stats');
    if (!stats) return;
    const visible = extensions.filter((e) =>
      (e.category || '').toLowerCase() !== 'authentication' &&
      !oauthExtensionUnavailable(e)
    );
    const totalCmds = visible.reduce((n, e) => n + (e.commands || []).length, 0);
    const enabledCmds = visible.reduce((n, e) => n + commandsEnabled(e), 0);
    stats.textContent = `${enabledCmds}/${totalCmds} abilities enabled · ${visible.length} extensions`;
  }

  function renderChips() {
    const chipsEl = document.getElementById('ext-chips');
    if (!chipsEl) return;
    const visible = extensions.filter((e) =>
      (e.category || '').toLowerCase() !== 'authentication' &&
      !oauthExtensionUnavailable(e)
    );
    const cats = Array.from(new Set(visible.map((e) => e.category || 'Other')))
      .sort((a, b) => {
        if (a === 'Core Abilities') return -1;
        if (b === 'Core Abilities') return 1;
        return a.localeCompare(b);
      });
    if (cats.length <= 1) {
      chipsEl.hidden = true;
      chipsEl.innerHTML = '';
      return;
    }
    chipsEl.hidden = false;
    const allChip = `<button class="ext-chip ${!activeCategory ? 'is-active' : ''}" type="button" data-cat="">All <span class="ext-chip-count">${visible.length}</span></button>`;
    const catChips = cats.map((c) => {
      const count = visible.filter((e) => (e.category || 'Other') === c).length;
      return `<button class="ext-chip ${activeCategory === c ? 'is-active' : ''}" type="button" data-cat="${escape(c)}">${escape(c)} <span class="ext-chip-count">${count}</span></button>`;
    }).join('');
    chipsEl.innerHTML = allChip + catChips;
    chipsEl.querySelectorAll('.ext-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const c = btn.getAttribute('data-cat');
        activeCategory = c || null;
        render();
      });
    });
  }

  function render() {
    if (!bodyEl) return;
    renderChips();

    const filtered = filterExtensions(extensions);
    if (filtered.length === 0) {
      bodyEl.innerHTML = '<div class="as-empty">No extensions match.</div>';
      refreshStats();
      return;
    }

    const sortAlpha = (a, b) => {
      const an = (a.friendly_name || a.extension_name || '').toLowerCase();
      const bn = (b.friendly_name || b.extension_name || '').toLowerCase();
      return an.localeCompare(bn);
    };

    // "Connected" = OAuth-connected, configured-non-OAuth, or always-on
    // (no setup concept). "Available" = anything that needs setup.
    const connected = filtered.filter((e) => !extensionHasConnectionState(e) || extensionConnected(e)).sort(sortAlpha);
    const available = filtered.filter((e) => extensionHasConnectionState(e) && !extensionConnected(e)).sort(sortAlpha);

    const sections = [];
    if (connected.length > 0) {
      sections.push(`
        <div class="ext-section">
          <div class="ext-section-head">
            <span class="ext-section-label">Connected</span>
            <span class="ext-section-count">${connected.length}</span>
          </div>
          <div class="ext-tile-grid">${connected.map(renderTile).join('')}</div>
        </div>
      `);
    }
    if (available.length > 0) {
      sections.push(`
        <div class="ext-section">
          <div class="ext-section-head">
            <span class="ext-section-label">Available</span>
            <span class="ext-section-count">${available.length}</span>
          </div>
          <div class="ext-tile-grid">${available.map(renderTile).join('')}</div>
        </div>
      `);
    }
    bodyEl.innerHTML = sections.join('');
    bindTileEvents();
    refreshStats();
  }

  function findExtensionByName(name) {
    return extensions.find((e) => (e.extension_name || '') === name) || null;
  }

  function bindTileEvents() {
    bodyEl.querySelectorAll('.ext-tile').forEach((tile) => {
      const extName = tile.getAttribute('data-ext-name');
      tile.addEventListener('click', () => {
        const ext = findExtensionByName(extName);
        if (ext) openDrawer(ext);
      });
    });
  }

  function openDrawer(ext) {
    drawerExt = ext;
    drawerOpen = true;
    // For custom-connect extensions, kick off a status probe and re-render
    // the drawer once it returns so the right CTA + state are shown.
    const customConnect = customConnectFor(ext);
    if (customConnect) {
      const raw = extensionRawName(ext);
      fetchCustomConnectStatus(raw, customConnect).then(() => {
        if (drawerOpen && drawerExt && extensionRawName(drawerExt) === raw) {
          renderDrawer();
        }
      });
    }
    renderDrawer();
    const drawer = document.getElementById('ext-drawer');
    const backdrop = document.getElementById('ext-drawer-backdrop');
    if (!drawer || !backdrop) return;
    drawer.hidden = false;
    backdrop.hidden = false;
    // Force reflow before adding the open class so the slide animation runs.
    void drawer.offsetWidth;
    drawer.classList.add('is-open');
    backdrop.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function closeDrawer() {
    const drawer = document.getElementById('ext-drawer');
    const backdrop = document.getElementById('ext-drawer-backdrop');
    drawerOpen = false;
    if (!drawer || !backdrop) return;
    drawer.classList.remove('is-open');
    backdrop.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    setTimeout(() => {
      if (!drawerOpen) {
        drawer.hidden = true;
        backdrop.hidden = true;
        drawerExt = null;
      }
    }, 200);
  }

  function renderDrawer() {
    if (!drawerExt) return;
    const ext = drawerExt;
    const friendly = formatExtensionName(ext.friendly_name || ext.extension_name);
    const connected = extensionConnected(ext);
    const isOAuth = hasConfiguredOAuthProvider(ext);
    const provider = isOAuth ? findProviderForExtension(ext) : null;
    const hasConnState = extensionHasConnectionState(ext);
    const enabled = commandsEnabled(ext);
    const total = (ext.commands || []).length;
    const cat = ext.category || 'Other';

    const iconEl = document.getElementById('ext-drawer-icon');
    const titleEl = document.getElementById('ext-drawer-title');
    const subEl = document.getElementById('ext-drawer-sub');
    const bodyDr = document.getElementById('ext-drawer-body');
    if (!iconEl || !titleEl || !subEl || !bodyDr) return;

    iconEl.innerHTML = iconHtmlForExtension(ext);
    titleEl.textContent = friendly;

    const customConnect = customConnectFor(ext);

    let statusText, statusClass;
    if (isOAuth) {
      statusText = connected ? 'Connected' : 'Not connected';
      statusClass = connected ? 'connected' : '';
    } else if (customConnect) {
      statusText = connected ? 'Connected' : 'Not connected';
      statusClass = connected ? 'connected' : '';
    } else if (hasConnState) {
      statusText = connected ? 'Configured' : 'Not configured';
      statusClass = connected ? 'connected' : '';
    } else {
      statusText = 'Always available';
      statusClass = 'connected';
    }
    subEl.innerHTML = `${escape(cat)} · <span class="ext-drawer-status ${statusClass}">${escape(statusText)}</span>`;

    const parts = [];

    if (ext.description) {
      let desc = '';
      if (md) {
        try { desc = md.render(ext.description); }
        catch (e) {
          console.warn('markdown render failed for', ext.extension_name, e);
          desc = `<p>${escape(ext.description)}</p>`;
        }
      } else {
        desc = `<p>${escape(ext.description)}</p>`;
      }
      parts.push(`<div class="ext-drawer-desc">${desc}</div>`);
    }

    // Primary action: connect (disconnected OAuth) — sized big and full-width
    // so it reads as the obvious "do this first" thing.
    if (isOAuth && provider && !connected) {
      parts.push(`
        <div class="ext-drawer-action ext-drawer-action-primary">
          <button class="btn btn-primary ext-oauth-connect" type="button">Connect ${escape(prettyProviderName(provider.name))}</button>
        </div>
      `);
    }

    // Custom-connect extensions (audible) — primary CTA jumps to the
    // sidenav view that hosts the actual auth flow. Even when already
    // connected we surface a "Manage" button so users can disconnect /
    // re-auth from the same place.
    if (customConnect) {
      const label = connected
        ? `Manage ${escape(friendly)}`
        : escape(customConnect.ctaLabel || `Connect ${friendly}`);
      parts.push(`
        <div class="ext-drawer-action ext-drawer-action-primary">
          <button class="btn btn-primary ext-custom-connect"
                  data-view="${escape(customConnect.view)}"
                  type="button">${label}</button>
        </div>
      `);
    }

    // Settings form for non-OAuth extensions with config fields.
    const settingsForm = renderExtensionSettingsForm(ext);
    if (settingsForm) {
      parts.push(`<div class="ext-drawer-section-title">Settings</div>${settingsForm}`);
    }

    // Abilities — only meaningful once the extension is reachable.
    // For OAuth and custom-connect extensions we hide the toggles
    // entirely until the user has connected; otherwise the user is
    // staring at switches that won't actually run anything.
    if (total > 0) {
      const reachable = (!isOAuth && !customConnect) || connected;
      if (reachable) {
        const allOn = enabled === total;
        parts.push(`<div class="ext-drawer-section-title">Abilities (${enabled}/${total})</div>`);
        parts.push(`
          <label class="ext-bulk-toggle">
            ${renderSwitch(allOn)}
            <span>Enable all abilities</span>
          </label>
        `);
        parts.push(renderExtensionCommands(ext));
      }
      // When not reachable, surface no abilities section at all — the
      // primary CTA above ("Connect …") is the only action that makes
      // sense; listing locked toggles just adds noise.
    }

    // Secondary action: disconnect lives at the bottom for connected OAuth.
    if (isOAuth && provider && connected) {
      parts.push(`
        <div class="ext-drawer-action">
          <button class="btn btn-secondary ext-oauth-disconnect" type="button">Disconnect ${escape(prettyProviderName(provider.name))}</button>
        </div>
      `);
    }

    bodyDr.innerHTML = parts.join('');
    bindDrawerBodyEvents();
  }

  function settingInput(bodyDr, key) {
    const rows = bodyDr.querySelectorAll('.ext-settings-row');
    const row = Array.from(rows).find((entry) => entry.getAttribute('data-setting-key') === key);
    return row ? row.querySelector('input, textarea') : null;
  }

  // Codex/Claude keep the raw JSON paste form in a collapsed <details>.
  // We only pop it open when one-click connect can't carry the user —
  // no local login file present, or running in the browser. When a
  // local login *is* found we leave it collapsed so the prominent
  // "Connect" button is the only thing competing for attention.
  function revealManualSettings(bodyDr) {
    const details = bodyDr.querySelector('.ext-local-manual');
    if (details && !details.open) details.open = true;
  }

  function setCodexLocalStatus(bodyDr, text, kind) {
    const status = bodyDr.querySelector('[data-codex-local-status]');
    if (!status) return;
    status.textContent = text || '';
    status.classList.toggle('connected', kind === 'connected');
    status.classList.toggle('error', kind === 'error');
  }

  async function initializeCodexLocalConnect(bodyDr, ext) {
    if (!isOpenAiCodexExtension(ext)) return;
    const box = bodyDr.querySelector('[data-codex-local]');
    const btn = bodyDr.querySelector('.ext-codex-local-connect');
    const invoke = tauriInvoke();
    if (!box || !btn) return;
    const connected = extensionConnected(ext);
    if (!invoke) { if (!connected) revealManualSettings(bodyDr); return; }

    box.hidden = false;
    btn.disabled = true;
    btn.textContent = 'Checking local Codex login…';
    try {
      const status = await invoke('local_codex_auth_json', { args: { includeSecret: false } });
      if (status && status.available) {
        btn.disabled = false;
        if (connected) {
          // Already wired up — the drawer header already says so. Keep
          // only a quiet "Re-import" affordance for refreshing an
          // expired token, not a loud "connect" prompt.
          box.classList.remove('ext-local-auth-primary');
          btn.classList.remove('btn-primary');
          btn.classList.add('btn-secondary');
          btn.textContent = 'Re-import credentials';
          setCodexLocalStatus(bodyDr, `Connected from ${status.path || '~/.codex/auth.json'}.`, 'connected');
        } else {
          btn.textContent = 'Import Credentials';
          setCodexLocalStatus(bodyDr, `Found ${status.path || '~/.codex/auth.json'}.`, 'connected');
        }
      } else {
        if (connected) { box.hidden = true; return; }
        if (status && /only available in the desktop app/i.test(status.error || '')) {
          box.hidden = true;
          revealManualSettings(bodyDr);
          return;
        }
        btn.disabled = true;
        btn.textContent = 'Local Codex login not found';
        const message = status && status.error
          ? status.error
          : `Run codex login, then reopen this settings panel.`;
        setCodexLocalStatus(bodyDr, message, 'error');
        revealManualSettings(bodyDr);
      }
    } catch (e) {
      if (connected) { box.hidden = true; return; }
      btn.disabled = true;
      btn.textContent = 'Local Codex login unavailable';
      setCodexLocalStatus(bodyDr, e.message || String(e), 'error');
      revealManualSettings(bodyDr);
    }

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Connecting…';
      try {
        const status = await invoke('local_codex_auth_json', { args: { includeSecret: true } });
        if (!status || !status.available || !status.authJson) {
          throw new Error((status && status.error) || 'No local Codex login was found.');
        }

        const modelInput = settingInput(bodyDr, CODEX_MODEL_KEY);
        const reasoningInput = settingInput(bodyDr, CODEX_REASONING_KEY);
        const model = ((modelInput && modelInput.value) || CODEX_DEFAULT_MODEL).trim() || CODEX_DEFAULT_MODEL;
        const reasoning = ((reasoningInput && reasoningInput.value) || CODEX_DEFAULT_REASONING).trim() || CODEX_DEFAULT_REASONING;
        if (modelInput) modelInput.value = model;
        if (reasoningInput) reasoningInput.value = reasoning;

        await api.updateAgentSettings(agentId, {
          [CODEX_AUTH_KEY]: status.authJson,
          [CODEX_MODEL_KEY]: model,
          [CODEX_REASONING_KEY]: reasoning,
        });
        window.AgentSettings.toast('OpenAI Codex connected.', 'success');
        await load();
      } catch (e) {
        window.AgentSettings.toast('Codex connect failed: ' + (e.message || e), 'error');
        setCodexLocalStatus(bodyDr, e.message || String(e), 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = connected ? 'Re-import credentials' : 'Import Credentials';
      }
    });
  }

  function setClaudeLocalStatus(bodyDr, text, kind) {
    const status = bodyDr.querySelector('[data-claude-local-status]');
    if (!status) return;
    status.textContent = text || '';
    status.classList.toggle('connected', kind === 'connected');
    status.classList.toggle('error', kind === 'error');
  }

  async function initializeClaudeLocalConnect(bodyDr, ext) {
    if (!isClaudeCodeExtension(ext)) return;
    const box = bodyDr.querySelector('[data-claude-local]');
    const btn = bodyDr.querySelector('.ext-claude-local-connect');
    const invoke = tauriInvoke();
    if (!box || !btn) return;
    const connected = extensionConnected(ext);
    if (!invoke) { if (!connected) revealManualSettings(bodyDr); return; }

    box.hidden = false;
    btn.disabled = true;
    btn.textContent = 'Checking local Claude Code login…';
    try {
      const status = await invoke('local_claude_code_credentials_json', { args: { includeSecret: false } });
      if (status && status.available) {
        btn.disabled = false;
        if (connected) {
          // Already wired up — the drawer header already says so. Keep
          // only a quiet "Re-import" affordance for refreshing an
          // expired token, not a loud "connect" prompt.
          box.classList.remove('ext-local-auth-primary');
          btn.classList.remove('btn-primary');
          btn.classList.add('btn-secondary');
          btn.textContent = 'Re-import credentials';
          setClaudeLocalStatus(bodyDr, `Connected from ${status.path || '~/.claude/.credentials.json'}.`, 'connected');
        } else {
          btn.textContent = 'Import Credentials';
          setClaudeLocalStatus(bodyDr, `Found ${status.path || '~/.claude/.credentials.json'}.`, 'connected');
        }
      } else {
        if (connected) { box.hidden = true; return; }
        if (status && /only available in the desktop app/i.test(status.error || '')) {
          box.hidden = true;
          revealManualSettings(bodyDr);
          return;
        }
        btn.disabled = true;
        btn.textContent = 'Local Claude Code login not found';
        const message = status && status.error
          ? status.error
          : `Run claude auth login, then reopen this settings panel.`;
        setClaudeLocalStatus(bodyDr, message, 'error');
        revealManualSettings(bodyDr);
      }
    } catch (e) {
      if (connected) { box.hidden = true; return; }
      btn.disabled = true;
      btn.textContent = 'Local Claude Code login unavailable';
      setClaudeLocalStatus(bodyDr, e.message || String(e), 'error');
      revealManualSettings(bodyDr);
    }

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Connecting…';
      try {
        const status = await invoke('local_claude_code_credentials_json', { args: { includeSecret: true } });
        if (!status || !status.available || !status.credentialsJson) {
          throw new Error((status && status.error) || 'No local Claude Code login was found.');
        }

        const modelInput = settingInput(bodyDr, CLAUDE_MODEL_KEY);
        const effortInput = settingInput(bodyDr, CLAUDE_EFFORT_KEY);
        const model = ((modelInput && modelInput.value) || CLAUDE_DEFAULT_MODEL).trim() || CLAUDE_DEFAULT_MODEL;
        const effort = ((effortInput && effortInput.value) || CLAUDE_DEFAULT_EFFORT).trim() || CLAUDE_DEFAULT_EFFORT;
        if (modelInput) modelInput.value = model;
        if (effortInput) effortInput.value = effort;

        await api.updateAgentSettings(agentId, {
          [CLAUDE_CREDENTIALS_KEY]: status.credentialsJson,
          [CLAUDE_MODEL_KEY]: model,
          [CLAUDE_EFFORT_KEY]: effort,
        });
        window.AgentSettings.toast('Claude Code connected.', 'success');
        await load();
      } catch (e) {
        window.AgentSettings.toast('Claude Code connect failed: ' + (e.message || e), 'error');
        setClaudeLocalStatus(bodyDr, e.message || String(e), 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = connected ? 'Re-import credentials' : 'Import Credentials';
      }
    });
  }

  function setKiroLocalStatus(bodyDr, text, kind) {
    const status = bodyDr.querySelector('[data-kiro-local-status]');
    if (!status) return;
    status.textContent = text || '';
    status.classList.toggle('connected', kind === 'connected');
    status.classList.toggle('error', kind === 'error');
  }

  async function initializeKiroLocalConnect(bodyDr, ext) {
    if (!isKiroCodeExtension(ext)) return;
    const box = bodyDr.querySelector('[data-kiro-local]');
    const btn = bodyDr.querySelector('.ext-kiro-local-connect');
    const invoke = tauriInvoke();
    if (!box || !btn) return;
    const connected = extensionConnected(ext);
    if (!invoke) { if (!connected) revealManualSettings(bodyDr); return; }

    box.hidden = false;
    btn.disabled = true;
    btn.textContent = 'Checking local Kiro IDE login…';
    try {
      const status = await invoke('local_kiro_refresh_token', { args: { includeSecret: false } });
      if (status && status.available) {
        btn.disabled = false;
        if (connected) {
          // Already wired up — the drawer header already says so. Keep
          // only a quiet "Re-import" affordance for refreshing an
          // expired token, not a loud "connect" prompt.
          box.classList.remove('ext-local-auth-primary');
          btn.classList.remove('btn-primary');
          btn.classList.add('btn-secondary');
          btn.textContent = 'Re-import credentials';
          setKiroLocalStatus(bodyDr, `Connected from ${status.path || '~/.aws/sso/cache/kiro-auth-token.json'}.`, 'connected');
        } else {
          btn.textContent = 'Import Credentials';
          setKiroLocalStatus(bodyDr, `Found ${status.path || '~/.aws/sso/cache/kiro-auth-token.json'}.`, 'connected');
        }
      } else {
        if (connected) { box.hidden = true; return; }
        if (status && /only available in the desktop app/i.test(status.error || '')) {
          box.hidden = true;
          revealManualSettings(bodyDr);
          return;
        }
        btn.disabled = true;
        btn.textContent = 'Local Kiro IDE login not found';
        const message = status && status.error
          ? status.error
          : `Login to Kiro IDE, then reopen this settings panel.`;
        setKiroLocalStatus(bodyDr, message, 'error');
        revealManualSettings(bodyDr);
      }
    } catch (e) {
      if (connected) { box.hidden = true; return; }
      btn.disabled = true;
      btn.textContent = 'Local Kiro IDE login unavailable';
      setKiroLocalStatus(bodyDr, e.message || String(e), 'error');
      revealManualSettings(bodyDr);
    }

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Connecting…';
      try {
        const status = await invoke('local_kiro_refresh_token', { args: { includeSecret: true } });
        if (!status || !status.available || !status.refreshToken) {
          throw new Error((status && status.error) || 'No local Kiro IDE login was found.');
        }

        const modelInput = settingInput(bodyDr, KIRO_MODEL_KEY);
        const trustAllInput = settingInput(bodyDr, KIRO_TRUST_ALL_TOOLS_KEY);
        const model = ((modelInput && modelInput.value) || KIRO_DEFAULT_MODEL).trim() || KIRO_DEFAULT_MODEL;
        const trustAllTools = ((trustAllInput && trustAllInput.value) || 'true').trim() || 'true';
        if (modelInput) modelInput.value = model;
        if (trustAllInput) trustAllInput.value = trustAllTools;

        await api.updateAgentSettings(agentId, {
          [KIRO_REFRESH_TOKEN_KEY]: status.refreshToken,
          [KIRO_MODEL_KEY]: model,
          [KIRO_TRUST_ALL_TOOLS_KEY]: trustAllTools,
        });
        window.AgentSettings.toast('Kiro Code connected from local Kiro IDE login.', 'success');
        await load();
      } catch (e) {
        window.AgentSettings.toast('Kiro Code connect failed: ' + (e.message || e), 'error');
        setKiroLocalStatus(bodyDr, e.message || String(e), 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = connected ? 'Re-import credentials' : 'Import Credentials';
      }
    });
  }

  function bindDrawerBodyEvents() {
    const ext = drawerExt;
    if (!ext) return;
    const bodyDr = document.getElementById('ext-drawer-body');
    if (!bodyDr) return;

    initializeCodexLocalConnect(bodyDr, ext);
    initializeClaudeLocalConnect(bodyDr, ext);
    initializeKiroLocalConnect(bodyDr, ext);

    // Per-command toggles
    bodyDr.querySelectorAll('.ext-cmd input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', async () => {
        const row = cb.closest('.ext-cmd');
        const idx = Number(row.getAttribute('data-cmd-idx'));
        const cmd = (ext.commands || [])[idx];
        if (!cmd) return;
        cb.disabled = true;
        try {
          await api.toggleCommand(agentId, cmd.command_name, cb.checked);
          cmd.enabled = cb.checked;
          // Refresh the drawer header counts and the tile badge.
          renderDrawer();
          render();
        } catch (e) {
          cb.checked = !cb.checked;
          window.AgentSettings.toast('Failed to toggle: ' + (e.message || e), 'error');
        } finally {
          cb.disabled = false;
        }
      });
    });

    // Bulk toggle
    const bulk = bodyDr.querySelector('.ext-bulk-toggle input[type="checkbox"]');
    if (bulk) {
      bulk.addEventListener('change', async () => {
        bulk.disabled = true;
        const target = bulk.checked;
        try {
          await api.bulkToggleExtension(agentId, ext.extension_name, target);
          (ext.commands || []).forEach((c) => { c.enabled = target; });
          renderDrawer();
          render();
        } catch (e) {
          bulk.checked = !target;
          window.AgentSettings.toast('Failed to bulk toggle: ' + (e.message || e), 'error');
        } finally {
          bulk.disabled = false;
        }
      });
    }

    // Save settings (non-OAuth)
    const saveBtn = bodyDr.querySelector('.ext-settings-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const inputs = bodyDr.querySelectorAll('.ext-settings-row');
        const map = {};
        inputs.forEach((row) => {
          const key = row.getAttribute('data-setting-key');
          const input = row.querySelector('input, textarea');
          if (!key || !input) return;
          // Skip empty password fields where the value is just the
          // placeholder dots — avoids overwriting saved secrets.
          if (isSensitiveKey(key) && (input.value === '' || looksMaskedSecretValue(input.value))) return;
          map[key] = input.value;
        });
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        try {
          await api.updateAgentSettings(agentId, map);
          window.AgentSettings.toast('Settings saved.', 'success');
          await load();
        } catch (e) {
          window.AgentSettings.toast('Save failed: ' + (e.message || e), 'error');
        } finally {
          saveBtn.disabled = false;
          saveBtn.textContent = 'Save settings';
        }
      });
    }

    // OAuth connect — delegate to the connections helper. The deep-link
    // handler will fire `agixt-extension-connected` and trigger a reload.
    const connectBtn = bodyDr.querySelector('.ext-oauth-connect');
    if (connectBtn) {
      connectBtn.addEventListener('click', async () => {
        const provider = findProviderForExtension(ext);
        if (!provider || !window.AgentSettingsConnections) return;
        connectBtn.disabled = true;
        connectBtn.textContent = 'Opening browser…';
        try { await window.AgentSettingsConnections.startConnect(provider); }
        finally {
          connectBtn.disabled = false;
          connectBtn.textContent = `Connect ${prettyProviderName(provider.name)}`;
        }
      });
    }

    const disconnectBtn = bodyDr.querySelector('.ext-oauth-disconnect');
    if (disconnectBtn) {
      disconnectBtn.addEventListener('click', async () => {
        const provider = findProviderForExtension(ext);
        if (!provider || !window.AgentSettingsConnections) return;
        disconnectBtn.disabled = true;
        disconnectBtn.textContent = 'Disconnecting…';
        try { await window.AgentSettingsConnections.startDisconnect(provider); }
        finally { disconnectBtn.disabled = false; }
      });
    }

    // Custom-connect (audible-style) — render the inline connect UI
    // INTO the drawer. The sidebar tab for these extensions stays
    // hidden until the auth file lands (manifest gating), so this is
    // the only entry point. On success we refresh the desktop
    // extensions manifest so the tab appears.
    const customConnectBtn = bodyDr.querySelector('.ext-custom-connect');
    if (customConnectBtn) {
      customConnectBtn.addEventListener('click', () => {
        const cfg = customConnectFor(ext);
        if (!cfg || typeof cfg.renderInline !== 'function') return;
        // Replace the action area with a host element the inline
        // renderer takes over. Keep the drawer open so the user can
        // see the marketplace picker + paste field without losing
        // their place in the settings list.
        const action = customConnectBtn.closest('.ext-drawer-action') || customConnectBtn.parentElement;
        if (!action) return;
        action.innerHTML = '<div class="ext-aud-host"></div>';
        const host = action.querySelector('.ext-aud-host');
        cfg.renderInline(host, async () => {
          const raw = extensionRawName(ext);
          delete customConnectStatus[raw];
          try { await fetchCustomConnectStatus(raw, cfg); } catch (_) {}
          // Tell the desktop loader to re-pull the manifest now that
          // the connection_check passes — that's what makes the
          // sidebar tab appear.
          try {
            if (window.AgixtDesktopExtensions
                && typeof window.AgixtDesktopExtensions.refresh === 'function') {
              await window.AgixtDesktopExtensions.refresh({ force: true });
            }
          } catch (_) {}
          // Re-fetch the agent extensions list so the tile grid
          // re-sections (audible moves from "Available" to
          // "Connected"), the bulk counter at the top updates, and
          // any abilities that were enabled but hidden behind the
          // connection_check now show up in the drawer abilities
          // section. Without this, the tile keeps reading "Not
          // connected" even though the auth blob was just written.
          try { await load(); } catch (err) {
            console.warn('custom-connect: extensions reload failed', err);
          }
          // Re-render the drawer so the status flips to "Connected"
          // and the CTA changes to "Manage". `load()` already replaced
          // `drawerExt` with the fresh entry from the new fetch.
          if (drawerOpen && drawerExt) renderDrawer();
          if (window.AgentSettings && window.AgentSettings.toast) {
            window.AgentSettings.toast(`${formatExtensionName(ext.friendly_name || ext.extension_name)} connected.`, 'success');
          }
        });
      });
    }
  }

  function bindDrawerChromeEvents() {
    if (drawerEventsWired) return;
    drawerEventsWired = true;
    const closeBtn = document.getElementById('ext-drawer-close');
    const backdrop = document.getElementById('ext-drawer-backdrop');
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (backdrop) backdrop.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && drawerOpen) closeDrawer();
    });
  }

  async function load() {
    if (!agentId) return;
    bodyEl = document.getElementById('ext-body');
    if (bodyEl) bodyEl.innerHTML = '<div class="as-empty" id="ext-loading">Loading extensions…</div>';
    try {
      const [exts, provs, conns] = await Promise.all([
        api.getAgentExtensions(agentId),
        api.getOAuthProviders().catch(() => []),
        api.getUserOAuthConnections().catch(() => null),
      ]);
      extensions = exts;
      providers = provs.filter((p) => p && p.client_id);   // only configured
      userConnections = conns;
      // Custom-connect extensions (audible) carry their connection
      // state on a separate server endpoint, not in the agent
      // extension payload. Fetch those probes in parallel BEFORE
      // rendering so the audible tile lands in the correct
      // Connected/Available section on first paint instead of
      // flashing under Available until the user opens the drawer.
      const customConnectExts = extensions.filter(customConnectFor);
      if (customConnectExts.length) {
        await Promise.all(customConnectExts.map((e) => {
          const cfg = customConnectFor(e);
          const raw = extensionRawName(e);
          return cfg ? fetchCustomConnectStatus(raw, cfg).catch(() => null) : null;
        }));
      }
      render();
      // If the drawer is open, the cached `drawerExt` is stale — find the
      // refreshed copy and rerender, or close if the extension disappeared.
      if (drawerOpen && drawerExt) {
        const updated = findExtensionByName(drawerExt.extension_name);
        if (updated) {
          drawerExt = updated;
          renderDrawer();
        } else {
          closeDrawer();
        }
      }
    } catch (e) {
      if (bodyEl) bodyEl.innerHTML = `<div class="as-empty">Failed to load: ${escape(e.message || e)}</div>`;
    }
  }

  function init(opts) {
    agentId = opts.agentId;
    agentName = opts.agentName || null;
    const search = document.getElementById('ext-search');
    const onlyChk = document.getElementById('ext-only-enabled');
    if (search) {
      search.addEventListener('input', () => {
        searchText = search.value || '';
        render();
      });
    }
    if (onlyChk) {
      onlyChk.addEventListener('change', () => {
        onlyEnabled = onlyChk.checked;
        render();
      });
    }
    bindDrawerChromeEvents();
    return load();
  }

  window.AgentSettingsExtensions = {
    init,
    reload: load,
    setAgent(id, name) { agentId = id; agentName = name || null; },
    refreshConnectionState: () => {
      // Called by connections module after a connect/disconnect succeeds —
      // re-fetch extensions so the tiles re-section and the drawer
      // reflects the new state.
      return load();
    },
  };
})();
