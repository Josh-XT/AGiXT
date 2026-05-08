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
    'microsoft', 'microsoft_email', 'microsoft_calendar', 'microsoft_onedrive', 'microsoft_sharepoint',
    'github', 'linkedin', 'meta_ads', 'amazon', 'alexa', 'tesla', 'discord',
    'x', 'twitter', 'fitbit', 'garmin', 'walmart', 'stripe_payments', 'notion',
    'todoist', 'spotify', 'trello', 'airtable', 'dropbox', 'youtube', 'reddit',
    'facebook', 'slack',
  ]);

  function extensionRawName(ext) {
    return (ext.extension_name || ext.friendly_name || '').toLowerCase().trim().replace(/\s+/g, '_');
  }

  function isOAuthExtension(ext) {
    return OAUTH_EXT_NAMES.has(extensionRawName(ext));
  }

  function findProviderForExtension(ext) {
    if (!isOAuthExtension(ext)) return null;
    const raw = extensionRawName(ext);
    let p = providers.find((p) => (p.name || '').toLowerCase() === raw);
    if (!p) {
      const alt = raw === 'twitter' ? 'x' : raw === 'x' ? 'twitter' : null;
      if (alt) p = providers.find((p) => (p.name || '').toLowerCase() === alt);
    }
    return p || null;
  }

  function commandsEnabled(ext) {
    return (ext.commands || []).filter((c) => c.enabled).length;
  }

  /** Does the user have an active OAuth connection for this provider? */
  function isProviderConnected(provider) {
    if (!provider || !userConnections) return false;
    const targetName = (provider.name || '').toLowerCase();
    const targetSlug = api.redirectSlug(provider.name);
    if (Array.isArray(userConnections)) {
      return userConnections.some((entry) => {
        if (typeof entry === 'string') {
          const e = entry.toLowerCase();
          return e === targetName || e === targetSlug;
        }
        if (entry && typeof entry === 'object') {
          const n = (entry.name || entry.provider || '').toLowerCase();
          if (n !== targetName && n !== targetSlug) return false;
          return !('connected' in entry) || !!entry.connected;
        }
        return false;
      });
    }
    if (Array.isArray(userConnections.connected)) {
      return userConnections.connected.includes(provider.name) ||
             userConnections.connected.includes(targetSlug);
    }
    if (Array.isArray(userConnections.providers)) {
      const match = userConnections.providers.find((p) => (p.name || '').toLowerCase() === targetName);
      return !!(match && match.connected);
    }
    return !!userConnections[provider.name];
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

  function settingValue(s) {
    if (!s || typeof s === 'string') return '';
    return s.setting_value == null ? '' : String(s.setting_value);
  }

  function hasAnyValue(settings) {
    return settings.some((s) => settingValue(s).length > 0);
  }

  function extensionConnected(ext) {
    if (isOAuthExtension(ext)) {
      return isProviderConnected(findProviderForExtension(ext));
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
    return isOAuthExtension(ext) || (ext.settings || []).length > 0;
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
    if (isOAuthExtension(ext)) return '';   // OAuth handles its own creds
    const rows = settings.map((s, idx) => {
      const key = typeof s === 'string' ? s : s.setting_key;
      const val = typeof s === 'string' ? '' : (s.setting_value || '');
      const meta = classifySetting(key);
      const label = formatSettingLabel(key, ext.extension_name);
      const placeholder = meta.type === 'password' && val ? '••••••••' : '';
      const numAttrs = meta.type === 'number' ? `step="${meta.step}" min="${meta.min || ''}" max="${meta.max || ''}"` : '';
      return `
        <div class="ext-settings-row" data-setting-key="${escape(key)}">
          <label class="ext-settings-label" for="ext-set-${idx}-${escape(ext.extension_name)}">${escape(label)}</label>
          <input id="ext-set-${idx}-${escape(ext.extension_name)}" class="as-input" type="${meta.type}" value="${escape(val)}" placeholder="${placeholder}" ${numAttrs} />
        </div>
      `;
    }).join('');
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
    const isOAuth = isOAuthExtension(ext);
    const needsSetup = hasConnState && !connected;
    const enabled = commandsEnabled(ext);
    const showDot = isOAuth && connected;
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
    const totalCmds = extensions.reduce((n, e) => n + (e.commands || []).length, 0);
    const enabledCmds = extensions.reduce((n, e) => n + commandsEnabled(e), 0);
    stats.textContent = `${enabledCmds}/${totalCmds} abilities enabled · ${extensions.length} extensions`;
  }

  function renderChips() {
    const chipsEl = document.getElementById('ext-chips');
    if (!chipsEl) return;
    const visible = extensions.filter((e) => (e.category || '').toLowerCase() !== 'authentication');
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
    const isOAuth = isOAuthExtension(ext);
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

    let statusText, statusClass;
    if (isOAuth) {
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

    // Settings form for non-OAuth extensions with config fields.
    const settingsForm = renderExtensionSettingsForm(ext);
    if (settingsForm) {
      parts.push(`<div class="ext-drawer-section-title">Settings</div>${settingsForm}`);
    }

    // Abilities — only meaningful once the extension is reachable.
    if (total > 0) {
      const reachable = !isOAuth || connected;
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
      } else {
        const pp = provider ? prettyProviderName(provider.name) : friendly;
        parts.push(`<div class="ext-drawer-section-title">Abilities</div>`);
        parts.push(`<div class="ext-drawer-empty">Connect ${escape(pp)} to use ${total} ${total === 1 ? 'ability' : 'abilities'}.</div>`);
      }
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

  function bindDrawerBodyEvents() {
    const ext = drawerExt;
    if (!ext) return;
    const bodyDr = document.getElementById('ext-drawer-body');
    if (!bodyDr) return;

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
          const input = row.querySelector('input');
          if (!key || !input) return;
          // Skip empty password fields where the value is just the
          // placeholder dots — avoids overwriting saved secrets.
          if (input.type === 'password' && input.value === '') return;
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
