/* Prompt Guidance bar.
 *
 * Vanilla-JS port of the web app's ResourceGuidanceCard
 * (web/components/ui/resource-guidance-card.tsx). The web app surfaces
 * per-page suggestions and clickable mini prompt-builders as a top
 * banner. The desktop app has a single always-visible agent chat with
 * content pages opening as side panes, so instead of a banner we pin a
 * compact suggestion bar to the bottom of the chat — directly above the
 * composer — and swap its contents to match whatever content page the
 * user currently has open (AgixtSidenav.getActiveView).
 *
 * Clicking a suggestion with no fields drops the prompt into the
 * composer and sends it. Clicking one with placeholders opens a small
 * builder modal to fill the fields first (mirrors the web's inline
 * prompt-builder), then sends (or hands off to the composer for edits).
 *
 * Data: prompt-guidance-data.js (window.AgixtPromptGuidanceData), keyed
 * by the web "resource" name, which matches the desktop extension/view
 * id for every ported page except where VIEW_ALIASES maps them.
 */
(function () {
  const DATA = window.AgixtPromptGuidanceData || {};
  // Desktop extension/view id -> web "resource" key when they differ.
  // The web "packages" page is the desktop "deployments" extension.
  const VIEW_ALIASES = { deployments: 'packages' };

  // Fallback shown whenever the active page has no ported, page-specific
  // guidance (plain chat, dashboard, network, settings, etc.). The set
  // is chosen by deployment platform because the client-side tool
  // surface differs: a native desktop build has full computer use +
  // local filesystem + shell; a mobile (Android/iOS) build can open
  // apps/URLs/settings and see the screen but has no shell/filesystem;
  // a plain web deployment has no client-side device tools at all. The
  // platform is resolved at init via the Tauri `client_platform`
  // command (see client-actions.js / src-tauri client_tool_specs).
  const DEFAULT_GUIDANCE_DESKTOP = {
    title: 'Put your agent to work on this computer',
    examples: [
      {
        label: 'See my screen & suggest next steps',
        prompt: 'Take a screenshot of my screen, describe what is currently open and what I appear to be working on, then suggest the 3 most useful things you could do for me right now.',
      },
      {
        label: 'Do this on screen for me',
        prompt: 'Using full computer control, do the following on my screen: {{task}}. Start by taking a screenshot to see the current state, work step by step, take screenshots to verify each step, and stop to tell me if anything looks risky before continuing.',
        placeholders: [
          { id: 'task', label: 'What should the agent do?', description: 'e.g. clean up my desktop icons into folders by type', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Open an app and set it up',
        prompt: 'Open {{app}} on this computer. Once it is open, take a screenshot, then {{goal}}. Verify it worked with a final screenshot and summarize what you changed.',
        placeholders: [
          { id: 'app', label: 'Application', description: 'e.g. Settings, Chrome, VS Code, Spotify', required: true, inputType: 'text' },
          { id: 'goal', label: 'What to do once it is open', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Find files on my computer',
        prompt: 'Search {{folder}} for files matching "{{what}}". List every match with its full path, size, and last-modified date, and give a one-line summary of what each file appears to be. Do not modify anything.',
        placeholders: [
          { id: 'what', label: 'What to look for', description: 'name, extension, or keyword', required: true, inputType: 'text' },
          { id: 'folder', label: 'Where to search', description: 'e.g. ~/Downloads, ~/Documents (defaults to home)', inputType: 'text' },
        ],
      },
      {
        label: 'Summarize a file or folder',
        prompt: 'Read {{path}} from my computer and give me a clear summary: what it is, the key points, anything that looks wrong or needs attention, and recommended next steps. If it is a folder, summarize its structure and the notable files first.',
        placeholders: [
          { id: 'path', label: 'File or folder path', required: true, inputType: 'text' },
        ],
      },
      {
        label: 'Run a command and explain it',
        prompt: 'Run this in a terminal on my computer: `{{command}}`. Show me the exact output, explain what it means in plain language, and flag anything concerning. Ask before running anything destructive.',
        placeholders: [
          { id: 'command', label: 'Command', required: true, inputType: 'text' },
        ],
      },
      {
        label: 'Troubleshoot something on my machine',
        prompt: 'Help me fix this problem on my computer: {{problem}}. Investigate using screenshots and terminal/diagnostic commands as needed, tell me the most likely root cause with evidence, then propose a fix and apply it once I approve. Do not make destructive changes without confirmation.',
        placeholders: [
          { id: 'problem', label: 'Describe the problem', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Automate a repetitive task',
        prompt: 'I regularly do this manually on my computer: {{routine}}. Watch what is on screen, work out the exact steps, then perform it for me end to end using computer control. Afterward, write the steps up as a repeatable runbook so we can schedule or automate it next time.',
        placeholders: [
          { id: 'routine', label: 'The routine you want automated', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Research this in my browser',
        prompt: 'Open my web browser and research: {{topic}}. Use the browser to visit relevant sources, take screenshots of key findings, then give me a concise briefing with the answer, the sources, and anything surprising.',
        placeholders: [
          { id: 'topic', label: 'What to research', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Organize a messy folder',
        prompt: 'Look at {{folder}} on my computer. Propose a clean organization scheme (subfolders by type/date/project), show me the plan with how many files go where, and once I approve, move the files into place and report exactly what moved. Never delete anything.',
        placeholders: [
          { id: 'folder', label: 'Folder to organize', description: 'e.g. ~/Downloads, ~/Desktop', required: true, inputType: 'text' },
        ],
      },
    ],
  };

  // Mobile (Android/iOS) build: the agent can look at the screen and
  // open apps / links / device settings, but there is no shell or
  // general filesystem, so the suggestions stay device- and
  // assistant-oriented rather than promising desktop-style control.
  const DEFAULT_GUIDANCE_MOBILE = {
    title: 'Put your agent to work on this device',
    examples: [
      {
        label: "See what's on my screen",
        prompt: "Look at what's currently on my screen, tell me what app or page I'm on, and suggest the most useful things you could help me with right here.",
      },
      {
        label: 'Open an app for me',
        prompt: 'Open the {{app}} app on my device. Once it is open, tell me what you see and {{goal}}.',
        placeholders: [
          { id: 'app', label: 'App name', description: 'e.g. Maps, Calendar, Gmail, Spotify', required: true, inputType: 'text' },
          { id: 'goal', label: 'What you want to do there', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Open a website & summarize it',
        prompt: 'Open {{url_or_topic}} in my browser, read the page, and give me a short plain-language summary of the key points plus anything I should act on.',
        placeholders: [
          { id: 'url_or_topic', label: 'URL or topic', required: true, inputType: 'text' },
        ],
      },
      {
        label: 'Change a device setting',
        prompt: 'I want to change this setting on my device: {{setting}}. Open the right device settings screen, walk me through it step by step, and confirm once it looks correct.',
        placeholders: [
          { id: 'setting', label: 'Setting to change', description: 'e.g. Wi-Fi, notifications, display brightness', required: true, inputType: 'text' },
        ],
      },
      {
        label: 'Research this for me',
        prompt: 'Research the following and give me a concise briefing with the answer, the key sources, and anything surprising: {{topic}}.',
        placeholders: [
          { id: 'topic', label: 'What to research', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Draft a message',
        prompt: 'Help me write {{what}}. Keep the tone {{tone}}, make it concise, and show me the draft for review before I send it anywhere.',
        placeholders: [
          { id: 'what', label: 'What to write', description: 'e.g. a reply to my landlord, a birthday text', required: true, inputType: 'textarea' },
          { id: 'tone', label: 'Tone', description: 'e.g. friendly, professional, apologetic', inputType: 'text' },
        ],
      },
      {
        label: 'Summarize something I paste',
        prompt: "I'll paste some text, an email, or a message thread next. Summarize it for me: the key points, who needs what, and the single most useful next step.",
      },
      {
        label: 'Set up a reminder or recurring check-in',
        prompt: 'Set up a {{cadence}} task that {{task}} and messages me with the results. Confirm the schedule with me before creating it.',
        placeholders: [
          { id: 'task', label: 'What it should do', required: true, inputType: 'textarea' },
          { id: 'cadence', label: 'How often', description: 'e.g. every morning, weekly on Monday', required: true, inputType: 'text' },
        ],
      },
    ],
  };

  // Plain web deployment (no Tauri): no client-side device tools at all.
  // Keep suggestions to what any agent can do server-side — research,
  // drafting, analysis, planning, and scheduling with its abilities.
  const DEFAULT_GUIDANCE_WEB = {
    title: 'Get started with your agent',
    examples: [
      {
        label: 'What can you help me with?',
        prompt: 'Based on your currently enabled abilities and tools, give me a short, concrete list of the most useful things you can do for me right now, with an example request for each.',
      },
      {
        label: 'Research a topic',
        prompt: 'Research the following and give me a concise briefing with the answer, the key sources, and anything surprising: {{topic}}.',
        placeholders: [
          { id: 'topic', label: 'What to research', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Draft something for me',
        prompt: 'Help me write {{what}}. Keep the tone {{tone}}, make it clear and concise, and show me the draft for review.',
        placeholders: [
          { id: 'what', label: 'What to write', description: 'e.g. a project proposal, a customer email', required: true, inputType: 'textarea' },
          { id: 'tone', label: 'Tone', description: 'e.g. professional, friendly, persuasive', inputType: 'text' },
        ],
      },
      {
        label: 'Summarize text I paste',
        prompt: "I'll paste a document, email, or thread next. Summarize it: the key points, decisions or asks, risks, and the most useful next step.",
      },
      {
        label: 'Plan a project',
        prompt: 'Help me plan this: {{goal}}. Break it into phases and concrete tasks, call out dependencies and risks, and propose a realistic order of operations.',
        placeholders: [
          { id: 'goal', label: 'What you want to accomplish', required: true, inputType: 'textarea' },
        ],
      },
      {
        label: 'Analyze data I provide',
        prompt: "I'll provide some data (paste it or attach a file) next. Analyze it for the trends, outliers, and takeaways that matter most, and recommend what I should do about them.",
      },
      {
        label: 'Set up a recurring report',
        prompt: 'Set up a {{cadence}} task that {{task}} and messages me with the results. Confirm the schedule with me before creating it.',
        placeholders: [
          { id: 'task', label: 'What the report should cover', required: true, inputType: 'textarea' },
          { id: 'cadence', label: 'How often', description: 'e.g. every Monday 9am, daily', required: true, inputType: 'text' },
        ],
      },
    ],
  };

  const DEFAULTS_BY_TIER = {
    desktop: DEFAULT_GUIDANCE_DESKTOP,
    mobile: DEFAULT_GUIDANCE_MOBILE,
    web: DEFAULT_GUIDANCE_WEB,
  };
  const DEFAULT_KEY = '__default__';

  // Synchronous best-guess: a Tauri build is the desktop client until
  // client_platform tells us it's mobile; no Tauri means a web build.
  let platformTier = (window.__TAURI__
    && window.__TAURI__.core
    && typeof window.__TAURI__.core.invoke === 'function')
    ? 'desktop'
    : 'web';

  // Refine the guess once the native side answers. Only the desktop ->
  // mobile correction matters in practice (web has no Tauri to ask).
  function detectPlatformTier() {
    const invoke = window.__TAURI__
      && window.__TAURI__.core
      && window.__TAURI__.core.invoke;
    if (typeof invoke !== 'function') return;
    Promise.resolve()
      .then(() => invoke('client_platform'))
      .then((info) => {
        if (!info) return;
        const next = info.mobile ? 'mobile' : 'desktop';
        if (next === platformTier) return;
        platformTier = next;
        // Force the next render to rebuild even if the view is unchanged.
        currentView = null;
        if (containerEl) containerEl.removeAttribute('data-key');
        render();
      })
      .catch(() => { /* keep the synchronous best-guess */ });
  }

  function defaultGuidance() {
    return DEFAULTS_BY_TIER[platformTier] || DEFAULT_GUIDANCE_DESKTOP;
  }

  const COLLAPSE_KEY = 'agixt.desktop.promptGuidance.collapsed.v1';
  let containerEl = null;
  let currentView = null;
  let collapsed = loadCollapsed();
  let modalEl = null;

  function loadCollapsed() {
    try { return window.localStorage.getItem(COLLAPSE_KEY) === '1'; }
    catch (_) { return false; }
  }
  function saveCollapsed(v) {
    try { window.localStorage.setItem(COLLAPSE_KEY, v ? '1' : '0'); }
    catch (_) {}
  }

  function resourceKeyFor(viewId) {
    if (!viewId) return null;
    if (DATA[viewId]) return viewId;
    const alias = VIEW_ALIASES[viewId];
    if (alias && DATA[alias]) return alias;
    return null;
  }

  function activeViewId() {
    const sn = window.AgixtSidenav;
    if (sn && typeof sn.getActiveView === 'function') {
      const v = sn.getActiveView();
      if (v) return v;
    }
    const btn = document.querySelector('.sidenav-btn.is-active[data-view]');
    if (btn && btn.dataset.view) return btn.dataset.view;
    return 'chat';
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ---- prompt composition / sending -----------------------------------

  function substitute(prompt, placeholders, values) {
    let out = prompt;
    (placeholders || []).forEach((ph) => {
      const raw = values[ph.id];
      const v = (raw != null && String(raw).trim())
        ? String(raw).trim()
        : (ph.label || ph.id);
      const safeId = String(ph.id).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp('\\{\\{\\s*' + safeId + '\\s*\\}\\}', 'gi');
      out = out.replace(re, v);
    });
    return out;
  }

  // Reuse the composer's full send path (conversation creation, turn
  // context, attachments) by writing into the textarea and clicking the
  // existing send button — exactly what a user typing the prompt would
  // trigger. While the agent is generating the send button is hidden
  // (swapped for stop), so we leave the composed prompt staged instead
  // of silently dropping it.
  function putInComposer(text) {
    const input = document.getElementById('composer-input');
    if (!input) return false;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
    return true;
  }

  function sendPrompt(text) {
    if (!putInComposer(text)) return;
    const sendBtn = document.getElementById('btn-send');
    if (sendBtn && !sendBtn.hidden) {
      sendBtn.click();
    } else if (window.AgixtChat
        && typeof window.AgixtChat.setComposerStatus === 'function') {
      window.AgixtChat.setComposerStatus(
        'Prompt ready — press Enter to send once the agent is idle.', '');
    }
  }

  // ---- builder modal ---------------------------------------------------

  function onModalKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); closeModal(); }
  }

  function closeModal() {
    if (modalEl) {
      modalEl.classList.remove('open');
      modalEl.remove();
      modalEl = null;
    }
    document.removeEventListener('keydown', onModalKey, true);
  }

  function openBuilder(example) {
    closeModal();
    const phs = example.placeholders || [];
    const modal = el('div', 'modal prompt-guidance-modal');
    const card = el('div', 'modal-card');

    const header = el('div', 'modal-header');
    header.appendChild(el('h2', null, example.label || 'Prompt builder'));
    const close = el('button', 'modal-close');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close');
    close.textContent = '✕';
    close.addEventListener('click', closeModal);
    header.appendChild(close);

    const body = el('div', 'modal-body');
    const inputs = {};
    phs.forEach((ph) => {
      const field = el('label', 'pg-field');
      field.appendChild(el('span', 'pg-field-label',
        (ph.label || ph.id) + (ph.required ? ' *' : '')));
      if (ph.description) {
        field.appendChild(el('span', 'pg-field-desc', ph.description));
      }
      let ctrl;
      if (ph.inputType === 'select'
          && Array.isArray(ph.options) && ph.options.length) {
        ctrl = el('select', 'pg-input');
        const blank = el('option', null,
          ph.required ? 'Select…' : '(optional)');
        blank.value = '';
        ctrl.appendChild(blank);
        ph.options.forEach((o) => {
          const op = el('option', null, o.label != null ? o.label : o.value);
          op.value = o.value;
          ctrl.appendChild(op);
        });
      } else if (ph.inputType === 'textarea') {
        ctrl = el('textarea', 'pg-input');
        ctrl.rows = 3;
      } else {
        ctrl = el('input', 'pg-input');
        ctrl.type = 'text';
      }
      ctrl.placeholder = ph.label || ph.id;
      inputs[ph.id] = ctrl;
      ctrl.addEventListener('input', validate);
      ctrl.addEventListener('change', validate);
      field.appendChild(ctrl);
      body.appendChild(field);
    });

    body.appendChild(el('span', 'pg-field-label', 'Preview'));
    const preview = el('div', 'pg-preview');
    body.appendChild(preview);

    const actions = el('div', 'pg-actions');
    const cancel = el('button', 'btn btn-secondary', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', closeModal);
    const fillBtn = el('button', 'btn btn-secondary', 'Edit in composer');
    fillBtn.type = 'button';
    const sendBtn = el('button', 'btn btn-primary', 'Send to chat');
    sendBtn.type = 'button';
    actions.appendChild(cancel);
    actions.appendChild(fillBtn);
    actions.appendChild(sendBtn);
    body.appendChild(actions);

    function readValues() {
      const v = {};
      Object.keys(inputs).forEach((k) => { v[k] = inputs[k].value; });
      return v;
    }
    function validate() {
      const ok = phs.every((ph) => !ph.required
        || (inputs[ph.id] && inputs[ph.id].value.trim()));
      sendBtn.disabled = !ok;
      fillBtn.disabled = !ok;
      preview.textContent = substitute(example.prompt, phs, readValues());
      return ok;
    }
    fillBtn.addEventListener('click', () => {
      if (!validate()) return;
      putInComposer(substitute(example.prompt, phs, readValues()));
      closeModal();
    });
    sendBtn.addEventListener('click', () => {
      if (!validate()) return;
      sendPrompt(substitute(example.prompt, phs, readValues()));
      closeModal();
    });

    card.appendChild(header);
    card.appendChild(body);
    modal.appendChild(card);
    modal.addEventListener('mousedown', (e) => {
      if (e.target === modal) closeModal();
    });
    document.body.appendChild(modal);
    modalEl = modal;
    requestAnimationFrame(() => modal.classList.add('open'));
    document.addEventListener('keydown', onModalKey, true);
    validate();
    const firstId = phs.length ? phs[0].id : null;
    if (firstId && inputs[firstId]) inputs[firstId].focus();
  }

  function onChipClick(example) {
    if (example.placeholders && example.placeholders.length) {
      openBuilder(example);
    } else {
      sendPrompt(example.prompt);
    }
  }

  // ---- bar render ------------------------------------------------------

  function applyCollapsed() {
    if (!containerEl) return;
    containerEl.classList.toggle('is-collapsed', collapsed);
    const toggle = containerEl.querySelector('.pg-bar-toggle');
    if (toggle) {
      toggle.textContent = collapsed ? 'Show suggestions' : 'Hide';
      toggle.setAttribute('aria-label',
        collapsed ? 'Show suggestions' : 'Hide suggestions');
    }
  }

  function render() {
    if (!containerEl) return;
    const viewId = activeViewId();
    const key = resourceKeyFor(viewId);
    let data = key ? DATA[key] : null;
    let resolvedKey = key;
    // Fall back to the platform-appropriate defaults whenever the page
    // has no specific guidance, so the bar is always useful.
    if (!data || !Array.isArray(data.examples) || !data.examples.length) {
      data = defaultGuidance();
      resolvedKey = DEFAULT_KEY;
    }
    // Skip a rebuild when nothing relevant changed (the view-changed and
    // extension-context-changed events can fire repeatedly).
    if (currentView === viewId
        && containerEl.dataset.key === resolvedKey
        && !containerEl.hidden) return;
    currentView = viewId;
    containerEl.dataset.key = resolvedKey;
    containerEl.hidden = false;
    containerEl.innerHTML = '';

    const headerRow = el('div', 'pg-bar-header');
    const titleWrap = el('div', 'pg-bar-titlewrap');
    titleWrap.appendChild(el('span', 'pg-bar-spark', '✦'));
    titleWrap.appendChild(el('span', 'pg-bar-title',
      data.title || 'Try asking'));
    headerRow.appendChild(titleWrap);
    const toggle = el('button', 'pg-bar-toggle');
    toggle.type = 'button';
    toggle.addEventListener('click', () => {
      collapsed = !collapsed;
      saveCollapsed(collapsed);
      applyCollapsed();
    });
    headerRow.appendChild(toggle);
    containerEl.appendChild(headerRow);

    const chips = el('div', 'pg-chips');
    data.examples.forEach((ex) => {
      const chip = el('button', 'pg-chip');
      chip.type = 'button';
      chip.title = ex.label || ex.prompt;
      chip.appendChild(el('span', 'pg-chip-label',
        ex.label || ex.prompt.slice(0, 60)));
      if (ex.placeholders && ex.placeholders.length) {
        chip.appendChild(el('span', 'pg-chip-badge', '✎'));
      }
      chip.addEventListener('click', () => onChipClick(ex));
      chips.appendChild(chip);
    });
    containerEl.appendChild(chips);
    applyCollapsed();
  }

  function init() {
    containerEl = document.getElementById('prompt-guidance');
    if (!containerEl) return;
    render();
    detectPlatformTier();
    window.addEventListener('agixt-view-changed', render);
    // A late extension manifest can add the currently-active extension
    // after the first render; its context-registration event lets the
    // bar pick up guidance for a page that wasn't known at nav time.
    window.addEventListener('agixt-extension-context-changed', render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.AgixtPromptGuidance = { render, open: openBuilder };
})();
