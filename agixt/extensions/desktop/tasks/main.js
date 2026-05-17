/* Scheduled Tasks — desktop port of /tasks.
 *
 * Endpoints:
 *   GET    /v1/tasks               list pending (scheduled) tasks
 *   GET    /v1/tasks/due           list due / overdue tasks
 *   POST   /v1/task                create one-time task
 *   POST   /v1/reoccurring_task    create recurring task
 *   PUT    /v1/task                modify or cancel
 *   GET    /v1/agent               list agents (for picker)
 */
ensureFormModalTk();

window.AgixtRegisterExtension('tasks', {
  mount(container, ctx) {
    const v = new TasksView(container, ctx);
    container._tasksView = v;
    v.start();
  },
  unmount() {
    const root = document.querySelector('.chat-screen-main .view-pane[data-view="tasks"]');
    if (root && root._tasksView) { root._tasksView.stop(); root._tasksView = null; }
  },
});

const TASK_COLS = [
  { id: 'title',     label: 'Title',     sortable: true,  width: 'minmax(220px, 2fr)' },
  { id: 'agent',     label: 'Agent',     sortable: true,  width: '140px' },
  { id: 'category',  label: 'Category',  sortable: true,  width: '140px' },
  { id: 'priority',  label: 'Priority',  sortable: true,  width: '100px' },
  { id: 'due',       label: 'Due',       sortable: true,  width: '160px' },
  { id: 'status',    label: 'Status',    sortable: true,  width: '120px' },
  { id: 'actions',   label: '',          sortable: false, width: '160px' },
];

function TasksView(container, ctx) {
  this.container = container; this.ctx = ctx;
  this.tasks = []; this.dueTasks = [];
  this.agents = []; this.agentNameById = {};
  this.search = '';
  this.statusFilter = readJsonTk('agixt.desktop.tasks.status.v1', 'pending');
  this.sort = readJsonTk('agixt.desktop.tasks.sort.v1', { id: 'due', dir: 'asc' });
  this.pollTimer = null;
}

TasksView.prototype.start = function () {
  this.injectStyles();
  this.render();
  this.bootstrap();
  this.onVis = () => { if (document.hidden) this.cancelPoll(); else { this.refresh(); this.scheduleNext(); } };
  document.addEventListener('visibilitychange', this.onVis);
};
TasksView.prototype.stop = function () {
  this.cancelPoll();
  if (this.onVis) document.removeEventListener('visibilitychange', this.onVis);
  this.container.innerHTML = '';
};

TasksView.prototype.fetchJson = async function (path, opts) {
  opts = opts || {};
  if (this.ctx && typeof this.ctx.fetchJson === 'function') {
    return this.ctx.fetchJson(path, opts);
  }
  if (window.AgixtSession && typeof window.AgixtSession.request === 'function') {
    return window.AgixtSession.request(path, opts);
  }
  const u = new URL(path, this.ctx.serverUrl).toString();
  const init = {
    method: opts.method || 'GET',
    headers: Object.assign({ Authorization: 'Bearer ' + this.ctx.jwt },
      (opts.json != null) ? { 'Content-Type': 'application/json' } : {}),
  };
  if (opts.json != null) init.body = JSON.stringify(opts.json);
  const resp = await fetch(u, init);
  if (resp.status === 204) return null;
  const text = await resp.text();
  let data = null; try { data = text ? JSON.parse(text) : null; } catch (_) {}
  if (!resp.ok) { const err = new Error((data && data.detail) || ('HTTP ' + resp.status)); err.status = resp.status; throw err; }
  return data;
};

TasksView.prototype.bootstrap = async function () {
  await this.loadAgents();
  this.renderHeader();
  await this.refresh();
  this.scheduleNext();
};
TasksView.prototype.loadAgents = async function () {
  try {
    const data = await this.fetchJson('/v1/agent');
    this.agents = (data && data.agents) || [];
    this.agentNameById = {};
    for (const a of this.agents) this.agentNameById[a.id] = a.name;
  } catch (_) {}
};

TasksView.prototype.scheduleNext = function () {
  this.cancelPoll();
  if (document.hidden) return;
  this.pollTimer = window.setTimeout(() => this.refresh().finally(() => this.scheduleNext()), 60_000);
};
TasksView.prototype.cancelPoll = function () {
  if (this.pollTimer) { window.clearTimeout(this.pollTimer); this.pollTimer = null; }
};

TasksView.prototype.refresh = async function () {
  try {
    const [pending, due] = await Promise.all([
      this.fetchJson('/v1/tasks').catch(() => ({ tasks: [] })),
      this.fetchJson('/v1/tasks/due').catch(() => ({ tasks: [] })),
    ]);
    this.tasks = (pending && pending.tasks) || [];
    this.dueTasks = (due && due.tasks) || [];
    this.renderError(null);
    this.renderHeader();
    this.renderTable();
  } catch (err) { this.renderError(err); }
};

