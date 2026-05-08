/* Repos — desktop extension port of repo-dashboard/templates/index.html.
 *
 * Backend (every call carries `Authorization: Bearer <jwt>`; the AGiXT
 * github extension's router validates the JWT, looks up the user's
 * stored GitHub OAuth token, and proxies to GitHub on their behalf):
 *   GET    /v1/github/repos
 *   POST   /v1/github/repos/refresh
 *   POST   /v1/github/repos/{owner}/{repo}/archive
 *   POST   /v1/github/repos/{owner}/{repo}/enable-security  body: {feature}
 *   GET    /v1/github/repos/{owner}/{repo}/alerts
 *   GET    /v1/github/repos/{owner}/{repo}/issues
 *   GET    /v1/github/repos/{owner}/{repo}/pulls
 *   GET    /v1/github/repos/{owner}/{repo}/pulls/{n}/files
 *   POST   /v1/github/repos/{owner}/{repo}/pulls/{n}/merge      body: {merge_method}
 *   POST   /v1/github/repos/{owner}/{repo}/issues/{n}/fix       (SSE)
 *   POST   /v1/github/repos/{owner}/{repo}/pulls/{n}/review     (SSE)
 *   POST   /v1/github/repos/{owner}/{repo}/fix-vulns            (SSE)
 *   POST   /v1/github/repos/{owner}/{repo}/security-audit       (SSE)
 */
window.AgixtRegisterExtension('repos', {
  mount(container, ctx) {
    const view = new ReposView(container, ctx);
    container._reposView = view;
    view.start();
  },
  unmount() {
    const root = document.querySelector('.chat-screen-main .view-pane[data-view="repos"]');
    if (root && root._reposView) {
      root._reposView.stop();
      root._reposView = null;
    }
  },
});

const STYLE_ID = 'agixt-repos-style';
const STYLE_CSS = `
  .repos-root { padding: 16px 20px 24px; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }
  .repos-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .repos-header h2 { margin: 0; font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .repos-last-updated { color: var(--text-faint); font-size: 12px; }
  .repos-btn { background: #238636; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
  .repos-btn:hover { background: #2ea043; }
  .repos-btn:disabled { opacity: 0.6; cursor: not-allowed; }

  .repos-summary { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .repos-summary-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; flex: 1; min-width: 140px; }
  .repos-summary-card .label { font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .repos-summary-card .value { font-size: 22px; font-weight: 600; }
  .repos-summary-card .value.critical { color: #f85149; }
  .repos-summary-card .value.warning { color: #d29922; }
  .repos-summary-card .value.success { color: #3fb950; }
  .repos-summary-card .value.info { color: var(--accent-blue); }

  .repos-filters { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  .repos-filters .search { background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 6px 10px; border-radius: 6px; font-size: 13px; min-width: 220px; flex: 0 0 auto; }
  .repos-filter-btn { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 5px 10px; border-radius: 16px; cursor: pointer; font-size: 12px; }
  .repos-filter-btn.active { background: var(--accent); border-color: var(--accent); }

  .repos-loading { text-align: center; padding: 40px; color: var(--text-faint); }
  .repos-loading .spinner { display:inline-block; width:18px; height:18px; border:3px solid var(--border); border-top-color: var(--accent-blue); border-radius:50%; animation:repos-spin 0.7s linear infinite; vertical-align:middle; margin-right:8px; }
  @keyframes repos-spin { to { transform: rotate(360deg); } }

  .repos-table-container { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .repos-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .repos-table th { text-align: left; padding: 8px 10px; background: var(--panel-2); border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; font-weight: 600; }
  .repos-table th:hover { background: var(--panel-hover); }
  .repos-table td { padding: 10px; border-bottom: 1px solid #1f242c; vertical-align: top; }
  .repos-table tr.has-vulns { background: rgba(248, 81, 73, 0.04); }
  .repos-table tr.selected { background: rgba(31, 111, 235, 0.08); }
  .repos-table .checkbox-col { width: 28px; }
  .repos-table .count-cell { text-align: center; white-space: nowrap; }
  .repos-table .repo-name { color: var(--text); text-decoration: none; font-weight: 600; }
  .repos-table .repo-name:hover { color: var(--accent-blue); }
  .repos-table .repo-owner { color: var(--text-faint); font-weight: 400; }
  .repos-table .repo-desc { color: var(--text-faint); font-size: 12px; margin-top: 2px; line-height: 1.4; max-width: 480px; }
  .repos-table .lang-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
  .repos-table .visibility-badge { display: inline-block; background: var(--panel-2); color: var(--text-faint); padding: 1px 6px; border-radius: 10px; font-size: 10px; margin-left: 6px; text-transform: uppercase; letter-spacing: 0.4px; }
  .repos-table .zero { color: var(--text-faint); }
  .repos-table .sort-arrow { color: var(--accent-blue); margin-left: 2px; }

  .repos-badge { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-right: 4px; }
  .repos-badge.critical { background: rgba(248,81,73,0.15); color: #f85149; }
  .repos-badge.high { background: rgba(248,81,73,0.10); color: #f85149; }
  .repos-badge.medium { background: rgba(210,153,34,0.15); color: #d29922; }
  .repos-badge.low { background: rgba(63,185,80,0.10); color: #3fb950; }
  .repos-badge.info { background: rgba(88,166,255,0.15); color: var(--accent-blue); }
  .repos-badge.neutral { background: rgba(139,148,158,0.15); color: var(--text-faint); }
  .repos-vuln-pills { display: inline-flex; gap: 4px; flex-wrap: wrap; }

  .repos-badge-disabled { background: rgba(210,153,34,0.10); color: #d29922; border: 1px solid rgba(210,153,34,0.4); padding: 2px 7px; border-radius: 6px; font-size: 11px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
  .repos-badge-disabled:hover { background: rgba(210,153,34,0.18); }
  .repos-security-warnings { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }

  .repos-toggle { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; user-select: none; padding: 2px 6px; border-radius: 4px; }
  .repos-toggle:hover { background: rgba(88,166,255,0.10); }
  .repos-toggle .expand-icon { font-size: 9px; transition: transform 0.15s; color: var(--text-faint); }
  .repos-toggle.expanded .expand-icon { transform: rotate(90deg); }

  .repos-detail-row td { padding: 0 !important; background: #0a0d12 !important; }
  .repos-detail-container { padding: 12px 16px; border-left: 3px solid var(--accent); }
  .repos-filter-bar { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }
  .repos-filter-bar .alert-filter-btn { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 3px 8px; border-radius: 12px; cursor: pointer; font-size: 11px; }
  .repos-filter-bar .alert-filter-btn.active { background: var(--accent); border-color: var(--accent); }

  .repos-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; display: flex; gap: 10px; }
  .repos-card .sev-indicator { width: 4px; border-radius: 4px; flex-shrink: 0; }
  .repos-card .sev-indicator.critical { background: #f85149; }
  .repos-card .sev-indicator.high { background: #f85149; opacity: 0.75; }
  .repos-card .sev-indicator.medium { background: #d29922; }
  .repos-card .sev-indicator.low { background: #3fb950; }
  .repos-card .sev-indicator.unknown { background: #6e7681; }
  .repos-card .body { flex: 1; min-width: 0; }
  .repos-card .header { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
  .repos-card .title { font-weight: 600; flex: 1; min-width: 200px; }
  .repos-card .title a { color: var(--text); text-decoration: none; }
  .repos-card .title a:hover { color: var(--accent-blue); }
  .repos-card .meta { font-size: 11px; color: var(--text-faint); display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }
  .repos-card .meta-label { color: #6e7681; margin-right: 3px; }
  .repos-card .desc { color: var(--text-faint); font-size: 12px; margin-top: 6px; line-height: 1.4; }
  .repos-card .alert-type-badge { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 1px 6px; border-radius: 8px; background: rgba(139,148,158,0.15); color: var(--text-faint); }

  .repos-label-badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 10px; }
  .repos-pr-actions { display: inline-flex; gap: 6px; margin-left: auto; }
  .repos-merge-method { background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 3px 6px; border-radius: 4px; font-size: 11px; }
  .repos-btn-action { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
  .repos-btn-action:hover { background: var(--panel-hover); }
  .repos-btn-action.danger { background: rgba(248,81,73,0.10); color: #f85149; border-color: rgba(248,81,73,0.4); }
  .repos-btn-action.success { background: rgba(63,185,80,0.10); color: #3fb950; border-color: rgba(63,185,80,0.4); }
  .repos-btn-action.merged { background: rgba(63,185,80,0.20); color: #3fb950; }

  .repos-agent-log { background: #0a0d12; border: 1px solid var(--border); border-radius: 4px; margin-top: 8px; max-height: 280px; overflow: auto; display: none; }
  .repos-agent-log.active { display: block; }
  .repos-agent-log-header { padding: 6px 10px; background: var(--panel-2); border-bottom: 1px solid var(--border); font-size: 11px; color: var(--text-faint); display: flex; justify-content: space-between; align-items: center; }
  .repos-agent-log-body { padding: 8px 10px; font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.5; white-space: pre-wrap; }
  .repos-agent-log-line { color: var(--text-faint); }
  .repos-agent-log-line.activity { color: #d29922; }
  .repos-agent-log-line.execution { color: var(--accent-blue); }
  .repos-agent-log-line.error { color: #f85149; }
  .repos-agent-response { padding: 10px; border-top: 1px solid var(--border); line-height: 1.5; font-size: 13px; }
  .repos-status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #6e7681; margin-right: 6px; vertical-align: middle; }
  .repos-status-dot.active { background: #3fb950; box-shadow: 0 0 6px rgba(63,185,80,0.5); animation: repos-pulse 1.2s infinite; }
  @keyframes repos-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }

  .repos-diff-container { background: #0a0d12; border: 1px solid var(--border); border-radius: 4px; margin-top: 8px; overflow: hidden; }
  .repos-diff-file { border-bottom: 1px solid #1f242c; }
  .repos-diff-file:last-child { border-bottom: none; }
  .repos-diff-file-header { padding: 6px 10px; background: var(--panel-2); border-bottom: 1px solid #1f242c; font-family: ui-monospace, monospace; font-size: 11px; color: var(--text-faint); cursor: pointer; display: flex; align-items: center; gap: 8px; }
  .repos-diff-file-header.collapsed .repos-diff-arrow { transform: rotate(-90deg); }
  .repos-diff-arrow { transition: transform 0.15s; font-size: 10px; }
  .repos-diff-file-name { font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .repos-diff-status { font-size: 10px; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.4px; }
  .repos-diff-status.added { background: rgba(63,185,80,0.20); color: #3fb950; }
  .repos-diff-status.removed { background: rgba(248,81,73,0.20); color: #f85149; }
  .repos-diff-status.modified { background: rgba(88,166,255,0.20); color: var(--accent-blue); }
  .repos-diff-status.renamed { background: rgba(210,153,34,0.20); color: #d29922; }
  .repos-additions { color: #3fb950; }
  .repos-deletions { color: #f85149; }
  .repos-diff-patch { background: #0a0d12; padding: 6px 0; max-height: 420px; overflow: auto; font-family: ui-monospace, monospace; font-size: 11px; }
  .repos-diff-patch .line { padding: 0 12px; line-height: 1.45; white-space: pre; }
  .repos-diff-patch .line.add { background: rgba(63,185,80,0.10); color: #56d364; }
  .repos-diff-patch .line.del { background: rgba(248,81,73,0.10); color: #f85149; }
  .repos-diff-patch .line.hunk { color: var(--accent-blue); background: var(--panel-2); }
  .repos-diff-patch .line.context { color: var(--text-faint); }

  .repos-error { color: #f85149; padding: 16px; }
`;

