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

  /** PATCH /v1/companies/{id} — update full company details (name, status,
   *  address, phone_number, email, website, city, state, zip_code, country,
   *  notes, icon_url). All fields optional; only provided keys are updated. */
  async function updateCompany(companyId, patch) {
    return request('PATCH', '/v1/companies/' + encodeURIComponent(companyId), {
      body: patch || {},
    });
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

  /** GET /v1/default-roles — system default roles with their scope lists. */
  async function listDefaultRoles() {
    const data = await request('GET', '/v1/default-roles');
    return (data && (data.roles || data.default_roles)) || data || [];
  }

  // ----- Custom roles & scopes ------------------------------------------

  /** GET /v1/scopes — all scopes available in the system. */
  async function listScopes() {
    const data = await request('GET', '/v1/scopes');
    return (data && (data.scopes || data)) || [];
  }

  /** GET /v1/roles?company_id=... — custom roles for a company. */
  async function listCustomRoles(companyId) {
    const path = companyId
      ? '/v1/roles?company_id=' + encodeURIComponent(companyId)
      : '/v1/roles';
    const data = await request('GET', path);
    return (data && data.roles) || [];
  }

  /** POST /v1/roles?company_id=... — create a custom role.
   *  payload: {name, friendly_name, description, priority, scope_ids: [...]}. */
  async function createCustomRole(companyId, payload) {
    const path = companyId
      ? '/v1/roles?company_id=' + encodeURIComponent(companyId)
      : '/v1/roles';
    return request('POST', path, { body: payload || {} });
  }

  /** PUT /v1/roles/{id} — update a custom role.
   *  payload: {friendly_name?, description?, priority?, is_active?, scope_ids?}. */
  async function updateCustomRole(roleId, payload) {
    return request('PUT', '/v1/roles/' + encodeURIComponent(roleId), {
      body: payload || {},
    });
  }

  /** DELETE /v1/roles/{id}. */
  async function deleteCustomRole(roleId) {
    return request('DELETE', '/v1/roles/' + encodeURIComponent(roleId));
  }

  /** GET /v1/user/{user_id}/custom-roles?company_id=...
   *  Returns the custom roles assigned to a user in a company. */
  async function getUserCustomRoles(userId, companyId) {
    const path = '/v1/user/' + encodeURIComponent(userId) + '/custom-roles' +
      (companyId ? '?company_id=' + encodeURIComponent(companyId) : '');
    const data = await request('GET', path);
    return Array.isArray(data) ? data : (data && data.custom_roles) || [];
  }

  /** POST /v1/user/custom-role?company_id=... — assign a custom role.
   *  body: {user_id, custom_role_id}. */
  async function assignUserCustomRole(companyId, userId, customRoleId) {
    const path = companyId
      ? '/v1/user/custom-role?company_id=' + encodeURIComponent(companyId)
      : '/v1/user/custom-role';
    return request('POST', path, {
      body: { user_id: userId, custom_role_id: customRoleId },
    });
  }

  /** DELETE /v1/user/{user_id}/custom-role/{custom_role_id}?company_id=... */
  async function removeUserCustomRole(companyId, userId, customRoleId) {
    const path = '/v1/user/' + encodeURIComponent(userId) +
      '/custom-role/' + encodeURIComponent(customRoleId) +
      (companyId ? '?company_id=' + encodeURIComponent(companyId) : '');
    return request('DELETE', path);
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

  // ----- Webhooks ---------------------------------------------------------
  // The webhook endpoints sit under `/api/webhooks/...` (not /v1/) — see
  // AGiXT/agixt/endpoints/Webhook.py and the web SDK methods around line
  // 1619 of web/lib/sdk.ts.

  async function listOutgoingWebhooks() {
    const data = await request('GET', '/api/webhooks/outgoing');
    return Array.isArray(data) ? data : (data && data.webhooks) || [];
  }

  async function createOutgoingWebhook(payload) {
    return request('POST', '/api/webhooks/outgoing', { body: payload || {} });
  }

  async function updateOutgoingWebhook(webhookId, payload) {
    return request('PUT', '/api/webhooks/outgoing/' + encodeURIComponent(webhookId), { body: payload || {} });
  }

  async function deleteOutgoingWebhook(webhookId) {
    return request('DELETE', '/api/webhooks/outgoing/' + encodeURIComponent(webhookId));
  }

  async function testOutgoingWebhook(webhookId, testPayload) {
    return request('POST', '/api/webhooks/test/' + encodeURIComponent(webhookId), {
      body: { webhook_id: webhookId, test_payload: testPayload },
    });
  }

  async function listIncomingWebhooks() {
    const data = await request('GET', '/api/webhooks/incoming');
    return Array.isArray(data) ? data : (data && data.webhooks) || [];
  }

  async function createIncomingWebhook(payload) {
    return request('POST', '/api/webhooks/incoming', { body: payload || {} });
  }

  async function updateIncomingWebhook(webhookId, payload) {
    return request('PUT', '/api/webhooks/incoming/' + encodeURIComponent(webhookId), { body: payload || {} });
  }

  async function deleteIncomingWebhook(webhookId) {
    return request('DELETE', '/api/webhooks/incoming/' + encodeURIComponent(webhookId));
  }

  async function getWebhookEventTypes() {
    try {
      const data = await request('GET', '/api/webhooks/event-types');
      return (data && data.event_types) || [];
    } catch (_) { return []; }
  }

  // ----- Chains -----------------------------------------------------------

  /** GET /v1/chains — list of {id, chainName, description}. */
  async function listChains() {
    const data = await request('GET', '/v1/chains');
    return Array.isArray(data) ? data : [];
  }

  /** GET /v1/chain/{id} — server returns {chainName: {description, steps}}.
   *  We unwrap to {chainName, description, steps} for callers. */
  async function getChain(chainId) {
    const data = await request('GET', '/v1/chain/' + encodeURIComponent(chainId));
    if (!data || typeof data !== 'object') return null;
    const keys = Object.keys(data);
    if (keys.length === 1 && data[keys[0]] && typeof data[keys[0]] === 'object') {
      const inner = data[keys[0]];
      return {
        chainName: keys[0],
        description: inner.description || '',
        steps: Array.isArray(inner.steps) ? inner.steps : [],
      };
    }
    return {
      chainName: data.chainName || data.name || '',
      description: data.description || '',
      steps: Array.isArray(data.steps) ? data.steps : [],
    };
  }

  /** GET /v1/chain/{id}/args — array of arg names propagated from the
   *  chain's prompts/commands. Used to surface external inputs the chain
   *  accepts when a user runs it. */
  async function getChainArgs(chainId) {
    try {
      const data = await request('GET', '/v1/chain/' + encodeURIComponent(chainId) + '/args');
      return Array.isArray(data) ? data : [];
    } catch (_) { return []; }
  }

  /** POST /v1/chain — body {chain_name, description}. Creates an empty
   *  chain; description is optional but stored when present. */
  async function createChain(chainName, description) {
    return request('POST', '/v1/chain', {
      body: {
        chain_name: chainName,
        description: description || '',
      },
    });
  }

  /** PUT /v1/chain/{id} — rename and/or update description. The endpoint
   *  takes both fields on the same payload (`{new_name, description}`),
   *  so callers can pass `description` as the existing value when only
   *  renaming, or pass the existing name to update only the description. */
  async function renameChain(chainId, newName, description) {
    const body = { new_name: newName };
    if (description !== undefined) body.description = description;
    return request('PUT', '/v1/chain/' + encodeURIComponent(chainId), { body });
  }

  /** DELETE /v1/chain/{id}. */
  async function deleteChain(chainId) {
    return request('DELETE', '/v1/chain/' + encodeURIComponent(chainId));
  }

  /** POST /v1/chain/import — body {chain_name, steps}. The server creates
   *  the chain (if missing) and writes the steps verbatim. */
  async function importChain(chainName, steps) {
    return request('POST', '/v1/chain/import', {
      body: { chain_name: chainName, steps: steps || [] },
    });
  }

  /** POST /v1/chain/{id}/step — body {step_number, agent_id, prompt_type,
   *  prompt}. Note the API uses agent_id on writes but agent_name on reads. */
  async function addChainStep(chainId, stepNumber, agentId, promptType, prompt) {
    return request('POST', '/v1/chain/' + encodeURIComponent(chainId) + '/step', {
      body: {
        step_number: stepNumber,
        agent_id: agentId,
        prompt_type: promptType,
        prompt: prompt || {},
      },
    });
  }

  /** PUT /v1/chain/{id}/step/{n}. */
  async function updateChainStep(chainId, stepNumber, agentId, promptType, prompt) {
    return request('PUT', '/v1/chain/' + encodeURIComponent(chainId) + '/step/' + encodeURIComponent(stepNumber), {
      body: {
        step_number: stepNumber,
        agent_id: agentId,
        prompt_type: promptType,
        prompt: prompt || {},
      },
    });
  }

  /** PATCH /v1/chain/{id}/step/move. */
  async function moveChainStep(chainId, oldStepNumber, newStepNumber) {
    return request('PATCH', '/v1/chain/' + encodeURIComponent(chainId) + '/step/move', {
      body: { old_step_number: oldStepNumber, new_step_number: newStepNumber },
    });
  }

  /** DELETE /v1/chain/{id}/step/{n}. */
  async function deleteChainStep(chainId, stepNumber) {
    return request('DELETE', '/v1/chain/' + encodeURIComponent(chainId) + '/step/' + encodeURIComponent(stepNumber));
  }

  /** POST /v1/chain/{idOrName}/run — body {prompt, agent_override,
   *  all_responses, from_step, chain_args}. */
  async function runChain(chainIdOrName, opts) {
    opts = opts || {};
    return request('POST', '/v1/chain/' + encodeURIComponent(chainIdOrName) + '/run', {
      body: {
        prompt: opts.user_input || '',
        agent_override: opts.agent_id || '',
        all_responses: !!opts.all_responses,
        from_step: Number(opts.from_step || 1),
        chain_args: opts.chain_args || {},
      },
    });
  }

  /** GET /v1/chain/{id}/responses — chain run history. */
  async function getChainResponses(chainId) {
    try {
      const data = await request('GET', '/v1/chain/' + encodeURIComponent(chainId) + '/responses');
      return (data && data.chain) || data || null;
    } catch (_) { return null; }
  }

  // ----- Agents / prompts / commands (helpers used by the chain editor) ---

  /** GET /v1/agent — list of {id, name, status, default, company_id}.
   *  The Rust `list_agents` invoke returns the same shape, but the JS
   *  helper is useful when we don't have Tauri (browser preview mode) and
   *  for cache parity inside chains.js. */
  async function listAgents() {
    const data = await request('GET', '/v1/agent');
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.agents)) return data.agents;
    if (data && typeof data === 'object') {
      // Legacy {name: {settings...}} shape.
      return Object.entries(data).map(([name, val]) => ({
        id: (val && val.id) || '',
        name,
        ...(val || {}),
      }));
    }
    return [];
  }

  /** GET /v1/prompts?prompt_category=Default — array of prompt rows. */
  async function listPrompts(category) {
    const cat = category || 'Default';
    const data = await request('GET', '/v1/prompts?prompt_category=' + encodeURIComponent(cat));
    return (data && data.prompts) || data || [];
  }

  /** GET /v1/prompt/categories. */
  async function listPromptCategories() {
    try {
      const data = await request('GET', '/v1/prompt/categories');
      return (data && data.categories) || data || [];
    } catch (_) { return [{ name: 'Default' }]; }
  }

  /** GET /v1/prompt/{id}/args — list of arg names referenced in the prompt
   *  template. */
  async function getPromptArgs(promptId) {
    try {
      const data = await request('GET', '/v1/prompt/' + encodeURIComponent(promptId) + '/args');
      const args = (data && data.prompt_args) || data || [];
      return Array.isArray(args) ? args : Object.keys(args || {});
    } catch (_) { return []; }
  }

  /** GET /v1/prompt/{id} — full prompt detail. The server returns the
   *  prompt's body under one of a few keys depending on version
   *  (`content`, `prompt`, `prompt_content`); we normalize so callers
   *  always read `.content`. */
  async function getPrompt(promptId) {
    const data = await request('GET', '/v1/prompt/' + encodeURIComponent(promptId));
    if (!data) return null;
    const content = data.content != null ? data.content
      : data.prompt != null ? data.prompt
      : data.prompt_content != null ? data.prompt_content
      : '';
    return {
      id: data.id || data.prompt_id || promptId,
      name: data.name || data.prompt_name || '',
      content: typeof content === 'string' ? content : String(content || ''),
      category: data.category || data.prompt_category || 'Default',
    };
  }

  /** POST /v1/prompt — body {prompt_name, prompt, prompt_category}. */
  async function createPrompt(promptName, promptBody, category) {
    return request('POST', '/v1/prompt', {
      body: {
        prompt_name: promptName,
        prompt: promptBody || '',
        prompt_category: category || 'Default',
      },
    });
  }

  /** PUT /v1/prompt/{id} — update prompt body (the AGiXT API uses `prompt`
   *  for the body). */
  async function updatePrompt(promptId, promptBody) {
    return request('PUT', '/v1/prompt/' + encodeURIComponent(promptId), {
      body: { prompt: promptBody || '' },
    });
  }

  /** PATCH /v1/prompt/{id} — rename ({prompt_name}). */
  async function renamePrompt(promptId, newName) {
    return request('PATCH', '/v1/prompt/' + encodeURIComponent(promptId), {
      body: { prompt_name: newName },
    });
  }

  /** DELETE /v1/prompt/{id}. */
  async function deletePrompt(promptId) {
    return request('DELETE', '/v1/prompt/' + encodeURIComponent(promptId));
  }

  /** POST /v1/agent/{id}/prompt — run a saved prompt with `prompt_args`
   *  filled in. Returns the agent's response text. */
  async function runPrompt(agentId, promptName, promptArgs) {
    const data = await request('POST', '/v1/agent/' + encodeURIComponent(agentId) + '/prompt', {
      body: {
        prompt_name: promptName,
        prompt_args: promptArgs || {},
      },
    });
    if (data && typeof data === 'object' && 'response' in data) return data.response;
    return data;
  }

  /** GET /v1/extensions/{command}/args — map of arg_name -> default value
   *  (or list of names depending on server version). */
  async function getCommandArgs(commandName) {
    try {
      const data = await request('GET', '/v1/extensions/' + encodeURIComponent(commandName) + '/args');
      const raw = (data && data.command_args) != null ? data.command_args : data;
      if (Array.isArray(raw)) return raw;
      if (raw && typeof raw === 'object') return Object.keys(raw);
      return [];
    } catch (_) { return []; }
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
    updateCompany,
    deleteCompany,
    updateCompanyOrder,
    getCompanyMembers,
    removeCompanyMember,
    updateMemberRole,
    getInvitations,
    createInvitation,
    deleteInvitation,
    listDefaultRoles,
    listScopes,
    listCustomRoles,
    createCustomRole,
    updateCustomRole,
    deleteCustomRole,
    getUserCustomRoles,
    assignUserCustomRole,
    removeUserCustomRole,
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
    // Chains
    listChains,
    getChain,
    getChainArgs,
    createChain,
    renameChain,
    deleteChain,
    importChain,
    addChainStep,
    updateChainStep,
    moveChainStep,
    deleteChainStep,
    runChain,
    getChainResponses,
    // Agents / prompts / commands (chain editor helpers)
    listAgents,
    listPrompts,
    listPromptCategories,
    getPromptArgs,
    getCommandArgs,
    // Prompt library
    getPrompt,
    createPrompt,
    updatePrompt,
    renamePrompt,
    deletePrompt,
    runPrompt,
    // Webhooks
    listOutgoingWebhooks,
    createOutgoingWebhook,
    updateOutgoingWebhook,
    deleteOutgoingWebhook,
    testOutgoingWebhook,
    listIncomingWebhooks,
    createIncomingWebhook,
    updateIncomingWebhook,
    deleteIncomingWebhook,
    getWebhookEventTypes,
  };
})();