TasksView.prototype.openCreate = async function () {
  if (!this.agents.length) { this.renderError(new Error('No agents available — create an agent first.')); return; }
  this.renderError(null);
  const hasMachines = await this.checkMachinesAvailable();
  let machines = [];
  let deployments = [];
  if (hasMachines) {
    const [m, d] = await Promise.all([this.fetchMachines(), this.fetchDeployments()]);
    machines = m; deployments = d;
  }
  const values = await this.showTaskDialog({
    mode: 'create',
    agents: this.agents,
    machines,
    deployments,
    showDeployment: hasMachines,
  });
  if (!values) return;
  try {
    const tz = browserTimezoneTk();
    if (values.recurring) {
      await this.fetchJson('/v1/reoccurring_task', { method: 'POST', json: {
        agent_name: values.agent_name,
        title: values.title,
        task_description: values.task_description || null,
        start_date: values.start_date,
        end_date: values.end_date,
        frequency: values.frequency || 'daily',
        weekdays: values.weekdays || null,
        timezone: tz || null,
        priority: Number(values.priority) || 1,
        task_type: values.task_type,
        command_script: values.command_script || null,
        command_name: values.command_name || null,
        command_args: values.command_args || null,
        deployment_id: values.deployment_id || null,
        target_machines: values.target_machines || null,
      }});
    } else {
      const payload = {
        agent_name: values.agent_name,
        title: values.title,
        task_description: values.task_description || null,
        priority: Number(values.priority) || 1,
        timezone: tz || null,
        task_type: values.task_type,
        command_script: values.command_script || null,
        command_name: values.command_name || null,
        command_args: values.command_args || null,
        deployment_id: values.deployment_id || null,
        target_machines: values.target_machines || null,
      };
      if (values.start_date) {
        payload.start_date = values.start_date;
      } else {
        payload.minutes = 60;
      }
      await this.fetchJson('/v1/task', { method: 'POST', json: payload });
    }
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

TasksView.prototype.checkMachinesAvailable = async function () {
  if (this._machinesAvailable !== undefined) return this._machinesAvailable;
  try {
    const data = await this.fetchJson('/v1/desktop/extensions');
    const exts = (data && data.extensions) || [];
    this._machinesAvailable = exts.some((e) => e && e.id === 'machines');
  } catch (_) { this._machinesAvailable = false; }
  return this._machinesAvailable;
};

TasksView.prototype.fetchMachines = async function () {
  try {
    const data = await this.fetchJson('/v1/machines?status=approved');
    return Array.isArray(data) ? data : (data && data.machines) || [];
  } catch (_) { return []; }
};

TasksView.prototype.fetchDeployments = async function () {
  try {
    const data = await this.fetchJson('/v1/deployments');
    return Array.isArray(data) ? data : (data && data.deployments) || [];
  } catch (_) { return []; }
};

/* Args injected/handled by the system or used structurally — not user-configurable. */
const IGNORE_CMD_ARGS_TK = [
  'agent_name', 'COMMANDS', 'command_list', 'date', 'working_directory',
  'helper_agent_name', 'conversation_history', 'persona', 'import_files', 'output_url',
  'prompt_name', 'prompt_category', 'command_name', 'chain', 'chain_name',
  'context', 'user_input',
];

/* Load the commands an agent has, grouped by extension. Cached per agent name. */
TasksView.prototype.loadAgentCommands = async function (agentName) {
  this._cmdCacheByAgent = this._cmdCacheByAgent || {};
  if (this._cmdCacheByAgent[agentName]) return this._cmdCacheByAgent[agentName];
  const agent = (this.agents || []).find((a) => a.name === agentName);
  const groups = {};
  if (agent && agent.id) {
    try {
      const data = await this.fetchJson('/v1/agent/' + encodeURIComponent(agent.id) + '/extensions');
      const exts = (data && data.extensions) || [];
      for (const ext of exts) {
        const extName = ext.extension_name || 'Other';
        for (const c of (ext.commands || [])) {
          const nm = c.friendly_name || c.command_name || '';
          if (!nm) continue;
          if (!groups[extName]) groups[extName] = [];
          groups[extName].push(nm);
        }
      }
    } catch (_) {}
  }
  const sorted = {};
  Object.keys(groups).filter((k) => groups[k].length).sort().forEach((k) => {
    sorted[k] = groups[k].sort();
  });
  this._cmdCacheByAgent[agentName] = sorted;
  return sorted;
};

/* Resolve the configurable argument names + defaults for a command. Cached. */
TasksView.prototype.loadCommandArgs = async function (commandName) {
  this._argCacheByCmd = this._argCacheByCmd || {};
  if (this._argCacheByCmd[commandName]) return this._argCacheByCmd[commandName];
  let raw = {};
  try {
    const data = await this.fetchJson('/v1/extensions/' + encodeURIComponent(commandName) + '/args');
    raw = (data && data.command_args) || {};
  } catch (_) { raw = {}; }
  let names = [];
  if (Array.isArray(raw)) names = raw;
  else if (raw && typeof raw === 'object') names = Object.keys(raw);
  const filtered = names.filter((n) => n && IGNORE_CMD_ARGS_TK.indexOf(n) < 0);
  const result = { names: filtered, defaults: (raw && typeof raw === 'object' && !Array.isArray(raw)) ? raw : {} };
  this._argCacheByCmd[commandName] = result;
  return result;
};

TasksView.prototype.modifyTask = async function (t) {
  const values = await this.showTaskDialog({
    mode: 'edit',
    task: t,
  });
  if (!values) return;
  try {
    const payload = { task_id: t.id, cancel_task: 'false' };
    if (values.title != null) payload.title = values.title;
    if (values.description != null) payload.description = values.description;
    if (values.due_date) payload.due_date = values.due_date;
    if (values.priority != null) payload.priority = String(values.priority);
    if (values.estimated_hours != null && values.estimated_hours !== '') {
      payload.estimated_hours = String(values.estimated_hours);
    }
    await this.fetchJson('/v1/task', { method: 'PUT', json: payload });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

TasksView.prototype.cancelTask = async function (t) {
  const values = await window.AgixtFormModal.show({
    title: 'Cancel task',
    description: 'Cancel "' + (t.title || t.id) + '"? This removes it from the schedule.',
    fields: [],
    submitLabel: 'Cancel task',
    danger: true,
  });
  if (!values) return;
  try {
    await this.fetchJson('/v1/task', { method: 'PUT', json: { task_id: t.id, cancel_task: 'true' } });
    await this.refresh();
  } catch (err) { this.renderError(err); }
};

/* --- create / edit dialog --- */

const WEEKDAY_LABELS_TK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

TasksView.prototype.showTaskDialog = function (opts) {
  const view = this;
  return new Promise((resolve) => {
    ensureFormModalTk(); // shared overlay/modal CSS
    injectTaskDialogStylesTk();
    const isEdit = opts.mode === 'edit';
    const t = opts.task || {};
    let resolved = false;

    const initialDue = isEdit ? splitIsoLocalTk(t.due_date) : { date: '', time: '' };
    const state = isEdit ? {
      title: t.title || '',
      description: t.description || '',
      due_date: initialDue.date,
      due_time: initialDue.time,
      priority: t.priority || 1,
      estimated_hours: t.estimated_hours == null ? '' : String(t.estimated_hours),
    } : {
      agent_name: opts.agents[0].name,
      title: '',
      task_description: '',
      command_script: '',
      command_name: '',
      command_args: {},
      deployment_id: (opts.deployments && opts.deployments[0]) ? opts.deployments[0].id : '',
      target_machines: [],
      task_type: 'prompt',
      recurring: false,
      start_date: '',
      start_time: '',
      end_date: '',
      end_time: '',
      frequency: 'daily',
      weekdays: [],
      priority: 1,
    };

    const overlay = document.createElement('div'); overlay.className = 'xt-modal-overlay';
    const modal = document.createElement('div'); modal.className = 'xt-modal tk-dialog';
    const head = document.createElement('div'); head.className = 'xt-modal-head';
    const tw = document.createElement('div');
    const title = document.createElement('h2'); title.className = 'xt-modal-title';
    title.textContent = isEdit ? 'Edit task' : 'New scheduled task';
    tw.appendChild(title);
    if (!isEdit) {
      const desc = document.createElement('p'); desc.className = 'xt-modal-desc';
      desc.textContent = 'Run a prompt, command, or deployment on a schedule. One-time or recurring.';
      tw.appendChild(desc);
    }
    head.appendChild(tw);
    const x = document.createElement('button'); x.type = 'button'; x.className = 'xt-modal-x'; x.innerHTML = '&times;';
    head.appendChild(x);
    modal.appendChild(head);
    const body = document.createElement('div'); body.className = 'xt-modal-body';
    modal.appendChild(body);
    const errEl = document.createElement('div'); errEl.className = 'xt-modal-error'; errEl.hidden = true;
    body.appendChild(errEl);
    const formWrap = document.createElement('div'); formWrap.className = 'tk-dialog-form';
    body.appendChild(formWrap);
    const foot = document.createElement('div'); foot.className = 'xt-modal-footer';
    const cancelBtn = document.createElement('button'); cancelBtn.type = 'button'; cancelBtn.className = 'xt-btn-cancel'; cancelBtn.textContent = 'Cancel';
    const submitBtn = document.createElement('button'); submitBtn.type = 'button'; submitBtn.className = 'xt-btn-submit'; submitBtn.textContent = isEdit ? 'Save changes' : 'Create task';
    foot.appendChild(cancelBtn); foot.appendChild(submitBtn);
    modal.appendChild(foot);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function close(result) {
      if (resolved) return;
      resolved = true;
      document.removeEventListener('keydown', onKey);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      resolve(result);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); close(null); }
      else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); doSubmit(); }
    }
    document.addEventListener('keydown', onKey);
    x.addEventListener('click', () => close(null));
    cancelBtn.addEventListener('click', () => close(null));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });

    function setState(patch) { Object.assign(state, patch); render(); }
    function showError(msg) { errEl.textContent = msg; errEl.hidden = false; }
    function clearError() { errEl.hidden = true; errEl.textContent = ''; }

    function field(label, requiredMark, helpText) {
      const f = document.createElement('div'); f.className = 'tk-field';
      if (label) {
        const lbl = document.createElement('label'); lbl.textContent = label;
        if (requiredMark) { const star = document.createElement('span'); star.className = 'xt-required'; star.textContent = ' *'; lbl.appendChild(star); }
        f.appendChild(lbl);
      }
      f._pendingHelp = helpText || null;
      return f;
    }
    function attachField(f) {
      if (f._pendingHelp) {
        const h = document.createElement('div'); h.className = 'tk-help'; h.textContent = f._pendingHelp;
        f.appendChild(h);
        f._pendingHelp = null;
      }
      formWrap.append(f);
    }

    function renderCreate() {
      // Agent
      const fAgent = field('Agent', true);
      const sel = document.createElement('select');
      for (const a of opts.agents) {
        const o = document.createElement('option'); o.value = a.name; o.textContent = a.name; sel.appendChild(o);
      }
      sel.value = state.agent_name;
      sel.addEventListener('change', () => {
        if (state.task_type === 'command') {
          setState({ agent_name: sel.value, command_name: '', command_args: {} });
        } else {
          state.agent_name = sel.value;
        }
      });
      fAgent.appendChild(sel); attachField(fAgent);

      // Title
      const fTitle = field('Title', true);
      const inTitle = document.createElement('input'); inTitle.type = 'text'; inTitle.placeholder = 'Short, descriptive name'; inTitle.value = state.title;
      inTitle.addEventListener('input', () => { state.title = inTitle.value; });
      fTitle.appendChild(inTitle); attachField(fTitle);

      // Task type segmented
      const fType = field('Task type');
      const seg = document.createElement('div'); seg.className = 'tk-segmented';
      const types = [
        { key: 'prompt',     label: 'Prompt',     icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' },
        { key: 'command',    label: 'Command',    icon: 'M4 17l6-6-6-6 M12 19h8' },
      ];
      if (opts.showDeployment) {
        types.push({ key: 'deployment', label: 'Deployment', icon: 'm7.5 4.27 9 5.15 M21 8L12 13 3 8 M3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8z' });
      }
      for (const ty of types) {
        const b = document.createElement('button'); b.type = 'button';
        b.className = 'tk-seg-btn' + (state.task_type === ty.key ? ' is-active' : '');
        b.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="' + ty.icon + '"/></svg><span>' + escapeTk(ty.label) + '</span>';
        b.addEventListener('click', () => setState({ task_type: ty.key }));
        seg.appendChild(b);
      }
      fType.appendChild(seg); attachField(fType);

      // Type-specific inputs
      if (state.task_type === 'prompt') {
        const fPrompt = field('Prompt', true);
        const ta = document.createElement('textarea'); ta.rows = 4;
        ta.placeholder = 'What should the agent do when this task fires?';
        ta.value = state.task_description;
        ta.addEventListener('input', () => { state.task_description = ta.value; });
        fPrompt.appendChild(ta); attachField(fPrompt);
      } else if (state.task_type === 'command') {
        const fCmd = field('Command', true, 'Select a command the agent has enabled. The agent runs it on schedule.');
        const groups = view._cmdCacheByAgent && view._cmdCacheByAgent[state.agent_name];
        if (!groups) {
          const loading = document.createElement('div'); loading.className = 'tk-empty-pick';
          loading.textContent = 'Loading commands…';
          fCmd.appendChild(loading); attachField(fCmd);
          view.loadAgentCommands(state.agent_name).then(() => { if (!resolved) setState({}); });
        } else if (!Object.keys(groups).length) {
          const empty = document.createElement('div'); empty.className = 'tk-empty-pick';
          empty.textContent = 'No commands enabled for this agent. Enable commands in agent settings first.';
          fCmd.appendChild(empty); attachField(fCmd);
        } else {
          const csel = document.createElement('select');
          const ph = document.createElement('option'); ph.value = ''; ph.textContent = 'Select a command…';
          csel.appendChild(ph);
          Object.keys(groups).forEach((gName) => {
            const og = document.createElement('optgroup'); og.label = gName;
            groups[gName].forEach((cmd) => {
              const o = document.createElement('option'); o.value = cmd; o.textContent = cmd; og.appendChild(o);
            });
            csel.appendChild(og);
          });
          csel.value = state.command_name || '';
          csel.addEventListener('change', () => { setState({ command_name: csel.value, command_args: {} }); });
          fCmd.appendChild(csel); attachField(fCmd);
          if (state.command_name) renderCommandArgs();
        }
      } else if (state.task_type === 'deployment') {
        const fDep = field('Deployment', true);
        if (!opts.deployments || !opts.deployments.length) {
          const empty = document.createElement('div'); empty.className = 'tk-empty-pick';
          empty.textContent = 'No deployments available. Create one first.';
          fDep.appendChild(empty);
        } else {
          const dsel = document.createElement('select');
          for (const d of opts.deployments) {
            const o = document.createElement('option'); o.value = d.id; o.textContent = d.name || d.id; dsel.appendChild(o);
          }
          if (state.deployment_id) dsel.value = state.deployment_id; else state.deployment_id = dsel.value;
          dsel.addEventListener('change', () => { state.deployment_id = dsel.value; });
          fDep.appendChild(dsel);
        }
        attachField(fDep);
        renderMachinePicker();
      }

      // Recurring checkbox
      const fRec = document.createElement('div'); fRec.className = 'tk-field tk-checkbox-row';
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.id = 'tk-recurring'; cb.checked = !!state.recurring;
      cb.addEventListener('change', () => setState({ recurring: cb.checked }));
      fRec.appendChild(cb);
      const cbLbl = document.createElement('label'); cbLbl.htmlFor = 'tk-recurring';
      cbLbl.textContent = 'Recurring task';
      fRec.appendChild(cbLbl);
      attachField(fRec);

      // Start date + time
      const startLabel = state.recurring ? 'First run' : 'Run at';
      attachField(buildDateTimeRow(startLabel, true,
        state.start_date, state.start_time,
        (d) => { state.start_date = d; }, (tm) => { state.start_time = tm; },
        state.recurring ? null : 'Leave blank to run 60 minutes from now.'));

      if (state.recurring) {
        // End date + time
        attachField(buildDateTimeRow('End by', true,
          state.end_date, state.end_time,
          (d) => { state.end_date = d; }, (tm) => { state.end_time = tm; }));

        // Frequency
        const fFreq = field('Frequency');
        const fsel = document.createElement('select');
        for (const o of [
          { value: 'hourly', label: 'Hourly' },
          { value: 'daily', label: 'Daily' },
          { value: 'weekly', label: 'Weekly' },
          { value: 'monthly', label: 'Monthly' },
        ]) {
          const op = document.createElement('option'); op.value = o.value; op.textContent = o.label; fsel.appendChild(op);
        }
        fsel.value = state.frequency;
        fsel.addEventListener('change', () => setState({ frequency: fsel.value }));
        fFreq.appendChild(fsel); attachField(fFreq);

        if (state.frequency === 'weekly') {
          const fW = field('Weekdays', false, 'Click to toggle which days the task runs on.');
          const wrap = document.createElement('div'); wrap.className = 'tk-weekday-row';
          for (let i = 0; i < 7; i++) {
            const wb = document.createElement('button'); wb.type = 'button';
            wb.className = 'tk-weekday' + (state.weekdays.indexOf(i) >= 0 ? ' is-active' : '');
            wb.textContent = WEEKDAY_LABELS_TK[i];
            wb.addEventListener('click', () => {
              const idx = state.weekdays.indexOf(i);
              const next = state.weekdays.slice();
              if (idx >= 0) next.splice(idx, 1); else { next.push(i); next.sort(); }
              setState({ weekdays: next });
            });
            wrap.appendChild(wb);
          }
          fW.appendChild(wrap); attachField(fW);
        }
      }

      // Priority
      const fPri = field('Priority');
      const np = document.createElement('input'); np.type = 'number'; np.min = '1'; np.max = '5'; np.value = String(state.priority || 1);
      np.addEventListener('input', () => { state.priority = Number(np.value) || 1; });
      fPri.appendChild(np); attachField(fPri);
    }

    function renderCommandArgs() {
      const cached = view._argCacheByCmd && view._argCacheByCmd[state.command_name];
      if (!cached) {
        const fLoad = field('Command arguments');
        const loading = document.createElement('div'); loading.className = 'tk-empty-pick';
        loading.textContent = 'Loading arguments…';
        fLoad.appendChild(loading); attachField(fLoad);
        view.loadCommandArgs(state.command_name).then((res) => {
          if (resolved) return;
          const seeded = {};
          (res.names || []).forEach((n) => {
            seeded[n] = Object.prototype.hasOwnProperty.call(state.command_args, n)
              ? state.command_args[n]
              : (res.defaults && res.defaults[n] != null ? res.defaults[n] : '');
          });
          state.command_args = seeded;
          setState({});
        });
        return;
      }
      if (!cached.names.length) {
        const fNone = field('Command arguments', false, 'No configurable arguments.');
        attachField(fNone);
        return;
      }
      for (const name of cached.names) {
        const label = name.replace(/_/g, ' ').replace(/(?:^|\s)\S/g, (c) => c.toUpperCase());
        const cur = Object.prototype.hasOwnProperty.call(state.command_args, name) ? state.command_args[name] : '';
        const isBool = typeof cur === 'boolean' || ['true', 'false'].indexOf(String(cur).toLowerCase()) >= 0;
        if (isBool) {
          const fb = document.createElement('div'); fb.className = 'tk-field tk-checkbox-row';
          const cb = document.createElement('input'); cb.type = 'checkbox';
          cb.id = 'tk-arg-' + name;
          cb.checked = cur === true || String(cur).toLowerCase() === 'true';
          cb.addEventListener('change', () => { state.command_args[name] = cb.checked; });
          fb.appendChild(cb);
          const lb = document.createElement('label'); lb.htmlFor = 'tk-arg-' + name; lb.textContent = label;
          fb.appendChild(lb);
          attachField(fb);
        } else {
          const fa = field(label);
          const isNum = typeof cur === 'number';
          const inp = document.createElement('input'); inp.type = isNum ? 'number' : 'text';
          inp.value = cur == null ? '' : String(cur);
          inp.placeholder = 'Enter ' + label;
          inp.addEventListener('input', () => { state.command_args[name] = inp.value; });
          fa.appendChild(inp); attachField(fa);
        }
      }
    }

    function renderMachinePicker() {
      const fM = field('Target machines', true,
        (opts.machines && opts.machines.length) ? null : 'No approved machines available — register one first.');
      if (opts.machines && opts.machines.length) {
        const list = document.createElement('div'); list.className = 'tk-machine-list';
        for (const m of opts.machines) {
          const row = document.createElement('label'); row.className = 'tk-machine';
          const cb = document.createElement('input'); cb.type = 'checkbox';
          cb.checked = state.target_machines.indexOf(m.id) >= 0;
          cb.addEventListener('change', () => {
            const idx = state.target_machines.indexOf(m.id);
            const next = state.target_machines.slice();
            if (cb.checked && idx < 0) next.push(m.id);
            else if (!cb.checked && idx >= 0) next.splice(idx, 1);
            state.target_machines = next;
          });
          const span = document.createElement('span');
          span.textContent = m.hostname || m.name || m.id;
          row.appendChild(cb); row.appendChild(span);
          list.appendChild(row);
        }
        fM.appendChild(list);
      }
      attachField(fM);
    }

    function buildDateTimeRow(label, required, dateVal, timeVal, onDate, onTime, helpText) {
      const f = field(label, required, helpText);
      const row = document.createElement('div'); row.className = 'tk-datetime-row';
      const di = document.createElement('input'); di.type = 'date'; di.value = dateVal || '';
      di.addEventListener('change', () => onDate(di.value));
      const ti = document.createElement('input'); ti.type = 'time'; ti.value = timeVal || '';
      ti.addEventListener('change', () => onTime(ti.value));
      row.appendChild(di); row.appendChild(ti);
      f.appendChild(row);
      return f;
    }

    function renderEdit() {
      // Title
      const fTitle = field('Title');
      const inTitle = document.createElement('input'); inTitle.type = 'text'; inTitle.value = state.title;
      inTitle.addEventListener('input', () => { state.title = inTitle.value; });
      fTitle.appendChild(inTitle); attachField(fTitle);

      // Description
      const fDesc = field('Description');
      const ta = document.createElement('textarea'); ta.rows = 3; ta.value = state.description;
      ta.addEventListener('input', () => { state.description = ta.value; });
      fDesc.appendChild(ta); attachField(fDesc);

      // Due date+time
      attachField(buildDateTimeRow('Due date / time', false,
        state.due_date, state.due_time,
        (d) => { state.due_date = d; }, (tm) => { state.due_time = tm; }));

      // Priority
      const fPri = field('Priority');
      const np = document.createElement('input'); np.type = 'number'; np.min = '1'; np.max = '5'; np.value = String(state.priority || 1);
      np.addEventListener('input', () => { state.priority = Number(np.value) || 1; });
      fPri.appendChild(np); attachField(fPri);

      // Estimated hours
      const fEst = field('Estimated hours');
      const ne = document.createElement('input'); ne.type = 'number'; ne.step = '0.25'; ne.value = state.estimated_hours;
      ne.addEventListener('input', () => { state.estimated_hours = ne.value; });
      fEst.appendChild(ne); attachField(fEst);
    }

    function render() {
      formWrap.innerHTML = '';
      if (isEdit) renderEdit(); else renderCreate();
    }

    function doSubmit() {
      clearError();
      if (isEdit) {
        const result = {
          title: state.title.trim(),
          description: state.description,
          priority: state.priority,
          estimated_hours: state.estimated_hours,
        };
        const iso = combineIsoFromPartsTk(state.due_date, state.due_time);
        if (state.due_date && !iso) { showError('Due date / time is invalid.'); return; }
        if (iso) result.due_date = iso;
        close(result);
        return;
      }
      // Create validation
      if (!state.title.trim()) { showError('Title is required.'); return; }
      if (state.task_type === 'prompt') {
        if (!state.task_description.trim()) { showError('Prompt is required.'); return; }
      }
      if (state.task_type === 'command') {
        if (!state.command_name) { showError('Pick a command for the agent to run.'); return; }
      }
      if (state.task_type === 'deployment') {
        if (!state.deployment_id) { showError('Pick a deployment.'); return; }
        if (!state.target_machines.length) { showError('Pick at least one target machine.'); return; }
      }
      const startIso = combineIsoFromPartsTk(state.start_date, state.start_time);
      if (state.recurring) {
        if (!startIso) { showError('Recurring tasks need a start date and time.'); return; }
        const endIso = combineIsoFromPartsTk(state.end_date, state.end_time);
        if (!endIso) { showError('Recurring tasks need an end date and time.'); return; }
        if (Date.parse(endIso) <= Date.parse(startIso)) { showError('End must be after start.'); return; }
      } else if ((state.start_date && !state.start_time) || (!state.start_date && state.start_time)) {
        showError('Pick both a date and a time, or leave both blank.'); return;
      }

      const out = {
        agent_name: state.agent_name,
        title: state.title.trim(),
        task_type: state.task_type,
        priority: state.priority,
        recurring: state.recurring,
      };
      // Description is the prompt for prompt-type, generic description for others.
      if (state.task_type === 'prompt') {
        out.task_description = state.task_description;
      } else if (state.task_description) {
        out.task_description = state.task_description;
      }
      if (state.task_type === 'command') {
        out.command_name = state.command_name;
        out.command_args = JSON.stringify(state.command_args || {});
      }
      if (state.task_type === 'deployment') {
        out.deployment_id = state.deployment_id;
        out.target_machines = JSON.stringify(state.target_machines);
      }
      if (startIso) out.start_date = startIso;
      if (state.recurring) {
        out.end_date = combineIsoFromPartsTk(state.end_date, state.end_time);
        out.frequency = state.frequency || 'daily';
        if (state.frequency === 'weekly' && state.weekdays.length) {
          out.weekdays = state.weekdays.join(',');
        }
      }
      close(out);
    }
    submitBtn.addEventListener('click', doSubmit);

    render();
    setTimeout(() => {
      const first = formWrap.querySelector('input, select, textarea');
      if (first) try { first.focus(); } catch (_) {}
    }, 0);
  });
};