class ReposView {
  constructor(container, ctx) {
    this.container = container;
    this.ctx = ctx;
    this.allRepos = [];
    this.lastUpdated = null;
    this.sort = { key: null, desc: true };
    this.ownerFilter = 'all';
    this.searchTerm = '';
    this.alertsCache = {};
    this.issuesCache = {};
    this.pullsCache = {};
    this.diffCache = {};
    this.expandedRepos = new Set();
    this.expandedIssues = new Set();
    this.expandedPRs = new Set();
    this._aborts = new Set();
  }

  start() {
    if (this.ctx && typeof this.ctx.registerContextProvider === 'function') {
      this.unregisterContextProvider = this.ctx.registerContextProvider(() => this.getContext());
    }
    if (!document.getElementById(STYLE_ID)) {
      const style = document.createElement('style');
      style.id = STYLE_ID;
      style.textContent = STYLE_CSS;
      document.head.appendChild(style);
    }
    this.render();
    this.loadData(false);
  }

  stop() {
    if (typeof this.unregisterContextProvider === 'function') {
      try { this.unregisterContextProvider(); } catch (_) {}
      this.unregisterContextProvider = null;
    }
    for (const a of this._aborts) {
      try { a.abort(); } catch (_) {}
    }
    this._aborts.clear();
  }

