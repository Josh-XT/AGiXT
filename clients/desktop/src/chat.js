/* WebSocket chat client for the AGiXT desktop sidebar.
 *
 * Wire-compatible with the AGiXT NextJS web client's
 * /v1/conversation/{id}/stream protocol:
 *   url: ws[s]://{host}/v1/conversation/{conversation_id}/stream?authorization={jwt}&limit=500
 *
 * Server sends JSON envelopes:
 *   { type: "connected" | "heartbeat" | "pong" }
 *   { type: "initial_data", data: [{ id, role, message, timestamp }, ...] }
 *   { type: "initial_message" | "message_added", data: { id, role, message, timestamp } }
 *   { type: "message_updated", data: { ... } }
 *   { type: "messages_deleted" }
 *   { type: "error", message: "..." }
 *
 * Message bodies use [ACTIVITY] and [SUBACTIVITY] prefixes for
 * agent thinking/action logs; we group them into collapsible sections.
 */
(function () {
  const md = window.AgixtMarkdown;
  const audio = window.AgixtAudio;
  const clientActions = window.AgixtClientActions;
  // Bumped whenever the activity rendering pipeline changes, so the
  // backend log immediately tells us whether the running webview picked
  // up the latest code or is showing a cached/older bundle.
  const CHAT_JS_VERSION = 'activity-elapsed-v28';
  if (window.AgixtFrontendLog) {
    window.AgixtFrontendLog('info', `chat.js loaded (${CHAT_JS_VERSION})`);
  }

  function dispatchAssistantEvent(name, detail) {
    try {
      window.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
    } catch (_) {}
  }

  let ws = null;
  let pingTimer = null;
  let reconnectTimer = null;
  let backoffMs = 1000;
  let conversationId = null;
  let serverUrl = null;
  let jwt = null;

  // AGiXT serves images/audio/video from `/outputs/...` (and `/workspace/...`)
  // under JWT authentication. The webview can't attach an Authorization
  // header to a plain <img src>, but AGiXT's serve_file endpoint accepts
  // `?auth=<jwt>` as a query-param fallback (see AGiXT/agixt/app.py:597).
  // Only add that query token to URLs on the configured AGiXT origin; a
  // malicious markdown image on some other host can also have `/outputs/` in
  // its path, and must not receive the user's JWT.
  const AGIXT_WORKSPACE_PATH = /(^|\/)(outputs|api\/workspace|workspace)\//;
  const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '[::1]', '::1']);

  function originFor(url) {
    try { return new URL(url).origin; }
    catch (_) { return null; }
  }

  function addLoopbackOriginVariants(origins, origin) {
    let parsed;
    try { parsed = new URL(origin); } catch (_) { return; }
    if (!LOOPBACK_HOSTS.has(parsed.hostname)) return;
    const port = parsed.port ? `:${parsed.port}` : '';
    origins.add(`${parsed.protocol}//localhost${port}`);
    origins.add(`${parsed.protocol}//127.0.0.1${port}`);
    origins.add(`${parsed.protocol}//0.0.0.0${port}`);
    origins.add(`${parsed.protocol}//[::1]${port}`);
  }

  function trustedWorkspaceOrigins() {
    const origins = new Set();
    const configured = originFor(serverUrl);
    if (configured) {
      origins.add(configured);
      addLoopbackOriginVariants(origins, configured);
    }
    return origins;
  }

  function isTrustedWorkspaceUrl(parsed, wasRelative) {
    if (wasRelative) return true;
    return trustedWorkspaceOrigins().has(parsed.origin);
  }

  function rewriteAuthForUrl(url) {
    if (!url || typeof url !== 'string') return url;
    if (url.startsWith('data:') || url.startsWith('blob:')) return url;
    let abs = url;
    const wasRelative = url.startsWith('/');
    if (wasRelative) {
      if (!serverUrl) return url;
      abs = serverUrl.replace(/\/+$/, '') + url;
    }
    let parsed;
    try { parsed = new URL(abs); } catch (_) { return url; }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return url;
    if (!AGIXT_WORKSPACE_PATH.test(parsed.pathname)) return url;
    if (!isTrustedWorkspaceUrl(parsed, wasRelative)) return url;
    if (!jwt) return abs;
    if (!parsed.searchParams.has('auth')) {
      parsed.searchParams.set('auth', jwt);
    }
    return parsed.toString();
  }

  function authMediaNodes(root) {
    if (!root || (!serverUrl && !jwt)) return;
    root.querySelectorAll('img[src], video[src], audio[src], source[src]').forEach((node) => {
      const next = rewriteAuthForUrl(node.getAttribute('src'));
      if (next) node.setAttribute('src', next);
    });
    // Anchors stay clickable but if they look like media, rewrite too
    // so right-click "open" works.
    root.querySelectorAll('a[href]').forEach((node) => {
      const href = node.getAttribute('href') || '';
      if (/\.(png|jpe?g|gif|webp|avif|svg|mp4|webm|mov|m4v|mp3|wav|ogg)(\?.*)?$/i.test(href)) {
        const next = rewriteAuthForUrl(href);
        if (next) node.setAttribute('href', next);
      }
    });
  }

  function replaceChildren(target, fragment) {
    if (typeof target.replaceChildren === 'function') {
      target.replaceChildren(fragment);
      return;
    }
    while (target.firstChild) target.removeChild(target.firstChild);
    target.appendChild(fragment);
  }

  // Always go through this helper so every render gets the same media URL
  // rewriting applied, including history replays.
  function renderMdInto(target, text) {
    if (!target) return;
    const value = text == null ? '' : String(text);
    if (md && typeof md.renderFragment === 'function') {
      const fragment = md.renderFragment(value);
      authMediaNodes(fragment);
      replaceChildren(target, fragment);
      return;
    }
    target.textContent = value;
  }
  let messages = new Map(); // id -> { id, role, text, ts, kind, parentId, el }
  let order = [];
  // Activity-grouping state, mirrors web/hooks/useConversationWebSocketStable.ts
  // groupMessages(): subactivities attach to a parent [ACTIVITY] (by id when
  // referenced, else the last activity), and consecutive "Thinking" activities
  // merge into one block so the user sees one rolling thinking section instead
  // of N separate ones. User messages and final assistant replies reset this.
  let lastActivityId = null;
  let lastThinkingActivityId = null;
  const activityIdAlias = new Map(); // alias id -> effective parent id
  let activeStreamingActivity = null; // one live activity block across tool-result recursion
  // Each tool call produces a CLIENT_TOOL subactivity followed by a string
  // of REMOTE / untagged subactivities ("Requesting remote execution…",
  // "Remote execution completed", "Received tool result", "Uploaded …",
  // "Processed …"). We collapse all of them into one disclosure so the
  // user sees a single "Called desktop_screenshot" line by default and
  // can click to expand for the request payload, transport status, and
  // result. Closes on THOUGHT, on a new CLIENT_TOOL, or when the parent
  // activity changes.
  let currentToolGroup = null; // { el, body, parentId } | null
  let lastConnectionState = '';

  const els = () => ({
    list: document.getElementById('messages'),
    empty: document.getElementById('empty-state'),
    status: document.getElementById('connection-state'),
    composerStatus: document.getElementById('composer-status'),
    scroll: document.getElementById('chat-scroll'),
  });

  function setStatus(text, cls) {
    const e = els().status;
    if (!e) return;
    // The new topbar uses a small badge overlaid on the logo instead of
    // text labels. Surface the connection text as the title attribute
    // (tooltip) and drive color via the cls modifier — the dot is hidden
    // when `connected` so a healthy session shows just the logo.
    e.title = text || '';
    e.className = 'brand-conn' + (cls ? ' ' + cls : '');
    lastConnectionState = text;
  }

  function setComposerStatus(text, cls) {
    const e = els().composerStatus;
    if (!e) return;
    e.textContent = text || '';
    e.className = 'composer-status' + (cls ? ' ' + cls : '');
  }

  function clear() {
    const { list, empty } = els();
    if (list) list.innerHTML = '';
    if (empty) empty.style.display = '';
    messages.clear();
    order = [];
    lastActivityId = null;
    lastThinkingActivityId = null;
    currentToolGroup = null;
    activeStreamingActivity = null;
    activityIdAlias.clear();
  }

  function removeMessage(id) {
    const existing = messages.get(id);
    if (!existing) return;
    if (existing.el && existing.el.parentNode) {
      existing.el.parentNode.removeChild(existing.el);
    }
    messages.delete(id);
    order = order.filter((x) => x !== id);
    if (lastActivityId === id) lastActivityId = null;
    if (lastThinkingActivityId === id) lastThinkingActivityId = null;
    if (currentToolGroup && currentToolGroup.id === id) currentToolGroup = null;
    if (activeStreamingActivity && activeStreamingActivity.id === id) activeStreamingActivity = null;
    activityIdAlias.delete(id);
  }

  function comparableRole(role) {
    const r = String(role || '').toLowerCase();
    if (r === 'user') return 'user';
    if (r === 'tool') return 'tool';
    return 'assistant';
  }

  function comparableText(text) {
    return String(text || '').trim().replace(/\s+/g, ' ');
  }

  function findMatchingPlainId(role, body, opts) {
    const incoming = (body || '').trim();
    if (!incoming) return null;
    const incomingRole = comparableRole(role);
    const options = opts || {};
    const startIndex = Number.isFinite(options.startIndex) ? options.startIndex : 0;
    for (const id of order.slice(startIndex)) {
      const isLocal = id.startsWith('local-');
      if (options.local === true && !isLocal) continue;
      if (options.local === false && isLocal) continue;
      const m = messages.get(id);
      if (!m || m.kind !== 'plain' || comparableRole(m.role) !== incomingRole) continue;
      if (comparableText(m.text) === comparableText(incoming)) {
        return id;
      }
    }
    return null;
  }

  function replaceMatchingLocalPlain(role, body) {
    const id = findMatchingPlainId(role, body, { local: true });
    if (id) {
      removeMessage(id);
    }
  }

  function replaceMatchingLocalThought(body) {
    const incoming = comparableText(body);
    if (!incoming) return;
    for (const id of order.slice()) {
      if (!id.startsWith('local-activity-')) continue;
      const m = messages.get(id);
      if (!m || m.kind !== 'activity' || !m.transient) continue;
      if (comparableText(m.streamText || m.text) === incoming) {
        removeMessage(id);
        return;
      }
    }
  }

  function replaceMatchingLocalSubactivity(body, tag) {
    const incoming = comparableText(body);
    if (!incoming) return;
    const wantedTag = tag || '';
    for (const id of order.slice()) {
      if (!id.startsWith('local-sub-')) continue;
      const m = messages.get(id);
      if (!m || !['subactivity', 'tool-group'].includes(m.kind)) continue;
      if ((m.tag || '') !== wantedTag) continue;
      if (comparableText(m.text) === incoming) {
        removeMessage(id);
        return;
      }
    }
  }

  function showChat() {
    const { empty } = els();
    if (empty) empty.style.display = 'none';
  }

  function scrollToBottom() {
    const { scroll } = els();
    if (!scroll) return;
    scroll.scrollTop = scroll.scrollHeight;
  }

  // ----- Activity / subactivity parsing -----

  function classifyActivity(text) {
    const t = text.toLowerCase();
    if (t.includes('error') || t.includes('failed')) return 'error';
    if (t.includes('warning') || t.includes('warn')) return 'warn';
    if (t.includes('thinking') || t.includes('thought') || t.includes('reflect')) return 'thought';
    if (t.includes('info') || t.includes('starting') || t.includes('done')) return 'info';
    return 'execution';
  }

  const KNOWN_SUB_TAGS = new Set(['THOUGHT', 'REFLECTION', 'INFO', 'ERROR', 'WARNING', 'CLIENT_TOOL', 'REMOTE', 'DIAGRAM', 'EXECUTION']);

  // Returns { kind, label, body, tag, parentRef }
  function parseMessageEnvelope(raw) {
    if (raw == null) return { kind: 'plain', body: '' };
    const text = String(raw);
    if (text.startsWith('[ACTIVITY]')) {
      const body = text.replace(/^\[ACTIVITY\]\s*/, '');
      return { kind: 'activity', label: body, body, type: classifyActivity(body) };
    }
    if (text.startsWith('[SUBACTIVITY]')) {
      // Three real-world shapes:
      //   [SUBACTIVITY] body…                                   (no tag, attaches to last activity)
      //   [SUBACTIVITY][TAG] body…                              (tag form: THOUGHT|INFO|ERROR|WARNING|CLIENT_TOOL|REMOTE|DIAGRAM|EXECUTION)
      //   [SUBACTIVITY][parent_uuid] body…                      (uuid parent ref)
      //   [SUBACTIVITY][parent_uuid][TAG] body…                 (parent ref + tag — strip both, keep tag)
      const stripped = text.replace(/^\[SUBACTIVITY\]\s*/, '');
      const tags = [];
      let parentRef = '';
      let body = stripped;
      // Pull off as many leading [bracket] tokens as we find and classify each.
      while (true) {
        const m = body.match(/^\[([^\]]*)\]\s*([\s\S]*)$/);
        if (!m) break;
        const token = m[1] || '';
        const upper = token.toUpperCase();
        if (KNOWN_SUB_TAGS.has(upper)) {
          tags.push(upper);
        } else if (!parentRef) {
          parentRef = token;
        } else {
          // Unknown extra bracket — keep it in body and stop stripping so we
          // don't accidentally eat real content like literal "[note]".
          break;
        }
        body = m[2];
      }
      const tag = tags[0] || undefined;
      const out = { kind: 'subactivity', body };
      if (tag) out.tag = tag;
      if (parentRef) out.parentRef = parentRef;
      return out;
    }
    return { kind: 'plain', body: text };
  }

  // ----- DOM rendering -----

  function el(tag, cls) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  // Format an ISO timestamp into "h:mm AM" + the absolute date as the
  // hover tooltip. Returns { short, long } so the renderer can show one
  // and surface the other on hover.
  function formatMessageTime(iso) {
    if (!iso) return { short: '', long: '' };
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return { short: '', long: '' };
    let short;
    try {
      short = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    } catch (_) { short = d.toISOString(); }
    let long;
    try {
      // Include seconds + milliseconds in the tooltip so users can
      // gauge response latency (e.g. how long the agent took between
      // their question and the reply).
      const base = d.toLocaleString([], {
        weekday: 'short', month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit', second: '2-digit',
      });
      const ms = String(d.getMilliseconds()).padStart(3, '0');
      long = `${base}.${ms}`;
    } catch (_) { long = d.toISOString(); }
    return { short, long };
  }

  // Compact, human-readable duration ("5s", "1m 5s", "1h 2m") for the
  // "Worked/Working for …" label on activity blocks.
  function formatDuration(ms) {
    if (!Number.isFinite(ms) || ms < 0) ms = 0;
    const totalSec = Math.round(ms / 1000);
    if (totalSec < 60) return `${totalSec}s`;
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
    const h = Math.floor(m / 60);
    const mm = m % 60;
    return mm ? `${h}h ${mm}m` : `${h}h`;
  }

  // Activity start/last timestamps live on the element as data attributes
  // so the ticker and finalize pass (which work off the DOM, not the
  // messages Map) can recompute elapsed time independently.
  //   data-start-ms      server timestamp of the [ACTIVITY] message
  //   data-last-ms       server timestamp of the most recent child event
  //   data-client-start  Date.now() when the block first rendered live
  //                       (absent for history replays so they use server
  //                       timestamps instead of a bogus client clock)
  function activityElapsedMs(elm, running) {
    const startMs = Number(elm.dataset.startMs);
    if (!Number.isFinite(startMs)) return 0;
    const lastMs = Number(elm.dataset.lastMs);
    let elapsed = Number.isFinite(lastMs) ? lastMs - startMs : 0;
    if (running) {
      const clientStart = Number(elm.dataset.clientStart);
      if (Number.isFinite(clientStart)) {
        elapsed = Math.max(elapsed, Date.now() - clientStart);
      }
    }
    return elapsed < 0 ? 0 : elapsed;
  }

  function refreshActivityElapsed(elm) {
    const span = elm.querySelector('.activity-elapsed');
    if (!span) return;
    const running = elm.getAttribute('data-running') === 'true'
      && elm.getAttribute('data-finalized') !== 'true';
    const verb = running ? 'Working' : 'Worked';
    span.textContent = `${verb} for ${formatDuration(activityElapsedMs(elm, running))}`;
  }

  // Bump an activity's last-seen timestamp from a child event so the
  // elapsed clock reflects server time, then redraw its label.
  function touchActivityElapsed(entry, ts) {
    if (!entry || entry.kind !== 'activity' || !entry.el) return;
    const ms = ts ? Date.parse(ts) : NaN;
    if (Number.isFinite(ms)) {
      const prev = Number(entry.el.dataset.lastMs);
      if (!Number.isFinite(prev) || ms > prev) entry.el.dataset.lastMs = String(ms);
    }
    refreshActivityElapsed(entry.el);
  }

  function initActivityElapsed(elm, ts, isInitial) {
    const startMs = ts ? Date.parse(ts) : Date.now();
    elm.dataset.startMs = String(startMs);
    elm.dataset.lastMs = String(startMs);
    if (!isInitial) elm.dataset.clientStart = String(Date.now());
    refreshActivityElapsed(elm);
  }

  // Single shared ticker keeps every still-running activity's "Working
  // for …" label counting up without a timer per block.
  let elapsedTicker = null;
  function ensureElapsedTicker() {
    if (elapsedTicker) return;
    elapsedTicker = setInterval(() => {
      const running = document.querySelectorAll(
        '.activity[data-running="true"]:not([data-finalized="true"])'
      );
      if (!running.length) {
        clearInterval(elapsedTicker);
        elapsedTicker = null;
        return;
      }
      running.forEach(refreshActivityElapsed);
    }, 1000);
  }

  function renderPlain(role, body, timestamp) {
    const wrap = el('div', `message message-${role === 'user' ? 'user' : 'assistant'}`);
    const row = el('div', 'message-row');
    const bubble = el('div', 'bubble');
    const content = el('div', 'md');
    renderMdInto(content, body);
    bubble.appendChild(content);
    row.appendChild(bubble);
    // Inline timestamp next to the bubble. Hidden by default; CSS reveals
    // it when the user hovers over the message row. Tooltip on hover
    // shows the full date for older conversations.
    if (timestamp) {
      const { short, long } = formatMessageTime(timestamp);
      if (short) {
        const t = document.createElement('time');
        t.className = 'message-ts';
        t.dateTime = timestamp;
        t.textContent = short;
        t.title = long || short;
        row.appendChild(t);
      }
    }
    wrap.appendChild(row);
    return { el: wrap, content };
  }

  function renderActivity(label, type) {
    const wrap = el('div', 'activity');
    wrap.setAttribute('data-type', type || 'execution');
    wrap.setAttribute('data-running', 'true');
    wrap.setAttribute('aria-expanded', 'false');
    const head = el('div', 'activity-head');
    head.innerHTML = `
      <span class="chev">▸</span>
      <span class="activity-title"></span>
      <span class="activity-elapsed"></span>
      <span class="activity-spinner"></span>
    `;
    head.querySelector('.activity-title').textContent = label || 'Working…';
    head.addEventListener('click', () => {
      const open = wrap.getAttribute('aria-expanded') === 'true';
      wrap.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
    const body = el('div', 'activity-body');
    wrap.appendChild(head);
    wrap.appendChild(body);
    return { el: wrap, body };
  }

  // Tag → leading icon + readable label. Mirrors the per-type icons web's
  // activity components show via lucide. We use unicode glyphs to avoid
  // pulling in an SVG library.
  const SUB_TAG_META = {
    THOUGHT:     { icon: '◐', label: 'Thought' },
    REFLECTION:  { icon: '◇', label: 'Reflection' },
    INFO:        { icon: 'ⓘ', label: 'Info' },
    ERROR:       { icon: '✖', label: 'Error' },
    WARNING:     { icon: '⚠', label: 'Warning' },
    CLIENT_TOOL: { icon: '▶', label: 'Tool' },
    REMOTE:      { icon: '⌘', label: 'Command' },
    DIAGRAM:     { icon: '✎', label: 'Diagram' },
    EXECUTION:   { icon: '⚙', label: 'Execution' },
  };

  function tryParseJson(text) {
    if (!text) return null;
    // Look for the first balanced JSON object/array in the body.
    const firstBrace = text.search(/[\{\[]/);
    if (firstBrace < 0) return null;
    const candidates = [
      text.slice(firstBrace),
      text.trim(),
    ];
    for (const c of candidates) {
      try { return JSON.parse(c); } catch (_) { /* keep going */ }
    }
    return null;
  }

  // AGiXT emits CLIENT_TOOL subactivity bodies as
  //   Calling client tool `<name>`.
  //   ```json
  //   { ... }
  //   ```
  // We render the entire thing as a collapsed <details> showing only the
  // tool-name line by default; the JSON payload is tucked away and
  // appears when the user expands it. This keeps the activity feed
  // skimmable and avoids duplicating the wall of JSON the model
  // generated from the schema. If parsing fails we still show the
  // single-line summary and put the raw body inside the details.
  function extractClientToolMeta(text) {
    if (!text) return null;
    const nameMatch = text.match(/`([^`]+)`/);
    const inferredName = nameMatch ? nameMatch[1] : null;
    // Pull JSON either from a fenced block or from the first balanced { ... }.
    let jsonText = null;
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenced) jsonText = fenced[1].trim();
    if (!jsonText) {
      const firstBrace = text.indexOf('{');
      if (firstBrace >= 0) {
        const candidate = text.slice(firstBrace).replace(/```\s*$/, '').trim();
        jsonText = candidate;
      }
    }
    let data = null;
    if (jsonText) {
      try { data = JSON.parse(jsonText); } catch (_) { /* leave null */ }
    }
    const name =
      inferredName
      || (data && (data.tool_name || data.name || data.action_type))
      || 'tool';
    return { name, data, jsonText: jsonText || '' };
  }

  function renderClientToolBody(text) {
    const meta = extractClientToolMeta(text);
    if (!meta) return null;
    const det = document.createElement('details');
    det.className = 'sub-tool';
    const sum = document.createElement('summary');
    sum.className = 'sub-tool-summary';
    // "Calling " + a styled `code` chip for the tool name.
    sum.appendChild(document.createTextNode('Calling client tool '));
    const code = el('code', 'sub-tool-name');
    code.textContent = meta.name;
    sum.appendChild(code);
    det.appendChild(sum);
    const pre = el('pre', 'sub-tool-pre');
    pre.textContent = meta.data
      ? JSON.stringify(meta.data, null, 2)
      : meta.jsonText || text;
    det.appendChild(pre);
    return det;
  }

  // EXECUTION subactivities carry a single-line summary plus a chunk of
  // detail (json args, command output, code, etc.). AGiXT emits them like
  //   "Executing `cmd`.\n```json\n{...}```"
  //   "`cmd` was executed successfully.\n<long output>"
  //   "Code interpreter\n```python\n...```"
  //   "Used tool: foo\n```json\n{...}```"
  //   "Edited file: path/to/x"
  // Render the first line as a clickable summary and tuck the rest behind
  // <details>. Single-line bodies render inline (no disclosure).
  function renderExecutionBody(text) {
    const value = text == null ? '' : String(text);
    const newlineIdx = value.indexOf('\n');
    const title = (newlineIdx >= 0 ? value.slice(0, newlineIdx) : value).trim();
    const rest = newlineIdx >= 0 ? value.slice(newlineIdx + 1).trim() : '';
    if (!rest) {
      const inline = el('div', 'md');
      renderMdInto(inline, title || value);
      return inline;
    }
    const det = document.createElement('details');
    det.className = 'sub-exec';
    const sum = document.createElement('summary');
    sum.className = 'sub-exec-summary';
    const sumMd = el('span', 'sub-exec-title md');
    renderMdInto(sumMd, title || 'Execution');
    sum.appendChild(sumMd);
    det.appendChild(sum);
    const bodyEl = el('div', 'sub-exec-body md');
    renderMdInto(bodyEl, rest);
    det.appendChild(bodyEl);
    return det;
  }

  // Render a REMOTE / command-result subactivity as a terminal block. AGiXT
  // emits these as `[REMOTE_COMMAND_RESULT] {json}` or as the plain JSON the
  // server stores after submit_remote_command_result. Falls back to markdown.
  function renderRemoteBody(text) {
    const cleaned = text.replace(/^\[REMOTE_COMMAND_RESULT\]\s*/, '');
    const data = tryParseJson(cleaned);
    if (!data || typeof data !== 'object') return null;
    const wrap = el('div', 'sub-remote');
    const head = el('div', 'sub-remote-head');
    const name = data.tool_name || data.command || 'command';
    const exit = data.exit_code != null ? data.exit_code : (data.success === false ? 1 : 0);
    const headLeft = el('span', 'sub-remote-name');
    headLeft.textContent = name;
    head.appendChild(headLeft);
    const exitEl = el('span', `sub-remote-exit ${exit === 0 ? 'ok' : 'err'}`);
    exitEl.textContent = `exit ${exit}`;
    head.appendChild(exitEl);
    wrap.appendChild(head);
    const stdout = (data.stdout != null ? String(data.stdout) : '').trim();
    const stderr = (data.stderr != null ? String(data.stderr) : '').trim();
    if (stdout) {
      const pre = el('pre', 'sub-remote-out');
      pre.textContent = stdout;
      wrap.appendChild(pre);
    }
    if (stderr) {
      const pre = el('pre', 'sub-remote-err');
      pre.textContent = stderr;
      wrap.appendChild(pre);
    }
    if (!stdout && !stderr && !data.exit_code && data.message) {
      const p = el('div', 'md');
      renderMdInto(p, String(data.message));
      wrap.appendChild(p);
    }
    return wrap;
  }

  function renderSubactivity(text, tag) {
    const sub = el('div', 'subactivity');
    if (tag) sub.setAttribute('data-tag', tag);
    const meta = tag ? SUB_TAG_META[tag] : null;
    if (meta) {
      const icon = el('span', 'sub-icon');
      icon.textContent = meta.icon;
      icon.setAttribute('aria-label', meta.label);
      icon.setAttribute('title', meta.label);
      sub.appendChild(icon);
    }
    const content = el('div', 'sub-content');
    let custom = null;
    if (tag === 'CLIENT_TOOL') custom = renderClientToolBody(text);
    else if (tag === 'REMOTE') custom = renderRemoteBody(text);
    else if (tag === 'EXECUTION') custom = renderExecutionBody(text);
    if (custom) {
      content.appendChild(custom);
    } else {
      const inner = el('div', 'md');
      // For tagged plain bodies markdown-render so fenced code, lists, etc
      // come out properly instead of as a single inline string.
      renderMdInto(inner, text);
      content.appendChild(inner);
    }
    sub.appendChild(content);
    return sub;
  }

  // Temporary instrumentation: log a sample of incoming messages so we can
  // confirm what shape the activity/subactivity bodies actually have when
  // they reach the renderer. Capped so we don't flood Rust tracing.
  let _ingestLogged = 0;

  // Insert a message envelope in chronological order.
  function ingest(msg, isInitial) {
    if (!msg || !msg.id) return;
    if (messages.has(msg.id)) return; // dedupe
    const role = (msg.role || 'assistant').toLowerCase();
    const rawMessage = String(msg.message || '');
    if (window.AgixtFrontendLog && _ingestLogged < 30) {
      _ingestLogged += 1;
    }
    if (role === 'user' && !rawMessage.trim()) return;
    const normalizedMessage = rawMessage.startsWith('[SUBACTIVITY]')
      ? rawMessage
      : (role === 'remote_terminal' || rawMessage.startsWith('[REMOTE_COMMAND_RESULT]')
          ? `[SUBACTIVITY][REMOTE] ${rawMessage}`
          : rawMessage);
    const parsed = parseMessageEnvelope(normalizedMessage);
    if (!String(msg.id).startsWith('local-') && parsed.kind === 'plain') {
      replaceMatchingLocalPlain(role, parsed.body);
    }

    showChat();
    const { list } = els();

    if (parsed.kind === 'activity') {
      const isThinking = (parsed.body || '').toLowerCase().includes('thinking');
      const existingThinking = lastThinkingActivityId
        ? messages.get(lastThinkingActivityId)
        : null;
      const shouldMergeThinking = isThinking
        && lastThinkingActivityId
        && existingThinking
        // A persisted server parent must not alias onto the transient
        // live-stream parent. The matching persisted subactivity removes
        // that transient block, then attaches to the real server parent.
        && !(existingThinking.transient && !String(msg.id).startsWith('local-'));
      // Thinking-merge: when AGiXT emits a second "Thinking" activity in
      // the same turn, attach future subactivities to the existing block
      // instead of opening a new one. Mirrors web's groupMessages().
      if (shouldMergeThinking) {
        activityIdAlias.set(msg.id, lastThinkingActivityId);
        // Mark this id as seen so update() / dedup don't re-create it.
        const merged = existingThinking;
        messages.set(msg.id, merged);
        touchActivityElapsed(merged, msg.timestamp);
        lastActivityId = lastThinkingActivityId;
      } else {
        const r = renderActivity(parsed.label, parsed.type);
        initActivityElapsed(r.el, msg.timestamp, isInitial);
        ensureElapsedTicker();
        list.appendChild(r.el);
        const entry = {
          id: msg.id, role, text: parsed.label, ts: msg.timestamp,
          kind: 'activity', el: r.el, body: r.body, type: parsed.type,
        };
        messages.set(msg.id, entry);
        order.push(msg.id);
        lastActivityId = msg.id;
        if (isThinking) lastThinkingActivityId = msg.id;
      }
    } else if (parsed.kind === 'subactivity') {
      if (!String(msg.id).startsWith('local-') && parsed.tag === 'THOUGHT') {
        replaceMatchingLocalThought(parsed.body);
      }
      let parent = null;
      // 1) Explicit parent reference (UUID inside [SUBACTIVITY][...]).
      if (parsed.parentRef) {
        const direct = messages.get(parsed.parentRef);
        if (direct && direct.kind === 'activity') {
          parent = direct;
        } else {
          const aliased = activityIdAlias.get(parsed.parentRef);
          if (aliased) parent = messages.get(aliased);
        }
      }
      // 2) Tag form ([SUBACTIVITY][THOUGHT|...]) — attach to last activity.
      if (!parent && lastActivityId && messages.has(lastActivityId)) {
        const candidate = messages.get(lastActivityId);
        if (candidate && candidate.kind === 'activity') parent = candidate;
      }
      // 3) Orphan subactivity arriving before any activity — synthesize a
      // "Thinking" parent so it doesn't render as a stranded line.
      if (!parent) {
        const synthId = `synthetic-act-${msg.id}`;
        const r = renderActivity('Thinking', 'thought');
        initActivityElapsed(r.el, msg.timestamp, isInitial);
        ensureElapsedTicker();
        list.appendChild(r.el);
        parent = {
          id: synthId, role, text: 'Thinking', ts: msg.timestamp,
          kind: 'activity', el: r.el, body: r.body, type: 'thought',
        };
        messages.set(synthId, parent);
        order.push(synthId);
        lastActivityId = synthId;
        lastThinkingActivityId = synthId;
      }

      // Every child event extends the parent's elapsed clock to the
      // latest server timestamp.
      touchActivityElapsed(parent, msg.timestamp);
      if (!String(msg.id).startsWith('local-')) {
        replaceMatchingLocalSubactivity(parsed.body, parsed.tag);
      }

      // Tool-call grouping. AGiXT emits a CLIENT_TOOL marker, then a
      // string of REMOTE / untagged follow-ups (request queued, completed,
      // received result, uploaded …). Collapse them into a single
      // "Called <tool>" disclosure so the activity feed isn't a wall of
      // status text. THOUGHT or a new CLIENT_TOOL closes the group.
      if (currentToolGroup && currentToolGroup.parentId !== parent.id) {
        currentToolGroup = null;
      }
      const isToolStart = parsed.tag === 'CLIENT_TOOL';
      const isThought = parsed.tag === 'THOUGHT';
      if (isToolStart || isThought) {
        currentToolGroup = null;
      }

      if (isToolStart) {
        const meta = extractClientToolMeta(parsed.body);
        const det = document.createElement('details');
        det.className = 'sub-tool-group';
        const sum = document.createElement('summary');
        sum.className = 'sub-tool-group-summary';
        sum.appendChild(document.createTextNode('Called '));
        const code = el('code', 'sub-tool-name');
        code.textContent = meta ? meta.name : 'tool';
        sum.appendChild(code);
        det.appendChild(sum);
        const groupBody = el('div', 'sub-tool-group-body');
        det.appendChild(groupBody);
        // Seed the body with the request payload so it's the first
        // detail visible on expand.
        if (meta && (meta.data || meta.jsonText)) {
          const pre = el('pre', 'sub-tool-pre');
          pre.textContent = meta.data
            ? JSON.stringify(meta.data, null, 2)
            : (meta.jsonText || '');
          groupBody.appendChild(pre);
        }
        parent.body.appendChild(det);
        parent.el.setAttribute('aria-expanded', 'true');
        currentToolGroup = { el: det, body: groupBody, parentId: parent.id, id: msg.id };
        if (!isInitial) dispatchClientToolFromText(parsed.body);
        messages.set(msg.id, {
          id: msg.id, role, text: parsed.body, ts: msg.timestamp,
          kind: 'tool-group', el: det, tag: parsed.tag,
        });
        order.push(msg.id);
        scrollToBottom();
        return;
      }

      // Fold follow-ups into the active tool group when one is open.
      if (currentToolGroup && !isThought) {
        const sub = renderSubactivity(parsed.body, parsed.tag);
        currentToolGroup.body.appendChild(sub);
        parent.el.setAttribute('aria-expanded', 'true');
        messages.set(msg.id, {
          id: msg.id, role, text: parsed.body, ts: msg.timestamp,
          kind: 'subactivity', el: sub, tag: parsed.tag,
        });
        order.push(msg.id);
        scrollToBottom();
        return;
      }

      const sub = renderSubactivity(parsed.body, parsed.tag);
      parent.body.appendChild(sub);
      parent.el.setAttribute('aria-expanded', 'true');
      messages.set(msg.id, { id: msg.id, role, text: parsed.body, ts: msg.timestamp, kind: 'subactivity', el: sub, tag: parsed.tag });
      order.push(msg.id);
    } else {
      // AGiXT writes assistant messages with the agent's name as the
      // role (e.g. "xt", "XT", custom agent names) — not the literal
      // "assistant". Use the comparableRole helper so the finalize +
      // reset logic fires regardless of which agent produced the reply.
      const cmpRole = comparableRole(role);
      const isAssistantLike = cmpRole === 'assistant';
      // Non-activity plain message. Reset activity grouping so the next
      // activity opens a fresh block (matches web's USER-or-assistant
      // boundary behavior).
      if (cmpRole === 'user' || isAssistantLike) {
        lastActivityId = null;
        lastThinkingActivityId = null;
        currentToolGroup = null;
        activityIdAlias.clear();
      }
      const specialToolCalls = isAssistantLike ? extractSpecialProtocolToolCalls(parsed.body, msg.id) : [];
      const visibleBody = specialToolCalls.length ? stripSpecialProtocolToolMarkup(parsed.body) : parsed.body;
      if (isAssistantLike && specialToolCalls.length && !visibleBody) {
        // Some models leak their internal tool-call wire format as normal
        // assistant text. The live streaming path already converts that into
        // client-side tool execution; suppress persisted copies so the raw
        // protocol does not reappear in history or WebSocket replays.
        messages.set(msg.id, {
          id: msg.id, role, text: parsed.body, ts: msg.timestamp,
          kind: 'suppressed-tool-call', el: null,
        });
        order.push(msg.id);
        return;
      }
      const r = renderPlain(role, visibleBody, msg.timestamp);
      list.appendChild(r.el);
      messages.set(msg.id, { id: msg.id, role, text: visibleBody, ts: msg.timestamp, kind: 'plain', el: r.el, content: r.content });
      order.push(msg.id);
      if (isAssistantLike && audio) audio.scanForAudio(visibleBody);
      if (isAssistantLike) {
        stopAllSpinners();
        // Final assistant text landed — relabel/collapse the preceding
        // activity blocks. Skip when the body is empty so an empty
        // router message doesn't prematurely collapse a still-running
        // thinking block.
        if (visibleBody && visibleBody.trim()) {
          finalizeActivityBlocks();
        }
        if (!isInitial) dispatchFencedClientTools(parsed.body);
      }
    }
    scrollToBottom();
  }

  function update(msg) {
    if (!msg || !msg.id) return;
    const existing = messages.get(msg.id);
    if (!existing) return ingest(msg, false);
    const parsed = parseMessageEnvelope(msg.message);
    if (existing.kind === 'suppressed-tool-call') {
      messages.delete(msg.id);
      order = order.filter((x) => x !== msg.id);
      return ingest(msg, false);
    }
    if (existing.kind === 'plain' && existing.content) {
      existing.text = parsed.body;
      renderMdInto(existing.content, parsed.body);
    } else if (existing.kind === 'activity') {
      const titleEl = existing.el.querySelector('.activity-title');
      if (titleEl) titleEl.textContent = parsed.label || parsed.body || existing.text;
      touchActivityElapsed(existing, msg.timestamp);
    } else if (existing.kind === 'subactivity') {
      // EXECUTION renders as <details><summary class=sub-exec-title>…</summary>
      // <body class=sub-exec-body>…</body></details>; rebuild the whole node
      // in place so a streaming update (title may grow, body may grow) lands
      // in the right slots instead of clobbering the title with the body.
      if (existing.el.classList.contains('subactivity')
          && existing.el.getAttribute('data-tag') === 'EXECUTION') {
        const content = existing.el.querySelector('.sub-content');
        if (content) {
          replaceChildren(content, document.createDocumentFragment());
          const next = renderExecutionBody(parsed.body);
          if (next) content.appendChild(next);
        }
      } else {
        const inner = existing.el.querySelector('.md');
        if (inner) renderMdInto(inner, parsed.body);
      }
    }
    scrollToBottom();
  }

  function stopAllSpinners() {
    document.querySelectorAll('.activity[data-running="true"]').forEach((a) => {
      a.setAttribute('data-running', 'false');
    });
  }

  // Once the assistant has produced a real reply, the activity block is
  // history. Relabel its header ("Thinking…" → "Activities"), stop the
  // spinner, and collapse it. The user can still expand it later.
  function finalizeActivityBlocks() {
    document.querySelectorAll('.activity').forEach((a) => {
      if (a.getAttribute('data-finalized') === 'true') return;
      // Freeze elapsed at the value last shown while running (which may
      // have come from the live client clock) so the final "Worked for …"
      // doesn't snap backwards to a smaller server-timestamp delta.
      const frozen = activityElapsedMs(a, true);
      const startMs = Number(a.dataset.startMs);
      if (Number.isFinite(startMs)) a.dataset.lastMs = String(startMs + frozen);
      a.setAttribute('data-finalized', 'true');
      a.setAttribute('data-running', 'false');
      a.setAttribute('aria-expanded', 'false');
      const titleEl = a.querySelector('.activity-title');
      if (titleEl) titleEl.textContent = 'Activities';
      refreshActivityElapsed(a);
    });
    activeStreamingActivity = null;
    currentToolGroup = null;
  }

  function dispatchClientToolFromText(text) {
    if (!clientActions) return;
    // Heuristic: look for a JSON object inside the subactivity body.
    const m = text.match(/\{[\s\S]*\}/);
    if (!m) return;
    let obj;
    try { obj = JSON.parse(m[0]); } catch (_) { return; }
    if (!obj || typeof obj !== 'object') return;
    if (!obj.tool_name && !obj.name && !obj.action_type) return;
    runClientTool(obj);
  }

  /** Scan an assistant message body for fenced ```client_tool``` JSON
   *  blocks and dispatch each one. Also accepts ```json blocks that
   *  unambiguously contain a `tool_name` so a slightly off-spec model
   *  doesn't silently fail. */
  function dispatchFencedClientTools(body) {
    if (!clientActions || !body) return;
    extractFencedToolCalls(body).forEach((tc) => {
      runClientTool({ tool_name: tc.name, tool_args: tc.args, id: tc.id });
    });
  }

  /** Send a tool call through the IPC dispatcher and surface the result
   *  inline as a small chip so the user can see what actually ran. */
  async function runClientTool(call) {
    const name = call.tool_name || call.name || call.action_type || '?';
    const chip = renderToolChip(`Calling ${name}…`, 'pending');
    const list = els().list;
    if (list && chip) list.appendChild(chip);
    scrollToBottom();
    try {
      const res = await clientActions.execute(call);
      if (chip) {
        if (res && res.error) {
          chip.classList.replace('pending', 'error');
          chip.querySelector('.tool-chip-text').textContent = `${name}: ${res.error}`;
        } else {
          chip.classList.replace('pending', 'ok');
          chip.querySelector('.tool-chip-text').textContent = `${name} ✓`;
        }
      }
    } catch (err) {
      if (chip) {
        chip.classList.replace('pending', 'error');
        chip.querySelector('.tool-chip-text').textContent =
          `${name}: ${(err && err.error) || err}`;
      }
    }
  }

  function renderToolChip(text, state) {
    const chip = el('div', `tool-chip ${state || 'pending'}`);
    const dot = el('span', 'tool-chip-dot');
    const txt = el('span', 'tool-chip-text');
    txt.textContent = text;
    chip.appendChild(dot);
    chip.appendChild(txt);
    return chip;
  }

  // ----- WebSocket lifecycle -----

  function buildUrl() {
    if (!serverUrl || !conversationId || !jwt) return null;
    const u = new URL(serverUrl);
    const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${u.host}/v1/conversation/${encodeURIComponent(conversationId)}/stream?authorization=${encodeURIComponent(jwt)}&limit=500`;
  }

  function disconnect() {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (ws) {
      try { ws.close(); } catch (_) { /* ignore */ }
      ws = null;
    }
    setStatus('disconnected');
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    setStatus(`reconnecting in ${Math.round(backoffMs / 1000)}s…`, 'error');
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, backoffMs);
    backoffMs = Math.min(backoffMs * 2, 30000);
  }

  function connect() {
    disconnect();
    const url = buildUrl();
    if (!url) {
      setStatus('not configured', 'error');
      return;
    }
    setStatus('connecting…');
    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error('WS construct error', err);
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      backoffMs = 1000;
      setStatus('connected', 'connected');
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          try { ws.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() })); } catch (_) { /* ignore */ }
        }
      }, 30000);
    };
    ws.onmessage = (ev) => {
      let envelope;
      try { envelope = JSON.parse(ev.data); } catch (_) { return; }
      handleEnvelope(envelope);
    };
    ws.onerror = (err) => {
      console.warn('WS error', err);
    };
    ws.onclose = () => {
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
      ws = null;
      scheduleReconnect();
    };
  }

  function handleEnvelope(env) {
    if (!env || !env.type) return;
    switch (env.type) {
      case 'connected':
      case 'heartbeat':
      case 'pong':
        return;
      case 'initial_data':
        if (Array.isArray(env.data)) {
          env.data.forEach((msg) => ingest(msg, true));
        }
        return;
      case 'initial_message':
      case 'message_added':
        ingest(env.data, env.type === 'initial_message');
        return;
      case 'message_updated':
        update(env.data);
        return;
      case 'messages_deleted':
        {
          const deletedIds = env.data && Array.isArray(env.data.deleted_message_ids)
            ? env.data.deleted_message_ids
            : null;
          if (deletedIds && deletedIds.length) {
            deletedIds.forEach((id) => removeMessage(id));
          } else {
            clear();
          }
        }
        return;
      case 'conversation_renamed':
        // AGiXT renames a conversation after the first user/assistant
        // exchange (replacing the default "-" placeholder with a
        // model-generated short title). Forward to the host page so
        // the topbar chip + the cached conversation list pick up the
        // new name without needing a manual refresh.
        try {
          const ev = new CustomEvent('agixt-conversation-renamed', {
            detail: env.data || {},
          });
          window.dispatchEvent(ev);
        } catch (_) { /* ignore */ }
        return;
      case 'typing_indicator':
        return;
      case 'error':
        setComposerStatus(env.message || 'agent error', 'error');
        return;
      default:
        return;
    }
  }

  /** Pretty-print a tool result for the model. Strips `image_url` data
   *  to avoid blowing the token budget — the desktop client renders the
   *  image to the user but the model only needs the metadata. */
  function summarizeToolResult(res) {
    if (res == null) return 'null';
    if (typeof res === 'string') return res;
    try {
      const cleaned = { ...res };
      delete cleaned.image_url;
      delete cleaned.image_data;
      return JSON.stringify(cleaned, null, 2);
    } catch (_) { return String(res); }
  }

  function screenshotDataUrl(result) {
    if (!result || !result.image_data) return '';
    let format = String(result.format || 'jpeg').toLowerCase().replace(/[^a-z0-9.+-]/g, '');
    if (!format || format === 'jpg') format = 'jpeg';
    return `data:image/${format};base64,${result.image_data}`;
  }

  function toolResultText(tc, result, summary, originalTask) {
    const taskText = originalTask && originalTask.trim()
      ? `\nOriginal user task: ${originalTask.trim()}`
      : '';
    const isError = result && result.error;
    const intro = isError
      ? `Client-side tool ${tc.name} failed.${taskText}`
      : `Client-side tool ${tc.name} completed.${taskText}`;
    const guidance = [
      intro,
      'This is a desktop tool observation, not a new user request.',
      'Continue the original task using this result as context.',
    ];
    if (tc.name === 'desktop_click' || tc.name === 'desktop_move' || tc.name === 'desktop_drag') {
      guidance.push(
        'Any x/y values in this result are actual screen pixels where the action happened; do not treat them as requested coordinates and do not click them again unless a fresh screenshot shows another click is needed.',
        'For visible UI tasks, take a fresh desktop_screenshot to verify the result before answering unless the user explicitly asked only to click exact coordinates.',
      );
    }
    if (isError) {
      guidance.push('Do not stop on this failure if another desktop route can complete the user task.');
    }
    return `${guidance.join('\n')}\nResult:\n${summary}`;
  }

  function toolResultMessage(tc, result, summary, originalTask) {
    const msg = {
      role: 'tool',
      tool_call_id: tc.id,
      name: tc.name,
      content: toolResultText(tc, result, summary, originalTask),
      log_user_input: false,
      enable_command_selection: false,
    };
    const shotUrl = tc.name === 'desktop_screenshot' ? screenshotDataUrl(result) : '';
    if (shotUrl) {
      const taskText = originalTask && originalTask.trim()
        ? `\nOriginal user task: ${originalTask.trim()}\n`
        : '\n';
      msg.content = [
        {
          type: 'text',
          text: `Client-side tool desktop_screenshot completed.${taskText}This is a desktop tool observation, not a new user request. Use this screenshot to decide the next desktop action. If the task asks to click, open, select, or inspect visible UI, identify the target element and its visual center coordinates in screenshot image pixels. The image coordinate space is 0,0 at the top-left and width,height from the screenshot metadata at the bottom-right. For application icons, prefer the OS dock/application launcher icon at the physical screen edge when visible rather than similar logos inside webpages, AGiXT sidebars, browser tabs, contacts, or code editors. If the dock is on the far left of a 1920px-wide screenshot, the icon center is usually under x=40 image pixels; x values around 50-384 usually belong to an app/sidebar, not the OS dock. Do not click the top-left edge of an icon; click the center of the requested target. On the click, send the screenshot pixel coordinates with coordinate_space:"screenshot", echo this screenshot's width/height as target_width/target_height, echo original_width/original_height as screen_width/screen_height, and include monitor_offset_x/monitor_offset_y. Metadata:\n${summary}`,
        },
        {
          type: 'image_url',
          image_url: { url: shotUrl },
        },
      ];
    }
    return msg;
  }

  // Active turn handle exposed for the Stop button. `runStreamingTurn`
  // refreshes this each round so `stop()` can always abort the live
  // listener and resolve the in-flight finished promise. setGenerating
  // notifies subscribers (typically the composer) when the send/stop
  // affordance should swap. Mirrors the web app's stop-conversation
  // flow (see web/components/conversation/conversation.tsx:3635).
  let activeTurn = null;
  // Sticky stopped flag: once the user clicks Stop the local recursion
  // (tool execution + follow-up runStreamingTurn) must NOT re-arm. Just
  // resolving the finished promise wasn't enough — runStreamingTurn
  // still ran the tool loop and recursed into another round, so the
  // user kept seeing screenshots / clicks / etc. fire after Stop.
  let turnStopped = false;
  const generatingListeners = new Set();
  function setGenerating(on) {
    generatingListeners.forEach((cb) => { try { cb(!!on); } catch (_) {} });
  }
  function onGeneratingChange(cb) {
    if (typeof cb !== 'function') return () => {};
    generatingListeners.add(cb);
    return () => generatingListeners.delete(cb);
  }

  async function stop() {
    const turn = activeTurn;
    turnStopped = true;
    activeTurn = null;
    setGenerating(false);
    if (!turn) return;
    try { if (typeof turn.unlisten === 'function') turn.unlisten(); } catch (_) {}
    try { if (typeof turn.resolveFinished === 'function') turn.resolveFinished('stopped'); } catch (_) {}
    if (turn.placeholder && turn.placeholder.content) {
      turn.placeholder.content.classList.remove('cursor-blink');
    }
    finalizeActivityBlocks();
    setComposerStatus('');
    if (!serverUrl || !jwt) return;
    const base = serverUrl.replace(/\/+$/, '');
    const headers = {
      Authorization: `Bearer ${jwt}`,
      'Content-Type': 'application/json',
    };
    // Mirror the web SDK: try the specific conversation first, then a
    // belt-and-suspenders stop-all so trailing background work halts too.
    const tries = [];
    if (turn.conversationId && turn.conversationId !== '-') {
      tries.push(`${base}/v1/conversation/${encodeURIComponent(turn.conversationId)}/stop`);
    }
    tries.push(`${base}/v1/conversations/stop`);
    for (const url of tries) {
      try {
        const fetcher = window.AgixtSession && typeof window.AgixtSession.fetch === 'function'
          ? window.AgixtSession.fetch(url, { method: 'POST', headers, body: '{}' })
          : fetch(url, { method: 'POST', headers, body: '{}' });
        await fetcher;
      } catch (err) {
        console.warn('stop POST failed', url, err);
      }
    }
  }

  // AGiXT's `/v1/chat/completions` persists the conversation server-side
  // keyed by `conversation_name`. Sending the entire OpenAI-style
  // history each round causes AGiXT to re-persist the user message and
  // tool calls every time, producing visible duplicates. The kids app and
  // ESP32 pattern is what we mirror: send only the new turn each call,
  // either a single user message or the matching role:tool result(s).
  function newStreamId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    const bytes = new Uint8Array(12);
    if (window.crypto && typeof window.crypto.getRandomValues === 'function') {
      window.crypto.getRandomValues(bytes);
    }
    const suffix = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `stream-${Date.now()}-${suffix}`;
  }

  function streamActivityTag(kind) {
    switch (String(kind || '').toLowerCase()) {
      case 'thinking':
      case 'thinking_stream':
        return 'THOUGHT';
      case 'reflection':
      case 'reflection_stream':
        return 'REFLECTION';
      case 'client_tool':
        return 'CLIENT_TOOL';
      case 'remote':
        return 'REMOTE';
      case 'activity_error':
      case 'error':
        return 'ERROR';
      case 'execute':
      case 'activity':
        return 'EXECUTION';
      default:
        return 'THOUGHT';
    }
  }

  function appendLiveSubactivity(parent, body, tag, streamId) {
    if (!parent || !parent.body || !body) return null;
    if (parent.el) {
      parent.el.setAttribute('data-running', 'true');
      refreshActivityElapsed(parent.el);
      ensureElapsedTicker();
    }
    const msgId = `local-sub-${streamId}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const isToolStart = tag === 'CLIENT_TOOL';
    const isThought = tag === 'THOUGHT' || tag === 'REFLECTION';
    if (isToolStart || isThought) currentToolGroup = null;

    if (isToolStart) {
      const meta = extractClientToolMeta(body);
      const det = document.createElement('details');
      det.className = 'sub-tool-group';
      const sum = document.createElement('summary');
      sum.className = 'sub-tool-group-summary';
      sum.appendChild(document.createTextNode('Called '));
      const code = el('code', 'sub-tool-name');
      code.textContent = meta ? meta.name : 'tool';
      sum.appendChild(code);
      det.appendChild(sum);
      const groupBody = el('div', 'sub-tool-group-body');
      det.appendChild(groupBody);
      if (meta && (meta.data || meta.jsonText)) {
        const pre = el('pre', 'sub-tool-pre');
        pre.textContent = meta.data
          ? JSON.stringify(meta.data, null, 2)
          : (meta.jsonText || '');
        groupBody.appendChild(pre);
      }
      parent.body.appendChild(det);
      parent.el.setAttribute('aria-expanded', 'true');
      currentToolGroup = { el: det, body: groupBody, parentId: parent.id, id: msgId };
      messages.set(msgId, {
        id: msgId, role: 'assistant', text: body, ts: new Date().toISOString(),
        kind: 'tool-group', el: det, tag,
      });
      order.push(msgId);
      return det;
    }

    if (currentToolGroup && currentToolGroup.parentId === parent.id && !isThought) {
      const sub = renderSubactivity(body, tag);
      currentToolGroup.body.appendChild(sub);
      parent.el.setAttribute('aria-expanded', 'true');
      messages.set(msgId, {
        id: msgId, role: 'assistant', text: body, ts: new Date().toISOString(),
        kind: 'subactivity', el: sub, tag,
      });
      order.push(msgId);
      return sub;
    }

    const sub = renderSubactivity(body, tag);
    parent.body.appendChild(sub);
    parent.el.setAttribute('aria-expanded', 'true');
    messages.set(msgId, {
      id: msgId, role: 'assistant', text: body, ts: new Date().toISOString(),
      kind: 'subactivity', el: sub, tag,
    });
    order.push(msgId);
    return sub;
  }

  function mergeStreamText(existing, incoming) {
    const current = String(existing || '');
    const chunk = String(incoming || '');
    if (!chunk) return current;
    if (!current) return chunk;
    // The Rust stream bridge normalizes cumulative snapshots into deltas,
    // but keep the renderer defensive for older bridges or direct test
    // harnesses. Snapshot: "hello" -> "hello world"; delta: " world".
    if (chunk.startsWith(current)) return chunk;
    if (current.startsWith(chunk)) return current;
    return current + chunk;
  }

  async function send(userInput, conversationName, turnContext) {
    if (!userInput || !userInput.trim()) return;
    const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    const event = window.__TAURI__ && window.__TAURI__.event;
    if (!inv || !event) {
      setComposerStatus('Tauri IPC unavailable', 'error');
      return;
    }
    showChat();
    setComposerStatus('Sending…');

    // Echo user message immediately so the user sees what they typed.
    const localUserId = `local-user-${Date.now()}`;
    ingest({
      id: localUserId,
      role: 'user',
      message: userInput,
      timestamp: new Date().toISOString(),
    }, false);

    // New turn — clear any sticky stopped flag from a prior run so this
    // user message is allowed to recurse normally.
    turnStopped = false;
    activeStreamingActivity = null;
    currentToolGroup = null;
    setGenerating(true);
    try {
      const message = { role: 'user', content: userInput };
      if (turnContext && String(turnContext).trim()) {
        message.context = String(turnContext).trim();
      }
      await runStreamingTurn(inv, event, conversationName, [message], userInput);
    } finally {
      activeTurn = null;
      setGenerating(false);
    }
  }

  /** Drive one streaming round through /v1/chat/completions. Repeats
   *  itself when the server emits tool calls — we execute the tools
   *  locally, send only the new role:tool results, and let AGiXT
   *  continue from its server-side conversation state. */
  async function runStreamingTurn(inv, event, conversationName, turnMessages, originalTask) {
    const asstId = `local-asst-${Date.now()}`;
    const turnBoundaryIndex = order.length;
    // Lazy placeholder: pure tool-call rounds (the model produces no
    // text, only `remote_command.request` events) used to leave behind
    // an empty grey bubble in the chat. We now defer creating the
    // placeholder until the first 'delta' actually arrives. Activities
    // still get a sane insertion point — when no placeholder exists
    // they just append to the list, which is fine because the next
    // round's bubble (if any) lands below them.
    let placeholder = null;
    let asstEntry = null;
    function ensurePlaceholder() {
      if (placeholder) return placeholder;
      placeholder = renderPlain('assistant', '', new Date().toISOString());
      els().list.appendChild(placeholder.el);
      asstEntry = {
        id: asstId, role: 'assistant', text: '', ts: new Date().toISOString(),
        kind: 'plain', el: placeholder.el, content: placeholder.content,
      };
      messages.set(asstId, asstEntry);
      order.push(asstId);
      placeholder.content.classList.add('cursor-blink');
      return placeholder;
    }

    const streamId = newStreamId();
    const collectedTools = [];
    let assistantText = '';
    // One rolling activity block is shared across recursive tool rounds:
    // user prompt -> client tool request -> role:tool result -> final answer.
    // This mirrors AGiXT Python's single [ACTIVITY] Thinking parent.
    function ensureStreamingActivity() {
      if (
        activeStreamingActivity
        && activeStreamingActivity.el
        && activeStreamingActivity.el.getAttribute('data-finalized') !== 'true'
      ) {
        return activeStreamingActivity;
      }
      const r = renderActivity('Thinking', 'thought');
      const activityId = `local-activity-${streamId}`;
      if (placeholder && placeholder.el && placeholder.el.parentNode) {
        placeholder.el.parentNode.insertBefore(r.el, placeholder.el);
      } else {
        els().list.appendChild(r.el);
      }
      r.el.setAttribute('aria-expanded', 'true');
      const entry = {
        id: activityId,
        role: 'assistant',
        text: '',
        ts: new Date().toISOString(),
        kind: 'activity',
        el: r.el,
        body: r.body,
        type: 'thought',
        transient: true,
        streamText: '',
      };
      messages.set(activityId, entry);
      order.push(activityId);
      lastActivityId = activityId;
      lastThinkingActivityId = activityId;
      activeStreamingActivity = {
        id: activityId,
        kind: 'activity',
        el: r.el,
        body: r.body,
        subContent: null,
        subTag: null,
        streamText: '',
      };
      initActivityElapsed(r.el, entry.ts, false);
      ensureElapsedTicker();
      return activeStreamingActivity;
    }
    let unlisten;
    let resolveFinished;
    const finished = new Promise((resolve) => { resolveFinished = resolve; });

    // Register this round so the global stop() can abort it. Each
    // recursion overrides — only the most-recent listener needs cleaning
    // up, and once a round resolves the next one re-registers.
    activeTurn = {
      conversationId,
      get placeholder() { return placeholder; },
      resolveFinished,
      unlisten: null,
    };

    try {
      unlisten = await event.listen(`chat-stream:${streamId}`, (msg) => {
        const ev = msg && msg.payload && msg.payload.event;
        if (!ev) return;
        switch (ev.kind) {
          case 'delta': {
            const inc = (ev.data && ev.data.text) || '';
            if (!inc && !assistantText) break;
            ensurePlaceholder();
            assistantText = mergeStreamText(assistantText, inc);
            asstEntry.text = assistantText;
            renderMdInto(placeholder.content, assistantText);
            dispatchAssistantEvent('agixt-chat-assistant-stream', {
              text: assistantText,
              chunk: inc,
              streamId,
              conversationId,
            });
            scrollToBottom();
            break;
          }
          case 'tool_call': {
            collectedTools.push({
              id: ev.data.id,
              name: ev.data.name,
              args: ev.data.args,
              origin: ev.data.origin || 'openai_tool_call',
            });
            break;
          }
          case 'activity': {
            const chunk = (ev.data && ev.data.content) || '';
            const tag = streamActivityTag(ev.data && ev.data.kind);
            const complete = !!(ev.data && ev.data.complete);
            if (!chunk && !complete) break;
            const streamingActivity = ensureStreamingActivity();
            if (chunk) {
              if (tag === 'THOUGHT' || tag === 'REFLECTION') {
                if (!streamingActivity.subContent || streamingActivity.subTag !== tag) {
                  currentToolGroup = null;
                  const sub = renderSubactivity('', tag);
                  streamingActivity.body.appendChild(sub);
                  streamingActivity.subContent = sub.querySelector('.sub-content .md') || sub;
                  streamingActivity.subTag = tag;
                  streamingActivity.streamText = '';
                }
                // AGiXT emits each thinking/reflection activity.stream event
                // as a delta, so concatenate into one rolling subactivity.
                streamingActivity.streamText += chunk;
                renderMdInto(streamingActivity.subContent, streamingActivity.streamText);
                const activityEntry = messages.get(streamingActivity.id);
                if (activityEntry) {
                  activityEntry.text = streamingActivity.streamText;
                  activityEntry.streamText = streamingActivity.streamText;
                }
              } else {
                appendLiveSubactivity(streamingActivity, chunk, tag, streamId);
              }
            }
            if (complete && (tag === 'THOUGHT' || tag === 'REFLECTION')) {
              streamingActivity.el.setAttribute('data-running', 'false');
            }
            scrollToBottom();
            break;
          }
          case 'done': {
            const finalText = ev.data.text || assistantText;
            const inlineTools = extractInlineClientToolCalls(finalText, streamId);
            if (inlineTools.length) {
              inlineTools.forEach((tc) => collectedTools.push(tc));
              if (placeholder) {
                placeholder.content.classList.remove('cursor-blink');
                asstEntry.text = '';
                renderMdInto(placeholder.content, '');
              }
              resolveFinished('tool_calls');
              break;
            }
            if (finalText && finalText.trim()) {
              const matchingServerId = findMatchingPlainId('assistant', finalText, {
                local: false,
                startIndex: turnBoundaryIndex,
              });
              if (matchingServerId) {
                if (placeholder) {
                  removeMessage(asstId);
                  placeholder = null;
                  asstEntry = null;
                }
              } else {
                ensurePlaceholder();
                placeholder.content.classList.remove('cursor-blink');
                asstEntry.text = finalText;
                renderMdInto(placeholder.content, finalText);
              }
              dispatchAssistantEvent('agixt-chat-assistant-final', {
                text: finalText,
                streamId,
                conversationId,
              });
            } else if (placeholder) {
              placeholder.content.classList.remove('cursor-blink');
            }
            if (audio && finalText) audio.scanForAudio(finalText);
            // Finalize the Activity block(s) only when an actual textual
            // reply landed — pure tool-call turns are still in progress
            // and will get finalized by the follow-up round's done.
            if (finalText && finalText.trim()) {
              finalizeActivityBlocks();
            }
            dispatchAssistantEvent('agixt-chat-turn-complete', {
              text: finalText || '',
              streamId,
              conversationId,
              finishReason: ev.data.finish_reason || '',
            });
            resolveFinished(ev.data.finish_reason || '');
            break;
          }
          case 'error': {
            const msg2 = (ev.data && ev.data.message) || 'stream error';
            if (placeholder) {
              placeholder.content.classList.remove('cursor-blink');
              asstEntry.text = msg2;
              placeholder.content.textContent = msg2;
            }
            setComposerStatus(msg2, 'error');
            resolveFinished('error');
            break;
          }
        }
      });
      // Hand the listener to activeTurn so stop() can detach it.
      if (activeTurn) activeTurn.unlisten = unlisten;
      await inv('chat_send', {
        args: { stream_id: streamId, messages: turnMessages, conversation_name: conversationName },
      });
    } catch (err) {
      if (typeof unlisten === 'function') unlisten();
      const msg2 = String((err && err.error) || err);
      if (placeholder) {
        placeholder.content.classList.remove('cursor-blink');
        asstEntry.text = msg2;
        placeholder.content.textContent = msg2;
      }
      setComposerStatus(msg2, 'error');
      return;
    }

    const finishReason = await finished;
    if (typeof unlisten === 'function') unlisten();
    setComposerStatus('');

    // Stop button pressed (or upstream error): drop everything we
    // collected this round and don't recurse. Without this guard the
    // local loop would still execute any tool calls AGiXT sent before
    // the stop landed and queue up another runStreamingTurn — the
    // visible "Stop didn't actually stop" symptom.
    if (turnStopped || finishReason === 'stopped' || finishReason === 'error') return;
    if (collectedTools.length === 0) return;

    // Execute the tools the model asked for. The activity block already
    // surfaces the call+result via the persisted [SUBACTIVITY][CLIENT_TOOL]
    // markers (see the tool-group rendering in ingest), so we don't
    // render redundant tool chips here. The chips were leaving the
    // activity feed cluttered with duplicates of the call status.
    const toolResultMessages = [];
    for (const tc of collectedTools) {
      // Re-check before every tool — stop() can land mid-loop while
      // earlier tools were awaiting. Bail without firing more desktop
      // automation than necessary.
      if (turnStopped) return;
      let result;
      try {
        if (!clientActions || typeof clientActions.execute !== 'function') {
          result = { error: 'client action dispatcher unavailable' };
        } else {
          const toolArgs = typeof tc.args === 'string' ? safeParse(tc.args) : (tc.args || {});
          if (toolArgs && typeof toolArgs === 'object' && originalTask) {
            toolArgs.__original_task = originalTask;
          }
          result = await clientActions.execute({
            tool_name: tc.name,
            tool_args: toolArgs,
          });
        }
      } catch (e) {
        result = { error: String(e && e.error ? e.error : e) };
      }
      const summary = summarizeToolResult(result);
      toolResultMessages.push(toolResultMessage(tc, result, summary, originalTask));
    }

    if (turnStopped || toolResultMessages.length === 0) {
      return;
    }

    // If this round produced no text reply (pure tool calls), drop the
    // empty assistant placeholder before recursing so we don't leave a
    // stranded grey bubble in the chat between rounds.
    if (placeholder && asstEntry && !asstEntry.text.trim()) {
      removeMessage(asstId);
      placeholder = null;
      asstEntry = null;
    }

    await runStreamingTurn(
      inv,
      event,
      conversationName,
      toolResultMessages,
      originalTask,
    );
  }

  function safeParse(s) {
    try { return JSON.parse(s); } catch (_) { return {}; }
  }

  function decodeXmlishText(value) {
    return String(value == null ? '' : value)
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, '&');
  }

  function parseInlineScalar(value) {
    const text = decodeXmlishText(value).trim();
    if (/^(true|false)$/i.test(text)) return text.toLowerCase() === 'true';
    if (/^-?\d+$/.test(text)) return Number(text);
    if (/^-?\d+\.\d+$/.test(text)) return Number(text);
    if (/^[\[{]/.test(text)) {
      try { return JSON.parse(text); } catch (_) { /* keep as text */ }
    }
    return text;
  }

  function normalizeInlineToolCall(obj, origin, index, streamId) {
    if (!obj || typeof obj !== 'object') return null;
    const name = obj.tool_name || obj.name || obj.action_type || obj.tool || '';
    if (!name) return null;
    let args = obj.tool_args ?? obj.arguments ?? obj.args ?? obj.input ?? null;
    if (typeof args === 'string') {
      try { args = JSON.parse(args); } catch (_) { /* dispatcher also accepts strings */ }
    }
    if (args == null || typeof args !== 'object' || Array.isArray(args)) {
      args = {};
      Object.keys(obj).forEach((k) => {
        if (!['id', 'tool_call_id', 'tool_name', 'name', 'action_type', 'tool', 'tool_args', 'arguments', 'args', 'input'].includes(k)) {
          args[k] = obj[k];
        }
      });
    }
    const id = obj.id || obj.tool_call_id || `inline-${streamId || Date.now()}-${index}`;
    return {
      id: String(id),
      name: String(name),
      args,
      origin,
    };
  }

  function parseSpecialToolArgs(raw) {
    const cleaned = String(raw || '')
      .replace(/<\|?tool_call_path\|?>/gi, '')
      .trim();
    if (!cleaned) return {};
    if (/^[\[{]/.test(cleaned)) {
      try { return JSON.parse(cleaned); } catch (_) { /* fall through */ }
    }
    const args = {};
    const tagRe = /<([A-Za-z_][\w.-]*)>([\s\S]*?)<\/\1>/g;
    let match;
    while ((match = tagRe.exec(cleaned)) !== null) {
      args[match[1]] = parseInlineScalar(match[2]);
    }
    return args;
  }

  function extractSpecialProtocolToolCalls(body, streamId) {
    const text = String(body || '');
    if (!text.includes('<|tool_call_begin|>')) return [];
    const calls = [];
    const callRe = /<\|tool_call_begin\|>\s*([A-Za-z0-9_.:-]+)?\s*([\s\S]*?)<\|tool_call_end\|>/gi;
    let match;
    while ((match = callRe.exec(text)) !== null) {
      const name = (match[1] || '').trim();
      if (!name) continue;
      calls.push({
        id: `special-${streamId || Date.now()}-${calls.length}`,
        name,
        args: parseSpecialToolArgs(match[2]),
        origin: 'inline_special_tool_call',
      });
    }
    return calls;
  }

  function stripSpecialProtocolToolMarkup(body) {
    return String(body || '')
      .replace(/<\|tool_calls_section_begin\|>[\s\S]*?<\|tool_calls_section_end\|>/gi, '')
      .replace(/<\|tool_call_begin\|>[\s\S]*?<\|tool_call_end\|>/gi, '')
      .trim();
  }

  function extractFencedToolCalls(body, streamId) {
    const calls = [];
    const fence = /```(client_tool|json)\s*\n([\s\S]*?)```/gi;
    let match;
    while ((match = fence.exec(String(body || ''))) !== null) {
      const blob = match[2].trim();
      let obj;
      try { obj = JSON.parse(blob); } catch (_) { continue; }
      const normalized = normalizeInlineToolCall(
        obj,
        match[1].toLowerCase() === 'client_tool' ? 'inline_client_tool_fence' : 'inline_json_tool_fence',
        calls.length,
        streamId,
      );
      if (normalized) calls.push(normalized);
    }
    return calls;
  }

  function extractInlineClientToolCalls(body, streamId) {
    return [
      ...extractSpecialProtocolToolCalls(body, streamId),
      ...extractFencedToolCalls(body, streamId),
    ];
  }

  function configure(opts) {
    serverUrl = opts.serverUrl || serverUrl;
    jwt = opts.jwt || jwt;
    conversationId = opts.conversationId || conversationId;
    if (md && typeof md.setTrustedMediaOrigins === 'function') {
      md.setTrustedMediaOrigins(Array.from(trustedWorkspaceOrigins()));
    }
    if (opts.reconnect !== false) connect();
  }

  /** Replay an entry from `GET /v1/conversation/{id}` history through the
   *  same `ingest()` path used for live WebSocket messages. The history
   *  payload uses the same `{id, role, message, timestamp}` shape so we
   *  can reuse the parser unchanged. */
  async function loadHistory(convoId) {
    if (!convoId) return;
    const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    if (!inv) return;
    clear();
    let entries = [];
    try {
      entries = await inv('get_conversation_history', {
        conversationId: convoId,
        limit: 200,
        page: 1,
      });
    } catch (e) {
      console.warn('get_conversation_history failed', e);
      return;
    }
    if (!Array.isArray(entries)) return;
    // AGiXT keeps the conversation log on the server. We only need to
    // re-render past turns for the user; we don't have to rebuild any
    // local history array because chat_send only sends the new turn.
    for (const m of entries) ingest(m, true);
    scrollToBottom();
  }

  function getConversationId() { return conversationId; }
  function isConnected() { return !!(ws && ws.readyState === WebSocket.OPEN); }

  window.AgixtChat = {
    configure,
    connect,
    disconnect,
    send,
    stop,
    onGeneratingChange,
    clear,
    loadHistory,
    getConversationId,
    isConnected,
    setComposerStatus,
  };
})();