/* --- predicates / sort --- */
TasksView.prototype.allTasks = function () {
  if (this.statusFilter === 'due') return this.dueTasks;
  return this.tasks;
};
TasksView.prototype.isDue = function (t) {
  if (!t || !t.due_date) return false;
  const ms = Date.parse(t.due_date); if (!isFinite(ms)) return false;
  return ms <= Date.now() && !t.completed;
};
TasksView.prototype.taskStatus = function (t) {
  if (t.completed) return 'completed';
  if (this.isDue(t)) return 'due';
  if (t.scheduled) return 'scheduled';
  return 'pending';
};

TasksView.prototype.filteredAndSorted = function () {
  const q = (this.search || '').trim().toLowerCase();
  const out = this.allTasks().filter((t) => {
    if (this.statusFilter === 'pending' && t.completed) return false;
    if (this.statusFilter === 'completed' && !t.completed) return false;
    if (!q) return true;
    const cat = (t.category && t.category.name) || t.category_name || '';
    const hay = [t.title, t.description, cat, this.agentNameById[t.agent_id] || t.agent_id].join(' ').toLowerCase();
    return hay.includes(q);
  });
  out.sort((a, b) => this.compare(a, b, this.sort.id, this.sort.dir));
  return out;
};
TasksView.prototype.compare = function (a, b, col, dir) {
  const sign = dir === 'desc' ? -1 : 1;
  const va = this.sortKey(a, col); const vb = this.sortKey(b, col);
  if (va == null && vb == null) return 0;
  if (va == null) return 1;
  if (vb == null) return -1;
  if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sign;
  return String(va).localeCompare(String(vb), undefined, { sensitivity: 'base' }) * sign;
};
TasksView.prototype.sortKey = function (t, col) {
  switch (col) {
    case 'title':    return (t.title || '').toLowerCase();
    case 'agent':    return (this.agentNameById[t.agent_id] || t.agent_id || '').toLowerCase();
    case 'category': return ((t.category && t.category.name) || t.category_name || '').toLowerCase();
    case 'priority': return Number(t.priority) || 0;
    case 'due':      return Date.parse(t.due_date) || Number.POSITIVE_INFINITY;
    case 'status':   return this.taskStatus(t);
    default: return '';
  }
};

