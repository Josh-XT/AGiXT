/* Marketplace — desktop surface for AGiXT app packages and add-ons.
 *
 * Lives in the framed extension pane (manifest.layout="framed"): refresh
 * + search migrate into the host header chrome via `ctx.setHeaderActions`,
 * the body owns its own scroll and renders a credits hero, two
 * site/base-app summary tiles, then categorized app cards with status
 * badges, price/plans/modules meta, scope chips, and Subscribe / Use
 * credits actions. */
(function () {
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
    }

  const ICONS = {
    wallet:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9H5a2 2 0 0 1-2-2Z"/><path d="M3 7a2 2 0 0 1 2-2h11v4"/><circle cx="17" cy="14" r="1.2"/></svg>',
    site:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 3 2.5 15 0 18"/><path d="M12 3c-2.5 3-2.5 15 0 18"/></svg>',
    box:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 8 12 3 3 8v8l9 5 9-5V8Z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/></svg>',
    check:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-11"/></svg>',
    lock:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    spark:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v4"/><path d="M12 17v4"/><path d="m4.9 4.9 2.8 2.8"/><path d="m16.3 16.3 2.8 2.8"/><path d="M3 12h4"/><path d="M17 12h4"/><path d="m4.9 19.1 2.8-2.8"/><path d="m16.3 7.7 2.8-2.8"/></svg>',
    refresh:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 0 1-15.4 6.4L3 16"/><path d="M3 12a9 9 0 0 1 15.4-6.4L21 8"/><path d="M3 21v-5h5"/><path d="M21 3v5h-5"/></svg>',
    card:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/><path d="M7 15h3"/></svg>',
    coins:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="9" cy="7" rx="6" ry="3"/><path d="M3 7v5c0 1.7 2.7 3 6 3s6-1.3 6-3V7"/><path d="M3 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/><path d="M15 11.5c1.8-.4 6-1.3 6-3.5 0-1.7-2.7-3-6-3"/></svg>',
    store:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16l-1 13H5L4 7Z"/><path d="M7 7a5 5 0 0 1 10 0"/></svg>',
  };

  function injectStyles() {
    if (document.getElementById('agx-marketplace-styles')) return;
    const css = `
      .agxm { display: flex; flex-direction: column; gap: 22px; padding: 18px 22px 28px; color: var(--text); }
      .agxm-loading { padding: 60px 4px; text-align: center; color: var(--text-faint); font-size: 13px; }
      .agxm-loading-spinner { display: inline-block; width: 22px; height: 22px; border: 2.5px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: agxm-spin .7s linear infinite; vertical-align: middle; margin-right: 10px; }
      @keyframes agxm-spin { to { transform: rotate(360deg); } }
      .agxm-alert { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); color: var(--text-dim); font-size: 12.5px; line-height: 1.45; }
      .agxm-alert-icon { width: 18px; height: 18px; flex-shrink: 0; margin-top: 1px; opacity: .85; }
      .agxm-error { border-color: rgba(220, 60, 80, 0.45); background: rgba(220, 60, 80, 0.12); color: #ffb4ba; }

      /* Hero strip — credits card spans wide, with site/base-app stacked
         on the right. Drops to a single column under ~560px. */
      .agxm-hero { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 12px; }
      @media (max-width: 720px) { .agxm-hero { grid-template-columns: 1fr; } }
      .agxm-hero-credits {
        position: relative; overflow: hidden;
        display: flex; align-items: center; gap: 16px;
        padding: 18px 20px;
        border: 1px solid var(--border); border-radius: 14px;
        background:
          linear-gradient(135deg, color-mix(in srgb, var(--accent) 18%, transparent), color-mix(in srgb, var(--accent-2, var(--accent)) 10%, transparent)),
          var(--panel-2);
      }
      .agxm-hero-credits::after {
        content: ""; position: absolute; inset: 0; pointer-events: none;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
        border-radius: inherit;
      }
      .agxm-hero-icon {
        flex-shrink: 0; width: 46px; height: 46px;
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: 12px;
        background: color-mix(in srgb, var(--accent) 22%, transparent);
        color: #fff;
      }
      .agxm-hero-icon svg { width: 22px; height: 22px; }
      .agxm-hero-body { min-width: 0; }
      .agxm-hero-label { color: var(--text-dim); font-size: 11.5px; text-transform: uppercase; letter-spacing: .08em; }
      .agxm-hero-value { margin-top: 2px; font-size: 26px; font-weight: 700; letter-spacing: -0.01em; color: var(--text); line-height: 1.1; }
      .agxm-hero-sub { margin-top: 4px; color: var(--text-faint); font-size: 12px; }

      .agxm-hero-side { display: flex; flex-direction: column; gap: 12px; }
      .agxm-tile {
        display: flex; align-items: center; gap: 12px;
        padding: 13px 14px;
        border: 1px solid var(--border); border-radius: 12px;
        background: var(--panel-2);
        min-width: 0;
      }
      .agxm-tile-icon {
        flex-shrink: 0; width: 34px; height: 34px;
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: 9px;
        background: color-mix(in srgb, var(--accent) 14%, var(--panel));
        color: var(--text-dim);
      }
      .agxm-tile-icon svg { width: 17px; height: 17px; }
      .agxm-tile-body { min-width: 0; }
      .agxm-tile-k { color: var(--text-faint); font-size: 10.5px; text-transform: uppercase; letter-spacing: .07em; }
      .agxm-tile-v { margin-top: 2px; color: var(--text); font-weight: 650; font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

      /* Category section. */
      .agxm-section { display: flex; flex-direction: column; gap: 12px; }
      .agxm-section-head { display: flex; align-items: center; gap: 10px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }
      .agxm-section-head h3 { margin: 0; font-size: 14px; font-weight: 650; color: var(--text); letter-spacing: 0; }
      .agxm-section-count {
        display: inline-flex; align-items: center; justify-content: center;
        min-width: 22px; height: 20px; padding: 0 7px;
        border-radius: 999px;
        background: color-mix(in srgb, var(--accent) 14%, var(--panel));
        color: var(--text-dim); font-size: 11px; font-weight: 600;
      }
      .agxm-section-spacer { flex: 1; }

      /* App grid + card. */
      .agxm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
      .agxm-card {
        position: relative;
        display: flex; flex-direction: column; gap: 12px;
        min-height: 232px;
        padding: 16px;
        border: 1px solid var(--border); border-radius: 12px;
        background: var(--panel-2);
        transition: border-color .14s ease, background .14s ease, transform .12s ease, box-shadow .14s ease;
      }
      .agxm-card:hover {
        border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
        background: color-mix(in srgb, var(--accent) 4%, var(--panel-2));
        transform: translateY(-1px);
        box-shadow: 0 6px 22px rgba(0,0,0,0.22);
      }
      .agxm-card.is-active { border-color: rgba(94, 210, 143, .32); }
      .agxm-card.is-active:hover { border-color: rgba(94, 210, 143, .55); }

      .agxm-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
      .agxm-card-title { min-width: 0; flex: 1; }
      .agxm-card-title h4 { margin: 0; font-size: 14.5px; font-weight: 650; line-height: 1.25; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .agxm-publisher { margin-top: 3px; color: var(--text-faint); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

      .agxm-badge {
        display: inline-flex; align-items: center; gap: 4px;
        height: 22px; padding: 0 9px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: var(--panel);
        color: var(--text-dim);
        font-size: 11px; font-weight: 600; white-space: nowrap;
      }
      .agxm-badge svg { width: 11px; height: 11px; }
      .agxm-badge-active { border-color: rgba(94, 210, 143, .42); background: rgba(94, 210, 143, .12); color: #72d99d; }
      .agxm-badge-available { border-color: color-mix(in srgb, var(--accent) 38%, var(--border)); background: color-mix(in srgb, var(--accent) 12%, var(--panel)); color: var(--accent); }
      .agxm-badge-trial  { border-color: rgba(255, 183, 116, .42); background: rgba(255, 183, 116, .12); color: #ffbd7e; }
      .agxm-badge-pastdue { border-color: rgba(248, 81, 73, .45); background: rgba(248, 81, 73, .14); color: #ff8a86; }
      .agxm-badge-base   { border-color: rgba(107, 123, 255, .42); background: rgba(107, 123, 255, .14); color: #aab2ff; }

      .agxm-card-summary { color: var(--text-dim); font-size: 12.5px; line-height: 1.5; min-height: 38px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }

      .agxm-meta {
        display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
        border-radius: 9px; overflow: hidden;
        background: var(--border);
      }
      .agxm-meta-item { padding: 9px 10px; background: var(--panel); min-width: 0; }
      .agxm-meta-k { color: var(--text-faint); font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; }
      .agxm-meta-v { margin-top: 2px; color: var(--text); font-weight: 650; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

      .agxm-scopes { display: flex; flex-wrap: wrap; gap: 5px; min-height: 22px; }
      .agxm-scope {
        border: 1px solid var(--border); border-radius: 6px;
        padding: 1px 7px;
        color: var(--text-faint); font-size: 10.5px;
        background: var(--panel);
      }

      .agxm-actions { display: flex; gap: 7px; margin-top: auto; }
      .agxm-btn {
        appearance: none;
        display: inline-flex; align-items: center; justify-content: center; gap: 6px;
        min-height: 34px; padding: 0 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel);
        color: var(--text);
        font: inherit; font-size: 12.5px; font-weight: 600;
        cursor: pointer;
        transition: background .12s ease, border-color .12s ease, color .12s ease, filter .12s ease;
      }
      .agxm-btn svg { width: 14px; height: 14px; }
      .agxm-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--text); background: color-mix(in srgb, var(--accent) 10%, var(--panel)); }
      .agxm-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
      .agxm-btn-primary {
        flex: 1;
        background: linear-gradient(135deg, var(--accent), var(--accent-2, var(--accent)));
        border-color: transparent;
        color: #fff;
      }
      .agxm-btn-primary:hover:not(:disabled) { filter: brightness(1.07); }
      .agxm-btn-ghost { padding: 0 10px; color: var(--text-dim); }
      .agxm-btn:disabled { opacity: .55; cursor: not-allowed; }
      .agxm-btn-active { background: rgba(94, 210, 143, .14); color: #72d99d; border-color: rgba(94, 210, 143, .42); flex: 1; }
      .agxm-btn-active:hover:not(:disabled) { background: rgba(94, 210, 143, .14); }

      .agxm-empty {
        display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
        min-height: 240px;
        padding: 32px;
        border: 1px dashed var(--border); border-radius: 12px;
        background: var(--panel-2);
        text-align: center;
      }
      .agxm-empty-icon { width: 36px; height: 36px; color: var(--text-faint); }
      .agxm-empty-title { color: var(--text); font-size: 14px; font-weight: 650; }
      .agxm-empty-sub { color: var(--text-faint); font-size: 12px; max-width: 360px; line-height: 1.45; }

      /* Header chrome controls (live inside the host pane header). */
      .agxm-iconbtn {
        width: 30px; height: 30px; border-radius: 7px;
        border: 1px solid var(--border);
        background: var(--panel-2); color: var(--text-dim);
        display: inline-flex; align-items: center; justify-content: center;
        cursor: pointer;
        transition: background .12s ease, color .12s ease, border-color .12s ease;
      }
      .agxm-iconbtn svg { width: 15px; height: 15px; }
      .agxm-iconbtn:hover:not(:disabled) { background: var(--panel); color: var(--text); border-color: var(--accent); }
      .agxm-iconbtn:disabled { opacity: .55; cursor: not-allowed; }
      .agxm-iconbtn.is-spinning svg { animation: agxm-spin 0.8s linear infinite; }

      .agxm-search {
        flex: 0 1 260px; min-width: 140px;
        padding: 6px 11px; font-size: 12.5px;
        background: var(--panel-2); color: var(--text);
        border: 1px solid var(--border); border-radius: 7px;
      }
      .agxm-search:focus { outline: none; border-color: var(--accent); }
      .agxm-search::placeholder { color: var(--text-faint); }
    `;
    const tag = document.createElement('style');
    tag.id = 'agx-marketplace-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  function MarketplaceView(container, ctx) {
    this.container = container;
    this.ctx = ctx || {};
    this.data = null;
    this.error = null;
    this.loading = true;
    this.busy = null;
    this.searchTerm = '';
    this._headerEls = null;
  }

  MarketplaceView.prototype.start = function () {
    injectStyles();
    this._mountHeader();
    this.render();
    this.refresh();
  };

  MarketplaceView.prototype.stop = function () {
    this.container.innerHTML = '';
  };

  MarketplaceView.prototype._mountHeader = function () {
    if (!this.ctx || !this.ctx.framed || typeof this.ctx.setHeaderActions !== 'function') return;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'agxm-search';
    search.placeholder = 'Search apps…';
    search.addEventListener('input', (e) => {
      this.searchTerm = (e.target.value || '').toLowerCase();
      this.render();
    });

    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'agxm-iconbtn';
    refresh.title = 'Refresh';
    refresh.innerHTML = ICONS.refresh;
    refresh.addEventListener('click', () => this.refresh());

    this._headerEls = { search, refresh };
    this.ctx.setHeaderActions(search, refresh);
  };

  MarketplaceView.prototype._setRefreshSpinning = function (spinning) {
    if (this._headerEls && this._headerEls.refresh) {
      this._headerEls.refresh.classList.toggle('is-spinning', !!spinning);
      this._headerEls.refresh.disabled = !!spinning;
    }
  };

  MarketplaceView.prototype.fetchJson = function (path, opts) {
    opts = opts || {};
    if (this.ctx && typeof this.ctx.fetchJson === 'function') return this.ctx.fetchJson(path, opts);
    if (window.AgixtSession && typeof window.AgixtSession.request === 'function') return window.AgixtSession.request(path, opts);
    const url = new URL(path, this.ctx.serverUrl || window.location.origin).toString();
    const init = {
      method: opts.method || 'GET',
      headers: Object.assign(
        this.ctx.jwt ? { Authorization: 'Bearer ' + this.ctx.jwt } : {},
        opts.json != null ? { 'Content-Type': 'application/json' } : {}
      ),
    };
    if (opts.json != null) init.body = JSON.stringify(opts.json);
    return fetch(url, init).then(async (resp) => {
      const text = await resp.text();
      const data = text ? JSON.parse(text) : null;
      if (!resp.ok) throw new Error((data && data.detail) || ('HTTP ' + resp.status));
      return data;
    });
  };

  MarketplaceView.prototype.refresh = async function () {
    this.loading = true;
    this._setRefreshSpinning(true);
    this.render();
    try {
      const query = this.ctx.companyId ? '?company_id=' + encodeURIComponent(this.ctx.companyId) : '';
      this.data = await this.fetchJson('/v1/marketplace/apps' + query);
      this.error = null;
    } catch (err) {
      this.error = err;
      this.data = null;
    }
    this.loading = false;
    this._setRefreshSpinning(false);
    this.render();
  };

  MarketplaceView.prototype.checkout = async function (app) {
    this.busy = app.app_slug + ':checkout';
    this.render();
    try {
      const query = this.ctx.companyId ? '?company_id=' + encodeURIComponent(this.ctx.companyId) : '';
      const result = await this.fetchJson('/v1/marketplace/apps/' + encodeURIComponent(app.app_slug) + '/checkout' + query, { method: 'POST' });
      if (result && result.checkout_url) window.location.href = result.checkout_url;
    } catch (err) {
      this.error = err;
    }
    this.busy = null;
    this.render();
  };

  MarketplaceView.prototype.activateCredits = async function (app) {
    this.busy = app.app_slug + ':credits';
    this.render();
    try {
      const query = this.ctx.companyId ? '?company_id=' + encodeURIComponent(this.ctx.companyId) : '';
      await this.fetchJson('/v1/marketplace/apps/' + encodeURIComponent(app.app_slug) + '/activate-with-credits' + query, { method: 'POST' });
      await this.refresh();
      return;
    } catch (err) {
      this.error = err;
    }
    this.busy = null;
    this.render();
  };

  MarketplaceView.prototype._statusBadge = function (app) {
    if (app.is_base_app) return { label: 'Base app', cls: 'agxm-badge-base', icon: ICONS.spark };
    if (app.is_entitled) {
      if (app.entitlement_status === 'included') return { label: 'Included', cls: 'agxm-badge-active', icon: ICONS.check };
      if (app.entitlement_status === 'trialing') return { label: 'Trialing', cls: 'agxm-badge-trial', icon: ICONS.spark };
      return { label: 'Active', cls: 'agxm-badge-active', icon: ICONS.check };
    }
    if (app.entitlement_status === 'past_due') return { label: 'Past due', cls: 'agxm-badge-pastdue', icon: ICONS.lock };
    return { label: 'Available', cls: 'agxm-badge-available', icon: ICONS.box };
  };

  MarketplaceView.prototype.render = function () {
    const root = document.createElement('div');
    root.className = 'agxm';

    if (this.loading && !this.data) {
      root.innerHTML = '<div class="agxm-loading"><span class="agxm-loading-spinner"></span>Loading marketplace…</div>';
      this.container.replaceChildren(root);
      return;
    }

    if (this.error) {
      const alert = document.createElement('div');
      alert.className = 'agxm-alert agxm-error';
      alert.innerHTML = '<span>' + esc(this.error.message || this.error) + '</span>';
      root.appendChild(alert);
    }

    const data = this.data || {};
    root.appendChild(this._renderHero(data));

    const apps = Array.isArray(data.apps) ? data.apps : [];
    const filtered = apps.filter((app) => this._matchesSearch(app));

    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'agxm-empty';
      empty.innerHTML = `
        <div class="agxm-empty-icon">${ICONS.store}</div>
        <div class="agxm-empty-title">${apps.length ? 'No apps match that search' : 'No marketplace apps yet'}</div>
        <div class="agxm-empty-sub">${apps.length ? 'Try clearing the search or refreshing.' : 'Add marketplace metadata to extension hub pricing files to list apps here.'}</div>
      `;
      root.appendChild(empty);
      this.container.replaceChildren(root);
      return;
    }

    const categories = Array.from(new Set(filtered.map((app) => app.category || 'Apps'))).sort();
    categories.forEach((category) => {
      const section = document.createElement('section');
      section.className = 'agxm-section';
      const inCat = filtered.filter((app) => (app.category || 'Apps') === category);

      const head = document.createElement('div');
      head.className = 'agxm-section-head';
      head.innerHTML = `
        <h3>${esc(category)}</h3>
        <span class="agxm-section-count">${inCat.length}</span>
      `;
      section.appendChild(head);

      const grid = document.createElement('div');
      grid.className = 'agxm-grid';
      inCat.forEach((app) => grid.appendChild(this.card(app)));
      section.appendChild(grid);

      root.appendChild(section);
    });

    this.container.replaceChildren(root);
  };

  MarketplaceView.prototype._matchesSearch = function (app) {
    if (!this.searchTerm) return true;
    const haystack = [
      app.display_name,
      app.app_name,
      app.app_slug,
      app.publisher,
      app.summary,
      app.description,
      app.category,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return haystack.includes(this.searchTerm);
  };

  MarketplaceView.prototype._renderHero = function (data) {
    const hero = document.createElement('div');
    hero.className = 'agxm-hero';

    const credits = Number(data.credit_balance_usd || 0);
    const creditsLabel = credits.toLocaleString(undefined, { style: 'currency', currency: 'USD' });

    const creditCard = document.createElement('div');
    creditCard.className = 'agxm-hero-credits';
    creditCard.innerHTML = `
      <div class="agxm-hero-icon">${ICONS.wallet}</div>
      <div class="agxm-hero-body">
        <div class="agxm-hero-label">Company credits</div>
        <div class="agxm-hero-value">${esc(creditsLabel)}</div>
        <div class="agxm-hero-sub">${data.credits_enabled ? 'Available to activate apps below' : 'Credit activation is disabled for this site'}</div>
      </div>
    `;
    hero.appendChild(creditCard);

    const side = document.createElement('div');
    side.className = 'agxm-hero-side';
    side.innerHTML = `
      <div class="agxm-tile">
        <div class="agxm-tile-icon">${ICONS.site}</div>
        <div class="agxm-tile-body">
          <div class="agxm-tile-k">Site</div>
          <div class="agxm-tile-v">${esc(data.site_slug || '—')}</div>
        </div>
      </div>
      <div class="agxm-tile">
        <div class="agxm-tile-icon">${ICONS.box}</div>
        <div class="agxm-tile-body">
          <div class="agxm-tile-k">Base app</div>
          <div class="agxm-tile-v">${esc(data.base_app_slug || '—')}</div>
        </div>
      </div>
    `;
    hero.appendChild(side);

    return hero;
  };

  MarketplaceView.prototype.card = function (app) {
    const card = document.createElement('article');
    card.className = 'agxm-card';
    const active = !!app.is_entitled || app.is_base_app;
    if (active) card.classList.add('is-active');

    const status = this._statusBadge(app);
    const price = app.price_summary && app.price_summary.label ? app.price_summary.label : 'Custom';
    const modules = (app.desktop_extension_ids || app.included_extensions || []).length;
    const tiers = (app.tiers || []).length;
    const scopes = (app.required_scopes || []).slice(0, 4);

    card.innerHTML = `
      <div class="agxm-card-head">
        <div class="agxm-card-title">
          <h4>${esc(app.display_name || app.app_name || app.app_slug)}</h4>
          <div class="agxm-publisher">${esc(app.publisher || '')}</div>
        </div>
        <span class="agxm-badge ${status.cls}">${status.icon}${esc(status.label)}</span>
      </div>
      <div class="agxm-card-summary">${esc(app.summary || app.description || 'No description provided.')}</div>
      <div class="agxm-meta">
        <div class="agxm-meta-item"><div class="agxm-meta-k">Price</div><div class="agxm-meta-v">${esc(price)}</div></div>
        <div class="agxm-meta-item"><div class="agxm-meta-k">Plans</div><div class="agxm-meta-v">${esc(tiers || 'Custom')}</div></div>
        <div class="agxm-meta-item"><div class="agxm-meta-k">Modules</div><div class="agxm-meta-v">${esc(modules)}</div></div>
      </div>
      <div class="agxm-scopes">${scopes.map((scope) => '<span class="agxm-scope">' + esc(scope) + '</span>').join('')}</div>
    `;

    const actions = document.createElement('div');
    actions.className = 'agxm-actions';
    if (app.is_entitled) {
      const enabled = document.createElement('button');
      enabled.type = 'button';
      enabled.className = 'agxm-btn agxm-btn-active';
      enabled.innerHTML = ICONS.check + '<span>Enabled</span>';
      enabled.disabled = true;
      actions.appendChild(enabled);
    } else if (app.is_base_app) {
      const baseBtn = document.createElement('button');
      baseBtn.type = 'button';
      baseBtn.className = 'agxm-btn agxm-btn-active';
      baseBtn.innerHTML = ICONS.spark + '<span>Included</span>';
      baseBtn.disabled = true;
      actions.appendChild(baseBtn);
    } else {
      const sub = document.createElement('button');
      sub.type = 'button';
      sub.className = 'agxm-btn agxm-btn-primary';
      const subBusy = this.busy === app.app_slug + ':checkout';
      sub.innerHTML = (subBusy ? '<span class="agxm-loading-spinner" style="width:13px;height:13px;border-width:2px;margin:0;"></span>' : ICONS.card) + '<span>' + (subBusy ? 'Starting…' : 'Subscribe') + '</span>';
      sub.title = app.can_purchase ? 'Subscribe to this extension package' : 'Marketplace checkout is not configured for this package';
      sub.disabled = !app.can_purchase || !!this.busy;
      sub.addEventListener('click', () => this.checkout(app));

      const credits = document.createElement('button');
      credits.type = 'button';
      credits.className = 'agxm-btn agxm-btn-ghost';
      const creditsBusy = this.busy === app.app_slug + ':credits';
      credits.innerHTML = (creditsBusy ? '<span class="agxm-loading-spinner" style="width:13px;height:13px;border-width:2px;margin:0;"></span>' : ICONS.coins) + '<span>Credits</span>';
      credits.title = app.can_use_credits ? 'Activate with company credits' : 'Credit activation is not configured for this package';
      credits.disabled = !app.can_use_credits || !!this.busy;
      credits.addEventListener('click', () => this.activateCredits(app));

      actions.appendChild(sub);
      actions.appendChild(credits);
    }
    card.appendChild(actions);
    return card;
  };

  window.AgixtRegisterExtension('marketplace', {
    mount(container, ctx) {
      const view = new MarketplaceView(container, ctx);
      container._marketplaceView = view;
      view.start();
    },
    unmount() {
      const root = document.querySelector('.chat-screen-main .view-pane[data-view="marketplace"]');
      if (root && root._marketplaceView) {
        root._marketplaceView.stop();
        root._marketplaceView = null;
      }
    },
  });
})();