  getContext() {
    const filtered = this.getFilteredRepos();
    const source = filtered.length ? filtered : this.allRepos;
    const total = source.length;
    const vulnRepos = source.filter((r) => r.total_vulns > 0).length;
    const totalAlerts = source.reduce((sum, r) => sum + (Number(r.total_vulns) || 0), 0);
    const totalIssues = source.reduce((sum, r) => sum + (Number(r.open_issues) || 0), 0);
    const totalPRs = source.reduce((sum, r) => sum + (Number(r.open_prs) || 0), 0);
    const unprotected = source.filter((r) => !r.dependabot_enabled || !r.code_scanning_enabled).length;
    const lines = [
      'The user is on the GitHub repo security dashboard desktop extension.',
      `Dashboard filter: ${this.ownerFilter || 'all'}`,
      `Search term: ${this.searchTerm || '(none)'}`,
      `Sort: ${this.sort && this.sort.key ? `${this.sort.key} ${this.sort.desc ? 'descending' : 'ascending'}` : 'default'}`,
      `Visible repositories: ${total}`,
      `Repositories with security alerts: ${vulnRepos}`,
      `Total open security alerts: ${totalAlerts}`,
      `Total open issues on visible repos: ${totalIssues}`,
      `Total open PRs on visible repos: ${totalPRs}`,
      `Repositories missing Dependabot or CodeQL: ${unprotected}`,
    ];

    const detailRows = Array.from(this.container.querySelectorAll('.repos-detail-row'))
      .map((row) => ({
        repo: row.dataset.detailFor,
        kind: row.dataset.detailKind,
      }))
      .filter((x) => x.repo && x.kind);

    if (detailRows.length) {
      lines.push('');
      lines.push('Expanded dashboard details:');
      for (const row of detailRows.slice(0, 4)) {
        lines.push(this.describeExpandedDetail(row.repo, row.kind));
      }
    } else {
      const notable = source
        .slice()
        .sort((a, b) => {
          const score = (r) =>
            (Number(r.severity && r.severity.critical) || 0) * 100
            + (Number(r.severity && r.severity.high) || 0) * 40
            + (Number(r.total_vulns) || 0) * 10
            + (!r.dependabot_enabled ? 5 : 0)
            + (!r.code_scanning_enabled ? 5 : 0)
            + (Number(r.open_issues) || 0);
          return score(b) - score(a);
        })
        .filter((r) => (r.total_vulns || r.open_issues || r.open_prs || !r.dependabot_enabled || !r.code_scanning_enabled))
        .slice(0, 5);
      if (notable.length) {
        lines.push('');
        lines.push('Notable repos currently called out by the dashboard:');
        for (const r of notable) lines.push('- ' + this.describeRepoSummary(r));
      }
    }

    lines.push('');
    lines.push('When the user asks about this dashboard, use the repo names, expanded issue/PR/security-alert details, and visible filters above as the current page context. Use GitHub extension commands or dashboard actions for deeper repo, issue, PR, security audit, or vulnerability-fix work when useful.');
    return lines.join('\n');
  }

  describeRepoSummary(r) {
    const parts = [`${r.full_name}`];
    if (r.language) parts.push(`language ${r.language}`);
    if (r.total_vulns) parts.push(`${r.total_vulns} security alert${r.total_vulns === 1 ? '' : 's'}`);
    if (r.severity) {
      const sev = [];
      for (const key of ['critical', 'high', 'medium', 'low']) {
        if (r.severity[key]) sev.push(`${r.severity[key]} ${key}`);
      }
      if (sev.length) parts.push(`severity: ${sev.join(', ')}`);
    }
    if (r.open_issues) parts.push(`${r.open_issues} open issue${r.open_issues === 1 ? '' : 's'}`);
    if (r.open_prs) parts.push(`${r.open_prs} open PR${r.open_prs === 1 ? '' : 's'}`);
    const missing = [];
    if (!r.dependabot_enabled) missing.push('Dependabot');
    if (!r.code_scanning_enabled) missing.push('CodeQL');
    if (missing.length) parts.push(`missing ${missing.join(' and ')}`);
    return parts.join('; ');
  }

  describeExpandedDetail(fullName, kind) {
    if (kind === 'issues') {
      const issues = this.issuesCache[fullName] || [];
      const shown = issues.slice(0, 5).map((issue) =>
        `#${issue.number} ${issue.title || '(untitled)'}`
        + (issue.assignees && issue.assignees.length ? ` assigned to ${issue.assignees.join(', ')}` : ''),
      );
      return `- ${fullName}: issues expanded (${issues.length} loaded). ${shown.join('; ') || 'No open issues in the expanded panel.'}`;
    }
    if (kind === 'prs') {
      const pulls = this.pullsCache[fullName] || [];
      const shown = pulls.slice(0, 5).map((pr) =>
        `#${pr.number} ${pr.title || '(untitled)'}`
        + (pr.draft ? ' [draft]' : '')
        + (pr.changed_files ? `, ${pr.changed_files} changed files` : ''),
      );
      return `- ${fullName}: pull requests expanded (${pulls.length} loaded). ${shown.join('; ') || 'No open pull requests in the expanded panel.'}`;
    }
    if (kind === 'alerts') {
      const alerts = this.alertsCache[fullName] || [];
      const shown = alerts.slice(0, 5).map((alert) => {
        const bits = [
          alert.severity || 'unknown severity',
          alert.type || 'alert',
          alert.summary || alert.package || alert.rule_id || 'untitled alert',
        ];
        if (alert.package) bits.push(`package ${alert.package}`);
        if (alert.patched_version) bits.push(`fix ${alert.patched_version}`);
        return bits.join(' ');
      });
      return `- ${fullName}: security alerts expanded (${alerts.length} loaded). ${shown.join('; ') || 'No open alerts in the expanded panel.'}`;
    }
    return `- ${fullName}: ${kind} details expanded.`;
  }

  // ------------------------------------------------------------------
  // HTTP
  // ------------------------------------------------------------------

  url(path) {
    return new URL(path, this.ctx.serverUrl).toString();
  }

  authHeaders(extra) {
    return Object.assign(
      { Authorization: 'Bearer ' + this.ctx.jwt },
      extra || {},
    );
  }

  async apiGet(path) {
    const resp = await fetch(this.url(path), { headers: this.authHeaders() });
    if (!resp.ok) {
      throw new Error('HTTP ' + resp.status);
    }
    return resp.json();
  }

  async apiPost(path, body) {
    const resp = await fetch(this.url(path), {
      method: 'POST',
      headers: this.authHeaders({ 'Content-Type': 'application/json' }),
      body: body ? JSON.stringify(body) : '{}',
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || data.error || ('HTTP ' + resp.status));
    }
    return data;
  }

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------

  async loadData(forceRefresh) {
    this.setLoading(true);
    try {
      let data;
      if (forceRefresh) {
        await this.apiPost('/v1/github/repos/refresh');
      }
      data = await this.apiGet('/v1/github/repos');
      this.allRepos = (data && data.repos) || [];
      this.lastUpdated = data && data.last_updated;
      this.renderBody();
    } catch (err) {
      this.renderError(err);
    } finally {
      this.setLoading(false);
    }
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  render() {
    this.container.innerHTML = `
      <div class="repos-root">
        <div class="repos-header">
          <!-- Page title comes from the host pane chrome (manifest.layout="framed"). -->
          <div style="display:flex;align-items:center;gap:12px;margin-left:auto;">
            <span class="repos-last-updated" data-role="last-updated"></span>
            <button class="repos-btn" data-role="refresh">Refresh</button>
          </div>
        </div>

        <div class="repos-summary" data-role="summary" style="display:none;"></div>

        <div class="repos-filters" data-role="filters" style="display:none;">
          <input type="text" class="search" data-role="search" placeholder="Search repos..." />
          <button class="repos-filter-btn active" data-filter="all">All</button>
          <button class="repos-filter-btn" data-filter="vuln">⚠️ Vulnerable</button>
          <button class="repos-filter-btn" data-filter="unprotected">🔓 Unprotected</button>
        </div>

        <div data-role="content"></div>
      </div>
    `;

    const root = this.container;
    root.querySelector('[data-role="refresh"]').addEventListener('click', () => this.loadData(true));
    root.querySelector('[data-role="search"]').addEventListener('input', (e) => {
      this.searchTerm = e.target.value.toLowerCase();
      this.renderTable();
    });
    root.querySelectorAll('.repos-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => this.setOwnerFilter(btn.dataset.filter, btn));
    });
  }