/* --- DOM --- */
TasksView.prototype.render = function () {
  this.container.innerHTML = '';
  const root = document.createElement('div'); root.className = 'tk-root';
  this.headerEl = document.createElement('div'); this.headerEl.className = 'tk-header'; root.appendChild(this.headerEl);
  this.errEl = document.createElement('div'); this.errEl.className = 'tk-error'; this.errEl.hidden = true; root.appendChild(this.errEl);
  this.tableEl = document.createElement('div'); this.tableEl.className = 'tk-table-wrap'; root.appendChild(this.tableEl);
  this.container.appendChild(root);
  this.renderHeader(); this.renderTable();
};

TasksView.prototype.renderHeader = function () {
  if (!this.headerEl) return;
  if (!this._tools) this._buildTools();
  const counts = {
    pending: this.tasks.filter((t) => !t.completed).length,
    completed: this.tasks.filter((t) => t.completed).length,
    due: this.dueTasks.length,
  };

  this.headerEl.innerHTML = '';
  if (this.ctx && this.ctx.framed && typeof this.ctx.setHeaderActions === 'function') {
    if (!this._toolbarMounted) {
      const order = [this._tools.search, this._tools.refresh, this._tools.add];
      this.ctx.setHeaderActions.apply(this.ctx, order);
      this._toolbarMounted = true;
    }
  } else {
    const row = document.createElement('div'); row.className = 'tk-title-row';
    row.appendChild(this._tools.refresh);
    row.appendChild(this._tools.add);
    row.appendChild(this._tools.search);
    this.headerEl.appendChild(row);
  }

  const tabs = [
    { key: 'pending',   label: 'Pending',   n: counts.pending },
    { key: 'due',       label: 'Due now',   n: counts.due },
    { key: 'completed', label: 'Completed', n: counts.completed },
  ];
  const tabsRow = document.createElement('div'); tabsRow.className = 'tk-tabs';
  for (const t of tabs) {
    const b = document.createElement('button'); b.type = 'button';
    b.className = 'tk-tab' + (this.statusFilter === t.key ? ' is-active' : '');
    b.textContent = t.label + ' (' + t.n + ')';
    b.addEventListener('click', () => { this.statusFilter = t.key; writeJsonTk('agixt.desktop.tasks.status.v1', t.key); this.renderHeader(); this.renderTable(); });
    tabsRow.appendChild(b);
  }
  this.headerEl.appendChild(tabsRow);
};

