/* App orchestrator. Decides whether to show the auth screen or the chat
 * screen, then wires the chat screen up the way it always did once we
 * have a JWT.
 */
(function () {
  const tauri = window.__TAURI__;
  if (!tauri) {
    const dot = document.getElementById('connection-state');
    if (dot) {
      dot.className = 'brand-conn error';
      dot.title = 'Tauri IPC unavailable';
    }
    return;
  }
  const invoke = tauri.core.invoke;
  const event = tauri.event;
  const frontendLog = window.AgixtFrontendLog || function () {};
  frontendLog('info', 'app.js boot');

  let settings = null;
  let companies = [];
  let agents = [];
  let conversationName = null;

  // ----- DOM -----
  const $ = (id) => document.getElementById(id);
  const composerInput = $('composer-input');
  const sendBtn = $('btn-send');
  const stopBtn = $('btn-stop');
  const newConvoBtn = $('btn-new-conversation');
  const settingsBtn = $('btn-settings');
  const collapseBtn = $('btn-collapse');
  const micBtn = $('btn-mic');
  const attachBtn = $('btn-attach');
  const attachmentsEl = $('attachments');
  const settingsModal = $('settings-modal');
  const settingsClose = $('btn-settings-close');
  const saveSettingsBtn = $('btn-save-settings');
  const logoutBtn = $('btn-logout');
  const settingsStatus = $('settings-status');
  const settingsUser = $('settings-user');
  const sudoPasswordInput = $('setting-sudo-password');
  const sudoAuthBtn = $('btn-sudo-auth');
  const sudoClearBtn = $('btn-sudo-clear');
  const sudoSessionStatus = $('sudo-session-status');
  const agentBtn = $('agent-switcher-btn');
  const agentLabel = $('agent-switcher-label');
  const agentMenu = $('agent-menu');
  const agentMenuList = $('agent-menu-list');
  const convoBtn = $('convo-switcher-btn');
  const convoLabel = $('convo-switcher-label');
  const convoMenu = $('convo-menu');
  const convoMenuList = $('convo-menu-list');
  const convoNewBtn = $('convo-new-btn');

  function setSettingsStatus(text, cls) {
    settingsStatus.textContent = text || '';
    settingsStatus.className = 'settings-status' + (cls ? ' ' + cls : '');
  }

  function setSudoSessionStatus(text, cls) {
    if (!sudoSessionStatus) return;
    sudoSessionStatus.textContent = text || '';
    sudoSessionStatus.className = 'sudo-session-status' + (cls ? ' ' + cls : '');
  }

  // ----- Screen switching --------------------------------------------------

  function showScreen(which) {
    const auth = which === 'auth';
    $('auth-screen').hidden = !auth;
    $('chat-screen').hidden = auth;
    // When showing auth, also disable the new-convo button etc. so users
    // don't get a weird state.
    [newConvoBtn].forEach((b) => { if (b) b.disabled = auth; });
  }

  // ----- Settings load / save ---------------------------------------------

  async function loadSettings() {
    settings = await invoke('get_settings');
    $('setting-allow-commands').checked = !!settings.allow_client_commands;
    $('setting-voice').checked = !!settings.voice_enabled;
    settingsUser.textContent = settings.user_email
      ? `${settings.user_email} @ ${settings.server_url}`
      : `not signed in`;
    // Apply the saved service branding to the topbar logo. Without this,
    // returning users always see the default AGiXT mark even when they
    // picked a different brand (e.g. BoltRemote) on first login.
    if (window.AgixtBranding && settings.service_brand) {
      window.AgixtBranding.apply(settings.service_brand);
    }
  }

  async function persistSettings(patch) {
    settings = { ...settings, ...patch };
    settings = await invoke('save_settings', { settings });
  }

  async function onSaveSettings() {
    setSettingsStatus('Saving…');
    try {
      await persistSettings({
        allow_client_commands: $('setting-allow-commands').checked,
        voice_enabled: $('setting-voice').checked,
      });
      setSettingsStatus('Saved.', 'success');
      await refreshSudoStatus();
    } catch (err) {
      setSettingsStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  async function refreshSudoStatus() {
    if (!settings || !sudoSessionStatus) return;
    if (!settings.allow_client_commands) {
      setSudoSessionStatus('Client commands disabled.', 'error');
      return;
    }
    setSudoSessionStatus('Checking…');
    try {
      const result = await invoke('sudo_status');
      if (result && result.authenticated) {
        setSudoSessionStatus('Authenticated.', 'success');
      } else {
        setSudoSessionStatus('Needs authentication.');
      }
    } catch (err) {
      const message = err && err.error ? err.error : String(err);
      if (/client commands are disabled/i.test(message)) {
        setSudoSessionStatus('Client commands disabled.', 'error');
      } else {
        setSudoSessionStatus('Needs authentication.');
      }
    }
  }

  async function onSudoAuth() {
    if (!sudoPasswordInput) return;
    const password = sudoPasswordInput.value;
    if (!password) {
      setSudoSessionStatus('Enter your sudo password.', 'error');
      sudoPasswordInput.focus();
      return;
    }
    setSudoSessionStatus('Authenticating…');
    try {
      await invoke('sudo_auth', { password });
      sudoPasswordInput.value = '';
      setSudoSessionStatus('Authenticated.', 'success');
    } catch (err) {
      setSudoSessionStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  async function onSudoClear() {
    setSudoSessionStatus('Forgetting…');
    try {
      await invoke('sudo_clear');
      if (sudoPasswordInput) sudoPasswordInput.value = '';
      setSudoSessionStatus('Forgotten.');
    } catch (err) {
      setSudoSessionStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  async function onLogout() {
    setSettingsStatus('Logging out…');
    try {
      await invoke('logout');
      window.AgixtChat.disconnect();
      window.AgixtChat.clear();
      companies = [];
      agents = [];
      renderSelectors();
      setSettingsStatus('Logged out.', 'success');
      // Close the settings modal and bounce back to the auth screen.
      closeSettings();
      showScreen('auth');
      await loadSettings();
      if (window.AgixtAuth) {
        window.AgixtAuth.boot({ onAuthenticated });
      }
    } catch (err) {
      setSettingsStatus(err && err.error ? err.error : String(err), 'error');
    }
  }

  // ----- Agent & company selectors ----------------------------------------

  function companyName(companyId) {
    if (!companyId) return '';
    const c = companies.find((x) => x.id === companyId);
    return (c && c.name) || '';
  }

  function renderSelectors() {
    // Header chip: "Agent @ Company".
    const aname = settings.agent_name || '—';
    const cname = companyName(settings.company_id) || settings.company_name || '';
    agentLabel.textContent = cname ? `${aname} @ ${cname}` : aname;
    // Composer placeholder mirrors the active agent so the user knows
    // which agent picks up their next prompt.
    if (composerInput) {
      composerInput.placeholder = aname && aname !== '—'
        ? `Ask ${aname}…`
        : 'Ask the agent…';
    }

    // Build the dropdown listing every reachable agent, grouped by company.
    agentMenuList.innerHTML = '';
    const everyAgent = agentEntriesAcrossCompanies();
    if (!everyAgent.length) {
      const empty = document.createElement('div');
      empty.className = 'popover-menu-item';
      empty.style.color = 'var(--text-faint)';
      empty.textContent = 'No agents available';
      agentMenuList.appendChild(empty);
    } else {
      everyAgent.forEach((entry) => {
        const item = document.createElement('button');
        item.className = 'popover-menu-item';
        item.type = 'button';
        const isSelected = entry.agent.id === settings.agent_id;
        if (isSelected) item.classList.add('is-selected');
        item.innerHTML =
          `<span class="popover-menu-check">${isSelected ? '✓' : ''}</span>` +
          `<span class="agent-name"></span>` +
          `<span class="agent-company"></span>`;
        item.querySelector('.agent-name').textContent = entry.agent.name || entry.agent.id;
        item.querySelector('.agent-company').textContent =
          entry.company ? `@${entry.company.name}` : '';
        item.addEventListener('click', () => onPickAgent(entry));
        agentMenuList.appendChild(item);
      });
    }
  }

  // Returns every (agent, company) pair the user can reach. AGiXT's
  // /v1/companies response on the desktop does NOT include a nested
  // `agents` list per company — that was only true for older API
  // shapes — so we resolve the company for each agent by matching
  // agent.company_id against the companies list. Falls back to
  // company-less entries when no match exists (shouldn't happen for
  // properly-scoped agents, but keeps the dropdown populated).
  function agentEntriesAcrossCompanies() {
    const out = [];
    if (agents.length) {
      agents.forEach((a) => {
        const c = a.company_id
          ? companies.find((co) => co.id === a.company_id) || null
          : null;
        out.push({ agent: a, company: c });
      });
    } else if (companies.length) {
      companies.forEach((c) => {
        (c.agents || []).forEach((a) => out.push({ agent: a, company: c }));
      });
    }
    return out;
  }

  async function onPickAgent(entry) {
    closeMenus();
    const a = entry.agent;
    const c = entry.company;
    await persistSettings({
      agent_id: a.id,
      agent_name: a.name,
      company_id: c ? c.id : settings.company_id,
      company_name: c ? c.name : settings.company_name,
    });
    renderSelectors();
    reconnectChat();
  }

  function filteredAgents() {
    // Used internally to pick a default agent when none is set yet.
    if (!agents.length) return [];
    if (!settings.company_id) return agents;
    const company = companies.find((c) => c.id === settings.company_id);
    if (company && Array.isArray(company.agents) && company.agents.length) {
      return company.agents;
    }
    return agents.filter((a) => !a.company_id || a.company_id === settings.company_id);
  }

  async function refreshAgentsAndCompanies() {
    if (!settings.jwt) {
      companies = [];
      agents = [];
      renderSelectors();
      return;
    }
    try {
      companies = await invoke('list_companies');
    } catch (err) {
      console.warn('list_companies failed', err);
      companies = [];
    }
    try {
      agents = await invoke('list_agents');
    } catch (err) {
      console.warn('list_agents failed', err);
      agents = [];
    }

    if (!settings.company_id && companies.length) {
      const primary = companies.find((c) => c.primary) || companies[0];
      await persistSettings({ company_id: primary.id, company_name: primary.name });
    }
    const eligible = filteredAgents();
    if (!settings.agent_id && eligible.length) {
      const def = eligible.find((a) => a.default) || eligible[0];
      await persistSettings({ agent_id: def.id, agent_name: def.name });
    }
    renderSelectors();
  }

  // ----- Popover menus (agent + conversation) -----

  function openMenu(which) {
    closeMenus();
    if (which === 'agent') {
      agentMenu.hidden = false;
      agentBtn.setAttribute('aria-expanded', 'true');
    } else if (which === 'convo') {
      convoMenu.hidden = false;
      convoBtn.setAttribute('aria-expanded', 'true');
      // Autofocus the search field so the user can start typing
      // immediately. Reset prior search so the full list shows first.
      if (convoSearchInput) {
        convoSearchInput.value = '';
        convoSearchTerm = '';
        setTimeout(() => convoSearchInput.focus(), 0);
      }
      refreshConversations();
    }
  }
  function closeMenus() {
    agentMenu.hidden = true;
    convoMenu.hidden = true;
    agentBtn.setAttribute('aria-expanded', 'false');
    convoBtn.setAttribute('aria-expanded', 'false');
  }
  agentBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (agentMenu.hidden) openMenu('agent'); else closeMenus();
  });
  convoBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (convoMenu.hidden) openMenu('convo'); else closeMenus();
  });
  document.addEventListener('click', (e) => {
    if (!agentMenu.hidden && !agentMenu.contains(e.target) && e.target !== agentBtn) closeMenus();
    if (!convoMenu.hidden && !convoMenu.contains(e.target) && e.target !== convoBtn) closeMenus();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (!agentMenu.hidden || !convoMenu.hidden)) closeMenus();
  });

  // ----- Conversation switcher -----

  let conversations = [];
  let convoSearchTerm = '';

  async function refreshConversations() {
    if (!settings.jwt) {
      convoMenuList.innerHTML = '<div class="popover-menu-item" style="color:var(--text-faint)">Sign in to see conversations</div>';
      return;
    }
    try {
      conversations = await invoke('list_conversations');
    } catch (e) {
      console.warn('list_conversations failed', e);
      conversations = [];
    }
    renderConversationList();
  }

  function renderConversationList() {
    convoMenuList.innerHTML = '';
    const term = convoSearchTerm.trim().toLowerCase();
    const filtered = term
      ? conversations.filter((c) => (c.name || '').toLowerCase().includes(term))
      : conversations;
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'popover-menu-item';
      empty.style.color = 'var(--text-faint)';
      empty.textContent = term ? 'No matching conversations' : 'No conversations yet';
      convoMenuList.appendChild(empty);
      return;
    }
    filtered.slice(0, 200).forEach((conv) => {
      const item = document.createElement('button');
      item.className = 'popover-menu-item';
      item.type = 'button';
      const isSelected = conv.id === settings.conversation_id;
      if (isSelected) item.classList.add('is-selected');
      item.innerHTML =
        `<span class="popover-menu-check">${isSelected ? '✓' : ''}</span>` +
        `<span class="convo-meta">` +
          `<span class="convo-name"></span>` +
          (conv.updated_at ? `<span class="convo-time"></span>` : '') +
        `</span>`;
      item.querySelector('.convo-name').textContent = prettyConvoName(conv);
      const t = item.querySelector('.convo-time');
      if (t && conv.updated_at) t.textContent = formatRelative(conv.updated_at);
      item.addEventListener('click', () => onPickConversation(conv));
      convoMenuList.appendChild(item);
    });
  }

  // Live-filter as the user types in the search box.
  const convoSearchInput = $('convo-search');
  if (convoSearchInput) {
    convoSearchInput.addEventListener('input', () => {
      convoSearchTerm = convoSearchInput.value;
      renderConversationList();
    });
  }

  function formatRelative(iso) {
    const ms = Date.parse(iso);
    if (!isFinite(ms)) return '';
    const diff = Date.now() - ms;
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
    return `${Math.round(diff / 86_400_000)}d ago`;
  }

  async function onPickConversation(conv) {
    closeMenus();
    if (conv.id === settings.conversation_id) return;
    try {
      await invoke('select_conversation', { id: conv.id, name: conv.name });
      settings = await invoke('get_settings');
      conversationName = conv.name;
      updateConvoLabel();
      // Reconnect the WebSocket FIRST (it uses the new conversation_id)
      // so any concurrent live messages funnel into the right thread,
      // then replay the historical messages through the same ingest()
      // path. The clear() that loadHistory does is safe because the
      // chat panel's previous content was for a different conversation.
      reconnectChat();
      await window.AgixtChat.loadHistory(conv.id);
    } catch (e) {
      console.warn('select_conversation failed', e);
    }
  }

  function prettyConvoName(conv) {
    if (!conv) return 'New conversation';
    const raw = (conv.name || '').trim();
    if (!raw || raw === '-') return 'New conversation';
    return raw;
  }

  function updateConvoLabel() {
    // Prefer the persisted name on settings — it's available immediately
    // on boot, before refreshConversations() has populated the full
    // conversation list. Fall back to a match in the list (e.g. when the
    // server renames a "-" conversation), then to the unnamed default.
    const persisted = (settings.conversation_name || '').trim();
    if (persisted && persisted !== '-') {
      convoLabel.textContent = persisted;
      return;
    }
    const cur = conversations.find((c) => c.id === settings.conversation_id);
    convoLabel.textContent = cur ? prettyConvoName(cur) : 'New conversation';
  }

  if (convoNewBtn) {
    convoNewBtn.addEventListener('click', async () => {
      closeMenus();
      await startNewConversation();
    });
  }

  // ----- Conversation lifecycle -------------------------------------------

  async function ensureConversation() {
    if (!settings.jwt) return;
    if (settings.conversation_id) {
      conversationName = settings.conversation_name || '-';
      return;
    }
    try {
      // Match the web app's new-conversation convention. AGiXT treats
      // "-" as the unnamed placeholder and runs the normal rename workflow
      // after the first exchange instead of leaving desktop timestamp names.
      const name = '-';
      await invoke('new_conversation', { name });
      settings = await invoke('get_settings');
      conversationName = name;
    } catch (err) {
      console.warn('new_conversation failed', err);
    }
  }

  async function startNewConversation() {
    window.AgixtChat.clear();
    settings = { ...settings, conversation_id: null, conversation_name: null };
    await invoke('save_settings', { settings });
    await ensureConversation();
    reconnectChat();
    // The toolbar `+` button used to leave the chip showing the previous
    // conversation's name. Refresh from inside startNewConversation so
    // every caller (toolbar `+`, dropdown's "+ New conversation", auth
    // boot) ends up with the chip in sync — and the label snaps to
    // "New conversation" until AGiXT auto-renames the "-" placeholder.
    updateConvoLabel();
  }

  function reconnectChat() {
    if (!settings.jwt || !settings.conversation_id) return;
    window.AgixtChat.configure({
      serverUrl: settings.server_url,
      jwt: settings.jwt,
      conversationId: settings.conversation_id,
    });
  }

  // ----- Composer ---------------------------------------------------------

  function autoResize() {
    composerInput.style.height = 'auto';
    composerInput.style.height = Math.min(composerInput.scrollHeight, 160) + 'px';
  }
  composerInput.addEventListener('input', autoResize);
  composerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      frontendLog('info', 'composer enter pressed');
      e.preventDefault();
      sendCurrent();
    }
  });

  // ----- Attachments -------------------------------------------------------
  // The "attachment" model is a context handoff, NOT an upload. The
  // selected files stay on the user's desktop. We tell the agent
  // "the user has attached these files" and include the absolute paths
  // so it can reach for fs_read / shell_run / workspace_upload via the
  // already-installed desktop tools. The chips are local-only state and
  // get cleared after the message is sent.
  let attachedFiles = [];

  function basename(p) {
    if (!p) return '';
    const m = String(p).match(/[^\\\/]+$/);
    return m ? m[0] : String(p);
  }

  function renderAttachments() {
    if (!attachmentsEl) return;
    attachmentsEl.innerHTML = '';
    if (!attachedFiles.length) {
      attachmentsEl.hidden = true;
      return;
    }
    attachedFiles.forEach((path, idx) => {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      chip.title = path;
      const name = document.createElement('span');
      name.className = 'attachment-name';
      name.textContent = basename(path);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'attachment-remove';
      remove.setAttribute('aria-label', `Remove ${basename(path)}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        attachedFiles.splice(idx, 1);
        renderAttachments();
      });
      chip.appendChild(name);
      chip.appendChild(remove);
      attachmentsEl.appendChild(chip);
    });
    attachmentsEl.hidden = false;
  }

  async function pickAttachments() {
    const dlg = tauri && tauri.dialog && tauri.dialog.open;
    if (!dlg) {
      window.AgixtChat.setComposerStatus('File picker unavailable', 'error');
      return;
    }
    let result;
    try {
      result = await tauri.dialog.open({
        multiple: true,
        directory: false,
        title: 'Attach files to send to the agent',
      });
    } catch (err) {
      window.AgixtChat.setComposerStatus(String((err && err.message) || err), 'error');
      return;
    }
    if (!result) return;
    const picks = Array.isArray(result) ? result : [result];
    for (const p of picks) {
      const path = typeof p === 'string' ? p : (p && p.path) || '';
      if (!path) continue;
      if (!attachedFiles.includes(path)) attachedFiles.push(path);
    }
    renderAttachments();
  }

  if (attachBtn) attachBtn.addEventListener('click', pickAttachments);

  // Build the context block sent to the agent for the attached files.
  // Phrasing primes the model that the *user* attached them deliberately
  // and that they live on disk — not in the AGiXT workspace — so it
  // reaches for fs_read / shell_run / workspace_upload instead of
  // assuming an attachment was already uploaded server-side.
  function buildAttachmentsPrefix(files) {
    if (!files || !files.length) return '';
    const list = files.map((p) => `- ${p}`).join('\n');
    return [
      'The user has attached the following file(s) from their local desktop',
      'to this message. These paths are on the user\'s machine — not in the',
      'AGiXT workspace. Use the desktop tools (fs_read, fs_list, shell_run,',
      'workspace_upload, etc.) to inspect, read, or otherwise interact with',
      'the files as needed to answer the user\'s request.',
      '',
      list,
      '',
      '---',
      '',
    ].join('\n');
  }

  async function sendCurrent() {
    frontendLog('info', 'sendCurrent invoked');
    try {
      if (!settings) await loadSettings();
      const text = composerInput.value;
      if (!text || !text.trim()) {
        frontendLog('info', 'sendCurrent ignored empty text');
        return;
      }
      if (!settings.jwt) {
        window.AgixtChat.setComposerStatus('Sign in first.', 'error');
        frontendLog('warn', 'sendCurrent blocked: missing jwt');
        return;
      }
      if (!settings.conversation_id) await ensureConversation();
      const filesForTurn = attachedFiles.slice();
      const prefixed = filesForTurn.length
        ? buildAttachmentsPrefix(filesForTurn) + text
        : text;
      composerInput.value = '';
      autoResize();
      // Clear chips before the await so a follow-up keystroke can't
      // accidentally re-include the same attachments on the next turn.
      attachedFiles = [];
      renderAttachments();
      frontendLog('info', `sendCurrent sending chat (attachments=${filesForTurn.length})`);
      await window.AgixtChat.send(prefixed, conversationName || settings.conversation_name || '-');
    } catch (err) {
      const message = err && err.error ? err.error : String(err);
      window.AgixtChat.setComposerStatus(message, 'error');
      frontendLog('error', 'sendCurrent failed', message);
      console.warn('sendCurrent failed', err);
    }
  }

  sendBtn.addEventListener('click', () => {
    frontendLog('info', 'send button clicked');
    sendCurrent();
  });
  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      frontendLog('info', 'stop button clicked');
      try { await window.AgixtChat.stop(); }
      catch (e) { console.warn('stop failed', e); }
    });
  }
  // Subscribe to chat.js's generating signal so we can swap the
  // send/stop affordance in the same composer slot, mirroring the web
  // app's behavior.
  if (window.AgixtChat && typeof window.AgixtChat.onGeneratingChange === 'function') {
    window.AgixtChat.onGeneratingChange((on) => {
      if (sendBtn) sendBtn.hidden = !!on;
      if (stopBtn) stopBtn.hidden = !on;
    });
  }
  newConvoBtn.addEventListener('click', startNewConversation);

  // ----- Voice input (mic) -------------------------------------------------
  // Tap-to-record / tap-to-stop. The recorded audio is POSTed to AGiXT's
  // /v1/audio/transcriptions (OpenAI-compatible), and the returned text
  // is sent through the normal compose path so all the activity/render
  // plumbing fires the same way as a typed message. Esc cancels.
  const micState = {
    recorder: null,
    stream: null,
    chunks: [],
    state: 'idle', // 'idle' | 'recording' | 'busy'
  };

  function setMicState(state) {
    micState.state = state;
    if (micBtn) micBtn.setAttribute('data-state', state);
  }

  function pickRecorderMime() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    for (const c of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) return c;
    }
    return '';
  }

  async function startRecording() {
    if (micState.state !== 'idle') return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      window.AgixtChat.setComposerStatus('Microphone API unavailable in this webview', 'error');
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      window.AgixtChat.setComposerStatus(
        err && err.name === 'NotAllowedError'
          ? 'Microphone access denied — allow it in system settings'
          : `Mic error: ${err && err.message ? err.message : err}`,
        'error',
      );
      return;
    }
    const mime = pickRecorderMime();
    const recorder = mime
      ? new MediaRecorder(stream, { mimeType: mime })
      : new MediaRecorder(stream);
    micState.stream = stream;
    micState.recorder = recorder;
    micState.chunks = [];
    micState.cancelled = false;
    recorder.addEventListener('dataavailable', (e) => {
      if (e.data && e.data.size > 0) micState.chunks.push(e.data);
    });
    recorder.addEventListener('stop', handleRecordingStopped);
    recorder.start();
    setMicState('recording');
    window.AgixtChat.setComposerStatus('Listening — tap mic again to send, Esc to cancel');
  }

  function teardownRecorderStream() {
    if (micState.stream) {
      micState.stream.getTracks().forEach((t) => t.stop());
      micState.stream = null;
    }
  }

  function stopRecording() {
    const r = micState.recorder;
    if (!r || micState.state !== 'recording') return;
    setMicState('busy');
    try { if (r.state !== 'inactive') r.stop(); } catch (e) { console.warn(e); }
  }

  function cancelRecording() {
    if (micState.state !== 'recording') return;
    micState.cancelled = true;
    const r = micState.recorder;
    try { if (r && r.state !== 'inactive') r.stop(); } catch (_) { /* ignore */ }
    teardownRecorderStream();
    micState.recorder = null;
    micState.chunks = [];
    setMicState('idle');
    window.AgixtChat.setComposerStatus('');
  }

  async function handleRecordingStopped() {
    teardownRecorderStream();
    const r = micState.recorder;
    micState.recorder = null;
    if (micState.cancelled) {
      micState.chunks = [];
      setMicState('idle');
      return;
    }
    const mime = (r && r.mimeType) || 'audio/webm';
    const blob = new Blob(micState.chunks, { type: mime });
    micState.chunks = [];
    if (!blob.size) {
      setMicState('idle');
      window.AgixtChat.setComposerStatus('No audio captured', 'error');
      return;
    }
    setMicState('busy');
    window.AgixtChat.setComposerStatus('Transcribing…');
    let transcript = '';
    try {
      const ext = (mime.split('/')[1] || 'webm').split(';')[0];
      const fd = new FormData();
      fd.append('file', blob, `recording.${ext}`);
      // AGiXT keys the transcription to the active agent via the `model`
      // form field — same convention as /v1/chat/completions.
      fd.append('model', settings.agent_name || 'XT');
      const url = (settings.server_url || '').replace(/\/+$/, '') + '/v1/audio/transcriptions';
      const resp = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${settings.jwt}` },
        body: fd,
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}${text ? `: ${text.slice(0, 160)}` : ''}`);
      }
      const data = await resp.json().catch(() => ({}));
      transcript = (data && (data.text || data.transcript)) || '';
    } catch (err) {
      setMicState('idle');
      window.AgixtChat.setComposerStatus(
        `Transcription failed: ${err && err.message ? err.message : err}`,
        'error',
      );
      return;
    }
    transcript = (transcript || '').trim();
    if (!transcript) {
      setMicState('idle');
      window.AgixtChat.setComposerStatus("Couldn't hear anything", 'error');
      return;
    }
    composerInput.value = transcript;
    autoResize();
    setMicState('idle');
    window.AgixtChat.setComposerStatus('');
    sendCurrent();
  }

  if (micBtn) {
    micBtn.addEventListener('click', () => {
      if (micState.state === 'recording') stopRecording();
      else if (micState.state === 'idle') startRecording();
    });
  }

  // Esc cancels an in-progress recording without sending. Doesn't
  // interfere when the user is just typing (recording state guards it).
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && micState.state === 'recording') {
      e.preventDefault();
      cancelRecording();
    }
  });

  collapseBtn.addEventListener('click', async () => {
    try { await invoke('set_sidebar_visible', { visible: false }); } catch (_) { /* ignore */ }
  });

  function openSettings() {
    settingsModal.classList.add('open');
    settingsModal.setAttribute('aria-hidden', 'false');
    settingsUser.textContent = settings.user_email
      ? `${settings.user_email} @ ${settings.server_url}`
      : 'not signed in';
    refreshSudoStatus();
  }
  function closeSettings() { settingsModal.classList.remove('open'); settingsModal.setAttribute('aria-hidden', 'true'); setSettingsStatus(''); }

  settingsBtn.addEventListener('click', openSettings);
  settingsClose.addEventListener('click', closeSettings);
  saveSettingsBtn.addEventListener('click', onSaveSettings);
  if (sudoAuthBtn) sudoAuthBtn.addEventListener('click', onSudoAuth);
  if (sudoClearBtn) sudoClearBtn.addEventListener('click', onSudoClear);
  if (sudoPasswordInput) {
    sudoPasswordInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        onSudoAuth();
      }
    });
  }
  logoutBtn.addEventListener('click', onLogout);
  settingsModal.addEventListener('click', (e) => { if (e.target === settingsModal) closeSettings(); });

  // ----- Boot --------------------------------------------------------------

  async function onAuthenticated() {
    await loadSettings();
    showScreen('chat');
    await refreshAgentsAndCompanies();
    await ensureConversation();
    reconnectChat();
    // Pre-populate the conversations list so the chip label can resolve
    // against the latest server-side names (e.g. an auto-rename that
    // happened since the last save), not just the persisted snapshot.
    await refreshConversations();
    updateConvoLabel();
    if (settings.conversation_id) {
      await window.AgixtChat.loadHistory(settings.conversation_id);
    }
  }

  (async () => {
    frontendLog('info', 'app boot sequence start');
    await loadSettings();
    if (settings.jwt) {
      // Returning user — straight into chat. We still let the user fix
      // anything via the settings modal.
      showScreen('chat');
      await refreshAgentsAndCompanies();
      await ensureConversation();
      reconnectChat();
      await refreshConversations();
      updateConvoLabel();
      if (settings.conversation_id) {
        await window.AgixtChat.loadHistory(settings.conversation_id);
      }
    } else {
      showScreen('auth');
      if (window.AgixtAuth) {
        await window.AgixtAuth.boot({ onAuthenticated });
      }
    }
    frontendLog('info', 'app boot sequence complete');
  })();

  // Live-update the conversation chip + cache when AGiXT renames a
  // conversation server-side. Chat.js forwards the WebSocket event as a
  // window CustomEvent so the chat module stays renderer-agnostic.
  window.addEventListener('agixt-conversation-renamed', (ev) => {
    const data = (ev && ev.detail) || {};
    const id = data.conversation_id || data.id;
    const newName = data.new_name || data.name || data.display_name;
    if (!id) return;
    const cached = conversations.find((c) => c.id === id);
    if (cached && newName) cached.name = newName;
    if (id === settings.conversation_id) {
      if (newName) {
        settings = { ...settings, conversation_name: newName };
        invoke('save_settings', { settings }).catch((err) => {
          console.warn('save renamed conversation failed', err);
        });
      }
      convoLabel.textContent = newName ? newName : 'New conversation';
    }
  });

  if (event && event.listen) {
    event.listen('sidebar-state', (ev) => { void ev; });
    // Fired by the Rust deep-link handler after `agixt://login?token=...`
    // arrives and has been verified against /v1/user. Swap the screen
    // automatically — no copy-paste needed.
    event.listen('agixt-authenticated', async () => {
      try { await onAuthenticated(); } catch (e) { console.warn('onAuthenticated', e); }
    });
  }
})();
