/* Extensions tab — vanilla JS port of web/components/settings/ExtensionGrid.tsx
 *
 * Renders extension categories → expandable extension cards → per-command
 * toggles + inline settings form for non-OAuth extensions. OAuth extensions
 * delegate the "Connect" action to settings-connections.js so we have one
 * code path for the OAuth handshake.
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
  let bodyEl = null;

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
    // Replace _ with space, leave existing spaces.
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
    // Prefer exact match
    let p = providers.find((p) => (p.name || '').toLowerCase() === raw);
    if (!p) {
      // twitter is sometimes registered as "x"
      const alt = raw === 'twitter' ? 'x' : raw === 'x' ? 'twitter' : null;
      if (alt) p = providers.find((p) => (p.name || '').toLowerCase() === alt);
    }
    return p || null;
  }

  function commandsEnabled(ext) {
    return (ext.commands || []).filter((c) => c.enabled).length;
  }

  /** Does the user have an active OAuth connection for this provider?
   *  Empirically /v1/oauth2 returns either a bare list of provider names,
   *  a list of `{name, connected}` objects, or an object with a
   *  `connected: [...]` field. Cover all three. */
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

  function extensionConnected(ext) {
    // OAuth extensions: connection follows the user's OAuth state.
    if (isOAuthExtension(ext)) {
      return isProviderConnected(findProviderForExtension(ext));
    }
    // Non-OAuth extensions with settings (API keys etc.): "connected"
    // means at least one setting is filled in.
    const settings = ext.settings || [];
    if (settings.length > 0) {
      return settings.some((s) => {
        const v = typeof s === 'string' ? '' : (s.setting_value || '');
        return typeof v === 'string' && v.length > 0;
      });
    }
    // Plain extensions with no settings need no configuration; they're
    // always usable.
    return true;
  }

  /** Some extensions don't really have a "connection" concept. Hide the
   *  status dot for those so it doesn't read as "this is broken". */
  function extensionHasConnectionState(ext) {
    return isOAuthExtension(ext) || (ext.settings || []).length > 0;
  }

  function groupByCategory(list) {
    const groups = {};
    for (const ext of list) {
      const cat = ext.category || 'Other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(ext);
    }
    return groups;
  }

  function filterExtensions(list) {
    const q = (searchText || '').trim().toLowerCase();
    return list.filter((ext) => {
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

  function renderExtensionCard(ext) {
    const name = formatExtensionName(ext.friendly_name || ext.extension_name);
    const enabled = commandsEnabled(ext);
    const total = (ext.commands || []).length;
    const connected = extensionConnected(ext);
    const isOAuth = isOAuthExtension(ext);
    const provider = isOAuth ? findProviderForExtension(ext) : null;
    const providerSlug = provider ? api.redirectSlug(provider.name) : null;
    const allOn = total > 0 && enabled === total;
    const dataAttrs = `data-ext-name="${escape(ext.extension_name || '')}" data-oauth="${isOAuth ? '1' : '0'}" ${providerSlug ? `data-provider-slug="${escape(providerSlug)}" data-provider-name="${escape(provider.name)}"` : ''}`;
    let desc = '';
    if (ext.description) {
      if (md) {
        try { desc = md.render(ext.description); }
        catch (e) {
          console.warn('markdown render failed for', ext.extension_name, e);
          desc = `<p>${escape(ext.description)}</p>`;
        }
      } else {
        desc = `<p>${escape(ext.description)}</p>`;
      }
    }

    let actions = '';
    if (isOAuth && provider) {
      if (connected) {
        actions = `<button class="btn btn-secondary ext-oauth-disconnect" type="button">Disconnect</button>`;
      } else {
        actions = `<button class="btn btn-primary ext-oauth-connect" type="button">Connect ${escape(prettyProviderName(provider.name))}</button>`;
      }
    }
    if (total > 0) {
      // For OAuth extensions only show the bulk toggle once connected — no
      // point in toggling commands for a provider you can't reach yet.
      if (!isOAuth || connected) {
        actions += `
          <label class="ext-bulk-toggle">
            ${renderSwitch(allOn)}
            <span>Enable all commands</span>
          </label>
        `;
      }
    }

    const showDot = extensionHasConnectionState(ext);
    const dotTitle = !showDot ? 'Always available'
      : isOAuth
        ? (connected ? 'Connected' : 'Not connected')
        : (connected ? 'Configured' : 'Not configured');
    // For OAuth extensions, hide the commands list until the user has
    // connected the provider — toggling abilities you can't reach is
    // confusing.
    const showCommands = !isOAuth || connected;
    return `
      <details class="ext-card" ${dataAttrs}>
        <summary class="ext-card-summary">
          <svg class="ext-card-chevron" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          ${showDot ? `<span class="ext-card-conn-dot ${connected ? 'connected' : ''}" title="${dotTitle}"></span>` : ''}
          <span class="ext-card-name">${escape(name)}</span>
          ${total > 0 ? `<span class="ext-card-counts">${enabled}/${total}</span>` : ''}
        </summary>
        <div class="ext-card-body">
          ${desc ? `<div class="ext-card-desc">${desc}</div>` : ''}
          ${actions ? `<div class="ext-card-actions">${actions}</div>` : ''}
          ${showCommands ? renderExtensionCommands(ext) : ''}
          ${renderExtensionSettingsForm(ext)}
        </div>
      </details>
    `;
  }

  function renderCategory(catName, exts) {
    const description = (exts.find((e) => e.category_description) || {}).category_description || '';
    const totalCmds = exts.reduce((n, e) => n + (e.commands || []).length, 0);
    const enabledCmds = exts.reduce((n, e) => n + commandsEnabled(e), 0);
    // Connection ratio counts only extensions whose connection has any
    // meaning (OAuth-backed or with sensitive settings). Plain-always-on
    // extensions inflate the ratio and confuse the at-a-glance read.
    const connExts = exts.filter(extensionHasConnectionState);
    const connectedCount = connExts.filter(extensionConnected).length;
    const cmdBadgeClass = totalCmds === 0 ? '' : enabledCmds === totalCmds ? 'ok' : enabledCmds > 0 ? 'partial' : '';
    return `
      <div class="ext-category" data-cat="${escape(catName)}">
        <div class="ext-category-header">
          <div>
            <h3 class="ext-category-title">${escape(catName)}</h3>
            ${description ? `<p class="ext-category-blurb">${escape(description)}</p>` : ''}
          </div>
          <div class="ext-category-badges">
            ${connExts.length > 0 ? `<span class="ext-badge connected">${connectedCount}/${connExts.length} connected</span>` : ''}
            ${totalCmds > 0 ? `<span class="ext-badge ${cmdBadgeClass}">${enabledCmds}/${totalCmds} abilities</span>` : ''}
          </div>
        </div>
        <div class="ext-category-body">
          ${exts.map(renderExtensionCard).join('')}
        </div>
      </div>
    `;
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

  function refreshStats() {
    const stats = document.getElementById('ext-stats');
    if (!stats) return;
    const totalCmds = extensions.reduce((n, e) => n + (e.commands || []).length, 0);
    const enabledCmds = extensions.reduce((n, e) => n + commandsEnabled(e), 0);
    stats.textContent = `${enabledCmds}/${totalCmds} abilities enabled · ${extensions.length} extensions`;
  }

  function render() {
    if (!bodyEl) return;
    const filtered = filterExtensions(extensions);
    const groups = groupByCategory(filtered);
    const sorted = Object.entries(groups)
      .filter(([n]) => n.toLowerCase() !== 'authentication')
      .sort((a, b) => {
        if (a[0] === 'Core Abilities') return -1;
        if (b[0] === 'Core Abilities') return 1;
        return a[0].localeCompare(b[0]);
      });
    if (sorted.length === 0) {
      bodyEl.innerHTML = '<div class="as-empty">No extensions match.</div>';
    } else {
      bodyEl.innerHTML = `<div class="ext-grid">${sorted.map(([n, e]) => renderCategory(n, e)).join('')}</div>`;
      bindCardEvents();
    }
    refreshStats();
  }

  function findExtensionByName(name) {
    return extensions.find((e) => (e.extension_name || '') === name) || null;
  }

  function bindCardEvents() {
    bodyEl.querySelectorAll('.ext-card').forEach((card) => {
      const extName = card.getAttribute('data-ext-name');
      const ext = findExtensionByName(extName);
      if (!ext) return;

      // Per-command toggles
      card.querySelectorAll('.ext-cmd input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', async () => {
          const row = cb.closest('.ext-cmd');
          const idx = Number(row.getAttribute('data-cmd-idx'));
          const cmd = (ext.commands || [])[idx];
          if (!cmd) return;
          cb.disabled = true;
          try {
            await api.toggleCommand(agentId, cmd.command_name, cb.checked);
            cmd.enabled = cb.checked;
            refreshStats();
          } catch (e) {
            cb.checked = !cb.checked;
            window.AgentSettings.toast('Failed to toggle: ' + (e.message || e), 'error');
          } finally {
            cb.disabled = false;
          }
        });
      });

      // Bulk toggle (on the card body, NOT in the cmd list — those are
      // wrapped in .ext-bulk-toggle)
      const bulk = card.querySelector('.ext-bulk-toggle input[type="checkbox"]');
      if (bulk) {
        bulk.addEventListener('change', async () => {
          bulk.disabled = true;
          const target = bulk.checked;
          try {
            await api.bulkToggleExtension(agentId, ext.extension_name, target);
            (ext.commands || []).forEach((c) => { c.enabled = target; });
            // Refresh just this card by re-rendering — easiest path.
            const open = card.hasAttribute('open');
            card.outerHTML = renderExtensionCard(ext);
            if (open) {
              // Re-find since outerHTML replaced the node.
              const newCard = bodyEl.querySelector(`.ext-card[data-ext-name="${CSS.escape(extName)}"]`);
              if (newCard) newCard.setAttribute('open', '');
            }
            // Re-bind events on the regenerated DOM.
            bindCardEvents();
            refreshStats();
          } catch (e) {
            bulk.checked = !target;
            window.AgentSettings.toast('Failed to bulk toggle: ' + (e.message || e), 'error');
          } finally {
            bulk.disabled = false;
          }
        });
      }

      // Save settings (non-OAuth)
      const saveBtn = card.querySelector('.ext-settings-save');
      if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
          const inputs = card.querySelectorAll('.ext-settings-row');
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
          } catch (e) {
            window.AgentSettings.toast('Save failed: ' + (e.message || e), 'error');
          } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save settings';
          }
        });
      }

      // OAuth connect — delegate to the connections helper.
      const connectBtn = card.querySelector('.ext-oauth-connect');
      if (connectBtn) {
        connectBtn.addEventListener('click', async () => {
          const providerName = card.getAttribute('data-provider-name');
          const provider = providers.find((p) => p.name === providerName);
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

      const disconnectBtn = card.querySelector('.ext-oauth-disconnect');
      if (disconnectBtn) {
        disconnectBtn.addEventListener('click', async () => {
          const providerName = card.getAttribute('data-provider-name');
          const provider = providers.find((p) => p.name === providerName);
          if (!provider || !window.AgentSettingsConnections) return;
          disconnectBtn.disabled = true;
          disconnectBtn.textContent = 'Disconnecting…';
          try { await window.AgentSettingsConnections.startDisconnect(provider); }
          finally { disconnectBtn.disabled = false; }
          // The connections helper already calls refreshConnectionState
          // which will rerender; no need to do anything else here.
        });
      }
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
    return load();
  }

  window.AgentSettingsExtensions = {
    init,
    reload: load,
    setAgent(id, name) { agentId = id; agentName = name || null; },
    refreshConnectionState: () => {
      // Called by connections module after a connect/disconnect succeeds —
      // re-fetch extensions so the per-card connection dots update.
      return load();
    },
  };
})();