TasksView.prototype._buildTools = function () {
  const tools = {};
  tools.refresh = document.createElement('button');
  tools.refresh.type = 'button'; tools.refresh.className = 'tk-iconbtn'; tools.refresh.textContent = '↻';
  tools.refresh.title = 'Refresh';
  tools.refresh.addEventListener('click', () => this.refresh());

  tools.add = document.createElement('button');
  tools.add.type = 'button'; tools.add.className = 'tk-primary'; tools.add.textContent = '+ New task';
  tools.add.addEventListener('click', () => {
    Promise.resolve()
      .then(() => this.openCreate())
      .catch((err) => {
        try { window.AgixtFrontendLog && window.AgixtFrontendLog('error', 'tasks: openCreate failed: ' + (err && err.stack || err)); } catch (_) {}
        this.renderError(err instanceof Error ? err : new Error(String(err)));
      });
  });

  tools.search = document.createElement('input');
  tools.search.type = 'search'; tools.search.placeholder = 'Search tasks…';
  tools.search.value = this.search; tools.search.className = 'tk-search';
  tools.search.addEventListener('input', (e) => { this.search = e.target.value; this.renderTable(); });

  this._tools = tools;
};

TasksView.prototype.renderTable = function () {
  if (!this.tableEl) return;
  const rows = this.filteredAndSorted();
  const headers = TASK_COLS.map((c) => {
    const sortable = c.sortable ? ' is-sortable' : '';
    const active = this.sort.id === c.id ? ' is-sorted' : '';
    const arrow = this.sort.id === c.id ? (this.sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
    return '<th class="tk-th' + sortable + active + '" data-col="' + c.id + '">' + escapeTk(c.label) + escapeTk(arrow) + '</th>';
  }).join('');
  const bodyRows = rows.length
    ? rows.map((t) => this.rowHtml(t)).join('')
    : '<tr><td colspan="' + TASK_COLS.length + '" class="tk-empty">No tasks match the current filter.</td></tr>';
  this.tableEl.innerHTML = '<table class="tk-table"><thead><tr>' + headers + '</tr></thead><tbody>' + bodyRows + '</tbody></table>';

  this.tableEl.querySelectorAll('.tk-th.is-sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const id = th.dataset.col;
      if (this.sort.id === id) this.sort.dir = this.sort.dir === 'asc' ? 'desc' : 'asc';
      else { this.sort.id = id; this.sort.dir = id === 'priority' ? 'desc' : 'asc'; }
      writeJsonTk('agixt.desktop.tasks.sort.v1', this.sort);
      this.renderTable();
    });
  });

  const view = this;
  this.tableEl.querySelectorAll('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const t = view.allTasks().find((x) => x.id === btn.dataset.id);
      if (!t) return;
      if (btn.dataset.action === 'edit') view.modifyTask(t);
      else if (btn.dataset.action === 'cancel') view.cancelTask(t);
    });
  });
};

