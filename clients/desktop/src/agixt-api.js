/* Thin AGiXT REST helper used by the agent-settings window.
 *
 * All calls hit `${settings.server_url}/v1/...` with `Authorization: Bearer
 * ${settings.jwt}`. Settings are loaded once via `invoke('get_settings')` and
 * cached for the lifetime of the window — the user's chosen agent comes from
 * `settings.agent_id` set by the topbar agent switcher in the main window.
 *
 * Decisions to call out for future maintainers:
 *   - We use `Bearer` prefix everywhere (matches existing chat.js + voice
 *     code). The web client uses raw JWT in some places; AGiXT accepts both.
 *   - When the server returns `{detail: "..."}` for a 4xx we surface
 *     `detail`; otherwise we surface the body text or status.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    console.error('agixt-api.js: Tauri IPC unavailable');
    return;
  }
  const invoke = tauri.core.invoke;

  let cachedSettings = null;
  let settingsPromise = null;

  async function getSettings() {
    if (cachedSettings) return cachedSettings;
    if (!settingsPromise) {
      settingsPromise = invoke('get_settings').then((s) => {
        cachedSettings = s;
        return s;
      });
    }
    return settingsPromise;
  }

  /** Force a refresh from disk — call this when settings might've changed
   *  (e.g. after the user switched agents in the main window). */
  async function refreshSettings() {
    cachedSettings = null;
    settingsPromise = null;
    return getSettings();
  }

  function trimSlashes(url) {
    return (url || '').replace(/\/+$/, '');
  }

  async function authHeaders(extra) {
    const s = await getSettings();
    const headers = { Authorization: 'Bearer ' + (s.jwt || '') };
    if (extra) Object.assign(headers, extra);
    return headers;
  }

  async function apiBase() {
    const s = await getSettings();
    return trimSlashes(s.server_url);
  }

  function detailToString(raw) {
    if (raw == null) return '';
    if (typeof raw === 'string') return raw;
    // FastAPI validation errors arrive as `[{loc, msg, type}, ...]`. Render
    // them human-readably instead of letting them stringify to
    // `[object Object]`.
    if (Array.isArray(raw)) {
      return raw.map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          if (typeof item.msg === 'string') {
            const loc = Array.isArray(item.loc) ? item.loc.join('.') : '';
            return loc ? `${loc}: ${item.msg}` : item.msg;
          }
          try { return JSON.stringify(item); } catch (_) { return String(item); }
        }
        return String(item);
      }).join('; ');
    }
    if (typeof raw === 'object') {
      if (typeof raw.msg === 'string') return raw.msg;
      try { return JSON.stringify(raw); } catch (_) { return String(raw); }
    }
    return String(raw);
  }

  async function parseError(resp) {
    let detail = '';
    try {
      const body = await resp.text();
      try {
        const j = JSON.parse(body);
        const raw = j.detail != null ? j.detail
          : j.error != null ? j.error
          : j.message != null ? j.message
          : body;
        detail = detailToString(raw);
      } catch (_) {
        detail = body;
      }
    } catch (_) {
      detail = '';
    }
    const msg = detail || `HTTP ${resp.status}`;
    const err = new Error(msg);
    err.status = resp.status;
    err.detail = detail;
    return err;
  }

  async function request(method, path, opts) {
    opts = opts || {};
    const base = await apiBase();
    const url = base + path;
    const headers = await authHeaders(opts.headers);
    const init = { method, headers };
    if (opts.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    }
    const resp = await fetch(url, init);
    if (!resp.ok) throw await parseError(resp);
    if (resp.status === 204) return null;
    const text = await resp.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  // ----- Agent + extensions ------------------------------------------------

  /** GET /v1/agent/{id}/extensions
   *  Returns: { extensions: [{ extension_name, friendly_name, description,
   *    settings: [...], commands: [{ command_name, friendly_name, enabled, ... }],
   *    category, category_description }, ...] }
   */
  async function getAgentExtensions(agentId) {
    const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/extensions');
    const arr = (data && (data.extensions || data)) || [];
    return Array.isArray(arr) ? arr : [];
  }

  /** PATCH /v1/agent/{id}/command — enable/disable one command. */
  async function toggleCommand(agentId, commandName, enable) {
    return request('PATCH', '/v1/agent/' + encodeURIComponent(agentId) + '/command', {
      body: { command_name: commandName, enable: !!enable },
    });
  }

  /** PATCH /v1/agent/{id}/extension/commands — bulk enable/disable every
   *  command in an extension. */
  async function bulkToggleExtension(agentId, extensionName, enable) {
    return request(
      'PATCH',
      '/v1/agent/' + encodeURIComponent(agentId) + '/extension/commands',
      { body: { extension_name: extensionName, enable: !!enable } },
    );
  }

  /** PUT /v1/agent/{id} — update agent settings (key/value map).
   *  AGiXT's PUT validator requires `agent_name` alongside `settings` (see
   *  web/app/settings/page.tsx handleSaveSettings); without it the server
   *  returns a 422 with a FastAPI validation array. */
  async function updateAgentSettings(agentId, settingsMap) {
    const s = await getSettings();
    return request('PUT', '/v1/agent/' + encodeURIComponent(agentId), {
      body: {
        agent_name: s.agent_name || '',
        settings: settingsMap,
      },
    });
  }

  // ----- OAuth providers ---------------------------------------------------

  /** GET /v1/oauth — list of configured OAuth providers, with `client_id`
   *  populated only for providers the server has credentials for. */
  async function getOAuthProviders() {
    const data = await request('GET', '/v1/oauth');
    const arr = (data && (data.providers || data)) || [];
    return Array.isArray(arr) ? arr : [];
  }

  /** GET /v1/oauth2 — same shape as /v1/oauth but used for connection state
   *  (which providers the *user* is currently connected to). The two paths
   *  return the same payload — the only thing that differs is that
   *  authenticated /v1/oauth2 attaches per-provider connection metadata if
   *  the backend exposes it. We treat them as interchangeable. */
  async function getUserOAuthConnections() {
    try {
      return await request('GET', '/v1/oauth2');
    } catch (_) {
      return null;
    }
  }

  /** DELETE /v1/oauth2/{provider} — disconnect a provider. */
  async function disconnectOAuth(providerSlug) {
    return request('DELETE', '/v1/oauth2/' + encodeURIComponent(providerSlug));
  }

  // ----- Training ----------------------------------------------------------

  /** GET /v1/agent/{id}/persona → { message: "..." }  ("None" → empty). */
  async function getPersona(agentId) {
    try {
      const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/persona');
      const msg = (data && data.message) || '';
      return msg === 'None' ? '' : msg;
    } catch (e) {
      // 404 etc — treat as empty so the editor still works.
      return '';
    }
  }

  /** PUT /v1/agent/{id}/persona — set the mandatory context. */
  async function setPersona(agentId, persona) {
    return request('PUT', '/v1/agent/' + encodeURIComponent(agentId) + '/persona', {
      body: { persona: persona || '' },
    });
  }

  /** GET /v1/agent/{id}/memory/external_sources/0 → { external_sources: [...] }. */
  async function listTrainingSources(agentId) {
    try {
      const data = await request('GET', '/v1/agent/' + encodeURIComponent(agentId) + '/memory/external_sources/0');
      const arr = (data && data.external_sources) || [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  /** POST /v1/agent/{id}/learn/file — upload a base64-encoded file. */
  async function learnFile(agentId, fileName, base64Content) {
    return request('POST', '/v1/agent/' + encodeURIComponent(agentId) + '/learn/file', {
      body: {
        file_name: fileName,
        file_content: base64Content,
        collection_number: '0',
      },
    });
  }

  /** POST /v1/agent/{id}/learn/url. */
  async function learnUrl(agentId, url) {
    return request('POST', '/v1/agent/' + encodeURIComponent(agentId) + '/learn/url', {
      body: { url },
    });
  }

  /** DELETE /v1/agent/{id}/memories/external_source — remove a source. */
  async function deleteSource(agentId, source) {
    const base = await apiBase();
    const url = base + '/v1/agent/' + encodeURIComponent(agentId) + '/memories/external_source';
    const headers = await authHeaders({ 'Content-Type': 'application/json' });
    const resp = await fetch(url, {
      method: 'DELETE',
      headers,
      body: JSON.stringify({
        external_source: source,
        collection_number: '0',
      }),
    });
    if (!resp.ok) throw await parseError(resp);
    return null;
  }

  // ----- Helpers exported for the tab modules ------------------------------

  /** Read a File object as base64 (without the data: prefix). Reports
   *  load progress 0-100 via onProgress. */
  function readFileAsBase64(file, onProgress) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const r = reader.result;
        const idx = typeof r === 'string' ? r.indexOf(',') : -1;
        resolve(idx >= 0 ? r.slice(idx + 1) : r);
      };
      reader.onerror = () => reject(reader.error || new Error('file read failed'));
      reader.onprogress = (ev) => {
        if (ev.lengthComputable && typeof onProgress === 'function') {
          onProgress(Math.round((ev.loaded * 100) / ev.total));
        }
      };
      reader.readAsDataURL(file);
    });
  }

  /** Slug a provider name the way AGiXT's OAuth apps were registered:
   *  strip trailing _sso, lowercase, replace _/./ space with - . Mirrors
   *  the Rust side `redirect_slug_for` and the web's OAuth.tsx. */
  function redirectSlug(name) {
    if (!name) return '';
    let s = String(name).toLowerCase();
    if (s.endsWith('_sso')) s = s.slice(0, -4);
    return s.replace(/_/g, '-').replace(/\./g, '-').replace(/\s+/g, '-');
  }

  // ----- User identity / preferences --------------------------------------

  /** GET /v1/user — current user (with companies + preferences). */
  async function getUser() { return request('GET', '/v1/user'); }

  /** PUT /v1/user — partial update. Field names use snake_case matching
   *  the AGiXT backend (first_name, last_name, email, username, phone_number,
   *  timezone, notification_preferences, etc.). */
  async function updateUser(patch) {
    return request('PUT', '/v1/user', { body: patch || {} });
  }

  /** DELETE /v1/user — permanently delete the signed-in account. */
  async function deleteUserAccount() { return request('DELETE', '/v1/user'); }

  /** POST /v1/user/verify/email — request a verification email or confirm
   *  if a 6-digit code is supplied. */
  async function requestEmailVerification(email) {
    return request('POST', '/v1/user/verify/email', { body: { email } });
  }

  /** POST /v1/user/password/change. */
  async function changePassword(currentPassword, newPassword, confirmPassword) {
    return request('POST', '/v1/user/password/change', {
      body: {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    });
  }

  /** GET /v1/user/mfa/setup — provisioning URI + secret + current state. */
  async function getMfaSetup() { return request('GET', '/v1/user/mfa/setup'); }

  /** POST /v1/user/mfa/enable — confirm 6-digit code to flip MFA on. */
  async function enableMfa(token) {
    return request('POST', '/v1/user/mfa/enable', { body: { mfa_token: token } });
  }

  /** POST /v1/user/mfa/disable — password + current code to flip MFA off. */
  async function disableMfa(password, token) {
    return request('POST', '/v1/user/mfa/disable', { body: { password, mfa_token: token } });
  }

  /** POST /v1/user/mfa/reset — issues a fresh otp_uri. */
  async function resetMfa() { return request('POST', '/v1/user/mfa/reset', { body: {} }); }

  // ----- Companies / members / invitations --------------------------------

  /** GET /v1/companies — top-level company list (with users[] when admin). */
  async function listCompanies() { return request('GET', '/v1/companies'); }

  /** POST /v1/companies — create a new company. */
  async function createCompany(payload) {
    return request('POST', '/v1/companies', { body: payload || {} });
  }

  /** PUT /v1/companies/{id} — rename. */
  async function renameCompany(companyId, name) {
    return request('PUT', '/v1/companies/' + encodeURIComponent(companyId), { body: { name } });
  }

  /** DELETE /v1/companies/{id}. */
  async function deleteCompany(companyId) {
    return request('DELETE', '/v1/companies/' + encodeURIComponent(companyId));
  }

  /** PUT /v1/user/companies/order — body is the array directly, e.g.
   *  [{company_id, sort_order}, ...]. */
  async function updateCompanyOrder(order) {
    return request('PUT', '/v1/user/companies/order', { body: order });
  }

  /** GET /v1/companies/{id}/members. */
  async function getCompanyMembers(companyId) {
    const data = await request('GET', '/v1/companies/' + encodeURIComponent(companyId) + '/members');
    return (data && data.members) || [];
  }

  /** DELETE /v1/companies/{id}/users/{user_id}. */
  async function removeCompanyMember(companyId, userId) {
    return request(
      'DELETE',
      '/v1/companies/' + encodeURIComponent(companyId) + '/users/' + encodeURIComponent(userId),
    );
  }

  /** PUT /v1/user/role — change a member's role within a company. */
  async function updateMemberRole(companyId, userId, roleId) {
    return request('PUT', '/v1/user/role', {
      body: { role_id: roleId, company_id: companyId, user_id: userId },
    });
  }

  /** GET /v1/invitations[/companyId]. */
  async function getInvitations(companyId) {
    const path = companyId
      ? '/v1/invitations/' + encodeURIComponent(companyId)
      : '/v1/invitations';
    const data = await request('GET', path);
    return (data && data.invitations) || [];
  }

  /** POST /v1/invitations. */
  async function createInvitation(payload) {
    return request('POST', '/v1/invitations', { body: payload || {} });
  }

  /** DELETE /v1/invitation/{id}. */
  async function deleteInvitation(invitationId) {
    return request('DELETE', '/v1/invitation/' + encodeURIComponent(invitationId));
  }

  /** GET /v1/roles — server-defined default roles + their scopes. */
  async function listDefaultRoles() {
    const data = await request('GET', '/v1/roles');
    return (data && (data.roles || data.default_roles)) || data || [];
  }

  // ----- Personal Access Tokens ------------------------------------------

  /** GET /v1/api-keys. */
  async function listPersonalAccessTokens() {
    const data = await request('GET', '/v1/api-keys');
    return (data && data.tokens) || [];
  }

  /** POST /v1/api-keys. */
  async function createPersonalAccessToken(payload) {
    return request('POST', '/v1/api-keys', { body: payload || {} });
  }

  /** DELETE /v1/api-keys/{id}. */
  async function revokePersonalAccessToken(tokenId) {
    return request('DELETE', '/v1/api-keys/' + encodeURIComponent(tokenId));
  }

  /** POST /v1/api-keys/{id}/regenerate. */
  async function regeneratePersonalAccessToken(tokenId) {
    return request('POST', '/v1/api-keys/' + encodeURIComponent(tokenId) + '/regenerate', { body: {} });
  }

  async function getAvailableTokenScopes(companyId) {
    const path = companyId
      ? '/v1/api-keys/available/scopes?company_id=' + encodeURIComponent(companyId)
      : '/v1/api-keys/available/scopes';
    const data = await request('GET', path);
    return (data && data.scopes) || [];
  }

  async function getAvailableTokenAgents() {
    const data = await request('GET', '/v1/api-keys/available/agents');
    return (data && data.agents) || [];
  }

  async function getAvailableTokenCompanies() {
    const data = await request('GET', '/v1/api-keys/available/companies');
    return (data && data.companies) || [];
  }

  // ----- Billing ----------------------------------------------------------

  /** GET /v1/billing/pricing/enabled — true when billing UI should appear. */
  async function getBillingEnabled() {
    try { return await request('GET', '/v1/billing/pricing/enabled'); }
    catch (_) { return { billing_enabled: false }; }
  }

  /** GET /v1/billing/pricing — pricing model + tiers + addons + topups. */
  async function getPricingConfig() {
    try { return await request('GET', '/v1/billing/pricing'); }
    catch (_) { return null; }
  }

  /** GET /v1/billing/tokens/balance?company_id=…&sync=… */
  async function getTokenBalance(companyId, sync) {
    const qs = '?company_id=' + encodeURIComponent(companyId) + '&sync=' + (sync ? 'true' : 'false');
    return request('GET', '/v1/billing/tokens/balance' + qs);
  }

  /** GET /v1/billing/auto-topup?company_id=… (also surfaces tiered-plan
   *  subscription state). */
  async function getAutoTopupStatus(companyId) {
    return request('GET', '/v1/billing/auto-topup?company_id=' + encodeURIComponent(companyId));
  }

  /** POST /v1/billing/auto-topup. */
  async function setAutoTopup(companyId, amountUsd) {
    return request('POST', '/v1/billing/auto-topup', {
      body: { company_id: companyId, amount_usd: amountUsd },
    });
  }

  /** GET /v1/billing/plan/limits?company_id=… */
  async function getPlanLimits(companyId) {
    return request('GET', '/v1/billing/plan/limits?company_id=' + encodeURIComponent(companyId));
  }

  /** POST /v1/billing/plan/checkout — returns a Stripe checkout URL the
   *  desktop should open in the user's browser. */
  async function createPlanCheckout(payload) {
    return request('POST', '/v1/billing/plan/checkout', { body: payload || {} });
  }

  /** POST /v1/billing/plan/topup — Stripe checkout URL for token top-up. */
  async function createPlanTopup(payload) {
    return request('POST', '/v1/billing/plan/topup', { body: payload || {} });
  }

  /** POST /v1/billing/tokens/topup/stripe — legacy per-token Stripe topup. */
  async function createTokenTopupStripe(payload) {
    return request('POST', '/v1/billing/tokens/topup/stripe', { body: payload || {} });
  }

  /** GET /v1/billing/transactions — payment history. */
  async function listBillingTransactions() {
    return request('GET', '/v1/billing/transactions');
  }

  /** POST /v1/billing/sync. */
  async function syncBilling(companyId) {
    return request('POST', '/v1/billing/sync', {
      body: companyId ? { company_id: companyId } : {},
    });
  }

  window.AgixtApi = {
    getSettings,
    refreshSettings,
    getAgentExtensions,
    toggleCommand,
    bulkToggleExtension,
    updateAgentSettings,
    getOAuthProviders,
    getUserOAuthConnections,
    disconnectOAuth,
    getPersona,
    setPersona,
    listTrainingSources,
    learnFile,
    learnUrl,
    deleteSource,
    readFileAsBase64,
    redirectSlug,
    // User identity
    getUser,
    updateUser,
    deleteUserAccount,
    requestEmailVerification,
    changePassword,
    getMfaSetup,
    enableMfa,
    disableMfa,
    resetMfa,
    // Companies
    listCompanies,
    createCompany,
    renameCompany,
    deleteCompany,
    updateCompanyOrder,
    getCompanyMembers,
    removeCompanyMember,
    updateMemberRole,
    getInvitations,
    createInvitation,
    deleteInvitation,
    listDefaultRoles,
    // Personal Access Tokens
    listPersonalAccessTokens,
    createPersonalAccessToken,
    revokePersonalAccessToken,
    regeneratePersonalAccessToken,
    getAvailableTokenScopes,
    getAvailableTokenAgents,
    getAvailableTokenCompanies,
    // Billing
    getBillingEnabled,
    getPricingConfig,
    getTokenBalance,
    getAutoTopupStatus,
    setAutoTopup,
    getPlanLimits,
    createPlanCheckout,
    createPlanTopup,
    createTokenTopupStripe,
    listBillingTransactions,
    syncBilling,
  };
})();