  setLoading(loading) {
    const content = this.container.querySelector('[data-role="content"]');
    if (loading) {
      content.innerHTML = '<div class="repos-loading"><div class="spinner"></div>Loading repos from GitHub…</div>';
    }
    const btn = this.container.querySelector('[data-role="refresh"]');
    btn.disabled = !!loading;
    btn.textContent = loading ? 'Refreshing…' : 'Refresh';
  }

  renderError(err) {
    const msg = (err && err.message) || String(err);
    const isAuth = /403|401/.test(msg) || /not connected/i.test(msg);
    const content = this.container.querySelector('[data-role="content"]');
    content.innerHTML = `<div class="repos-error">${
      isAuth
        ? 'GitHub OAuth is not connected for this account. Connect GitHub in Settings → Connections to use this dashboard.'
        : ('Failed to load repos: ' + escapeHtml(msg))
    }</div>`;
  }

  renderBody() {
    const root = this.container;
    root.querySelector('[data-role="summary"]').style.display = 'flex';
    root.querySelector('[data-role="filters"]').style.display = 'flex';

    if (this.lastUpdated) {
      const d = new Date(this.lastUpdated);
      root.querySelector('[data-role="last-updated"]').textContent =
        'Updated: ' + d.toLocaleTimeString();
    }

    this.buildOwnerFilters();
    this.renderTable();
  }

  buildOwnerFilters() {
    const bar = this.container.querySelector('[data-role="filters"]');
    bar.querySelectorAll('.repos-filter-btn[data-owner]').forEach((b) => b.remove());
    const owners = [...new Set(this.allRepos.map((r) => r.owner))].sort();
    for (const owner of owners) {
      const btn = document.createElement('button');
      btn.className = 'repos-filter-btn';
      btn.textContent = owner;
      btn.dataset.filter = owner;
      btn.dataset.owner = '1';
      btn.addEventListener('click', () => this.setOwnerFilter(owner, btn));
      bar.appendChild(btn);
    }
  }