TasksView.prototype.rowHtml = function (t) {
  const status = this.taskStatus(t);
  const statusClass = status === 'due' ? 'tk-pill-bad' : (status === 'completed' ? 'tk-pill-good' : '');
  const cat = (t.category && t.category.name) || t.category_name || '';
  const due = t.due_date
    ? '<span class="' + (this.isDue(t) ? 'tk-overdue' : '') + '" title="' + escapeTk(t.due_date) + '">' + escapeTk(formatRelativeTk(t.due_date)) + '</span>'
    : '<span class="tk-faint">—</span>';
  const actions = [];
  if (!t.completed) {
    actions.push('<button data-action="edit" data-id="' + escapeTk(t.id) + '">Edit</button>');
    actions.push('<button class="danger" data-action="cancel" data-id="' + escapeTk(t.id) + '">Cancel</button>');
  }
  return '<tr>' +
    '<td><div class="tk-name">' + escapeTk(t.title || '(untitled)') + '</div>' +
    (t.description ? '<div class="tk-desc">' + escapeTk(truncTk(t.description, 100)) + '</div>' : '') +
    '</td>' +
    '<td>' + escapeTk(this.agentNameById[t.agent_id] || t.agent_id || '') + '</td>' +
    '<td>' + escapeTk(cat) + '</td>' +
    '<td>' + (t.priority != null ? '<span class="tk-pill">' + escapeTk(String(t.priority)) + '</span>' : '<span class="tk-faint">—</span>') + '</td>' +
    '<td>' + due + '</td>' +
    '<td><span class="tk-pill ' + statusClass + '">' + escapeTk(status) + '</span></td>' +
    '<td class="tk-actions">' + actions.join('') + '</td>' +
  '</tr>';
};

TasksView.prototype.renderError = function (err) {
  if (!this.errEl) return;
  if (!err) { this.errEl.hidden = true; this.errEl.textContent = ''; return; }
  this.errEl.textContent = err.message || 'Request failed.';
  this.errEl.hidden = false;
};

TasksView.prototype.injectStyles = function () {
  if (document.getElementById('tk-task-styles')) return;
  const css = `
    .tk-root { --tk-border: var(--border); --tk-divider: var(--border-muted); --tk-row-hover: var(--panel-hover); --tk-card-bg: var(--panel-2);
      display: flex; flex-direction: column; gap: 16px; padding: 16px 20px 32px; min-height: 100%; color: var(--text); }
    .tk-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .tk-iconbtn { width: 30px; height: 30px; border-radius: 6px; border: 1px solid var(--tk-border); background: var(--panel-2); color: var(--text-dim); cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; }
    .tk-iconbtn:hover { background: var(--panel); color: var(--text); }
    .tk-primary { font-size: 12.5px; padding: 6px 14px; border-radius: 6px; background: var(--accent); color: #fff; border: 1px solid var(--accent); cursor: pointer; font-weight: 500; }
    .tk-search { flex: 1 1 240px; max-width: 360px; padding: 7px 12px; font-size: 13px; background: var(--panel-2); color: var(--text); border: 1px solid var(--tk-border); border-radius: 6px; }
    .tk-search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(107,123,255,0.18); }
    .tk-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .tk-tab { padding: 5px 12px; font-size: 12.5px; font-weight: 500; border-radius: 999px; background: transparent; color: var(--text-dim); border: 1px solid var(--tk-border); cursor: pointer; }
    .tk-tab:hover { background: var(--panel-2); color: var(--text); }
    .tk-tab.is-active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .tk-error { padding: 10px 14px; border-radius: 8px; font-size: 12.5px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; }
    .tk-table-wrap { overflow: auto; background: var(--tk-card-bg); border: 1px solid var(--tk-border); border-radius: 10px; }
    .tk-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 1000px; }
    .tk-table th, .tk-table td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--tk-divider); vertical-align: middle; }
    .tk-table tbody tr:hover { background: var(--tk-row-hover); }
    .tk-table tbody tr:last-child td { border-bottom: 0; }
    .tk-th { color: var(--text-faint); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.07em; background: var(--border-muted); border-bottom: 1px solid var(--tk-border); white-space: nowrap; user-select: none; }
    .tk-th.is-sortable { cursor: pointer; }
    .tk-th.is-sortable:hover { color: var(--text); background: var(--tk-row-hover); }
    .tk-name { font-weight: 600; }
    .tk-desc { font-size: 11.5px; color: var(--text-faint); margin-top: 2px; max-width: 480px; }
    .tk-pill { display: inline-flex; align-items: center; font-size: 11px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--tk-border); color: var(--text-dim); text-transform: capitalize; background: var(--panel-2); }
    .tk-pill-good { background: rgba(80,200,130,0.16); color: #9ce0b3; border-color: rgba(80,200,130,0.4); }
    .tk-pill-bad { background: rgba(220,60,80,0.16); color: #ff7a86; border-color: rgba(220,60,80,0.4); }
    .tk-faint { color: var(--text-faint); }
    .tk-overdue { color: #ff8a96; font-weight: 600; }
    .tk-actions { display: flex; gap: 4px; justify-content: flex-end; }
    .tk-actions button { font-size: 11px; padding: 3px 9px; border-radius: 5px; border: 1px solid var(--tk-border); background: var(--panel-2); color: var(--text); cursor: pointer; white-space: nowrap; }
    .tk-actions button:hover { background: var(--panel); }
    .tk-actions button.danger { color: #ffb4ba; border-color: rgba(220,60,80,0.4); }
    .tk-actions button.danger:hover { background: rgba(220, 60, 80, 0.18); }
    .tk-empty { padding: 32px; text-align: center; color: var(--text-faint); }
  `;
  const tag = document.createElement('style'); tag.id = 'tk-task-styles'; tag.textContent = css; document.head.appendChild(tag);
};

function escapeTk(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function truncTk(s, n) { if (s == null) return ''; const v = String(s); return v.length > n ? v.slice(0, n - 1) + '…' : v; }
function formatRelativeTk(iso) {
  const ms = Date.parse(iso); if (!isFinite(ms)) return '';
  const diff = Date.now() - ms;
  if (diff < 0) {
    const fwd = -diff;
    if (fwd < 3600_000) return 'in ' + Math.round(fwd / 60_000) + 'm';
    if (fwd < 86400_000) return 'in ' + Math.round(fwd / 3600_000) + 'h';
    return 'in ' + Math.round(fwd / 86400_000) + 'd';
  }
  if (diff < 60_000) return 'just now';
  if (diff < 3600_000) return Math.round(diff / 60_000) + 'm ago';
  if (diff < 86400_000) return Math.round(diff / 3600_000) + 'h ago';
  return Math.round(diff / 86400_000) + 'd ago';
}
function readJsonTk(k, f) { try { const r = window.localStorage.getItem(k); if (!r) return f; const v = JSON.parse(r); return v == null ? f : v; } catch (_) { return f; } }
function writeJsonTk(k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} }
function browserTimezoneTk() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (_) { return ''; }
}
// Split an ISO timestamp into local-zone date and time strings the
// `<input type=date>` / `<input type=time>` elements expect. The desktop
// webview's datetime-local rendering is unreliable, so the dialog uses
// two paired inputs and recombines them on submit.
function splitIsoLocalTk(iso) {
  const empty = { date: '', time: '' };
  if (!iso) return empty;
  const ms = Date.parse(iso); if (!isFinite(ms)) return empty;
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, '0');
  return {
    date: d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()),
    time: pad(d.getHours()) + ':' + pad(d.getMinutes()),
  };
}
function combineIsoFromPartsTk(dateStr, timeStr) {
  if (!dateStr || !timeStr) return null;
  const ms = Date.parse(dateStr + 'T' + timeStr);
  return isFinite(ms) ? new Date(ms).toISOString() : null;
}
function injectTaskDialogStylesTk() {
  if (document.getElementById('tk-dialog-styles')) return;
  const css = `
    .tk-dialog { max-width: 580px; }
    .tk-dialog .xt-modal-body { padding: 16px 20px; }
    .tk-dialog-form { display: flex; flex-direction: column; gap: 14px; }
    .tk-dialog .tk-field { display: flex; flex-direction: column; gap: 5px; }
    .tk-dialog .tk-field > label { font-size: 12px; font-weight: 600; color: var(--text-dim, #aab1be); }
    .tk-dialog .tk-help { font-size: 11px; color: var(--text-faint, #8b94a3); }
    .tk-dialog .tk-checkbox-row { flex-direction: row; align-items: center; gap: 10px; }
    .tk-dialog .tk-checkbox-row input { width: 16px; height: 16px; cursor: pointer; }
    .tk-dialog .tk-checkbox-row label { font-weight: 500; color: var(--text, #e6e8ee); cursor: pointer; }
    .tk-dialog input[type=text], .tk-dialog input[type=number], .tk-dialog input[type=date], .tk-dialog input[type=time], .tk-dialog textarea, .tk-dialog select {
      font-family: inherit; font-size: 13px; background: var(--panel-2, #232730); color: var(--text, #e6e8ee);
      border: 1px solid var(--border, #2a2e38); border-radius: 6px; padding: 8px 10px; box-sizing: border-box; width: 100%;
    }
    .tk-dialog textarea { resize: vertical; min-height: 60px; }
    .tk-dialog textarea.tk-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .tk-dialog input:focus, .tk-dialog textarea:focus, .tk-dialog select:focus {
      outline: none; border-color: var(--accent, #6b7bff); box-shadow: 0 0 0 3px rgba(107,123,255,0.18);
    }
    .tk-dialog select { appearance: none; -webkit-appearance: none; padding-right: 28px; cursor: pointer;
      background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23a1a7b5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>");
      background-repeat: no-repeat; background-position: right 10px center; background-size: 10px 10px;
    }
    .tk-segmented { display: inline-flex; gap: 0; padding: 3px; background: var(--panel-2, #232730); border: 1px solid var(--border, #2a2e38); border-radius: 8px; align-self: flex-start; }
    .tk-seg-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 6px; border: 0; background: transparent; color: var(--text-dim, #aab1be); cursor: pointer; font-size: 12.5px; font-weight: 500; }
    .tk-seg-btn:hover { color: var(--text, #e6e8ee); }
    .tk-seg-btn.is-active { background: var(--accent, #6b7bff); color: #fff; }
    .tk-seg-btn svg { stroke: currentColor; }
    .tk-datetime-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .tk-weekday-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .tk-weekday { padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border, #2a2e38); background: var(--panel-2, #232730); color: var(--text-dim, #aab1be); cursor: pointer; font-size: 12px; min-width: 44px; }
    .tk-weekday:hover { color: var(--text, #e6e8ee); }
    .tk-weekday.is-active { background: var(--accent, #6b7bff); color: #fff; border-color: var(--accent, #6b7bff); }
    .tk-machine-list { display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow-y: auto; padding: 8px; border: 1px solid var(--border, #2a2e38); border-radius: 6px; background: var(--panel-2, #232730); }
    .tk-machine { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; cursor: pointer; font-size: 13px; color: var(--text, #e6e8ee); }
    .tk-machine:hover { background: var(--panel, #1c1f26); }
    .tk-machine input { width: 14px; height: 14px; }
    .tk-empty-pick { padding: 10px; border-radius: 6px; background: var(--panel-2, #232730); border: 1px dashed var(--border, #2a2e38); color: var(--text-faint, #8b94a3); font-size: 12px; }
  `;
  const tag = document.createElement('style'); tag.id = 'tk-dialog-styles'; tag.textContent = css; document.head.appendChild(tag);
}

// Inject the base `.xt-modal-overlay` / `.xt-modal` styles. Idempotent
// via a fixed style-tag id so it's safe to call many times across
// extensions. Pulled out of `ensureFormModalTk` because the tasks
// dialog renders its own modal directly (bypassing AgixtFormModal.show)
// and otherwise the overlay would appear unstyled — invisible — when
// no AgixtFormModal.show() has run yet this session.
function injectFormModalStylesTk() {
  const STYLE_ID = 'agixt-ext-modal-styles';
  if (document.getElementById(STYLE_ID)) return;
  const css = `.xt-modal-overlay { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.55); padding: 24px; } .xt-modal { background: var(--panel, #1c1f26); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); border-radius: 12px; width: 100%; max-width: 560px; max-height: calc(100vh - 64px); display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,0.5); overflow: hidden; } .xt-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 16px 20px; border-bottom: 1px solid var(--border, #2a2e38); background: var(--panel-2, #232730); } .xt-modal-title { margin: 0; font-size: 16px; font-weight: 700; } .xt-modal-desc { margin: 4px 0 0; font-size: 12px; color: var(--text-faint, #8b94a3); } .xt-modal-x { background: transparent; border: 0; color: var(--text-dim, #aab1be); font-size: 18px; cursor: pointer; padding: 0 4px; line-height: 1; } .xt-modal-x:hover { color: var(--text, #e6e8ee); } .xt-modal-body { padding: 18px 20px; overflow: auto; display: flex; flex-direction: column; gap: 14px; } .xt-modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border, #2a2e38); background: var(--panel-2, #232730); } .xt-field { display: flex; flex-direction: column; gap: 5px; } .xt-field label { font-size: 12px; font-weight: 600; color: var(--text-dim, #aab1be); } .xt-field .xt-required { color: #ff7a86; } .xt-field .xt-help { font-size: 11px; color: var(--text-faint, #8b94a3); } .xt-field input[type=text], .xt-field input[type=email], .xt-field input[type=number], .xt-field input[type=date], .xt-field input[type=datetime-local], .xt-field input[type=password], .xt-field textarea, .xt-field select { font-family: inherit; font-size: 13px; background: var(--panel-2, #232730); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); border-radius: 6px; padding: 8px 10px; box-sizing: border-box; width: 100%; } .xt-field textarea { resize: vertical; min-height: 60px; } .xt-field select { appearance: none; -webkit-appearance: none; padding-right: 28px; cursor: pointer; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23a1a7b5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>"); background-repeat: no-repeat; background-position: right 10px center; background-size: 10px 10px; } .xt-field input:focus, .xt-field textarea:focus, .xt-field select:focus { outline: none; border-color: var(--accent, #6b7bff); box-shadow: 0 0 0 3px rgba(107,123,255,0.18); } .xt-field-checkbox { flex-direction: row; align-items: center; gap: 10px; } .xt-field-checkbox label { order: 2; margin: 0; font-weight: 500; color: var(--text, #e6e8ee); cursor: pointer; } .xt-field-checkbox input[type=checkbox] { width: 16px; height: 16px; margin: 0; cursor: pointer; } .xt-kv-list { display: flex; flex-direction: column; gap: 6px; } .xt-kv-row { display: grid; grid-template-columns: 1fr 1.5fr auto; gap: 6px; align-items: center; } .xt-kv-row input { width: 100%; } .xt-kv-add { font-size: 12px; padding: 5px 12px; border-radius: 6px; background: var(--panel-2, #232730); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); cursor: pointer; align-self: flex-start; } .xt-kv-add:hover { background: var(--panel, #1c1f26); } .xt-kv-del { width: 26px; height: 26px; border-radius: 5px; border: 1px solid var(--border, #2a2e38); background: transparent; color: #ffb4ba; cursor: pointer; } .xt-kv-del:hover { background: rgba(220, 60, 80, 0.18); } .xt-modal-error { padding: 8px 12px; border-radius: 6px; font-size: 12px; background: rgba(220, 60, 80, 0.18); border: 1px solid rgba(220, 60, 80, 0.4); color: #ffb4ba; } .xt-btn-cancel { font-size: 12.5px; padding: 7px 16px; border-radius: 6px; background: var(--panel, #1c1f26); color: var(--text, #e6e8ee); border: 1px solid var(--border, #2a2e38); cursor: pointer; } .xt-btn-cancel:hover { background: var(--panel-hover, #2a2e38); } .xt-btn-submit { font-size: 12.5px; padding: 7px 16px; border-radius: 6px; background: var(--accent, #6b7bff); color: #fff; border: 1px solid var(--accent, #6b7bff); cursor: pointer; font-weight: 500; } .xt-btn-submit:hover { filter: brightness(1.1); } .xt-btn-submit[disabled] { opacity: 0.6; cursor: not-allowed; } .xt-btn-submit.danger { background: rgba(220, 60, 80, 0.85); border-color: rgba(220, 60, 80, 0.85); }`;
  const tag = document.createElement('style'); tag.id = STYLE_ID; tag.textContent = css;
  document.head.appendChild(tag);
}