  setOwnerFilter(filter, btn) {
    this.ownerFilter = filter;
    this.container.querySelectorAll('.repos-filter-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    this.renderTable();
  }

  getFilteredRepos() {
    let repos = this.allRepos.slice();
    const s = this.searchTerm;
    if (s) {
      repos = repos.filter((r) =>
        r.full_name.toLowerCase().includes(s) ||
        (r.description || '').toLowerCase().includes(s) ||
        (r.language || '').toLowerCase().includes(s),
      );
    }
    if (this.ownerFilter === 'vuln') {
      repos = repos.filter((r) => r.total_vulns > 0);
    } else if (this.ownerFilter === 'unprotected') {
      repos = repos.filter((r) => !r.dependabot_enabled || !r.code_scanning_enabled);
    } else if (this.ownerFilter !== 'all') {
      repos = repos.filter((r) => r.owner === this.ownerFilter);
    }
    return repos;
  }

  renderSummary(repos) {
    const sum = this.container.querySelector('[data-role="summary"]');
    const total = repos.length;
    const vuln = repos.filter((r) => r.total_vulns > 0).length;
    const totalAlerts = repos.reduce((s, r) => s + r.total_vulns, 0);
    const totalIssues = repos.reduce((s, r) => s + r.open_issues, 0);
    const totalPRs = repos.reduce((s, r) => s + r.open_prs, 0);
    const unprotected = repos.filter((r) => !r.dependabot_enabled || !r.code_scanning_enabled).length;
    sum.innerHTML = `
      <div class="repos-summary-card"><div class="label">Total Repos</div><div class="value info">${total}</div></div>
      <div class="repos-summary-card"><div class="label">Repos w/ Vulns</div><div class="value critical">${vuln}</div></div>
      <div class="repos-summary-card"><div class="label">Total Alerts</div><div class="value warning">${totalAlerts}</div></div>
      <div class="repos-summary-card"><div class="label">Open Issues</div><div class="value">${totalIssues}</div></div>
      <div class="repos-summary-card"><div class="label">Open PRs</div><div class="value success">${totalPRs}</div></div>
      <div class="repos-summary-card"><div class="label">Unprotected</div><div class="value warning">${unprotected}</div></div>
    `;
  }

  renderTable() {
    let repos = this.getFilteredRepos();
    if (this.sort.key) {
      repos.sort((a, b) => {
        let av = a[this.sort.key]; let bv = b[this.sort.key];
        if (typeof av === 'string') av = av.toLowerCase();
        if (typeof bv === 'string') bv = bv.toLowerCase();
        if (av < bv) return this.sort.desc ? 1 : -1;
        if (av > bv) return this.sort.desc ? -1 : 1;
        return 0;
      });
    }
    this.renderSummary(repos);

    const content = this.container.querySelector('[data-role="content"]');
    if (repos.length === 0) {
      content.innerHTML = '<div class="repos-loading">No repos match your filters.</div>';
      return;
    }

    content.innerHTML = `
      <div class="repos-table-container">
        <table class="repos-table">
          <thead>
            <tr>
              <th data-sort="full_name">Repository <span class="sort-arrow" data-arrow="full_name"></span></th>
              <th data-sort="language">Language <span class="sort-arrow" data-arrow="language"></span></th>
              <th data-sort="open_issues">Issues <span class="sort-arrow" data-arrow="open_issues"></span></th>
              <th data-sort="open_prs">PRs <span class="sort-arrow" data-arrow="open_prs"></span></th>
              <th data-sort="total_vulns">Security Alerts <span class="sort-arrow" data-arrow="total_vulns"></span></th>
              <th data-sort="stars">Stars <span class="sort-arrow" data-arrow="stars"></span></th>
              <th data-sort="updated_at">Updated <span class="sort-arrow" data-arrow="updated_at"></span></th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody data-role="tbody"></tbody>
        </table>
      </div>
    `;
    content.querySelectorAll('th[data-sort]').forEach((th) =>
      th.addEventListener('click', () => this.sortBy(th.dataset.sort)),
    );
    if (this.sort.key) {
      const arrow = content.querySelector(`[data-arrow="${this.sort.key}"]`);
      if (arrow) arrow.textContent = this.sort.desc ? '▼' : '▲';
    }

    const tbody = content.querySelector('[data-role="tbody"]');
    for (const r of repos) {
      tbody.appendChild(this.makeRepoRow(r));
    }
  }

  sortBy(key) {
    if (this.sort.key === key) {
      this.sort.desc = !this.sort.desc;
    } else {
      this.sort.key = key;
      this.sort.desc = true;
    }
    this.renderTable();
  }

  makeRepoRow(r) {
    const tr = document.createElement('tr');
    if (r.total_vulns > 0) tr.classList.add('has-vulns');
    tr.dataset.repo = r.full_name;
    const langColor = LANG_COLORS[r.language] || '#8b949e';

    let pills = [];
    if (r.severity.critical > 0) pills.push(`<span class="repos-badge critical">${r.severity.critical} Critical</span>`);
    if (r.severity.high > 0) pills.push(`<span class="repos-badge high">${r.severity.high} High</span>`);
    if (r.severity.medium > 0) pills.push(`<span class="repos-badge medium">${r.severity.medium} Medium</span>`);
    if (r.severity.low > 0) pills.push(`<span class="repos-badge low">${r.severity.low} Low</span>`);
    if (r.code_scanning_count > 0) pills.push(`<span class="repos-badge info">${r.code_scanning_count} Code</span>`);
    if (r.advisory_count > 0) pills.push(`<span class="repos-badge neutral">${r.advisory_count} Advisory</span>`);
    if (pills.length === 0 && r.dependabot_count > 0) pills.push(`<span class="repos-badge medium">${r.dependabot_count} Dependabot</span>`);
    let vulnHtml = pills.length ? `<div class="repos-vuln-pills">${pills.join('')}</div>` : '<span class="zero">None</span>';

    let warnings = [];
    if (!r.dependabot_enabled) warnings.push(`<button class="repos-badge-disabled" data-enable="dependabot">⚠ Dependabot off</button>`);
    if (!r.code_scanning_enabled) warnings.push(`<button class="repos-badge-disabled" data-enable="code_scanning">⚠ CodeQL off</button>`);
    const warningsHtml = warnings.length ? `<div class="repos-security-warnings">${warnings.join('')}</div>` : '';

    const visibilityBadge = r.visibility !== 'public' ? `<span class="visibility-badge">${r.visibility}</span>` : '';
    const forkBadge = r.fork ? '<span class="visibility-badge">fork</span>' : '';

    const issuesHtml = r.open_issues > 0
      ? `<div class="repos-toggle" data-toggle="issues"><span>${r.open_issues}</span><span class="expand-icon">▶</span></div>`
      : '<span class="zero">0</span>';
    const prsHtml = r.open_prs > 0
      ? `<div class="repos-toggle" data-toggle="prs"><span>${r.open_prs}</span><span class="expand-icon">▶</span></div>`
      : '<span class="zero">0</span>';
    const alertsHtml = r.total_vulns > 0
      ? `<div class="repos-toggle" data-toggle="alerts">${vulnHtml}<span class="expand-icon">▶</span></div>${warningsHtml}`
      : `${vulnHtml}${warningsHtml}`;

    tr.innerHTML = `
      <td>
        <a class="repo-name" href="${escapeAttr(r.html_url)}" target="_blank">
          <span class="repo-owner">${escapeHtml(r.owner)}/</span>${escapeHtml(r.name)}
        </a>${visibilityBadge}${forkBadge}
        ${r.description ? `<div class="repo-desc">${escapeHtml(r.description)}</div>` : ''}
      </td>
      <td>${r.language ? `<span class="lang-dot" style="background:${langColor}"></span>${escapeHtml(r.language)}` : '<span class="zero">—</span>'}</td>
      <td class="count-cell">${issuesHtml}</td>
      <td class="count-cell">${prsHtml}</td>
      <td>${alertsHtml}</td>
      <td class="count-cell">${r.stars > 0 ? `⭐ ${r.stars}` : '<span class="zero">0</span>'}</td>
      <td style="white-space:nowrap;color: var(--text-faint);">${escapeHtml(r.updated_at_display || '')}</td>
      <td class="count-cell"><button class="repos-btn-action" data-action="audit">🛡️ Audit</button></td>
    `;

    // Wire up row interactions.
    const issuesToggle = tr.querySelector('[data-toggle="issues"]');
    if (issuesToggle) issuesToggle.addEventListener('click', () => this.toggleIssues(r, issuesToggle));
    const prsToggle = tr.querySelector('[data-toggle="prs"]');
    if (prsToggle) prsToggle.addEventListener('click', () => this.togglePulls(r, prsToggle));
    const alertsToggle = tr.querySelector('[data-toggle="alerts"]');
    if (alertsToggle) alertsToggle.addEventListener('click', () => this.toggleAlerts(r, alertsToggle));
    tr.querySelectorAll('[data-enable]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.enableSecurity(r, btn.dataset.enable, btn);
      });
    });
    tr.querySelector('[data-action="audit"]').addEventListener(
      'click',
      (e) => {
        e.stopPropagation();
        this.startAgentStream({
          path: `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/security-audit`,
          host: e.target,
          label: 'Security audit',
        });
      },
    );

    return tr;
  }

  // ------------------------------------------------------------------
  // Inline expansions
  // ------------------------------------------------------------------

  async toggleAlerts(r, toggleEl) {
    await this._toggleDetail(r, toggleEl, 'alerts',
      () => this.alertsCache[r.full_name],
      async () => {
        const data = await this.apiGet(`/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/alerts`);
        this.alertsCache[r.full_name] = data.alerts || [];
        return this.alertsCache[r.full_name];
      },
      (container, alerts) => this.renderAlertDetails(container, r, alerts),
    );
  }

  async toggleIssues(r, toggleEl) {
    await this._toggleDetail(r, toggleEl, 'issues',
      () => this.issuesCache[r.full_name],
      async () => {
        const data = await this.apiGet(`/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/issues`);
        this.issuesCache[r.full_name] = data.issues || [];
        return this.issuesCache[r.full_name];
      },
      (container, issues) => this.renderIssueDetails(container, r, issues),
    );
  }

  async togglePulls(r, toggleEl) {
    await this._toggleDetail(r, toggleEl, 'prs',
      () => this.pullsCache[r.full_name],
      async () => {
        const data = await this.apiGet(`/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/pulls`);
        this.pullsCache[r.full_name] = data.pulls || [];
        return this.pullsCache[r.full_name];
      },
      (container, pulls) => this.renderPRDetails(container, r, pulls),
    );
  }

  /** Generic expand/collapse helper used by alerts/issues/prs. */
  async _toggleDetail(r, toggleEl, kind, peekCache, fetcher, render) {
    const row = toggleEl.closest('tr');
    const next = row.nextElementSibling;
    if (next && next.classList.contains('repos-detail-row') && next.dataset.detailKind === kind && next.dataset.detailFor === r.full_name) {
      next.remove();
      toggleEl.classList.remove('expanded');
      return;
    }
    // Collapse any other detail row first so multiple don't stack confusingly.
    if (next && next.classList.contains('repos-detail-row') && next.dataset.detailFor === r.full_name) {
      next.remove();
      toggleEl.parentElement.querySelectorAll('.repos-toggle').forEach((t) => t.classList.remove('expanded'));
    }
    toggleEl.classList.add('expanded');

    const colCount = row.children.length;
    const detail = document.createElement('tr');
    detail.className = 'repos-detail-row';
    detail.dataset.detailKind = kind;
    detail.dataset.detailFor = r.full_name;
    detail.innerHTML = `<td colspan="${colCount}"><div class="repos-detail-container"><div class="repos-loading"><div class="spinner"></div>Loading…</div></div></td>`;
    row.after(detail);
    const container = detail.querySelector('.repos-detail-container');

    try {
      let data = peekCache();
      if (!data) data = await fetcher();
      render(container, data);
    } catch (err) {
      container.innerHTML = `<div class="repos-error">Failed to load: ${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  renderAlertDetails(container, r, alerts) {
    if (!alerts || alerts.length === 0) {
      container.innerHTML = '<div style="color: var(--text-faint);padding:8px;">No open alerts</div>';
      return;
    }
    const types = [...new Set(alerts.map((a) => a.type))];
    const sevOrder = ['critical', 'high', 'medium', 'low'];
    const typeLabels = { dependabot: 'Dependabot', code_scanning: 'Code Scanning', advisory: 'Advisory' };

    let bar = '<div class="repos-filter-bar">';
    bar += `<button class="alert-filter-btn active" data-filter="all">All (${alerts.length})</button>`;
    types.forEach((t) => {
      const c = alerts.filter((a) => a.type === t).length;
      bar += `<button class="alert-filter-btn" data-filter="type:${t}">${typeLabels[t] || t} (${c})</button>`;
    });
    sevOrder.forEach((s) => {
      const c = alerts.filter((a) => (a.severity || '').toLowerCase() === s).length;
      if (c > 0) bar += `<button class="alert-filter-btn" data-filter="sev:${s}">${cap(s)} (${c})</button>`;
    });
    bar += `<a href="https://github.com/${enc(r.owner)}/${enc(r.name)}/security" target="_blank" style="font-size:11px;color: var(--accent-blue);margin-left:auto;text-decoration:none;">View on GitHub →</a>`;
    bar += `<button class="repos-btn-action danger" data-action="fix-vulns">🤖 Fix All Vulns</button>`;
    bar += `<button class="repos-btn-action" data-action="audit">🛡️ AI Audit</button>`;
    bar += '</div>';

    const list = '<div class="repos-list">' + alerts.map((a) => this.renderAlertCard(a)).join('') + '</div>';
    container.innerHTML = bar + list;

    container.querySelectorAll('.alert-filter-btn').forEach((b) => {
      b.addEventListener('click', () => {
        container.querySelectorAll('.alert-filter-btn').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
        const f = b.dataset.filter;
        container.querySelectorAll('.repos-card').forEach((card) => {
          if (f === 'all') card.style.display = '';
          else if (f.startsWith('type:')) card.style.display = card.dataset.type === f.slice(5) ? '' : 'none';
          else if (f.startsWith('sev:')) card.style.display = card.dataset.sev === f.slice(4) ? '' : 'none';
        });
      });
    });
    container.querySelector('[data-action="fix-vulns"]').addEventListener('click', (e) =>
      this.startAgentStream({
        path: `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/fix-vulns`,
        host: e.target, label: 'Fixing vulnerabilities',
      }),
    );
    container.querySelector('[data-action="audit"]').addEventListener('click', (e) =>
      this.startAgentStream({
        path: `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/security-audit`,
        host: e.target, label: 'Security audit',
      }),
    );
  }

  renderAlertCard(a) {
    const sev = (a.severity || '').toLowerCase() || 'unknown';
    const sevClass = ['critical', 'high', 'medium', 'low'].includes(sev) ? sev : 'unknown';
    const typeLabels = { dependabot: 'Dependabot', code_scanning: 'Code Scan', advisory: 'Advisory' };
    let meta = '';
    const m = (k, label, val) => {
      if (val === undefined || val === null || val === '') return;
      meta += `<span><span class="meta-label">${label}</span>${escapeHtml(String(val))}</span>`;
    };
    m('package', 'pkg:', a.package);
    m('ecosystem', 'eco:', a.ecosystem);
    m('vulnerable_range', 'vuln:', a.vulnerable_range);
    if (a.patched_version) meta += `<span><span class="meta-label">fix:</span><strong style="color:#3fb950;">${escapeHtml(a.patched_version)}</strong></span>`;
    m('manifest_path', 'file:', a.manifest_path);
    m('scope', 'scope:', a.scope);
    m('relationship', 'dep:', a.relationship);
    if (a.cvss_score) meta += `<span><span class="meta-label">CVSS:</span><strong>${escapeHtml(String(a.cvss_score))}</strong></span>`;
    if (a.cve) meta += `<span>${escapeHtml(a.cve)}</span>`;
    if (a.ghsa) meta += `<span>${escapeHtml(a.ghsa)}</span>`;
    m('state', 'state:', a.state);
    m('reporter', 'reporter:', a.reporter);
    if (a.tool) {
      let t = a.tool;
      if (a.tool_version) t += ' v' + a.tool_version;
      meta += `<span><span class="meta-label">tool:</span>${escapeHtml(t)}</span>`;
    }
    m('rule_id', 'rule:', a.rule_id);
    m('location', 'at:', a.location);
    if (a.classifications && a.classifications.length) meta += `<span><span class="meta-label">class:</span>${a.classifications.map(escapeHtml).join(', ')}</span>`;
    if (a.rule_tags && a.rule_tags.length) meta += `<span><span class="meta-label">tags:</span>${a.rule_tags.slice(0, 5).map(escapeHtml).join(', ')}</span>`;

    const cwesHtml = a.cwes && a.cwes.length
      ? `<div class="meta"><span><span class="meta-label">CWE:</span>${a.cwes.map(escapeHtml).join(' | ')}</span></div>`
      : '';
    const titleLink = a.html_url
      ? `<a href="${escapeAttr(a.html_url)}" target="_blank">${escapeHtml(a.summary || 'Alert')}</a>`
      : escapeHtml(a.summary || 'Alert');
    return `<div class="repos-card" data-type="${escapeAttr(a.type)}" data-sev="${escapeAttr(sev)}">
      <div class="sev-indicator ${sevClass}"></div>
      <div class="body">
        <div class="header">
          <span class="repos-badge ${sevClass === 'unknown' ? 'neutral' : sevClass}">${escapeHtml(sev)}</span>
          <span class="alert-type-badge">${escapeHtml(typeLabels[a.type] || a.type)}</span>
          <span class="title">${titleLink}</span>
        </div>
        ${meta ? `<div class="meta">${meta}</div>` : ''}
        ${cwesHtml}
        ${a.description ? `<div class="desc">${escapeHtml(String(a.description).slice(0, 300))}</div>` : ''}
      </div>
    </div>`;
  }

  renderIssueDetails(container, r, issues) {
    if (!issues || issues.length === 0) {
      container.innerHTML = '<div style="color: var(--text-faint);padding:8px;">No open issues</div>';
      return;
    }
    container.innerHTML = `
      <div class="repos-filter-bar">
        <span style="font-size:12px;color: var(--text-faint);font-weight:600;">${issues.length} open issue${issues.length !== 1 ? 's' : ''}</span>
        <a href="https://github.com/${enc(r.owner)}/${enc(r.name)}/issues" target="_blank" style="font-size:11px;color: var(--accent-blue);margin-left:auto;text-decoration:none;">View on GitHub →</a>
      </div>
      <div class="repos-list" data-role="issues-list"></div>
    `;
    const list = container.querySelector('[data-role="issues-list"]');
    for (const issue of issues) list.appendChild(this.makeIssueCard(r, issue));
  }

  makeIssueCard(r, issue) {
    const card = document.createElement('div');
    card.className = 'repos-card';
    card.innerHTML = `
      <div class="sev-indicator unknown"></div>
      <div class="body">
        <div class="header">
          <span class="title"><a href="${escapeAttr(issue.html_url)}" target="_blank">#${issue.number} ${escapeHtml(issue.title)}</a></span>
          ${(issue.labels || []).map(labelHtml).join(' ')}
          <button class="repos-btn-action" data-action="fix-issue" style="margin-left:auto;">🤖 Fix Issue</button>
        </div>
        <div class="meta">
          ${issue.user ? `<span><span class="meta-label">by</span>${escapeHtml(issue.user)}</span>` : ''}
          ${issue.comments ? `<span>💬 ${issue.comments}</span>` : ''}
          ${issue.assignees && issue.assignees.length ? `<span><span class="meta-label">→</span>${issue.assignees.map(escapeHtml).join(', ')}</span>` : ''}
          ${issue.milestone ? `<span>🎯 ${escapeHtml(issue.milestone)}</span>` : ''}
        </div>
        ${issue.body ? `<div class="desc">${escapeHtml(String(issue.body).slice(0, 300))}</div>` : ''}
      </div>
    `;
    card.querySelector('[data-action="fix-issue"]').addEventListener('click', (e) =>
      this.startAgentStream({
        path: `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/issues/${issue.number}/fix`,
        host: e.target, label: `Fix issue #${issue.number}`,
      }),
    );
    return card;
  }

  renderPRDetails(container, r, pulls) {
    if (!pulls || pulls.length === 0) {
      container.innerHTML = '<div style="color: var(--text-faint);padding:8px;">No open pull requests</div>';
      return;
    }
    container.innerHTML = `
      <div class="repos-filter-bar">
        <span style="font-size:12px;color: var(--text-faint);font-weight:600;">${pulls.length} open PR${pulls.length !== 1 ? 's' : ''}</span>
        <a href="https://github.com/${enc(r.owner)}/${enc(r.name)}/pulls" target="_blank" style="font-size:11px;color: var(--accent-blue);margin-left:auto;text-decoration:none;">View on GitHub →</a>
      </div>
      <div class="repos-list" data-role="pr-list"></div>
    `;
    const list = container.querySelector('[data-role="pr-list"]');
    for (const pr of pulls) list.appendChild(this.makePRCard(r, pr));
  }

  makePRCard(r, pr) {
    const card = document.createElement('div');
    card.className = 'repos-card';
    const draftBadge = pr.draft ? '<span class="repos-badge neutral">Draft</span>' : '';
    const stats = pr.changed_files > 0
      ? `<span style="font-size:11px;color: var(--text-faint);">${pr.changed_files} file${pr.changed_files !== 1 ? 's' : ''} <span class="repos-additions">+${pr.additions}</span> <span class="repos-deletions">-${pr.deletions}</span></span>`
      : '';
    card.innerHTML = `
      <div class="sev-indicator unknown"></div>
      <div class="body">
        <div class="header">
          <span class="title"><a href="${escapeAttr(pr.html_url)}" target="_blank">#${pr.number} ${escapeHtml(pr.title)}</a></span>
          ${draftBadge}
          ${(pr.labels || []).map(labelHtml).join(' ')}
          ${stats}
          <div class="repos-pr-actions">
            <button class="repos-btn-action" data-action="diff">📄 Diff</button>
            <button class="repos-btn-action" data-action="review">🤖 Review</button>
            <select class="repos-merge-method" data-role="merge-method">
              <option value="squash">Squash</option>
              <option value="merge">Merge</option>
              <option value="rebase">Rebase</option>
            </select>
            <button class="repos-btn-action success" data-action="merge">✅ Merge</button>
          </div>
        </div>
        <div class="meta">
          ${pr.user ? `<span><span class="meta-label">by</span>${escapeHtml(pr.user)}</span>` : ''}
          ${pr.head_ref ? `<span><span class="meta-label">branch:</span>${escapeHtml(pr.head_ref)} → ${escapeHtml(pr.base_ref || '')}</span>` : ''}
          ${pr.comments ? `<span>💬 ${pr.comments}</span>` : ''}
        </div>
        ${pr.body ? `<div class="desc">${escapeHtml(String(pr.body).slice(0, 300))}</div>` : ''}
        <div data-role="diff-host"></div>
      </div>
    `;
    const diffHost = card.querySelector('[data-role="diff-host"]');
    card.querySelector('[data-action="diff"]').addEventListener('click', (e) =>
      this.toggleDiff(r, pr, e.target, diffHost),
    );
    card.querySelector('[data-action="review"]').addEventListener('click', (e) =>
      this.startAgentStream({
        path: `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/pulls/${pr.number}/review`,
        host: e.target, label: `Review PR #${pr.number}`,
      }),
    );
    card.querySelector('[data-action="merge"]').addEventListener('click', () =>
      this.mergePR(r, pr, card),
    );
    return card;
  }

  // ------------------------------------------------------------------
  // Mutations
  // ------------------------------------------------------------------

  async enableSecurity(r, feature, btn) {
    btn.disabled = true;
    btn.textContent = 'Enabling…';
    try {
      await this.apiPost(
        `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/enable-security`,
        { feature },
      );
      const repo = this.allRepos.find((x) => x.full_name === r.full_name);
      if (repo) {
        if (feature === 'dependabot') repo.dependabot_enabled = true;
        if (feature === 'code_scanning') repo.code_scanning_enabled = true;
      }
      this.renderTable();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = '⚠ ' + (feature === 'dependabot' ? 'Dependabot off' : 'CodeQL off');
      alert('Enable failed: ' + (err.message || String(err)));
    }
  }

  async mergePR(r, pr, card) {
    const select = card.querySelector('[data-role="merge-method"]');
    const method = select ? select.value : 'merge';
    if (!confirm(`Merge PR #${pr.number} on ${r.full_name} using ${method}?`)) return;
    const btn = card.querySelector('[data-action="merge"]');
    btn.disabled = true;
    btn.textContent = '⏳ Merging…';
    try {
      await this.apiPost(
        `/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/pulls/${pr.number}/merge`,
        { merge_method: method },
      );
      btn.textContent = '✅ Merged';
      btn.classList.add('merged');
      // Drop card; update local data + table cell.
      card.style.opacity = '0.4';
      setTimeout(() => card.remove(), 250);
      const repo = this.allRepos.find((x) => x.full_name === r.full_name);
      if (repo) repo.open_prs = Math.max(0, repo.open_prs - 1);
      delete this.pullsCache[r.full_name];
      const cellToggle = this.container.querySelector(`tr[data-repo="${escapeAttr(r.full_name)}"] [data-toggle="prs"] span`);
      if (cellToggle && repo) cellToggle.textContent = repo.open_prs;
    } catch (err) {
      btn.disabled = false;
      btn.textContent = '✅ Merge';
      alert('Merge failed: ' + (err.message || String(err)));
    }
  }

  async toggleDiff(r, pr, btn, host) {
    if (host.children.length > 0 && btn.classList.contains('active')) {
      host.innerHTML = '';
      btn.classList.remove('active');
      return;
    }
    btn.classList.add('active');
    const cacheKey = `${r.full_name}/${pr.number}`;
    let files = this.diffCache[cacheKey];
    if (!files) {
      host.innerHTML = '<div class="repos-loading"><div class="spinner"></div>Loading diff…</div>';
      try {
        const data = await this.apiGet(`/v1/github/repos/${enc(r.owner)}/${enc(r.name)}/pulls/${pr.number}/files`);
        files = data.files || [];
        this.diffCache[cacheKey] = files;
      } catch (err) {
        host.innerHTML = `<div class="repos-error">Failed to load diff: ${escapeHtml(err.message || String(err))}</div>`;
        btn.classList.remove('active');
        return;
      }
    }
    host.innerHTML = renderDiffHtml(files);
    host.querySelectorAll('.repos-diff-file-header').forEach((h) =>
      h.addEventListener('click', () => {
        const patch = h.nextElementSibling;
        if (!patch) return;
        const collapsed = patch.style.display === 'none';
        patch.style.display = collapsed ? '' : 'none';
        h.classList.toggle('collapsed', !collapsed);
      }),
    );
  }

  // ------------------------------------------------------------------
  // SSE agent streaming
  // ------------------------------------------------------------------

  /** Fetch an SSE endpoint and render activity / response into a panel
   *  inserted right after the host element. The host is the button the
   *  user clicked, so each repo / PR / issue gets its own log. */
  async startAgentStream({ path, host, label }) {
    if (!host) return;
    if (host.dataset.agentBusy) return;
    host.dataset.agentBusy = '1';
    const originalText = host.textContent;
    host.disabled = true;
    host.textContent = '⏳ ' + (label || 'Working…');

    const log = document.createElement('div');
    log.className = 'repos-agent-log active';
    log.innerHTML = `
      <div class="repos-agent-log-header">
        <span><span class="repos-status-dot active"></span>${escapeHtml(label || 'XT Agent')}</span>
        <span data-role="log-count"></span>
      </div>
      <div class="repos-agent-log-body" data-role="log-body"></div>
      <div class="repos-agent-response" data-role="response" style="display:none;"></div>
    `;
    // Place the log right after the .repos-card or row that hosts the button.
    const anchor = host.closest('.repos-card') || host.closest('tr') || host.parentElement;
    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(log, anchor.nextSibling);
    } else {
      this.container.appendChild(log);
    }
    const body = log.querySelector('[data-role="log-body"]');
    const countEl = log.querySelector('[data-role="log-count"]');
    const responseEl = log.querySelector('[data-role="response"]');
    let lineCount = 0;
    let responseText = '';

    const append = (cls, content) => {
      const div = document.createElement('div');
      div.className = 'repos-agent-log-line ' + cls;
      div.textContent = content;
      body.appendChild(div);
      lineCount++;
      countEl.textContent = `${lineCount} events`;
      body.scrollTop = body.scrollHeight;
    };

    const finish = () => {
      host.dataset.agentBusy = '';
      host.disabled = false;
      host.textContent = originalText;
      const dot = log.querySelector('.repos-status-dot');
      if (dot) dot.classList.remove('active');
    };

    const ac = new AbortController();
    this._aborts.add(ac);
    try {
      const resp = await fetch(this.url(path), {
        method: 'POST',
        headers: this.authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
        body: '{}',
        signal: ac.signal,
      });
      if (!resp.ok) {
        const text = await resp.text();
        append('error', `HTTP ${resp.status}: ${text.slice(0, 500)}`);
        finish();
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // Split on SSE event boundary (blank line).
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const dataLines = chunk.split('\n').filter((l) => l.startsWith('data: '));
          for (const dl of dataLines) {
            const raw = dl.slice(6);
            if (raw === '[DONE]') break;
            let evt;
            try { evt = JSON.parse(raw); } catch (_) { continue; }
            const t = evt.type || '';
            const c = evt.content || '';
            if (t === 'response' && c) {
              responseText += c;
              responseEl.style.display = '';
              responseEl.textContent = responseText;
            } else if (t === 'activity' || t === 'new_activity') {
              append('activity', c);
            } else if (t === 'execution') {
              append('execution', c.length > 400 ? c.slice(0, 400) + '…' : c);
            } else if (t === 'error') {
              append('error', c);
            } else if (t === 'status') {
              append('', c);
            } else if (t === 'done') {
              // SSE stream finished.
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') append('error', err.message || String(err));
    } finally {
      this._aborts.delete(ac);
      finish();
    }
  }
}

// ---- helpers --------------------------------------------------------------

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function escapeAttr(s) { return escapeHtml(s); }
function enc(s) { return encodeURIComponent(s); }
function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function labelHtml(l) {
  const color = l.color || 'ccc';
  const lum = parseInt(color, 16);
  const fg = lum > 0x7fffff ? '#000' : '#fff';
  return `<span class="repos-label-badge" style="background:#${escapeAttr(color)};color:${fg};">${escapeHtml(l.name || '')}</span>`;
}

function renderDiffHtml(files) {
  if (!files || files.length === 0) {
    return '<div style="color: var(--text-faint);padding:12px;">No file changes</div>';
  }
  const sum = files.reduce((s, f) => { s.add += f.additions || 0; s.del += f.deletions || 0; return s; }, { add: 0, del: 0 });
  let html = '<div class="repos-diff-container">';
  html += `<div style="padding:6px 10px;background: var(--panel-2); border-bottom: 1px solid var(--border);font-size:11px;color: var(--text-faint);">${files.length} file${files.length !== 1 ? 's' : ''} changed <span class="repos-additions">+${sum.add}</span> <span class="repos-deletions">-${sum.del}</span></div>`;
  for (const f of files) {
    const status = f.status || 'modified';
    html += '<div class="repos-diff-file">';
    html += `<div class="repos-diff-file-header"><span class="repos-diff-arrow">▼</span><span class="repos-diff-status ${escapeAttr(status)}">${escapeHtml(status)}</span><span class="repos-diff-file-name">${escapeHtml(f.filename || '')}</span><span><span class="repos-additions">+${f.additions || 0}</span> <span class="repos-deletions">-${f.deletions || 0}</span></span></div>`;
    html += '<div class="repos-diff-patch">';
    if (f.patch) {
      for (const line of f.patch.split('\n')) {
        let cls = 'context';
        if (line.startsWith('@@')) cls = 'hunk';
        else if (line.startsWith('+') && !line.startsWith('+++')) cls = 'add';
        else if (line.startsWith('-') && !line.startsWith('---')) cls = 'del';
        html += `<div class="line ${cls}">${escapeHtml(line) || '&nbsp;'}</div>`;
      }
    } else {
      html += '<div class="line context" style="color: var(--text-faint);">No patch available — too large.</div>';
    }
    html += '</div></div>';
  }
  html += '</div>';
  return html;
}

const LANG_COLORS = {
  Python: '#3572A5', JavaScript: '#f1e05a', TypeScript: '#3178c6',
  Rust: '#dea584', Go: '#00ADD8', Java: '#b07219', 'C++': '#f34b7d',
  C: '#555555', 'C#': '#178600', Ruby: '#701516', Shell: '#89e051',
  HTML: '#e34c26', CSS: '#563d7c', Dart: '#00B4AB', Kotlin: '#A97BFF',
  Swift: '#F05138', PHP: '#4F5D95', 'Jupyter Notebook': '#DA5B0B',
  Vue: '#41b883', Dockerfile: '#384d54', Makefile: '#427819',
};