/* Shared form modal — see assets/main.js for full documentation. */
function ensureFormModalTk() {
  injectFormModalStylesTk();
  if (window.AgixtFormModal) return;
  function injectStyles() { injectFormModalStylesTk(); }
  function renderKvList(initial, opts) {
    opts = opts || {}; const wrap = document.createElement('div'); wrap.className = 'xt-kv-list';
    function addRow(k, v) {
      const row = document.createElement('div'); row.className = 'xt-kv-row';
      const keyIn = document.createElement('input'); keyIn.type = 'text'; keyIn.placeholder = 'Key'; keyIn.value = k || '';
      const valIn = document.createElement('input'); valIn.type = 'text'; valIn.placeholder = opts.valuePlaceholder || 'Value'; valIn.value = v == null ? '' : String(v);
      const del = document.createElement('button'); del.type = 'button'; del.className = 'xt-kv-del'; del.textContent = '×';
      del.addEventListener('click', () => { wrap.removeChild(row); });
      row.appendChild(keyIn); row.appendChild(valIn); row.appendChild(del);
      wrap.insertBefore(row, addBtn);
    }
    const addBtn = document.createElement('button'); addBtn.type = 'button'; addBtn.className = 'xt-kv-add'; addBtn.textContent = '+ Add row';
    addBtn.addEventListener('click', () => addRow('', ''));
    wrap.appendChild(addBtn);
    if (initial && initial.length) for (const it of initial) addRow(it.key, it.value); else addRow('', '');
    return wrap;
  }
  function readKvList(wrap) {
    const out = []; wrap.querySelectorAll('.xt-kv-row').forEach((row) => {
      const inputs = row.querySelectorAll('input');
      if (!inputs[0]) return;
      const k = inputs[0].value.trim(); const v = inputs[1] ? inputs[1].value : '';
      if (k) out.push({ key: k, value: v });
    });
    return out;
  }
  function show(opts) {
    injectStyles();
    return new Promise((resolve) => {
      const overlay = document.createElement('div'); overlay.className = 'xt-modal-overlay';
      const modal = document.createElement('div'); modal.className = 'xt-modal';
      const head = document.createElement('div'); head.className = 'xt-modal-head';
      const tw = document.createElement('div');
      const title = document.createElement('h2'); title.className = 'xt-modal-title'; title.textContent = opts.title || ''; tw.appendChild(title);
      if (opts.description) { const d = document.createElement('p'); d.className = 'xt-modal-desc'; d.textContent = opts.description; tw.appendChild(d); }
      head.appendChild(tw);
      const x = document.createElement('button'); x.type = 'button'; x.className = 'xt-modal-x'; x.innerHTML = '&times;'; head.appendChild(x);
      modal.appendChild(head);
      const body = document.createElement('div'); body.className = 'xt-modal-body'; modal.appendChild(body);
      const errEl = document.createElement('div'); errEl.className = 'xt-modal-error'; errEl.hidden = true; body.appendChild(errEl);
      const refs = {};
      const fields = opts.fields || [];
      for (const f of fields) {
        const fd = document.createElement('div'); fd.className = 'xt-field';
        if (f.type === 'checkbox') fd.classList.add('xt-field-checkbox');
        if (f.label) {
          const lbl = document.createElement('label'); lbl.textContent = f.label;
          if (f.required) { const star = document.createElement('span'); star.className = 'xt-required'; star.textContent = ' *'; lbl.appendChild(star); }
          fd.appendChild(lbl);
        }
        let input;
        if (f.type === 'textarea') { input = document.createElement('textarea'); if (f.rows) input.rows = f.rows; if (f.placeholder) input.placeholder = f.placeholder; if (f.value != null) input.value = String(f.value); }
        else if (f.type === 'select') { input = document.createElement('select'); for (const o of (f.options || [])) { const opt = document.createElement('option'); opt.value = o.value; opt.textContent = o.label; input.appendChild(opt); } if (f.value != null) input.value = String(f.value); }
        else if (f.type === 'checkbox') { input = document.createElement('input'); input.type = 'checkbox'; input.checked = !!f.value; fd.insertBefore(input, fd.firstChild); }
        else if (f.type === 'kv') { input = renderKvList(f.value || []); }
        else if (f.type === 'kvtype') { const arr = Object.entries(f.value || {}).map(([k, v]) => ({ key: k, value: (v && typeof v === 'object' && v.type) ? v.type : (typeof v === 'string' ? v : 'text') })); input = renderKvList(arr, { valuePlaceholder: 'text|number|date|boolean|email' }); input.dataset.kind = 'kvtype'; }
        else { input = document.createElement('input'); input.type = f.type || 'text'; if (f.placeholder) input.placeholder = f.placeholder; if (f.value != null) input.value = String(f.value); if (f.min != null) input.min = String(f.min); if (f.max != null) input.max = String(f.max); if (f.step != null) input.step = String(f.step); }
        if (input.tagName !== 'DIV') fd.appendChild(input);
        if (f.help) { const help = document.createElement('div'); help.className = 'xt-help'; help.textContent = f.help; fd.appendChild(help); }
        refs[f.key] = { field: f, input: input };
        body.appendChild(fd);
      }
      const foot = document.createElement('div'); foot.className = 'xt-modal-footer';
      const cancelBtn = document.createElement('button'); cancelBtn.type = 'button'; cancelBtn.className = 'xt-btn-cancel'; cancelBtn.textContent = opts.cancelLabel || 'Cancel';
      const submitBtn = document.createElement('button'); submitBtn.type = 'button'; submitBtn.className = 'xt-btn-submit' + (opts.danger ? ' danger' : ''); submitBtn.textContent = opts.submitLabel || 'Save';
      foot.appendChild(cancelBtn); foot.appendChild(submitBtn);
      modal.appendChild(foot); overlay.appendChild(modal); document.body.appendChild(overlay);
      let closed = false;
      function close(r) { if (closed) return; closed = true; document.removeEventListener('keydown', onKey); if (overlay.parentNode) overlay.parentNode.removeChild(overlay); resolve(r); }
      function onKey(e) { if (e.key === 'Escape') { e.preventDefault(); close(null); } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); doSubmit(); } }
      document.addEventListener('keydown', onKey);
      x.addEventListener('click', () => close(null)); cancelBtn.addEventListener('click', () => close(null));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
      function readValue(ref) {
        const f = ref.field; const i = ref.input;
        if (f.type === 'checkbox') return !!i.checked;
        if (f.type === 'kv') return readKvList(i);
        if (f.type === 'kvtype') { const arr = readKvList(i); const out = {}; for (const it of arr) if (it.key) out[it.key] = { type: (it.value || 'text') }; return out; }
        if (f.type === 'number') { const v = i.value; if (v === '' || v == null) return null; const n = Number(v); return isFinite(n) ? n : null; }
        const v = i.value; return v === '' ? null : v;
      }
      function doSubmit() {
        errEl.hidden = true; errEl.textContent = '';
        const result = {};
        for (const key of Object.keys(refs)) {
          const ref = refs[key]; const val = readValue(ref);
          if (ref.field.required) { if (val == null || (typeof val === 'string' && !val.trim())) { errEl.textContent = (ref.field.label || ref.field.key) + ' is required.'; errEl.hidden = false; try { ref.input.focus(); } catch (_) {} return; } }
          result[key] = val;
        }
        if (typeof opts.validate === 'function') { const err = opts.validate(result); if (err) { errEl.textContent = err; errEl.hidden = false; return; } }
        close(result);
      }
      submitBtn.addEventListener('click', doSubmit);
      setTimeout(() => { const ff = fields.find((f) => f.type !== 'checkbox' && f.type !== 'kv' && f.type !== 'kvtype'); if (ff && refs[ff.key]) { try { refs[ff.key].input.focus(); } catch (_) {} } }, 0);
    });
  }
  window.AgixtFormModal = { show: show };
}
