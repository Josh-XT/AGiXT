/* Team chat (Discord-style group chat) pane.
 *
 * Vanilla-JS port of the web's group chat surface. Keeping each web
 * component → desktop function mapping here so future maintainers can
 * jump between codebases quickly:
 *
 *   - web/components/layout/GroupRail.tsx       → renderCompanyRail()
 *   - web/components/layout/ChannelList.tsx     → renderChannelList() +
 *                                                  renderDMList() (split
 *                                                  between agents/people)
 *   - web/components/layout/ChannelMemberList.tsx → renderMembers()
 *   - web/components/layout/ChannelContextMenus.tsx → showCtxMenu() +
 *                                                      ChannelContextMenu /
 *                                                      MemberContextMenu /
 *                                                      MessageContextMenu /
 *                                                      GroupContextMenu /
 *                                                      ThreadContextMenu
 *                                                      ports
 *   - web/components/conversation/Message/Message.tsx → renderMessage()
 *                                                       (handles reply
 *                                                        cards, mentions,
 *                                                        emoji shortcodes,
 *                                                        attachment chips,
 *                                                        and OG previews)
 *   - web/components/conversation/Message/LinkPreview.tsx → buildOGPreview()
 *   - web/components/conversation/input/chat-input.tsx → composer logic
 *                                                        (file attach,
 *                                                        emoji autocomplete,
 *                                                        gif picker, send)
 *   - web/components/conversation/input/GifPicker.tsx → openGifPicker()
 *
 * Message flow for plain channel/DM posts is the AGiXT pattern:
 *   1) POST /v1/conversation/{id}/message  (append, no LLM)
 *   2) Live updates arrive over the existing WS protocol
 *      (ws://…/v1/conversation/{id}/stream) — same protocol chat.js uses.
 *
 * State is persisted to localStorage (active company, last channel per
 * company, collapse state for the channel + member panels) so the user
 * lands back where they left off on reopen.
 */
(function () {
  if (window.AgixtTeamChat) return; // re-entrancy guard

  // ----- Constants ------------------------------------------------------

  const STORAGE_ACTIVE_COMPANY = 'agixt-team-chat-active-company';
  const STORAGE_LAST_CHANNEL_PREFIX = 'agixt-team-chat-last-channel:';
  const STORAGE_COLLAPSE_CHANNELS = 'agixt-team-chat-collapse-channels';
  const STORAGE_COLLAPSE_MEMBERS = 'agixt-team-chat-collapse-members';
  // Member list is a right-docked, resizable column (mirrors the
  // workspace Files sidebar / chat-pane resize idiom).
  const STORAGE_MEMBER_WIDTH = 'agixt-team-chat-member-width';
  const MEMBER_WIDTH_MIN = 160;
  const MEMBER_WIDTH_MAX = 420;
  const MEMBER_WIDTH_DEFAULT = 200;
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  // ----- State ----------------------------------------------------------

  let mounted = false;
  let companies = [];
  let channelsByCompany = new Map(); // companyId -> [channel, ...]
  let allConversationsCache = null;   // for the private/DM view
  // Flattened, de-duplicated list of every human teammate across the
  // user's companies. Populated by loadTeammates() so the DM list can
  // surface people you can message even before a DM conversation exists.
  let allTeammates = [];
  let activeCompanyId = null;          // null = DM mode
  let activeChannelId = null;
  let participantsByChannel = new Map(); // channelId -> [participant, ...]
  let senderProfilesById = new Map();    // userId -> richest profile seen
  let currentUser = null;
  let messageCache = new Map();        // channelId -> [message, ...]
  let renderedMessageIds = new Set();
  // Optimistically-rendered sends awaiting their WebSocket echo.
  // [{ tempId, channelId, normBody, hasAttach, ts, timer }]
  let pendingOptimistic = [];
  let activeWs = null;
  let activeWsChannelId = null;
  let wsReconnectTimer = null;
  let wsBackoffMs = 1000;
  let participantsPollTimer = null;
  // Remote typing indicator (web parity): userId -> { name, timeout }.
  // We send `{type:'typing'}` at most every 3s while typing and expire
  // a remote typist after 4s of silence, exactly like the web hook.
  let typingUsers = new Map();
  let lastTypingSent = 0;
  // Per-server unread badge counts, fed by the channel:notification
  // WebSocket events. Matches GroupRail.tsx's `serverNotifications` state
  // so the company-rail badges light up the same way they do on web.
  const serverNotifications = new Map(); // companyId -> count
  // Member-list search query (filter-as-you-type).
  let memberSearch = '';
  // Reply target — when set, the next message will be sent as a quote
  // header. Mirrors the web's `replyingTo` state in chat-input.tsx.
  let replyTarget = null; // { messageId, authorName, authorUserId, preview }
  // Active thread info — populated by 'thread:active' events when a
  // thread is open inside this channel. Renders nested under the parent.
  let activeThreadInfo = null;
  // In-flight edit. Mirrors Message.tsx isEditing state.
  let editingMessageId = null;
  // Draft text per conversation (so the user doesn't lose what they
  // typed when jumping between channels).
  const drafts = new Map();
  // Quick-react row shown in the message hover toolbar / context menu.
  const QUICK_REACTIONS = ['\u{1F44D}', '\u{1F62D}', '❤️', '\u{1F525}', '\u{1F923}']; // 👍 😭 ❤️ 🔥 🤣
  // Pending attachments staged for the next send. Each entry is
  // { filename, dataUrl }; we keep them around until send (or until the
  // user clicks the chip's × to drop them).
  let pendingAttachments = [];
  // OG preview cache so we don't re-fetch on every re-render. Keys are
  // raw URLs; values are { title, description, image, siteName } or
  // null on miss.
  const ogCache = new Map();
  // In-flight OG fetches keyed by URL so we don't issue parallel
  // duplicates while the first request is still going.
  const ogInflight = new Map();
  // GIF picker state (Tenor v2).
  let gifPickerOpen = false;
  // Emoji autocomplete state — when active, we render a popover under
  // the textarea with matching shortcodes.
  let emojiAutocomplete = null;

  // ----- Tiny DOM helpers ------------------------------------------------

  function el(id) { return document.getElementById(id); }
  function ce(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (k === 'class') node.className = v;
        else if (k === 'dataset') for (const [dk, dv] of Object.entries(v)) node.dataset[dk] = dv;
        else if (k === 'on') for (const [evt, fn] of Object.entries(v)) node.addEventListener(evt, fn);
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'text') node.textContent = v;
        else if (v === true) node.setAttribute(k, '');
        else if (v != null && v !== false) node.setAttribute(k, v);
      }
    }
    for (const kid of kids) {
      if (kid == null || kid === false) continue;
      if (typeof kid === 'string') node.appendChild(document.createTextNode(kid));
      else node.appendChild(kid);
    }
    return node;
  }

  function toast(message, isError) {
    const t = el('tc-toast');
    if (!t) return;
    t.textContent = message;
    t.hidden = false;
    t.classList.toggle('is-error', !!isError);
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { t.hidden = true; }, 3200);
  }

  function lsGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }

  function initialsFor(name) {
    if (!name) return '?';
    return String(name).split(/\s+/).map((w) => w[0] || '').join('').slice(0, 2).toUpperCase();
  }

  // Best-effort display name for a participant. Mirrors the web's
  // `nameFor` / `resolveDisplayName` (we don't have nicknames yet).
  function nameForParticipant(participant) {
    if (!participant) return 'Unknown';
    if (participant.participant_type === 'agent') {
      return (participant.agent && participant.agent.name) || 'Agent';
    }
    const u = participant.user || {};
    const full = ((u.first_name || '') + ' ' + (u.last_name || '')).trim();
    return full || u.email || 'Unknown';
  }

  function participantById(uid) {
    if (!activeChannelId) return null;
    const list = participantsByChannel.get(activeChannelId) || [];
    for (const p of list) {
      if (p.participant_type === 'user' && p.user && p.user.id === uid) return p;
      if (p.participant_type === 'agent' && p.agent && p.agent.id === uid) return p;
    }
    return null;
  }

  function userIdOf(user) {
    if (!user) return null;
    return user.id || user.user_id || user.userId || user.sub || null;
  }

  function normalizeUserProfile(user) {
    if (!user) return null;
    const nested = (user.user && typeof user.user === 'object' && user.user)
      || (user.profile && typeof user.profile === 'object' && user.profile)
      || (user.data && typeof user.data === 'object' && user.data)
      || user;
    const id = userIdOf(nested) || userIdOf(user);
    return Object.assign({}, nested, id ? { id } : {});
  }

  function firstNameOf(user) {
    return (user && (user.first_name || user.firstName)) || '';
  }

  function lastNameOf(user) {
    return (user && (user.last_name || user.lastName)) || '';
  }

  function emailOf(user) {
    return (user && user.email) || null;
  }

  function avatarUrlOf(user) {
    return (user && (user.avatar_url || user.avatarUrl)) || null;
  }

  function displayNameForUser(user) {
    if (!user) return '';
    const full = (firstNameOf(user) + ' ' + lastNameOf(user)).trim();
    return full || user.display_name || user.displayName || user.name || emailOf(user) || '';
  }

  function profileScore(user) {
    if (!user) return 0;
    let score = 0;
    if (displayNameForUser(user)) score += 2;
    if (emailOf(user)) score += 1;
    if (avatarUrlOf(user)) score += 1;
    return score;
  }

  function rememberUserProfile(user, forcedId) {
    const normalized = normalizeUserProfile(user);
    const id = forcedId || userIdOf(normalized);
    if (!id) return null;
    const existing = senderProfilesById.get(id) || {};
    const merged = Object.assign({}, existing);
    for (const [key, value] of Object.entries(normalized || {})) {
      if (value !== null && value !== undefined && value !== '') merged[key] = value;
    }
    if (forcedId || !userIdOf(merged)) merged.id = id;
    senderProfilesById.set(id, merged);
    return merged;
  }

  function rememberSenderFromMessage(msg) {
    if (!msg) return;
    const senderUserId = getMessageSenderId(msg);
    if (msg.sender && typeof msg.sender === 'object') {
      rememberUserProfile(msg.sender, senderUserId);
    }
  }

  function rememberParticipantProfiles(list) {
    for (const p of list || []) {
      if (p && p.participant_type !== 'agent' && p.user) rememberUserProfile(p.user);
    }
  }

  function pickBestProfile(primary, fallback) {
    if (!primary) return fallback || null;
    if (!fallback) return primary;
    return profileScore(primary) >= profileScore(fallback) ? primary : fallback;
  }

  function currentUserId() {
    return userIdOf(currentUser);
  }

  function getMessageSenderId(msg) {
    if (!msg) return null;
    const sender = msg.sender || {};
    return msg.sender_user_id || msg.senderUserId
      || msg.sender_id || msg.senderId
      || msg.user_id || msg.userId
      || sender.id || sender.user_id || sender.userId
      || null;
  }

  function userById(uid) {
    if (!uid) return null;
    const p = participantById(uid);
    if (p && p.participant_type === 'user' && p.user) return p.user;
    if (senderProfilesById.has(uid)) return senderProfilesById.get(uid);
    if (currentUserId() === uid) return currentUser;
    for (const teammate of allTeammates) {
      if (userIdOf(teammate) === uid) return teammate;
    }
    return null;
  }

  function senderInfoForMessage(msg) {
    const senderUserId = getMessageSenderId(msg);
    const rawSender = (msg && msg.sender && typeof msg.sender === 'object') ? msg.sender : {};
    const rosterUser = userById(senderUserId);
    const merged = Object.assign({}, rosterUser || {}, rawSender);
    if (senderUserId && !userIdOf(merged)) merged.id = senderUserId;
    const fromCurrentUser = !!(senderUserId && currentUserId() === senderUserId);
    return {
      id: senderUserId || userIdOf(merged),
      name: displayNameForUser(merged) || (fromCurrentUser ? displayNameForUser(currentUser) : '') || 'User',
      email: emailOf(merged),
      avatarUrl: avatarUrlOf(merged),
    };
  }

  function isMessageFromCurrentUser(msg) {
    const senderUserId = getMessageSenderId(msg);
    return !!(senderUserId && currentUserId() === senderUserId);
  }

  function normalizeReactionList(reactions) {
    if (!Array.isArray(reactions) || !reactions.length) return [];
    const byEmoji = new Map();
    for (const reaction of reactions) {
      if (!reaction || !reaction.emoji) continue;
      const entry = byEmoji.get(reaction.emoji) || {
        emoji: reaction.emoji,
        count: 0,
        users: [],
      };
      if (Array.isArray(reaction.users)) {
        for (const user of reaction.users) {
          if (!user) continue;
          entry.users.push(typeof user === 'string' ? { id: user } : user);
        }
        entry.count += Number(reaction.count || reaction.users.length || 0);
      } else {
        entry.users.push({
          id: reaction.user_id || reaction.userId || reaction.id || '',
          email: reaction.user_email || reaction.email || '',
          first_name: reaction.user_first_name || reaction.first_name || '',
        });
        entry.count += 1;
      }
      byEmoji.set(reaction.emoji, entry);
    }
    return Array.from(byEmoji.values()).map((reaction) => ({
      ...reaction,
      count: reaction.count || reaction.users.length || 1,
    }));
  }

  function mergeMessageRecord(existing, incoming) {
    const base = existing || {};
    const next = Object.assign({}, base, incoming || {});
    if (Array.isArray(next.reactions)) {
      next.reactions = normalizeReactionList(next.reactions);
    }
    const senderUserId = getMessageSenderId(incoming) || getMessageSenderId(base);
    if (senderUserId && !next.sender_user_id) next.sender_user_id = senderUserId;
    const bestSender = pickBestProfile(
      incoming && incoming.sender,
      base && base.sender,
    );
    if (bestSender) {
      next.sender = Object.assign(
        {},
        bestSender,
        senderUserId && !userIdOf(bestSender) ? { id: senderUserId } : {},
      );
    }
    rememberSenderFromMessage(next);
    return next;
  }

  function mergeMessageList(existingMessages, incomingMessages) {
    const byId = new Map();
    const withoutId = [];
    for (const msg of existingMessages || []) {
      if (msg && msg.id) byId.set(msg.id, mergeMessageRecord(null, msg));
      else if (msg) withoutId.push(mergeMessageRecord(null, msg));
    }
    for (const msg of incomingMessages || []) {
      if (!msg) continue;
      if (msg.id) byId.set(msg.id, mergeMessageRecord(byId.get(msg.id), msg));
      else withoutId.push(mergeMessageRecord(null, msg));
    }
    return withoutId.concat(Array.from(byId.values())).sort((a, b) => {
      const at = a && a.timestamp || '';
      const bt = b && b.timestamp || '';
      return at < bt ? -1 : at > bt ? 1 : 0;
    });
  }

  // Resolver fed to the mention rewriter so `<@uid>` tokens render as
  // `@DisplayName`. Falls back to undefined → "User" when the uid is
  // unknown (the participant may have left the channel since the
  // message was authored).
  function resolveMention(uid) {
    const p = participantById(uid);
    return p ? nameForParticipant(p) : null;
  }

  // Online when last_seen is within 5 minutes (matches usePresence.ts).
  function isUserOnline(lastSeen) {
    if (!lastSeen) return false;
    const t = new Date(lastSeen).getTime();
    return Number.isFinite(t) && (Date.now() - t) < 5 * 60 * 1000;
  }

  function presenceLabel(lastSeen) {
    if (!lastSeen) return 'Offline';
    if (isUserOnline(lastSeen)) return 'Online';
    const t = new Date(lastSeen).getTime();
    if (!Number.isFinite(t)) return 'Offline';
    const mins = Math.floor((Date.now() - t) / 60000);
    if (mins < 60) return `Last seen ${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Last seen ${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `Last seen ${days}d ago`;
  }

  // Tiny inline SVG factory so each role icon stays a single statement.
  function roleIconSVG(role) {
    if (role === 'owner') {
      // Crown (gold) — owners only.
      return '<svg width="11" height="11" viewBox="0 0 24 24" aria-hidden="true">'
        + '<path fill="#eab308" d="m2 4 4 6 6-7 6 7 4-6v15H2zM2 21h20v2H2z"/></svg>';
    }
    if (role === 'admin') {
      // Shield (blue) — admins.
      return '<svg width="11" height="11" viewBox="0 0 24 24" aria-hidden="true">'
        + '<path fill="#60a5fa" d="M12 2 4 5v6c0 5 3.5 9.7 8 11 4.5-1.3 8-6 8-11V5z"/></svg>';
    }
    if (role === 'observer') {
      // Eye-off — observer/muted.
      return '<svg width="11" height="11" viewBox="0 0 24 24" aria-hidden="true">'
        + '<path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
        + ' d="m1 1 22 22M17.94 17.94A10.95 10.95 0 0 1 12 20c-7 0-11-8-11-8a18.4 18.4 0 0 1 5.06-5.94"/></svg>';
    }
    return '';
  }

  // Bell-off icon for muted channels.
  function bellOffSVG() {
    return '<svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">'
      + '<path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
      + ' d="m1 1 22 22M13.73 21a2 2 0 0 1-3.46 0M18.63 13A17 17 0 0 1 18 8M6.26 6.26A5.95 5.95 0 0 0 6 8c0 7-3 9-3 9h14"/></svg>';
  }

  // ----- Avatar rendering -----------------------------------------------

  function buildAvatar(opts) {
    const { name, email, avatarUrl, isAgent, size } = opts;
    const px = size || 36;
    const wrap = ce('div', { class: 'tc-avatar' + (isAgent ? ' is-agent' : '') });
    wrap.style.width = px + 'px';
    wrap.style.height = px + 'px';
    if (isAgent) {
      // Bot icon for agents (mirrors web's <Bot /> from lucide).
      wrap.innerHTML = '<svg width="' + Math.round(px * 0.5) + '" height="'
        + Math.round(px * 0.5) + '" viewBox="0 0 24 24" aria-hidden="true">'
        + '<path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
        + ' d="M12 8V4M5 12H3m18 0h-2M12 16v4M9 12a3 3 0 0 0 6 0M8 8h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2z"/>'
        + '</svg>';
      return wrap;
    }
    // Layered <img> cascade: explicit avatar_url first; gravatar second
    // (404s out to nothing); initials fallback always renders underneath.
    wrap.appendChild(ce('span', { class: 'tc-avatar-initials', text: initialsFor(name) }));
    function addImg(url) {
      if (!url) return;
      const img = ce('img', { class: 'tc-avatar-img', alt: '', loading: 'lazy' });
      img.referrerPolicy = 'no-referrer';
      // Hide on error so the initials show through.
      img.onerror = () => { img.remove(); };
      img.src = url;
      wrap.appendChild(img);
    }
    if (avatarUrl) addImg(avatarUrl);
    if (email && window.AgixtTeamChatHelpers) {
      addImg(window.AgixtTeamChatHelpers.gravatarUrl(email, px * 2));
    }
    return wrap;
  }

  // ----- Custom context menu --------------------------------------------
  // We replace the global context-menu.js handler whenever the menu lives
  // INSIDE the team-chat view-pane — that way the channel/member/message
  // right-click actions take priority over the generic "Copy / Copy link"
  // menu and the user gets the Discord-style actions instead.

  let menuEl = null;
  function ensureMenuEl() {
    if (menuEl) return menuEl;
    menuEl = ce('div', { class: 'tc-ctxmenu', role: 'menu' });
    menuEl.hidden = true;
    document.body.appendChild(menuEl);
    return menuEl;
  }
  function hideCtxMenu() {
    if (!menuEl) return;
    menuEl.hidden = true;
    menuEl.innerHTML = '';
  }
  function showCtxMenu(x, y, items) {
    const m = ensureMenuEl();
    m.innerHTML = '';
    items.forEach((item) => {
      if (item === '-') {
        m.appendChild(ce('div', { class: 'tc-ctxmenu-sep' }));
        return;
      }
      if (item.heading) {
        m.appendChild(ce('div', { class: 'tc-ctxmenu-head', text: item.heading }));
        return;
      }
      // Inline reactions row — `{ row: [{emoji, onClick}, ...] }` paints
      // a single horizontal strip of emoji buttons, the way the web's
      // ContextMenu does for the quick-react row at the top of the
      // message menu. Mirrors Message.tsx lines 990-1010.
      if (Array.isArray(item.row)) {
        const row = ce('div', { class: 'tc-ctxmenu-row' });
        for (const entry of item.row) {
          const btn = ce('button', {
            type: 'button',
            class: 'tc-ctxmenu-row-btn',
            title: entry.title || '',
            text: entry.label || '',
          });
          if (entry.onClick) {
            btn.addEventListener('click', () => {
              hideCtxMenu();
              try { entry.onClick(); }
              catch (e) { console.warn('tc ctx menu row action failed', e); }
            });
          }
          row.appendChild(btn);
        }
        m.appendChild(row);
        return;
      }
      const btn = ce('button', {
        type: 'button',
        class: 'tc-ctxmenu-item'
          + (item.danger ? ' is-danger' : '')
          + (item.disabled ? ' is-disabled' : ''),
      });
      // Optional leading icon (matches the web's `<Icon className="mr-2 h-4 w-4" />`
      // before each ContextMenuItem label).
      if (item.icon) {
        const ic = ce('span', { class: 'tc-ctxmenu-icon', html: item.icon });
        btn.appendChild(ic);
      }
      btn.appendChild(ce('span', { class: 'tc-ctxmenu-label', text: item.label || '' }));
      btn.disabled = !!item.disabled;
      if (!item.disabled && typeof item.onClick === 'function') {
        btn.addEventListener('click', () => {
          hideCtxMenu();
          try { item.onClick(); }
          catch (e) { console.warn('tc ctx menu action failed', e); }
        });
      }
      m.appendChild(btn);
    });
    m.hidden = false;
    const w = m.offsetWidth || 200;
    const h = m.offsetHeight || 120;
    const px = Math.min(x, window.innerWidth - w - 6);
    const py = Math.min(y, window.innerHeight - h - 6);
    m.style.left = Math.max(4, px) + 'px';
    m.style.top = Math.max(4, py) + 'px';
  }
  document.addEventListener('mousedown', (e) => {
    if (menuEl && !menuEl.hidden && !menuEl.contains(e.target)) hideCtxMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideCtxMenu();
  });
  window.addEventListener('blur', hideCtxMenu);

  async function copyToClipboard(text) {
    if (text == null) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(String(text));
        toast('Copied to clipboard');
        return;
      }
    } catch (_) { /* fall through */ }
    const tmp = document.createElement('textarea');
    tmp.value = String(text);
    tmp.style.position = 'fixed';
    tmp.style.opacity = '0';
    document.body.appendChild(tmp);
    tmp.select();
    try { document.execCommand('copy'); toast('Copied to clipboard'); } catch (_) {}
    document.body.removeChild(tmp);
  }

  // ----- Loading --------------------------------------------------------

  async function loadCompanies() {
    try {
      currentUser = normalizeUserProfile(await window.AgixtApi.getUser());
      rememberUserProfile(currentUser);
      const list = await window.AgixtApi.listCompanies();
      const arr = Array.isArray(list) ? list : (list && list.companies) || [];
      companies = arr.filter(Boolean).map((c) => ({
        id: c.id,
        name: c.name || '(unnamed)',
        icon_url: c.icon_url || null,
        sort_order: c.sort_order != null ? c.sort_order : 0,
        agents: c.agents || [],
        // Preserve the embedded member roster when the server ships it
        // (newer /v1/companies shape). The DM list uses this to render
        // a row per teammate without needing a per-company members fetch.
        users: Array.isArray(c.users) ? c.users : null,
      })).sort((a, b) => (a.sort_order - b.sort_order) || a.name.localeCompare(b.name));
    } catch (e) {
      console.warn('team-chat: loadCompanies failed', e);
      companies = [];
    }
  }

  async function loadChannelsForCompany(companyId) {
    if (!companyId) return [];
    try {
      const map = await window.AgixtApi.getGroupConversations(companyId);
      // Preserve the server's order within each category (matches the
      // web's ChannelList — categorizedChannels keeps the input order
      // and only groups by category). Manual reorder lives on top of
      // this via `channelOrder` localStorage.
      const arr = Object.entries(map || {}).map(([id, ch]) => Object.assign({ id }, ch));
      const visible = arr.filter((c) =>
        (c.conversation_type || c.conversationType) !== 'thread');
      channelsByCompany.set(companyId, applyChannelOrder(companyId, visible));
      return channelsByCompany.get(companyId);
    } catch (e) {
      console.warn('team-chat: loadChannels failed', e);
      channelsByCompany.set(companyId, []);
      return [];
    }
  }

  // Per-company channel order overrides — populated by drag-and-drop
  // reorder. Stored as a flat array of channel IDs; channels missing
  // from the override fall through to the server order.
  const channelOrders = new Map(); // companyId -> [channelId, ...]
  function loadChannelOrderFor(companyId) {
    if (!companyId) return null;
    if (channelOrders.has(companyId)) return channelOrders.get(companyId);
    const raw = lsGet('agixt-team-chat-channel-order:' + companyId);
    if (!raw) { channelOrders.set(companyId, null); return null; }
    try {
      const parsed = JSON.parse(raw);
      const arr = Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : null;
      channelOrders.set(companyId, arr);
      return arr;
    } catch (_) {
      channelOrders.set(companyId, null);
      return null;
    }
  }
  function saveChannelOrderFor(companyId, ids) {
    if (!companyId) return;
    channelOrders.set(companyId, ids);
    lsSet('agixt-team-chat-channel-order:' + companyId, JSON.stringify(ids));
  }
  function applyChannelOrder(companyId, channels) {
    const order = loadChannelOrderFor(companyId);
    if (!order || !order.length) return channels;
    const byId = new Map(channels.map((c) => [c.id, c]));
    const out = [];
    const seen = new Set();
    for (const id of order) {
      if (byId.has(id)) { out.push(byId.get(id)); seen.add(id); }
    }
    // Anything new from the server slots in at the end in its server
    // order — channels created after the user last reordered.
    for (const c of channels) if (!seen.has(c.id)) out.push(c);
    return out;
  }

  // Pull every conversation visible to the current user, then split them
  // into agent DMs and human DMs the way the web's DMPanel does — agent
  // DMs are detected via the agent_name field (the authoritative server
  // signal), human DMs by the legacy "DM-…" name prefix.
  async function loadPrivateConversations() {
    try {
      const map = await window.AgixtApi.listAllConversations();
      const arr = Object.entries(map || {}).map(([id, c]) => Object.assign({ id }, c));
      const filtered = arr.filter((c) => {
        const t = c.conversation_type || c.conversationType;
        return t === 'dm' || t === 'private'
          || (c.name && (c.name.startsWith('DM-') || c.name.startsWith('DM with ')));
      });
      filtered.sort((a, b) => {
        const ua = a.updated_at || a.updatedAt || '';
        const ub = b.updated_at || b.updatedAt || '';
        return ub.localeCompare(ua);
      });
      allConversationsCache = filtered;
      return filtered;
    } catch (e) {
      console.warn('team-chat: loadPrivateConversations failed', e);
      allConversationsCache = [];
      return [];
    }
  }

  function ensurePrivateConversationCached(conversation) {
    if (!conversation || !conversation.id) return;
    const current = Array.isArray(allConversationsCache)
      ? allConversationsCache.slice()
      : [];
    const idx = current.findIndex((c) => c.id === conversation.id);
    if (idx >= 0) current[idx] = Object.assign({}, current[idx], conversation);
    else current.unshift(conversation);
    allConversationsCache = current;
  }

  // Build the flat teammate roster the DM list uses. Mirrors the
  // dedupe-by-user-id pass that NewDMDialog does on web: collapse the
  // same person showing up in multiple companies into a single entry,
  // skip the current user, and fall back to per-company fetches if the
  // /v1/companies payload didn't ship members embedded.
  async function loadTeammates() {
    const byId = new Map();
    const needsFallback = [];
    function addMember(u, company) {
      if (!u || !u.id) return;
      if (currentUser && u.id === currentUser.id) return;
      rememberUserProfile(u);
      const existing = byId.get(u.id) || {};
      const merged = Object.assign({}, existing, u);
      const ids = Array.isArray(existing.company_ids) ? existing.company_ids.slice() : [];
      const names = Array.isArray(existing.company_names) ? existing.company_names.slice() : [];
      if (company && company.id && !ids.includes(company.id)) ids.push(company.id);
      if (company && company.name && !names.includes(company.name)) names.push(company.name);
      merged.company_ids = ids;
      merged.company_names = names;
      byId.set(u.id, merged);
    }
    for (const company of companies) {
      if (Array.isArray(company.users) && company.users.length) {
        for (const u of company.users) addMember(u, company);
      } else if (company.users === null) {
        needsFallback.push(company.id);
      }
    }
    if (needsFallback.length && window.AgixtApi
        && typeof window.AgixtApi.getCompanyMembers === 'function') {
      const fetched = await Promise.all(needsFallback.map((id) =>
        window.AgixtApi.getCompanyMembers(id)
          .then((members) => ({ company: companies.find((c) => c.id === id), members }))
          .catch(() => ({ company: companies.find((c) => c.id === id), members: [] }))));
      for (const group of fetched) {
        if (!Array.isArray(group.members)) continue;
        for (const u of group.members) addMember(u, group.company);
      }
    }
    allTeammates = Array.from(byId.values()).sort((a, b) => {
      const an = ((a.first_name || '') + ' ' + (a.last_name || '')).trim()
        || a.email || '';
      const bn = ((b.first_name || '') + ' ' + (b.last_name || '')).trim()
        || b.email || '';
      return an.localeCompare(bn);
    });
    return allTeammates;
  }

  async function loadParticipants(channelId) {
    if (!channelId || channelId === '-') return [];
    try {
      const list = await window.AgixtApi.getConversationParticipants(channelId);
      participantsByChannel.set(channelId, list);
      rememberParticipantProfiles(list);
      return list;
    } catch (e) {
      console.warn('team-chat: loadParticipants failed', e);
      participantsByChannel.set(channelId, []);
      return [];
    }
  }

  // Hover-prefetch: warm the message + participants caches for a
  // channel the user is likely to click. Mirrors ChannelList.tsx's
  // prefetchChannelOnHover. Skips channels we've already loaded or
  // the one currently active.
  const prefetchedChannels = new Set();
  function prefetchChannel(channelId) {
    if (!channelId || channelId === activeChannelId) return;
    if (prefetchedChannels.has(channelId)) return;
    prefetchedChannels.add(channelId);
    if (!messageCache.has(channelId)) loadMessages(channelId);
    if (!participantsByChannel.has(channelId)) loadParticipants(channelId);
  }

  async function loadMessages(channelId) {
    if (!channelId) return [];
    const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    if (!inv) return [];
    try {
      const entries = await inv('get_conversation_history', {
        conversationId: channelId,
        limit: 200,
        page: 1,
      });
      const arr = Array.isArray(entries) ? entries : [];
      const merged = mergeMessageList(messageCache.get(channelId) || [], arr);
      messageCache.set(channelId, merged);
      return merged;
    } catch (e) {
      console.warn('team-chat: loadMessages failed', e);
      return [];
    }
  }

  // ----- Rendering: company rail ----------------------------------------

  function renderCompanyRail() {
    const rail = el('tc-company-list');
    if (!rail) return;
    rail.innerHTML = '';
    for (const c of companies) {
      const initials = initialsFor(c.name);
      const unread = serverNotifications.get(c.id) || 0;
      const btn = ce('button', {
        type: 'button',
        class: 'tc-company' + (activeCompanyId === c.id ? ' is-active' : ''),
        title: c.name + (unread ? ` (${unread} unread)` : ''),
        'aria-label': c.name,
        on: {
          click: () => selectCompany(c.id),
          contextmenu: (e) => { e.preventDefault(); showGroupContextMenu(e, c); },
        },
      });
      btn.appendChild(ce('span', { class: 'tc-company-pill', 'aria-hidden': 'true' }));
      if (c.icon_url) {
        btn.appendChild(ce('img', { src: c.icon_url, alt: '', class: 'tc-company-img' }));
      } else {
        btn.appendChild(ce('span', { class: 'tc-company-initials', text: initials }));
      }
      if (unread > 0 && activeCompanyId !== c.id) {
        btn.appendChild(ce('span', { class: 'tc-company-badge',
          text: unread > 9 ? '9+' : String(unread) }));
      }
      rail.appendChild(btn);
    }
    const privBtn = el('tc-company-private');
    if (privBtn) privBtn.classList.toggle('is-active', !activeCompanyId);
    // Show the Add Server button when the user has any company:write
    // scope. We don't have a scope check available client-side here,
    // so we use a softer signal: show it whenever the user has at
    // least one company (every authenticated user can create more).
    const addBtn = el('tc-company-add');
    if (addBtn) addBtn.hidden = !companies.length && !currentUser;
  }

  // ----- Rendering: channel + DM list -----------------------------------

  // Per-category collapse state, persisted across the session. Matches
  // CategorySection's local `collapsed` state in ChannelList.tsx.
  const collapsedCategories = new Set(
    (lsGet('agixt-team-chat-collapsed-cats') || '').split(',').filter(Boolean),
  );
  function saveCollapsedCategories() {
    lsSet('agixt-team-chat-collapsed-cats', Array.from(collapsedCategories).join(','));
  }

  function renderChannelList() {
    const wrap = el('tc-channel-scroll');
    const titleEl = el('tc-channel-header-title');
    if (!wrap || !titleEl) return;
    wrap.innerHTML = '';

    // Toggle the header buttons FIRST — the early-return for the DM
    // path used to skip this and leave stale state from the prior
    // company view.
    const addBtn = el('tc-channel-add');
    if (addBtn) addBtn.hidden = !activeCompanyId;
    const dmBtn = el('tc-new-dm-btn');
    if (dmBtn) dmBtn.hidden = !!activeCompanyId; // only show in DM mode

    if (!activeCompanyId) {
      titleEl.textContent = 'Direct Messages';
      renderDMList(wrap);
      return;
    }

    const company = companies.find((c) => c.id === activeCompanyId);
    titleEl.textContent = company ? company.name : 'Channels';

    // Loading state — shown when channelsByCompany hasn't populated yet
    // for the active company. We populate before this renderer runs in
    // selectCompany(), so this only fires on the first render between
    // mount and the first load.
    if (!channelsByCompany.has(activeCompanyId)) {
      wrap.appendChild(ce('div', { class: 'tc-channel-empty tc-loading',
        text: 'Loading channels…' }));
      return;
    }

    const channels = channelsByCompany.get(activeCompanyId) || [];
    if (!channels.length) {
      wrap.appendChild(ce('div', { class: 'tc-channel-empty',
        text: 'No channels yet — click + to create one.' }));
      return;
    }

    const byCat = new Map();
    for (const ch of channels) {
      const cat = ch.category || null;
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(ch);
    }
    const categoryKeys = Array.from(byCat.keys());
    const named = categoryKeys.filter((k) => k != null).sort();
    if (byCat.has(null)) named.push(null);
    for (const cat of named) {
      const list = byCat.get(cat);
      if (cat) {
        const isCollapsed = collapsedCategories.has(cat);
        const unread = list.reduce((sum, c) =>
          sum + (c.notification_count || c.notificationCount || 0), 0);
        const header = ce('button', {
          type: 'button',
          class: 'tc-channel-category tc-channel-category-btn'
            + (isCollapsed ? ' is-collapsed' : ''),
          'aria-expanded': isCollapsed ? 'false' : 'true',
          on: { click: () => {
            if (collapsedCategories.has(cat)) collapsedCategories.delete(cat);
            else collapsedCategories.add(cat);
            saveCollapsedCategories();
            renderChannelList();
          }},
        });
        header.appendChild(ce('span', { class: 'tc-channel-cat-chev',
          html: isCollapsed
            ? '<svg width="10" height="10" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="m9 6 6 6-6 6"/></svg>'
            : '<svg width="10" height="10" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6"/></svg>',
        }));
        header.appendChild(ce('span', { class: 'tc-channel-cat-label', text: cat }));
        if (isCollapsed && unread > 0) {
          header.appendChild(ce('span', { class: 'tc-channel-cat-unread',
            text: unread > 99 ? '99+' : String(unread) }));
        }
        wrap.appendChild(header);
        if (isCollapsed) continue;
      }
      for (const ch of list) {
        const row = renderChannelRow(ch, /*isDM*/ false);
        wrap.appendChild(row);
        // Nest the active thread under its parent channel, the way
        // ChannelList.tsx renders ThreadContextMenu rows.
        if (activeThreadInfo && activeThreadInfo.parentId === ch.id) {
          wrap.appendChild(renderActiveThreadRow(activeThreadInfo));
        }
      }
    }
  }

  function renderActiveThreadRow(thread) {
    return ce('button', {
      type: 'button',
      class: 'tc-channel-row tc-channel-thread is-active',
      on: { click: () => selectChannel(thread.id) },
    },
      ce('span', { class: 'tc-channel-icon', html:
        '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' }),
      ce('span', { class: 'tc-channel-name', text: thread.name }),
    );
  }

  // Per-agent expansion state so the user can collapse/expand each
  // agent group. Mirrors AgentNode's `isExpanded` in DMPanel.tsx.
  const expandedAgents = new Set();

  // Build the DM tree the same way the web's DMPanel does:
  //   - "People" = a row per human you've DM'd (de-duplicated by user id
  //     when possible). Clicking opens that person's most recent DM.
  //   - "Agents" = a row per agent contact; expandable to show that
  //     agent's conversations. Detection rule (matches DMPanel.tsx
  //     lines 1604-1621): agentName field is authoritative. Legacy
  //     name patterns ("DM-…", "DM with …") fall back to the people
  //     bucket so older conversations still classify correctly.
  function classifyConversations() {
    const convos = allConversationsCache || [];
    const peopleConvos = [];
    const agentConvos = [];
    for (const c of convos) {
      const t = c.conversation_type || c.conversationType;
      const name = c.name || '';
      const display = c.display_name || c.displayName || '';
      const agentName = c.agent_name || c.agentName;
      // Legacy / hand-rolled DMs use a `DM-` or `DM with ` name prefix
      // even when conversation_type is 'private' (the older AGiXT
      // shape). Accept both wire formats so DMs from older accounts
      // don't silently disappear from the panel.
      const hasDMPrefix = (name.startsWith('DM-') || name.startsWith('DM with ')
        || display.startsWith('DM-') || display.startsWith('DM with '));
      const isDM = t === 'dm' || (t === 'private' && hasDMPrefix);
      // A "people DM" is any DM where the other side isn't an agent.
      // We treat any conversation flagged as a DM but with an agent
      // attached as an agent DM (which the side AI chat already
      // surfaces) and skip it here.
      const looksLikeUserDM = (isDM && !agentName) || hasDMPrefix;
      if (looksLikeUserDM) peopleConvos.push(c);
      else if (agentName) agentConvos.push(c);
    }
    return { peopleConvos, agentConvos };
  }

  function teammateDisplayName(u) {
    const full = ((u.first_name || '') + ' ' + (u.last_name || '')).trim();
    return full || u.email || 'User';
  }

  function renderTeammateRow(member) {
    // A "pre-DM" row: a teammate the current user can message but hasn't
    // yet. Click opens (or creates) the underlying DM via startUserDM.
    const name = teammateDisplayName(member);
    const row = ce('button', {
      type: 'button',
      class: 'tc-channel-row tc-channel-teammate',
      title: name + (member.email ? ` — ${member.email}` : ''),
      on: {
        click: () => startUserDM(member),
        contextmenu: (e) => {
          e.preventDefault();
          showCtxMenu(e.clientX, e.clientY, [
            { heading: name },
            { label: 'Send DM', onClick: () => startUserDM(member) },
            '-',
            { label: 'Copy email',
              onClick: () => member.email && copyToClipboard(member.email),
              disabled: !member.email },
          ]);
        },
      },
    });
    const icon = ce('span', { class: 'tc-channel-icon tc-channel-icon-avatar' });
    icon.appendChild(buildAvatar({
      name, email: member.email, avatarUrl: member.avatar_url, size: 18,
    }));
    row.appendChild(icon);
    row.appendChild(ce('span', { class: 'tc-channel-name', text: name }));
    return row;
  }

  function renderDMList(wrap) {
    // Agent DMs already live in the side AI chat (existing chat pane +
    // topbar agent/conversation switchers); duplicating them here just
    // clutters the panel. So this list is humans-only.
    //
    // Sources merged into the "People" section:
    //   1. Every teammate across the user's companies (allTeammates) —
    //      so the DM list works as a contact picker even before any DM
    //      conversation exists.
    //   2. Every existing human DM conversation — matched to a teammate
    //      by display name where possible (so we render the DM row, not
    //      the bare teammate row, and surface unread state). Orphan DMs
    //      that don't match any current teammate still appear so older
    //      DMs aren't hidden.
    const { peopleConvos } = classifyConversations();

    // Latest DM per cleaned-name key (lowercased), so we can match
    // teammates to their most-recent DM.
    const dmByKey = new Map();
    for (const c of peopleConvos) {
      const name = c.display_name || c.displayName || c.name || '';
      const cleaned = name.startsWith('DM-') ? name.slice(3)
        : name.startsWith('DM with ') ? name.slice(8) : name;
      const key = cleaned.toLowerCase().trim() || c.id;
      const existing = dmByKey.get(key);
      if (!existing
          || (c.updated_at || c.updatedAt || '')
             > (existing.updated_at || existing.updatedAt || '')) {
        dmByKey.set(key, c);
      }
    }

    // Walk teammates first so the picker shows everyone you can DM,
    // with existing-DM rows taking precedence (they carry unread state).
    const usedKeys = new Set();
    const teammateRows = [];
    for (const m of allTeammates) {
      const display = teammateDisplayName(m);
      const nameKey = display.toLowerCase().trim();
      const emailKey = (m.email || '').toLowerCase().trim();
      const matchKey = (nameKey && dmByKey.has(nameKey)) ? nameKey
        : (emailKey && dmByKey.has(emailKey)) ? emailKey
        : null;
      if (matchKey) {
        usedKeys.add(matchKey);
        teammateRows.push(renderChannelRow(dmByKey.get(matchKey), /*isDM*/ true));
      } else {
        teammateRows.push(renderTeammateRow(m));
      }
    }

    // Orphan DMs — existing conversations whose other party isn't a
    // current teammate (different company, ex-member, agent-less legacy
    // shape). Keep them visible so we don't lose history.
    const orphanRows = [];
    for (const [key, c] of dmByKey) {
      if (usedKeys.has(key)) continue;
      orphanRows.push(renderChannelRow(c, /*isDM*/ true));
    }

    if (!teammateRows.length && !orphanRows.length) {
      wrap.appendChild(ce('div', { class: 'tc-channel-empty',
        text: 'No teammates or direct messages yet — click + to start one.' }));
      return;
    }

    if (teammateRows.length) {
      wrap.appendChild(ce('div', { class: 'tc-channel-category', text: 'People' }));
      for (const r of teammateRows) wrap.appendChild(r);
    }
    if (orphanRows.length) {
      wrap.appendChild(ce('div', { class: 'tc-channel-category',
        text: teammateRows.length ? 'Other' : 'People' }));
      for (const r of orphanRows) wrap.appendChild(r);
    }
  }

  function renderAgentNode(agentName, convs, primary, expanded, totalUnread, hasUnread) {
    const isActive = !!convs.find((c) => c.id === activeChannelId);
    const row = ce('div', {
      class: 'tc-agent-node'
        + (isActive && !expanded ? ' is-active' : '')
        + (hasUnread ? ' has-unread' : ''),
    });
    const chev = ce('button', {
      type: 'button',
      class: 'tc-agent-chev' + (expanded ? ' is-expanded' : ''),
      title: expanded ? 'Collapse' : 'Expand',
      'aria-label': expanded ? 'Collapse agent' : 'Expand agent',
      on: { click: (e) => {
        e.stopPropagation();
        if (expandedAgents.has(agentName)) expandedAgents.delete(agentName);
        else expandedAgents.add(agentName);
        renderChannelList();
      }},
      html: '<svg width="10" height="10" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="m9 6 6 6-6 6"/></svg>',
    });
    row.appendChild(chev);
    const main = ce('button', {
      type: 'button',
      class: 'tc-agent-main',
      title: agentName + ` — ${convs.length} conversation${convs.length === 1 ? '' : 's'}`,
      on: {
        click: () => primary && selectChannel(primary.id),
        contextmenu: (e) => {
          e.preventDefault();
          showCtxMenu(e.clientX, e.clientY, [
            { heading: agentName },
            { label: 'Open primary conversation',
              onClick: () => primary && selectChannel(primary.id) },
            { label: 'New conversation with agent',
              onClick: () => startAgentDM({ name: agentName }) },
            '-',
            { label: 'Copy agent name', onClick: () => copyToClipboard(agentName) },
          ]);
        },
      },
    });
    main.appendChild(buildAvatar({ name: agentName, isAgent: true, size: 22 }));
    main.appendChild(ce('span', { class: 'tc-agent-name', text: agentName }));
    if (!expanded && totalUnread > 0) {
      main.appendChild(ce('span', {
        class: 'tc-channel-unread',
        text: totalUnread > 99 ? '99+' : String(totalUnread),
      }));
    } else if (!expanded && hasUnread) {
      main.appendChild(ce('span', { class: 'tc-channel-dot' }));
    } else if (!expanded && convs.length > 1) {
      main.appendChild(ce('span', { class: 'tc-agent-count',
        text: String(convs.length) }));
    }
    row.appendChild(main);
    return row;
  }

  function renderChannelRow(channel, isDM) {
    const isActive = channel.id === activeChannelId;
    const hasUnread = !!(channel.has_notifications || channel.hasNotifications);
    const unreadCount = channel.notification_count || channel.notificationCount || 0;
    const displayName = channel.display_name || channel.displayName || channel.name || 'channel';
    const cleaned = isDM && displayName.startsWith('DM-') ? displayName.slice(3)
      : isDM && displayName.startsWith('DM with ') ? displayName.slice(8)
      : displayName;
    const agentName = channel.agent_name || channel.agentName;
    const isAgentDM = isDM && agentName && !(channel.name || '').startsWith('DM-')
      && !(channel.name || '').startsWith('DM with ');
    const row = ce('button', {
      type: 'button',
      class: 'tc-channel-row'
        + (isActive ? ' is-active' : '')
        + (hasUnread ? ' has-unread' : ''),
      on: {
        click: () => selectChannel(channel.id),
        contextmenu: (e) => { e.preventDefault(); showChannelContextMenu(e, channel, isDM); },
        mouseenter: () => prefetchChannel(channel.id),
      },
    });
    // Drag-to-reorder support (channels in a company only — DM rows
    // sort by recency and don't get manual ordering).
    if (!isDM && activeCompanyId) {
      row.setAttribute('draggable', 'true');
      row.dataset.channelId = channel.id;
      row.addEventListener('dragstart', (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', channel.id);
        row.classList.add('is-dragging');
      });
      row.addEventListener('dragend', () => row.classList.remove('is-dragging'));
      row.addEventListener('dragover', (e) => {
        if (!e.dataTransfer.types.includes('text/plain')) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const r = row.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        row.classList.toggle('is-drop-above', before);
        row.classList.toggle('is-drop-below', !before);
      });
      row.addEventListener('dragleave', () => {
        row.classList.remove('is-drop-above');
        row.classList.remove('is-drop-below');
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        row.classList.remove('is-drop-above');
        row.classList.remove('is-drop-below');
        const draggedId = e.dataTransfer.getData('text/plain');
        if (!draggedId || draggedId === channel.id) return;
        const r = row.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        reorderChannel(draggedId, channel.id, before);
      });
    }
    let iconSvg;
    if (isAgentDM) {
      // Robot/agent icon for agent DMs
      iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M12 8V4M5 12H3m18 0h-2M12 16v4M9 12a3 3 0 0 0 6 0M8 8h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2z"/></svg>';
    } else if (isDM) {
      // Speech bubble for human DMs
      iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
    } else {
      // Hash for channels
      iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/></svg>';
    }
    row.appendChild(ce('span', { class: 'tc-channel-icon', html: iconSvg }));
    row.appendChild(ce('span', { class: 'tc-channel-name', text: cleaned }));
    const notifMode = channel.notification_mode || channel.notificationMode || 'all';
    if (notifMode === 'none') {
      row.appendChild(ce('span', { class: 'tc-channel-muted', html: bellOffSVG(),
        title: 'Muted' }));
    }
    if (unreadCount > 0) {
      row.appendChild(ce('span', {
        class: 'tc-channel-unread',
        text: unreadCount > 99 ? '99+' : String(unreadCount),
      }));
    } else if (hasUnread) {
      row.appendChild(ce('span', { class: 'tc-channel-dot' }));
    }
    return row;
  }

  // ----- Rendering: content header --------------------------------------

  function renderContentHeader() {
    const titleEl = el('tc-content-title');
    if (!titleEl) return;
    if (!activeChannelId) {
      titleEl.textContent = 'Select a channel';
      return;
    }
    const channels = activeCompanyId
      ? (channelsByCompany.get(activeCompanyId) || [])
      : (allConversationsCache || []);
    const ch = channels.find((c) => c.id === activeChannelId);
    const display = (ch && (ch.display_name || ch.displayName || ch.name)) || 'Channel';
    const prefix = !activeCompanyId ? '@ ' : '# ';
    const cleaned = !activeCompanyId && display.startsWith('DM-') ? display.slice(3)
      : !activeCompanyId && display.startsWith('DM with ') ? display.slice(8)
      : display;
    titleEl.textContent = prefix + cleaned;
  }

  // ----- Rendering: messages --------------------------------------------

  function renderMessages() {
    const scroller = el('tc-messages-scroll');
    const list = el('tc-messages');
    const empty = el('tc-messages-empty');
    if (!scroller || !list || !empty) return;
    // Disconnect any pending lazy observations from the previous
    // render — we're about to throw their target wrappers away.
    if (lazyObserver) {
      lazyObserver.disconnect();
      lazyObserver = null;
    }
    list.innerHTML = '';
    renderedMessageIds.clear();
    const msgs = activeChannelId ? (messageCache.get(activeChannelId) || []) : [];
    if (!activeChannelId || !msgs.length) {
      empty.hidden = false;
      empty.textContent = activeChannelId
        ? 'No messages yet — say hi.'
        : 'Pick a channel or DM from the list on the left.';
      return;
    }
    empty.hidden = true;
    for (const m of msgs) appendMessage(m, /*scroll*/ false);
    // content-visibility:auto on .tc-message means the engine reports
    // a placeholder height (the contain-intrinsic-size) until each row
    // is painted, so setting scrollTop = scrollHeight RIGHT NOW lands
    // on the placeholder layout's "bottom" rather than the real one.
    // Wait two animation frames + run a ResizeObserver-backed retry
    // loop that keeps re-pinning to the bottom as content settles
    // (images load, OG cards arrive, GIF auto-stop wraps render). The
    // retry self-terminates after 1.5s.
    pinScrollToBottom(scroller);
  }

  function pinScrollToBottom(scroller) {
    if (!scroller) return;
    const start = Date.now();
    const target = scroller;
    const raf = (typeof requestAnimationFrame === 'function')
      ? requestAnimationFrame : (cb) => setTimeout(cb, 16);
    function step() {
      if (!target.isConnected) return;
      target.scrollTop = target.scrollHeight;
    }
    raf(() => raf(step));
    // While content settles, keep snapping to the bottom. Stop after
    // 1.5s OR as soon as the user starts scrolling (we don't want to
    // yank them away from history they're reading).
    let userScrolled = false;
    const onUserScroll = () => {
      if (Date.now() - start < 50) return; // ignore our own snaps
      const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 40;
      if (!atBottom) userScrolled = true;
    };
    target.addEventListener('scroll', onUserScroll, { passive: true });
    if (typeof ResizeObserver !== 'function') {
      // Fallback: a couple of timed retries cover image/OG settle.
      setTimeout(step, 80);
      setTimeout(step, 250);
      setTimeout(() => target.removeEventListener('scroll', onUserScroll), 1500);
      return;
    }
    const ro = new ResizeObserver(() => {
      if (userScrolled) { ro.disconnect(); return; }
      target.scrollTop = target.scrollHeight;
      if (Date.now() - start > 1500) {
        ro.disconnect();
        target.removeEventListener('scroll', onUserScroll);
      }
    });
    ro.observe(target);
    // Hard stop in case ResizeObserver never fires (e.g. very short
    // content list).
    setTimeout(() => {
      ro.disconnect();
      target.removeEventListener('scroll', onUserScroll);
    }, 1600);
  }

  function appendMessage(msg, scroll) {
    const list = el('tc-messages');
    const scroller = el('tc-messages-scroll');
    const empty = el('tc-messages-empty');
    if (!list || !scroller) return;
    if (msg.id && renderedMessageIds.has(msg.id)) return;
    if (msg.id) renderedMessageIds.add(msg.id);
    if (empty) empty.hidden = true;
    const body = String(msg.message || '');
    const trimmed = body.trim();
    // Skip activity/subactivity bookkeeping — those belong to the agent
    // execution UI, not channel chat.
    if (trimmed.startsWith('[ACTIVITY]') || trimmed.startsWith('[SUBACTIVITY]')) return;

    const node = buildMessageNode(msg);
    if (scroll !== false) {
      const wasAtBottom = (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight) < 60;
      list.appendChild(node);
      if (wasAtBottom) scroller.scrollTop = scroller.scrollHeight;
    } else {
      list.appendChild(node);
    }
  }

  // ---- Incremental DOM updates -----------------------------------------
  // These exist so WebSocket events (edits, reactions, deletes, reconnect
  // `initial_data`) don't nuke + rebuild the whole message list via
  // renderMessages(). A full rebuild blanks the scroller, re-runs the
  // 1.5s pinScrollToBottom snap loop, and visibly "reloads the page".
  // Touching only the affected node keeps scroll position rock-steady.

  function findMessageNode(id) {
    if (!id) return null;
    const list = el('tc-messages');
    if (!list) return null;
    const safe = (typeof CSS !== 'undefined' && CSS.escape)
      ? CSS.escape(id) : String(id).replace(/["\\]/g, '\\$&');
    return list.querySelector('[data-message-id="' + safe + '"]');
  }

  // Swap a single message's node in place. Preserves scroll: if the user
  // was pinned to the bottom we re-pin after the height change, otherwise
  // we leave their position untouched. Returns false when the node isn't
  // currently mounted (caller can fall back to reconcile/append).
  function replaceMessageNode(msg) {
    if (!msg || !msg.id) return false;
    const old = findMessageNode(msg.id);
    if (!old) return false;
    const scroller = el('tc-messages-scroll');
    const wasAtBottom = scroller
      && (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight) < 60;
    const trimmed = String(msg.message || '').trim();
    if (trimmed.startsWith('[ACTIVITY]') || trimmed.startsWith('[SUBACTIVITY]')) {
      // Became an activity record — drop it rather than render it.
      old.remove();
      renderedMessageIds.delete(msg.id);
      return true;
    }
    old.replaceWith(buildMessageNode(msg));
    renderedMessageIds.add(msg.id);
    if (wasAtBottom && scroller) scroller.scrollTop = scroller.scrollHeight;
    return true;
  }

  // Remove specific messages without rebuilding the rest.
  function removeMessageNodes(ids) {
    const list = el('tc-messages');
    if (!list) return;
    for (const id of ids) {
      const n = findMessageNode(id);
      if (n) n.remove();
      renderedMessageIds.delete(id);
    }
    const empty = el('tc-messages-empty');
    if (empty && !list.children.length) {
      empty.hidden = false;
      empty.textContent = 'No messages yet — say hi.';
    }
  }

  // Reconcile the live DOM with the (already-merged) message cache while
  // touching as little as possible. The common cases — a reconnect that
  // re-sends the same backlog, or a backlog that simply grew — resolve to
  // "do nothing" or "append the new tail". Only genuine divergence
  // (an edit/reorder/deletion mid-list) falls back to a full rebuild,
  // and those paths now have their own incremental handlers anyway.
  function reconcileMessages() {
    const list = el('tc-messages');
    if (!list || !list.children.length || !renderedMessageIds.size) {
      renderMessages();
      return;
    }
    const msgs = activeChannelId ? (messageCache.get(activeChannelId) || []) : [];
    const domIds = Array.from(list.children)
      .map((c) => c.dataset && c.dataset.messageId)
      .filter(Boolean);
    let i = 0;
    for (const m of msgs) {
      if (!m || !m.id) continue;
      const t = String(m.message || '').trim();
      if (t.startsWith('[ACTIVITY]') || t.startsWith('[SUBACTIVITY]')) continue;
      if (i < domIds.length) {
        if (domIds[i] !== m.id) { renderMessages(); return; } // mid-list change
        i++;
      } else {
        appendMessage(m, true); // brand-new tail message
      }
    }
    if (i < domIds.length) { renderMessages(); return; } // trailing deletions
  }

  // ---- Optimistic send -------------------------------------------------
  // Show the user's message instantly instead of waiting for the
  // server→WebSocket round-trip (that gap is the "nothing happens, then
  // it pops in" jump on send). A lightweight temp node is rendered
  // immediately and swapped out when the real echo arrives.

  function normForMatch(s) { return String(s || '').trim(); }

  // Remove an optimistic placeholder (DOM + cache + bookkeeping).
  function dropOptimistic(tempId) {
    const idx = pendingOptimistic.findIndex((p) => p.tempId === tempId);
    if (idx < 0) return;
    const entry = pendingOptimistic[idx];
    pendingOptimistic.splice(idx, 1);
    if (entry.timer) clearTimeout(entry.timer);
    const node = findMessageNode(tempId);
    if (node) node.remove();
    renderedMessageIds.delete(tempId);
    const arr = messageCache.get(entry.channelId);
    if (arr) {
      const k = arr.findIndex((m) => m && m.id === tempId);
      if (k >= 0) arr.splice(k, 1);
    }
  }

  // When a real message_added arrives, swap the matching placeholder
  // (same channel, our own user, body matches — or it carried an
  // attachment the server rewrites, so body can't be compared) for the
  // server's record IN PLACE. This preserves message order and keeps
  // scroll dead-still (no remove-then-append shuffle). Returns true if a
  // placeholder was consumed, in which case the caller must not append.
  function consumeOptimistic(realMsg, channelId) {
    if (!realMsg || !realMsg.id || !pendingOptimistic.length) return false;
    const senderId = getMessageSenderId(realMsg);
    if (senderId && currentUserId() && senderId !== currentUserId()) return false;
    const body = normForMatch(realMsg.message);
    const now = Date.now();
    const pi = pendingOptimistic.findIndex((p) =>
      p.channelId === channelId
      && (now - p.ts) < 90000
      && (p.hasAttach || p.normBody === body));
    if (pi < 0) return false;
    const entry = pendingOptimistic[pi];
    pendingOptimistic.splice(pi, 1);
    if (entry.timer) clearTimeout(entry.timer);
    // Replace the temp record in the cache array at the same index.
    const arr = messageCache.get(channelId) || [];
    const ci = arr.findIndex((m) => m && m.id === entry.tempId);
    if (ci >= 0) arr[ci] = realMsg; else arr.push(realMsg);
    messageCache.set(channelId, arr);
    // Swap the DOM node in place; fall back to a plain append if the
    // placeholder node is somehow gone.
    const tempNode = findMessageNode(entry.tempId);
    renderedMessageIds.delete(entry.tempId);
    if (tempNode) {
      const scroller = el('tc-messages-scroll');
      const wasAtBottom = scroller
        && (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight) < 60;
      tempNode.replaceWith(buildMessageNode(realMsg));
      renderedMessageIds.add(realMsg.id);
      if (wasAtBottom && scroller) scroller.scrollTop = scroller.scrollHeight;
    } else {
      appendMessage(realMsg, true);
    }
    return true;
  }

  function addOptimisticMessage(channelId, wireBody, hasAttach) {
    const tempId = 'optimistic-' + Date.now() + '-'
      + Math.random().toString(36).slice(2, 8);
    const msg = {
      id: tempId,
      role: 'user',
      message: wireBody,
      timestamp: new Date().toISOString(),
      sender_user_id: currentUserId() || undefined,
      _optimistic: true,
    };
    const arr = messageCache.get(channelId) || [];
    arr.push(msg);
    messageCache.set(channelId, arr);
    appendMessage(msg, true);
    const node = findMessageNode(tempId);
    if (node) node.classList.add('tc-msg-pending');
    const entry = {
      tempId, channelId,
      normBody: normForMatch(wireBody),
      hasAttach: !!hasAttach,
      ts: Date.now(),
      timer: setTimeout(() => dropOptimistic(tempId), 15000),
    };
    pendingOptimistic.push(entry);
    return tempId;
  }

  // ---- Typing indicator (web parity) -----------------------------------
  // Outbound: debounced to once per 3s while the user is typing, sent
  // only when the socket for the active channel is open.
  function sendTypingIndicator() {
    const now = Date.now();
    if (now - lastTypingSent < 3000) return;
    if (activeWs && activeWs.readyState === WebSocket.OPEN) {
      try { activeWs.send(JSON.stringify({ type: 'typing' })); } catch (_) {}
      lastTypingSent = now;
    }
  }

  function clearTypingUsers() {
    for (const v of typingUsers.values()) {
      if (v && v.timeout) clearTimeout(v.timeout);
    }
    typingUsers.clear();
    renderTypingIndicator();
  }

  // Inbound: a remote user is typing. Self-filtered, name-resolved via
  // the participant roster, and auto-expired after 4s of silence —
  // matching useConversationWebSocketStable's typing_indicator handler.
  function noteTypingUser(data) {
    if (!data) return;
    const uid = data.user_id || data.userId;
    if (!uid || uid === currentUserId()) return;
    const roster = userById(uid);
    const name = (roster && displayNameForUser(roster))
      || [data.first_name, data.last_name].filter(Boolean).join(' ').trim()
      || data.email || 'Someone';
    const existing = typingUsers.get(uid);
    if (existing && existing.timeout) clearTimeout(existing.timeout);
    typingUsers.set(uid, {
      name,
      timeout: setTimeout(() => {
        typingUsers.delete(uid);
        renderTypingIndicator();
      }, 4000),
    });
    renderTypingIndicator();
  }

  function renderTypingIndicator() {
    const elx = el('tc-typing-indicator');
    if (!elx) return;
    const names = Array.from(typingUsers.values()).map((v) => v.name);
    if (!names.length || replyTarget) {
      elx.hidden = true;
      elx.textContent = '';
      return;
    }
    let text;
    if (names.length === 1) text = names[0] + ' is typing…';
    else if (names.length === 2) text = names[0] + ' and ' + names[1] + ' are typing…';
    else text = names.slice(0, -1).join(', ') + ' and '
      + names[names.length - 1] + ' are typing…';
    elx.textContent = text;
    elx.hidden = false;
  }

  // The "real" message renderer — handles reply cards, mention/emoji
  // rewrites, attachments, and OG previews. Matches what
  // web/components/conversation/Message/Message.tsx outputs (minus
  // reaction strips and thread chips, which we plan to add later).
  function buildMessageNode(msg) {
    const helpers = window.AgixtTeamChatHelpers;
    const md = window.AgixtMarkdown;
    const role = (msg.role || '').toString();
    const isUserMsg = /^user$/i.test(role);
    const isAgent = !isUserMsg;
    let displayName;
    let email = null;
    let avatarUrl = null;
    if (isUserMsg) {
      const sender = senderInfoForMessage(msg);
      email = sender.email;
      avatarUrl = sender.avatarUrl;
      displayName = sender.name;
    } else {
      displayName = role || 'Agent';
    }

    // Reply detection + mention/emoji rewrite, ported from
    // Message.tsx:useMemo() handling.
    let actualBody = body(msg);
    let replyRef = null;
    if (helpers) {
      replyRef = helpers.parseReply(actualBody);
      if (replyRef) {
        replyRef.actualMessage = helpers.applyEmojiShortcodes(replyRef.actualMessage);
        replyRef.replyPreview = helpers.applyEmojiShortcodes(replyRef.replyPreview);
        // The reply preview is plain text (no nested markdown rendering
        // pass), so the chip can't be a real element here — flatten
        // `<@uuid>` to `@DisplayName` text.
        replyRef.replyPreview = helpers.applyMentions(replyRef.replyPreview, resolveMention);
        actualBody = replyRef.actualMessage;
        // Resolve `<@uid>` author name if stored as such.
        const authorMention = replyRef.replyAuthor.match(
          /^<@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>$/i,
        );
        if (authorMention) {
          const uid = authorMention[1];
          replyRef.replyAuthor = resolveMention(uid) || 'User';
          if (!replyRef.replyAuthorUserId) replyRef.replyAuthorUserId = uid;
        }
      }
      actualBody = helpers.applyEmojiShortcodes(actualBody);
      // Leave `<@uuid>` tokens in place — markdown.js's mention pattern
      // turns them into clickable chips via the resolver we register in
      // mount(). Pre-rewriting to plain text would lose the click /
      // context-menu affordances Discord users expect.
    }

    const wrap = ce('div', {
      class: 'tc-message' + (isAgent ? ' is-agent' : ''),
      dataset: { messageId: msg.id || '' },
      on: {
        contextmenu: (e) => { e.preventDefault(); showMessageContextMenu(e, msg, actualBody); },
      },
    });
    wrap.appendChild(buildAvatar({ name: displayName, email, avatarUrl, isAgent, size: 36 }));

    const main = ce('div', { class: 'tc-message-main' });
    const head = ce('div', { class: 'tc-message-head' });
    head.appendChild(ce('span', { class: 'tc-message-name', text: displayName }));
    const ts = msg.timestamp ? new Date(msg.timestamp) : null;
    if (ts && !isNaN(ts.getTime())) {
      head.appendChild(ce('span', { class: 'tc-message-ts', text: ts.toLocaleString() }));
    }
    // "(edited)" — when the server reports the message has been touched
    // after creation. Mirrors Message.tsx's chatItem.updated_by check.
    if (msg.updated_by || msg.updated_at && msg.updated_at !== msg.timestamp) {
      head.appendChild(ce('span', { class: 'tc-message-edited', text: '(edited)' }));
    }
    if (msg.pinned) head.appendChild(ce('span', { class: 'tc-message-pinned', text: '📌' }));
    main.appendChild(head);

    if (replyRef) main.appendChild(buildReplyCard(replyRef));

    if (editingMessageId === msg.id) {
      main.appendChild(buildEditEditor(msg, actualBody));
    } else {
      const bodyEl = ce('div', { class: 'tc-message-body md' });
      if (md && typeof md.renderFragment === 'function') {
        bodyEl.appendChild(md.renderFragment(actualBody));
      } else {
        bodyEl.textContent = actualBody;
      }
      // 1) JWT-rewrite media that resolves to the AGiXT backend so
      //    `/outputs/...` etc. images / video / audio actually load.
      authMediaNodes(bodyEl);
      // 2) Click-to-expand on inline images. markdown.js tags each
      //    <img> with `.md-image`.
      bodyEl.querySelectorAll('img.md-image').forEach((img) => {
        img.classList.add('tc-message-image');
        img.style.cursor = 'zoom-in';
        img.addEventListener('click', (ev) => {
          ev.preventDefault();
          openImageLightbox(img.src, img.getAttribute('alt') || '');
        });
      });
      // 3) GIF auto-stop is deferred until the message scrolls into
      //    view (see observeForLazy + the GIF branch in renderMessages).
      //    Without this, opening a busy channel triggers N canvas
      //    captures up front and tanks scroll perf.
      main.appendChild(bodyEl);
    }

    // OG link previews — fire-and-forget BUT lazy: defer the fetch
    // until the message scrolls into view so opening a 200-message
    // channel doesn't start 200+ network requests at once.
    if (helpers) {
      const urls = helpers.extractFirstFewUrls(actualBody, 3);
      if (urls.length) {
        const previewWrap = ce('div', { class: 'tc-og-previews' });
        main.appendChild(previewWrap);
        wrap.dataset.lazyOg = '1';
        wrap._lazyOgUrls = urls;
        wrap._lazyOgContainer = previewWrap;
      }
    }

    // Reactions strip — render whatever the server has aggregated under
    // `reactions: [{ emoji, count, users: [...] }]`.
    if (Array.isArray(msg.reactions) && msg.reactions.length) {
      main.appendChild(buildReactionsStrip(msg));
    }

    // Thread chip — "💬 N replies — View Thread →" when this message
    // is the anchor for one. Mirrors the chip Message.tsx renders.
    const thread = threadForMessage(msg.id);
    if (thread) main.appendChild(buildThreadChip(thread));

    wrap.appendChild(main);
    wrap.appendChild(buildHoverToolbar(msg, actualBody));
    // Find any GIF <img> inside the body so the lazy observer can wrap
    // it the moment the message enters the viewport.
    const gifs = main.querySelectorAll('img.md-image');
    let hasGif = false;
    gifs.forEach((img) => {
      if (looksLikeGif(img.getAttribute('src') || '')) hasGif = true;
    });
    if (hasGif) wrap.dataset.lazyGif = '1';
    observeForLazy(wrap);
    return wrap;
  }

  // IntersectionObserver-backed lazy-mount: heavy per-message work
  // (OG fetches, GIF auto-stop canvas captures, large image decoding)
  // only kicks in when the row actually enters the viewport. Scrolling
  // a 200-msg channel now triggers a handful of fetches at a time
  // instead of 200 simultaneous ones.
  let lazyObserver = null;
  function ensureLazyObserver() {
    if (lazyObserver) return lazyObserver;
    if (typeof IntersectionObserver !== 'function') return null;
    lazyObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const wrap = entry.target;
        // OG previews
        if (wrap.dataset.lazyOg === '1') {
          const urls = wrap._lazyOgUrls || [];
          const container = wrap._lazyOgContainer;
          if (container && container.isConnected) {
            urls.forEach((u) => attachOGPreview(container, u));
          }
          wrap.dataset.lazyOg = '0';
          wrap._lazyOgUrls = null;
          wrap._lazyOgContainer = null;
        }
        // GIF auto-stop
        if (wrap.dataset.lazyGif === '1') {
          wrap.querySelectorAll('img.md-image').forEach((img) => {
            if (looksLikeGif(img.getAttribute('src') || '')) installGifAutoStop(img);
          });
          wrap.dataset.lazyGif = '0';
        }
        lazyObserver.unobserve(wrap);
      }
    }, { root: el('tc-messages-scroll'), rootMargin: '300px 0px' });
    return lazyObserver;
  }
  function observeForLazy(wrap) {
    if (wrap.dataset.lazyOg !== '1' && wrap.dataset.lazyGif !== '1') return;
    const obs = ensureLazyObserver();
    if (obs) obs.observe(wrap);
  }

  function buildEditEditor(msg, currentBody) {
    const wrap = ce('div', { class: 'tc-edit-wrap' });
    const ta = ce('textarea', { class: 'tc-edit-textarea', rows: '3' });
    ta.value = currentBody;
    wrap.appendChild(ta);
    const actions = ce('div', { class: 'tc-edit-actions' });
    const hint = ce('span', { class: 'tc-edit-hint',
      text: 'Esc to cancel · Ctrl+Enter to save' });
    actions.appendChild(hint);
    const cancel = ce('button', { type: 'button', class: 'tc-btn tc-btn-secondary',
      text: 'Cancel', on: { click: () => { editingMessageId = null; renderMessages(); }}});
    const save = ce('button', { type: 'button', class: 'tc-btn tc-btn-primary',
      text: 'Save' });
    save.addEventListener('click', () => doSaveEdit(msg, ta.value));
    actions.appendChild(cancel);
    actions.appendChild(save);
    wrap.appendChild(actions);
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        editingMessageId = null;
        renderMessages();
      } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        doSaveEdit(msg, ta.value);
      }
    });
    setTimeout(() => {
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }, 20);
    return wrap;
  }

  async function doSaveEdit(msg, newText) {
    if (!msg || !msg.id) return;
    const channels = activeCompanyId
      ? (channelsByCompany.get(activeCompanyId) || [])
      : (allConversationsCache || []);
    const ch = channels.find((c) => c.id === activeChannelId);
    const convName = (ch && (ch.name || ch.display_name || ch.displayName)) || activeChannelId;
    try {
      await window.AgixtApi.editMessage(convName, msg.id, newText);
      // Optimistic update — patch the message in the cache so the user
      // sees the edit immediately; the WS message_updated event will
      // overwrite this with the canonical version.
      const arr = messageCache.get(activeChannelId) || [];
      const idx = arr.findIndex((m) => m.id === msg.id);
      if (idx >= 0) {
        arr[idx] = { ...arr[idx], message: newText, updated_at: new Date().toISOString(), updated_by: 'self' };
      }
      editingMessageId = null;
      renderMessages();
      toast('Edited');
    } catch (e) {
      toast('Failed to edit', true);
    }
  }

  function threadForMessage(messageId) {
    if (!messageId || !activeChannelId) return null;
    const list = threadsByChannel.get(activeChannelId) || [];
    for (const t of list) {
      if ((t.parent_message_id || t.parentMessageId) === messageId) return t;
    }
    return null;
  }

  function buildThreadChip(thread) {
    const count = thread.message_count || thread.messageCount || 0;
    const last = thread.last_message_at || thread.lastMessageAt;
    const lastTxt = last ? relativeTime(last) : '';
    const wrap = ce('button', {
      type: 'button',
      class: 'tc-thread-chip',
      title: 'Open thread: ' + (thread.name || ''),
      on: { click: (e) => {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('thread:active', {
          detail: {
            id: thread.id,
            name: thread.name || 'Thread',
            parentId: thread.parent_id || activeChannelId,
          },
        }));
        selectChannel(thread.id);
      }},
    });
    wrap.appendChild(ce('span', { class: 'tc-thread-chip-icon', html:
      '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    }));
    const label = count === 1 ? '1 reply' : count + ' replies';
    wrap.appendChild(ce('span', { class: 'tc-thread-chip-label', text: label }));
    if (lastTxt) wrap.appendChild(ce('span', { class: 'tc-thread-chip-ts', text: '· ' + lastTxt }));
    wrap.appendChild(ce('span', { class: 'tc-thread-chip-cta', text: 'View Thread →' }));
    return wrap;
  }

  function relativeTime(iso) {
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return '';
    const diff = Date.now() - t;
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return Math.floor(diff / 60_000) + 'm ago';
    if (diff < 86_400_000) return Math.floor(diff / 3_600_000) + 'h ago';
    return Math.floor(diff / 86_400_000) + 'd ago';
  }

  function buildReactionsStrip(msg) {
    const wrap = ce('div', { class: 'tc-reactions-strip' });
    for (const r of msg.reactions) {
      const userIds = (r.users || []).map((u) => u.id || u);
      const mine = currentUser && userIds.includes(currentUser.id);
      const pill = ce('button', {
        type: 'button',
        class: 'tc-reaction-pill' + (mine ? ' is-mine' : ''),
        title: (r.users || []).map((u) => u.first_name || u.email || 'user').join(', '),
        on: { click: () => {
          if (!msg.id) return;
          window.AgixtApi.toggleReaction(activeChannelId, msg.id, r.emoji)
            .catch(() => toast('Failed to react', true));
        }},
      });
      pill.appendChild(ce('span', { class: 'tc-reaction-emoji', text: r.emoji }));
      pill.appendChild(ce('span', { class: 'tc-reaction-count',
        text: String(r.count || userIds.length || 1) }));
      wrap.appendChild(pill);
    }
    return wrap;
  }

  function buildHoverToolbar(msg, renderedText) {
    const bar = ce('div', { class: 'tc-msg-toolbar' });
    for (const emoji of QUICK_REACTIONS) {
      bar.appendChild(ce('button', {
        type: 'button', class: 'tc-msg-toolbar-btn',
        title: 'React ' + emoji,
        on: { click: () => {
          if (!msg.id) return;
          window.AgixtApi.toggleReaction(activeChannelId, msg.id, emoji)
            .catch(() => toast('Failed to react', true));
        }},
        text: emoji,
      }));
    }
    // "Add reaction" — opens the full emoji picker, same affordance the
    // web's AddReactionButton renders at the end of its hover toolbar.
    // Without this, users could only reach the picker through the
    // right-click menu.
    bar.appendChild(ce('button', {
      type: 'button',
      class: 'tc-msg-toolbar-btn tc-msg-toolbar-add-react',
      title: 'Add reaction…',
      'aria-label': 'Add reaction',
      html: '<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">'
        + '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        + '<path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
        + ' d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01M18 4v6M21 7h-6"/></svg>',
      on: { click: (e) => {
        if (!msg.id) return;
        const rect = e.currentTarget.getBoundingClientRect();
        openEmojiPicker(rect.right, rect.bottom, (emoji) => {
          window.AgixtApi.toggleReaction(activeChannelId, msg.id, emoji)
            .catch(() => toast('Failed to react', true));
        });
      }},
    }));
    bar.appendChild(ce('span', { class: 'tc-msg-toolbar-sep' }));
    bar.appendChild(ce('button', {
      type: 'button', class: 'tc-msg-toolbar-btn',
      title: 'Reply',
      'aria-label': 'Reply',
      html: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="m15 10-5 5 5 5M20 4v7a4 4 0 0 1-4 4H5"/></svg>',
      on: { click: () => setReplyTarget(msg, renderedText) },
    }));
    const isMine = isMessageFromCurrentUser(msg);
    if (isMine) {
      bar.appendChild(ce('button', {
        type: 'button', class: 'tc-msg-toolbar-btn',
        title: 'Edit',
        'aria-label': 'Edit',
        html: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
        on: { click: () => { editingMessageId = msg.id; renderMessages(); }},
      }));
    }
    bar.appendChild(ce('button', {
      type: 'button', class: 'tc-msg-toolbar-btn',
      title: msg.pinned ? 'Unpin' : 'Pin',
      'aria-label': msg.pinned ? 'Unpin' : 'Pin',
      html: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 17v5M9 10.76V6h6v4.76l3 1.76V14H6v-1.48z"/></svg>',
      on: { click: () => {
        if (!msg.id) return;
        window.AgixtApi.togglePinMessage(activeChannelId, msg.id)
          .then(() => toast(msg.pinned ? 'Unpinned' : 'Pinned'))
          .catch(() => toast('Failed to update pin', true));
      }},
    }));
    bar.appendChild(ce('button', {
      type: 'button', class: 'tc-msg-toolbar-btn',
      title: 'More',
      'aria-label': 'More',
      html: '<svg width="14" height="14" viewBox="0 0 24 24"><circle cx="6" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="18" cy="12" r="1.6" fill="currentColor"/></svg>',
      on: { click: (e) => showMessageContextMenu(e, msg, renderedText) },
    }));
    return bar;
  }

  function body(msg) {
    // Some channel messages come back as a JSON envelope with a text
    // field (the agent execution path does this for tool calls). Mirror
    // the web's Message.tsx unwrap.
    const raw = String(msg.message || '');
    const trimmed = raw.trim();
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed.text === 'string') return parsed.text.replace(/\\n/g, '\n');
      } catch (_) { /* fall through */ }
    }
    return raw;
  }

  function buildReplyCard(replyRef) {
    const card = ce('div', {
      class: 'tc-reply-card',
      title: 'Jump to original',
      on: {
        click: () => {
          if (!replyRef.replyMessageId) return;
          const target = document.querySelector(
            '.tc-message[data-message-id="' + cssEscape(replyRef.replyMessageId) + '"]',
          );
          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('tc-message-flash');
            setTimeout(() => target.classList.remove('tc-message-flash'), 1500);
          }
        },
      },
    });
    card.appendChild(ce('span', { class: 'tc-reply-connector' }));
    const author = replyRef.replyAuthor || 'User';
    card.appendChild(ce('span', { class: 'tc-reply-author', text: '↪ ' + author }));
    card.appendChild(ce('span', {
      class: 'tc-reply-preview',
      text: (replyRef.replyPreview || '').slice(0, 200),
    }));
    return card;
  }

  function cssEscape(s) {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(s);
    return String(s).replace(/["\\]/g, '\\$&');
  }

  // ----- AGiXT-served media: JWT rewrite + GIF auto-stop ----------------
  // Ported from chat.js — the webview can't attach a Bearer header to
  // a plain <img src>, but AGiXT's serve_file endpoint accepts
  // `?auth=<jwt>` as a query-param fallback. We restrict the rewrite to
  // the AGiXT origin so a markdown image hosted on someone else's site
  // can't be tricked into receiving the user's token.

  const AGIXT_WORKSPACE_PATH = /(^|\/)(outputs|api\/workspace|workspace)\//;
  const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '[::1]', '::1']);
  let agixtServerUrl = null;
  let agixtJwt = null;

  function refreshAgixtMediaContext() {
    Promise.resolve(window.AgixtApi && window.AgixtApi.getSettings
      ? window.AgixtApi.getSettings() : null)
      .then((s) => {
        if (!s) return;
        agixtServerUrl = s.server_url || null;
        agixtJwt = s.jwt || null;
      }).catch(() => {});
  }

  function trustedWorkspaceOrigins() {
    const origins = new Set();
    if (!agixtServerUrl) return origins;
    try {
      const parsed = new URL(agixtServerUrl);
      origins.add(parsed.origin);
      if (LOOPBACK_HOSTS.has(parsed.hostname)) {
        const port = parsed.port ? ':' + parsed.port : '';
        origins.add(parsed.protocol + '//localhost' + port);
        origins.add(parsed.protocol + '//127.0.0.1' + port);
        origins.add(parsed.protocol + '//0.0.0.0' + port);
        origins.add(parsed.protocol + '//[::1]' + port);
      }
    } catch (_) {}
    return origins;
  }

  function rewriteAuthForUrl(url) {
    if (!url || typeof url !== 'string') return url;
    if (url.startsWith('data:') || url.startsWith('blob:')) return url;
    let abs = url;
    const wasRelative = url.startsWith('/');
    if (wasRelative) {
      if (!agixtServerUrl) return url;
      abs = agixtServerUrl.replace(/\/+$/, '') + url;
    }
    let parsed;
    try { parsed = new URL(abs); } catch (_) { return url; }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return url;
    if (!AGIXT_WORKSPACE_PATH.test(parsed.pathname)) return url;
    const origins = trustedWorkspaceOrigins();
    if (!wasRelative && !origins.has(parsed.origin)) return url;
    if (!agixtJwt) return abs;
    if (!parsed.searchParams.has('auth')) {
      parsed.searchParams.set('auth', agixtJwt);
    }
    return parsed.toString();
  }

  function authMediaNodes(root) {
    if (!root || (!agixtServerUrl && !agixtJwt)) return;
    root.querySelectorAll('img[src], video[src], audio[src], source[src]')
      .forEach((node) => {
        const next = rewriteAuthForUrl(node.getAttribute('src'));
        if (next) node.setAttribute('src', next);
      });
    root.querySelectorAll('a[href]').forEach((node) => {
      const href = node.getAttribute('href') || '';
      if (/\.(png|jpe?g|gif|webp|avif|svg|mp4|webm|mov|m4v|mp3|wav|ogg)(\?.*)?$/i.test(href)) {
        const next = rewriteAuthForUrl(href);
        if (next) node.setAttribute('href', next);
      }
    });
  }

  // ----- GIF auto-stop --------------------------------------------------
  // Discord and the web's GifPlayer.tsx auto-pause GIFs after ~10s by
  // capturing the current frame to a canvas, then swapping the <img>
  // for the still frame. We mirror the same behavior: every <img> whose
  // src looks like a GIF gets wrapped in a `.tc-gif-wrap` that overlays
  // a play / pause button. Multiple GIFs in the same channel don't all
  // animate forever.

  const GIF_AUTO_PAUSE_MS = 10000;

  function looksLikeGif(url) {
    if (!url) return false;
    return /\.gif(\?.*)?$/i.test(url)
      || /media\.tenor\.com|tenor\.com|giphy\.com|media\.giphy\.com/i.test(url);
  }

  // Tracks every mounted GIF player so the viewport observer can
  // play / pause them as the user scrolls.
  const gifPlayers = new WeakMap(); // wrap element -> { play, pause }
  let gifViewportObserver = null;
  function ensureGifViewportObserver() {
    if (gifViewportObserver) return gifViewportObserver;
    if (typeof IntersectionObserver !== 'function') return null;
    gifViewportObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const ctrl = gifPlayers.get(entry.target);
        if (!ctrl) continue;
        // Only auto-toggle while the player is in its initial 10s
        // window — once the user has clicked to pause/resume, respect
        // their choice.
        if (ctrl.userPaused) continue;
        if (entry.isIntersecting) ctrl.play();
        else ctrl.pause();
      }
    }, { rootMargin: '50px 0px' });
    return gifViewportObserver;
  }

  function installGifAutoStop(img) {
    if (!img || img.dataset.gifBound === '1') return;
    img.dataset.gifBound = '1';
    // Wrap the <img> so the play/pause overlay can sit on top and the
    // viewport observer has a single element to watch. We DON'T start
    // playing until the wrap enters the viewport (handled by
    // ensureGifViewportObserver below).
    const wrap = document.createElement('span');
    wrap.className = 'tc-gif-wrap';
    img.parentNode.insertBefore(wrap, img);
    wrap.appendChild(img);
    img.classList.add('tc-gif-img');
    const overlay = document.createElement('button');
    overlay.type = 'button';
    overlay.className = 'tc-gif-overlay is-paused';
    overlay.title = 'Play / pause GIF';
    overlay.setAttribute('aria-label', 'Play GIF');
    overlay.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
    wrap.appendChild(overlay);
    const src = img.getAttribute('src') || '';
    if (!src.startsWith('data:')) {
      try { img.crossOrigin = 'anonymous'; } catch (_) {}
    }

    // We keep the animated src in a dataset slot whenever we swap to
    // a still PNG so resume just flips the src back. The browser
    // re-decodes the GIF from the start each time, which matches the
    // web's GifPlayer behavior.
    let playing = false;
    let pauseTimer = null;
    const ctrl = {
      userPaused: false,
      play() {
        if (playing) return;
        playing = true;
        const animated = img.dataset.animatedSrc;
        if (animated) {
          img.setAttribute('src', animated);
          img.dataset.animatedSrc = '';
        }
        wrap.classList.remove('is-paused-fallback');
        overlay.classList.remove('is-paused');
        clearTimeout(pauseTimer);
        // Auto-stop after 10s of playback — matches the web's
        // GifPlayer AUTO_PAUSE_MS so a chat full of GIFs settles
        // instead of looping forever.
        pauseTimer = setTimeout(() => { ctrl.pause(); }, GIF_AUTO_PAUSE_MS);
      },
      pause() {
        if (!playing) return;
        playing = false;
        clearTimeout(pauseTimer);
        try {
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth || img.clientWidth || 1;
          canvas.height = img.naturalHeight || img.clientHeight || 1;
          const ctx = canvas.getContext('2d');
          if (ctx && canvas.width && canvas.height) {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            img.dataset.animatedSrc = src;
            img.setAttribute('src', canvas.toDataURL('image/png'));
          } else {
            wrap.classList.add('is-paused-fallback');
          }
        } catch (_) {
          // Tainted canvas (CORS) — fall back to a CSS class that
          // desaturates the still without swapping the src.
          wrap.classList.add('is-paused-fallback');
        }
        overlay.classList.add('is-paused');
      },
      toggle() {
        if (playing) { ctrl.userPaused = true; ctrl.pause(); }
        else { ctrl.userPaused = false; ctrl.play(); }
      },
    };
    gifPlayers.set(wrap, ctrl);
    // Click ANYWHERE in the wrap (the GIF image or the overlay button)
    // toggles play/pause — matches Discord / web's GifPlayer click
    // target.
    wrap.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      ctrl.toggle();
    });
    // Observe so we only play when the GIF is on-screen.
    const obs = ensureGifViewportObserver();
    if (obs) obs.observe(wrap);
    else {
      // No IntersectionObserver — just start playing immediately.
      if (img.complete && img.naturalWidth) ctrl.play();
      else img.addEventListener('load', () => ctrl.play(), { once: true });
    }
  }

  // Image lightbox — full-screen overlay with the image centered, click
  // anywhere (or Esc) to close, button to download. Single instance is
  // re-used across the session.
  function openImageLightbox(src, alt) {
    let backdrop = document.querySelector('.tc-lightbox-backdrop');
    if (backdrop) backdrop.remove();
    backdrop = ce('div', { class: 'tc-lightbox-backdrop' });
    const img = ce('img', { class: 'tc-lightbox-img', alt: alt || '' });
    img.src = src;
    backdrop.appendChild(img);
    const closeBtn = ce('button', {
      type: 'button',
      class: 'tc-lightbox-close',
      'aria-label': 'Close',
      text: '×',
    });
    backdrop.appendChild(closeBtn);
    const dlBtn = ce('button', {
      type: 'button',
      class: 'tc-lightbox-dl',
      title: 'Download',
      'aria-label': 'Download image',
      html: '<svg width="16" height="16" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
    });
    backdrop.appendChild(dlBtn);
    function close() {
      backdrop.remove();
      document.removeEventListener('keydown', escClose);
    }
    function escClose(e) { if (e.key === 'Escape') close(); }
    closeBtn.addEventListener('click', close);
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop || e.target === img) close();
    });
    dlBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const a = document.createElement('a');
      a.href = src;
      // Pick a sensible filename — for data: URLs derive an ext, else
      // fall back to the alt text or "image".
      let name = alt || 'image';
      const dataMime = src.match(/^data:image\/([a-z0-9+-]+)/i);
      if (dataMime) name = (alt || 'image') + '.' + dataMime[1].split('+')[0];
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
    document.addEventListener('keydown', escClose);
    document.body.appendChild(backdrop);
  }

  // ----- OG previews ----------------------------------------------------

  async function attachOGPreview(container, url) {
    let data = ogCache.has(url) ? ogCache.get(url) : null;
    let skeleton = null;
    if (!ogCache.has(url)) {
      // Drop a skeleton card while the fetch is in flight — mirrors
      // LinkPreview.tsx (compact placeholder, animated pulse). If the
      // fetch yields no metadata, we just remove the skeleton.
      skeleton = buildOGSkeleton();
      container.appendChild(skeleton);
      try {
        if (ogInflight.has(url)) {
          data = await ogInflight.get(url);
        } else {
          const p = fetchOGData(url);
          ogInflight.set(url, p);
          data = await p;
          ogInflight.delete(url);
          ogCache.set(url, data);
        }
      } catch (e) {
        ogCache.set(url, null);
      }
    }
    if (skeleton && skeleton.isConnected) skeleton.remove();
    if (!data) return;
    if (!container.isConnected) return;
    container.appendChild(buildOGCard(url, data));
  }

  function buildOGSkeleton() {
    const card = ce('div', { class: 'tc-og-card tc-og-skel' });
    card.appendChild(ce('div', { class: 'tc-og-skel-img' }));
    const meta = ce('div', { class: 'tc-og-meta' });
    meta.appendChild(ce('div', { class: 'tc-og-skel-bar tc-og-skel-bar-sm' }));
    meta.appendChild(ce('div', { class: 'tc-og-skel-bar' }));
    meta.appendChild(ce('div', { class: 'tc-og-skel-bar tc-og-skel-bar-sm' }));
    card.appendChild(meta);
    return card;
  }

  // Browser-like UA — Twitter / Reddit / a number of other sites
  // serve a different (or no) HTML payload to bots, so a desktop
  // app that wants OG previews has to look like Chrome. Matches the
  // BROWSER_UA the web's /api/og route uses.
  const OG_BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    + 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';
  // fxtwitter responds to Twitterbot specifically with OG metadata.
  const OG_TWITTERBOT_UA = 'Twitterbot/1.0';

  // The webview's fetch() silently drops User-Agent / Referer / Origin
  // per the WHATWG forbidden-header list, which breaks every Twitter
  // OG path (fxtwitter only emits OG tags to Twitterbot; syndication
  // 403s without the right Referer + Origin). Route every OG fetch
  // through a Rust-side IPC that uses reqwest, which has no such
  // restriction. Falls back to a webview fetch when Tauri isn't
  // around (jsdom test env).
  async function ogFetch(opts) {
    const tauri = window.__TAURI__ && window.__TAURI__.core
      && typeof window.__TAURI__.core.invoke === 'function';
    if (tauri) {
      try {
        return await window.__TAURI__.core.invoke('og_fetch', { args: opts });
      } catch (_) {
        return null;
      }
    }
    // Fallback path used by tests (jsdom) — forbidden headers will be
    // dropped but the call won't blow up.
    try {
      const resp = await fetch(opts.url, {
        method: 'GET',
        credentials: 'omit',
        redirect: 'follow',
        referrerPolicy: 'no-referrer',
        headers: {
          'Accept': opts.accept
            || 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': opts.accept_language || 'en-US,en;q=0.9',
        },
      });
      const body = await resp.text();
      return {
        ok: resp.ok,
        status: resp.status,
        content_type: resp.headers.get('content-type') || '',
        body,
        final_url: resp.url || opts.url,
      };
    } catch (_) {
      return null;
    }
  }
  // Most popular Twitter / X URL shapes carry the tweet ID right
  // before a `/photo`, `/video`, or end-of-path. We grab it and reuse
  // it across the three proxies.
  const TWEET_ID_RE = /(?:^|\/)status(?:es)?\/(\d+)/;

  function isTwitterUrl(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === 'twitter.com' || host === 'www.twitter.com'
        || host === 'x.com' || host === 'www.x.com' || host === 'mobile.twitter.com';
    } catch (_) { return false; }
  }

  function extractTweetId(url) {
    try {
      const m = new URL(url).pathname.match(TWEET_ID_RE);
      return m ? m[1] : null;
    } catch (_) { return null; }
  }

  function isYouTubeUrl(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === 'youtube.com' || host === 'www.youtube.com'
        || host === 'm.youtube.com' || host === 'youtu.be'
        || host === 'www.youtu.be';
    } catch (_) { return false; }
  }

  function isGitHubUrl(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === 'github.com' || host === 'www.github.com'
        || host === 'gist.github.com';
    } catch (_) { return false; }
  }

  function extractYouTubeId(url) {
    try {
      const u = new URL(url);
      if (u.hostname.endsWith('youtu.be')) return u.pathname.slice(1).split('/')[0];
      if (u.pathname === '/watch') return u.searchParams.get('v');
      const m = u.pathname.match(/^\/(?:shorts|embed|v|live)\/([\w-]{6,})/);
      if (m) return m[1];
      return null;
    } catch (_) { return null; }
  }

  function metaFrom(text, prop) {
    if (!text) return '';
    const esc = prop.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(
      '<meta[^>]+(?:property|name)=["\']' + esc
        + '["\'][^>]*content=["\']([^"\']*)["\']',
      'i',
    );
    const re2 = new RegExp(
      '<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']'
        + esc + '["\']',
      'i',
    );
    const m = text.match(re) || text.match(re2);
    return m ? m[1] : '';
  }

  function parseOGFromHtml(text, baseUrl) {
    const title = metaFrom(text, 'og:title') || metaFrom(text, 'twitter:title')
      || (text.match(/<title[^>]*>([^<]+)<\/title>/i) || [, ''])[1];
    const description = metaFrom(text, 'og:description')
      || metaFrom(text, 'twitter:description')
      || metaFrom(text, 'description');
    let image = metaFrom(text, 'og:image') || metaFrom(text, 'twitter:image')
      || metaFrom(text, 'og:image:url') || metaFrom(text, 'og:image:secure_url');
    // og:video lets us show animated previews for Tweet videos /
    // YouTube shorts / etc. Prefer the player URL when available.
    let video = metaFrom(text, 'og:video:secure_url')
      || metaFrom(text, 'og:video:url')
      || metaFrom(text, 'og:video')
      || metaFrom(text, 'twitter:player:stream');
    let siteName = metaFrom(text, 'og:site_name');
    try { siteName = siteName || new URL(baseUrl).hostname.replace(/^www\./, ''); }
    catch (_) {}
    function abs(u) {
      if (!u) return u;
      if (u.startsWith('/')) { try { return new URL(u, baseUrl).toString(); } catch (_) {} }
      return u;
    }
    image = abs(image);
    video = abs(video);
    if (!title && !description && !image && !video) return null;
    return {
      title: (title || '').trim(),
      description: (description || '').trim(),
      image: image || '',
      video: video || '',
      siteName: siteName || '',
      url: baseUrl,
    };
  }

  // Port of the web's /api/og strategy. For Twitter / X URLs we try
  // three proxies in order (each speaks OG fluently when the public
  // site doesn't):
  //   1. fxtwitter — Twitter's de-facto OG proxy. UA: Twitterbot.
  //   2. Twitter syndication endpoint — JSON, no API key required.
  //   3. publish.twitter.com oEmbed — returns an HTML snippet we
  //      strip down to author + text.
  // For everything else we fetch with a real browser UA so bot-blocked
  // sites still serve the OG meta tags.
  async function fetchOGData(url) {
    // Twitter / X-specific path.
    if (isTwitterUrl(url)) {
      const tweetId = extractTweetId(url);
      if (tweetId) {
        // 1. fxtwitter
        const fx = await tryFxTwitter(tweetId);
        if (fx) return fx;
        // 2. syndication
        const syn = await trySyndication(tweetId);
        if (syn) return syn;
        // 3. oEmbed
        const oe = await tryOEmbed(url);
        if (oe) return oe;
        // 4. minimal card from URL path — better than nothing.
        try {
          const path = new URL(url).pathname.split('/').filter(Boolean);
          const author = path[0] || 'Tweet';
          return {
            title: '@' + author + ' on X',
            description: '',
            image: '',
            siteName: 'X (Twitter)',
            url,
          };
        } catch (_) { return null; }
      }
    }
    // YouTube-specific path. The full HTML is a JS-rendered shell so
    // OG meta tags don't always survive. The public oEmbed endpoint
    // returns title + author + thumbnail without an API key. We also
    // synthesize an embeddable video URL pointing at the player so
    // the OG card can autoplay inline when the user clicks the card.
    if (isYouTubeUrl(url)) {
      const videoId = extractYouTubeId(url);
      const oe = await tryYouTubeOEmbed(url);
      if (oe) {
        if (videoId) oe.video = 'https://www.youtube.com/embed/' + videoId;
        return oe;
      }
      // oEmbed failed (rate-limited, etc.) — fall back to a still
      // image card built from the canonical thumbnail URL pattern.
      if (videoId) {
        return {
          title: 'YouTube video',
          description: '',
          image: 'https://i.ytimg.com/vi/' + videoId + '/hqdefault.jpg',
          video: '',
          siteName: 'YouTube',
          url,
        };
      }
    }
    // GitHub-specific path. github.com sometimes gates the public HTML
    // behind a bot challenge, so when the generic fetch returns
    // nothing useful, fall back to the opengraph.githubassets.com URL
    // shape that github embeds in their own meta tags.
    if (isGitHubUrl(url)) {
      const direct = await fetchGenericOG(url);
      if (direct) return direct;
      // Synthesize a card from the URL path.
      try {
        const parts = new URL(url).pathname.split('/').filter(Boolean);
        const owner = parts[0];
        const repo = parts[1];
        if (owner && repo) {
          return {
            title: owner + '/' + repo,
            description: '',
            image: 'https://opengraph.githubassets.com/1/'
              + encodeURIComponent(owner) + '/'
              + encodeURIComponent(repo),
            video: '',
            siteName: 'GitHub',
            url,
          };
        }
      } catch (_) {}
    }
    // Generic OG fetch — routed through the IPC so the User-Agent
    // actually reaches the destination server.
    return fetchGenericOG(url);
  }

  // Same logic as the generic fetch but exposed so site-specific
  // branches can call it directly. Used by the GitHub path to try a
  // direct fetch before falling back to the synthesized card.
  async function fetchGenericOG(url) {
    const r = await ogFetch({ url, user_agent: OG_BROWSER_UA });
    if (!r || !r.ok || !r.body) return null;
    return parseOGFromHtml(r.body, r.final_url || url);
  }

  async function tryYouTubeOEmbed(url) {
    const oeUrl = 'https://www.youtube.com/oembed?url='
      + encodeURIComponent(url) + '&format=json';
    const r = await ogFetch({
      url: oeUrl,
      user_agent: OG_BROWSER_UA,
      accept: 'application/json',
    });
    if (!r || !r.ok || !r.body) return null;
    let json;
    try { json = JSON.parse(r.body); } catch (_) { return null; }
    if (!json || !json.title) return null;
    return {
      title: json.title,
      description: json.author_name ? 'by ' + json.author_name : '',
      image: json.thumbnail_url || '',
      video: '',
      siteName: 'YouTube',
      url,
    };
  }

  async function tryFxTwitter(tweetId) {
    const r = await ogFetch({
      url: 'https://fxtwitter.com/i/status/' + tweetId,
      // fxtwitter ONLY emits the rich OG tags to Twitterbot. A regular
      // browser UA just gets redirected to x.com (no OG, no preview).
      // This is the whole reason og_fetch exists — the webview's
      // fetch() strips the UA header so we couldn't reach this path
      // before.
      user_agent: OG_TWITTERBOT_UA,
      accept: 'text/html',
    });
    if (!r || !r.ok || !r.body) return null;
    const parsed = parseOGFromHtml(r.body, 'https://x.com/i/status/' + tweetId);
    if (!parsed) return null;
    if (parsed.image && /\/profile_images\//i.test(parsed.image)) parsed.image = '';
    if (/^FxTwitter$/i.test(parsed.title || '')) return null;
    if (/^Sorry, that/i.test(parsed.description || '')) return null;
    parsed.siteName = 'X (Twitter)';
    return parsed;
  }

  async function trySyndication(tweetId) {
    const url = 'https://cdn.syndication.twimg.com/tweet-result?id='
      + encodeURIComponent(tweetId) + '&token=x';
    const r = await ogFetch({
      url,
      user_agent: OG_BROWSER_UA,
      accept: 'application/json, text/javascript, */*',
      // The syndication endpoint rejects (403) without the headers its
      // own embed widget sends. The webview can't add these — the IPC
      // can.
      referer: 'https://platform.twitter.com/',
      origin: 'https://platform.twitter.com',
    });
    if (!r || !r.ok || !r.body) return null;
    try {
      const json = JSON.parse(r.body);
      if (!json || !(json.text || json.full_text)) return null;
      const u = json.user || {};
      const authorName = u.name || u.screen_name || 'Tweet';
      const authorHandle = u.screen_name ? '@' + u.screen_name : '';
      // Media extraction — walk every well-known place the syndication
      // API stuffs photos / videos. Matches the web's parsing order.
      const mediaSources = [].concat(
        json.mediaDetails || [],
        (json.entities && json.entities.media) || [],
        (json.extended_entities && json.extended_entities.media) || [],
      );
      let image = '';
      let video = '';
      for (const m of mediaSources) {
        if (!m) continue;
        const mediaUrl = m.media_url_https || m.media_url;
        if (!image && mediaUrl && !/profile_images\//i.test(mediaUrl)) {
          image = mediaUrl;
        }
        // Video tweets carry a `video_info.variants` array; pick the
        // highest-bitrate mp4 so the inline <video> player works.
        const variants = (m.video_info && m.video_info.variants) || [];
        if (!video) {
          let best = null;
          let bestBitrate = -1;
          for (const v of variants) {
            if (v.content_type !== 'video/mp4') continue;
            const br = Number(v.bitrate || 0);
            if (br > bestBitrate) { best = v; bestBitrate = br; }
          }
          if (best && best.url) video = best.url;
        }
      }
      // Fallback to the `photos` array (older syndication shape).
      if (!image && json.photos) {
        for (const p of json.photos) {
          if (p && p.url && !/profile_images\//i.test(p.url)) {
            image = p.url;
            break;
          }
        }
      }
      const text = (json.text || json.full_text || '').trim();
      return {
        title: authorName + (authorHandle ? ' (' + authorHandle + ')' : '') + ' on X',
        description: text.length > 280 ? text.slice(0, 280) + '…' : text,
        image,
        video,
        siteName: 'X (Twitter)',
        url: 'https://x.com/i/status/' + tweetId,
      };
    } catch (_) { return null; }
  }

  async function tryOEmbed(tweetUrl) {
    const url = 'https://publish.twitter.com/oembed?url='
      + encodeURIComponent(tweetUrl) + '&omit_script=true';
    const r = await ogFetch({
      url, user_agent: OG_BROWSER_UA, accept: 'application/json',
    });
    if (!r || !r.ok || !r.body) return null;
    let json;
    try { json = JSON.parse(r.body); } catch (_) { return null; }
    if (!json || !json.html) return null;
    let body = String(json.html);
    while (/<[^>]+>/.test(body)) body = body.replace(/<[^>]+>/g, ' ');
    const text = body.replace(/&[a-z]+;/gi, ' ').replace(/\s+/g, ' ').trim();
    return {
      title: (json.author_name || 'Tweet') + ' on X',
      description: text.slice(0, 280),
      image: '',
      siteName: 'X (Twitter)',
      url: tweetUrl,
    };
  }

  function buildOGCard(url, data) {
    // Twitter / X URLs get the Discord-style colored embed: blue left
    // rule, X logo in the header, author + handle parsed out of the
    // title. Everything else uses the generic "image on top when there
    // is an image" layout the web's LinkPreview applies.
    if (isTwitterUrl(url) || /^https?:\/\/(?:www\.)?fxtwitter\.com\//i.test(url)) {
      return buildTwitterCard(url, data);
    }
    return buildGenericOGCard(url, data);
  }

  function buildGenericOGCard(url, data) {
    // The web's LinkPreview pattern: when an image is present, the
    // card flips to flex-column with the image full-width on top and
    // text underneath. Without an image, it's text-only.
    const hasMedia = !!(data.image || data.video);
    const card = ce('a', {
      class: 'tc-og-card' + (hasMedia ? ' tc-og-card-media' : ''),
      href: url,
      target: '_blank',
      rel: 'noreferrer',
    });
    if (data.video) {
      const video = ce('video', {
        class: 'tc-og-video',
        controls: true,
        preload: 'metadata',
        playsinline: true,
      });
      if (data.image) video.setAttribute('poster', data.image);
      video.src = data.video;
      video.addEventListener('click', (e) => e.stopPropagation());
      card.appendChild(video);
    } else if (data.image) {
      const img = ce('img', { class: 'tc-og-image', alt: '', loading: 'lazy' });
      img.referrerPolicy = 'no-referrer';
      img.onerror = () => { img.remove(); card.classList.remove('tc-og-card-media'); };
      img.src = data.image;
      card.appendChild(img);
    }
    const meta = ce('div', { class: 'tc-og-meta' });
    if (data.siteName) {
      const site = ce('div', { class: 'tc-og-site' });
      site.appendChild(ce('span', { class: 'tc-og-site-icon', html:
        '<svg width="10" height="10" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/></svg>' }));
      site.appendChild(ce('span', { text: data.siteName }));
      meta.appendChild(site);
    }
    if (data.title) meta.appendChild(ce('div', { class: 'tc-og-title', text: data.title }));
    if (data.description) meta.appendChild(ce('div', {
      class: 'tc-og-desc',
      text: data.description.slice(0, 280),
    }));
    card.appendChild(meta);
    return card;
  }

  function buildTwitterCard(url, data) {
    // fxtwitter / syndication both stuff the author name + handle into
    // the title field as "Author Name (@handle) on X". Parse that out
    // so we can render them on separate visual lines like the web.
    let authorName = data.title || 'Tweet';
    let authorHandle = '';
    const m = String(data.title || '').match(/^(.+?)\s*\((@[\w]+)\)/);
    if (m) { authorName = m[1].trim(); authorHandle = m[2]; }

    const card = ce('a', {
      class: 'tc-og-card tc-og-card-twitter',
      href: url,
      target: '_blank',
      rel: 'noreferrer',
    });
    const head = ce('div', { class: 'tc-og-tw-head' });
    head.appendChild(ce('span', { class: 'tc-og-tw-logo', html:
      '<svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">'
      + '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>'
      + '</svg>',
    }));
    head.appendChild(ce('span', { text: 'X (Twitter)' }));
    card.appendChild(head);
    const author = ce('div', { class: 'tc-og-tw-author' });
    author.appendChild(ce('span', { class: 'tc-og-tw-name', text: authorName }));
    if (authorHandle) author.appendChild(ce('span', {
      class: 'tc-og-tw-handle', text: ' ' + authorHandle,
    }));
    card.appendChild(author);
    if (data.description) {
      card.appendChild(ce('div', {
        class: 'tc-og-tw-text',
        text: data.description,
      }));
    }
    // Twitter media: we prefer video > image. If we have a video URL,
    // render a <video> inline; otherwise an image. Matches the web's
    // visual emphasis (media is the centerpiece of the tweet card).
    if (data.video) {
      const video = ce('video', {
        class: 'tc-og-tw-video',
        controls: true,
        preload: 'metadata',
        playsinline: true,
      });
      if (data.image) video.setAttribute('poster', data.image);
      video.src = data.video;
      video.addEventListener('click', (e) => e.stopPropagation());
      card.appendChild(video);
    } else if (data.image) {
      const img = ce('img', { class: 'tc-og-tw-image', alt: '', loading: 'lazy' });
      img.referrerPolicy = 'no-referrer';
      img.onerror = () => { img.remove(); };
      img.src = data.image;
      card.appendChild(img);
    }
    return card;
  }

  // ----- Rendering: member list -----------------------------------------

  function memberMatchesSearch(participant) {
    if (!memberSearch) return true;
    const q = memberSearch.toLowerCase();
    if (participant.participant_type === 'agent') {
      return (participant.agent && participant.agent.name || '').toLowerCase().includes(q);
    }
    const u = participant.user || {};
    return (
      (u.email || '').toLowerCase().includes(q)
      || (u.first_name || '').toLowerCase().includes(q)
      || (u.last_name || '').toLowerCase().includes(q)
    );
  }

  // Build the list of "company agents you can also message" — mirrors
  // ChannelMemberList.tsx's extraAgents filter (agents from the active
  // server that aren't explicit channel participants).
  function extraCompanyAgents() {
    if (!activeCompanyId) return [];
    const company = companies.find((c) => c.id === activeCompanyId);
    if (!company || !company.agents) return [];
    const list = participantsByChannel.get(activeChannelId) || [];
    const inChannel = new Set(
      list.filter((p) => p.participant_type === 'agent' && p.agent && p.agent.name)
        .map((p) => p.agent.name.toLowerCase()),
    );
    return company.agents
      .filter((a) => a && a.name && !inChannel.has(a.name.toLowerCase()))
      .filter((a) => !memberSearch
        || a.name.toLowerCase().includes(memberSearch.toLowerCase()));
  }

  function renderMembers() {
    const wrap = el('tc-member-scroll');
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!activeChannelId) {
      wrap.appendChild(ce('div', { class: 'tc-member-empty', text: 'No channel selected.' }));
      return;
    }
    const list = participantsByChannel.get(activeChannelId) || [];
    const agents = list.filter((p) => p.participant_type === 'agent' && memberMatchesSearch(p));
    const users = list.filter((p) => p.participant_type !== 'agent' && memberMatchesSearch(p));
    const extras = extraCompanyAgents();
    if (!list.length && !extras.length) {
      wrap.appendChild(ce('div', { class: 'tc-member-empty', text: 'No members yet.' }));
      return;
    }
    if (agents.length || extras.length) {
      const total = agents.length + extras.length;
      wrap.appendChild(ce('div', { class: 'tc-member-section',
        text: 'Agents — ' + total }));
      for (const p of agents) wrap.appendChild(renderMemberRow(p));
      for (const a of extras) wrap.appendChild(renderExtraAgentRow(a));
    }
    if (users.length) {
      wrap.appendChild(ce('div', { class: 'tc-member-section',
        text: 'Members — ' + users.length }));
      for (const p of users) wrap.appendChild(renderMemberRow(p));
    }
    if (!agents.length && !users.length && !extras.length && memberSearch) {
      wrap.appendChild(ce('div', { class: 'tc-member-empty', text: 'No matches.' }));
    }
  }

  function renderMemberRow(participant) {
    const isAgent = participant.participant_type === 'agent';
    const name = nameForParticipant(participant);
    const u = participant.user || {};
    const role = participant.role || 'member';
    const row = ce('div', {
      class: 'tc-member-row' + (isAgent ? ' is-agent' : ''),
      on: {
        contextmenu: (e) => {
          e.preventDefault();
          showMemberContextMenu(e, participant);
        },
      },
    });
    // Avatar wrapped in a positioning context so the presence dot can
    // pin to its bottom-right corner.
    const avatarWrap = ce('div', { class: 'tc-member-avatar-wrap' });
    avatarWrap.appendChild(buildAvatar({
      name,
      email: u.email,
      avatarUrl: u.avatar_url,
      isAgent,
      size: 28,
    }));
    const online = isAgent || isUserOnline(u.last_seen);
    const dot = ce('span', {
      class: 'tc-presence-dot' + (online ? ' is-online' : ''),
      title: isAgent ? 'Agent' : presenceLabel(u.last_seen),
    });
    avatarWrap.appendChild(dot);
    row.appendChild(avatarWrap);
    const main = ce('div', { class: 'tc-member-main' });
    const nameRow = ce('div', { class: 'tc-member-name-row' });
    nameRow.appendChild(ce('span', {
      class: 'tc-member-name' + (role === 'observer' ? ' is-observer' : ''),
      text: name,
    }));
    if (!isAgent && role !== 'member') {
      const ic = ce('span', { class: 'tc-member-role-icon', html: roleIconSVG(role),
        title: role[0].toUpperCase() + role.slice(1) });
      nameRow.appendChild(ic);
    }
    main.appendChild(nameRow);
    if (isAgent) {
      main.appendChild(ce('div', { class: 'tc-member-sub', text: 'Agent' }));
    } else if (role === 'observer') {
      main.appendChild(ce('div', { class: 'tc-member-sub', text: 'Muted' }));
    } else if (role && role !== 'member') {
      main.appendChild(ce('div', {
        class: 'tc-member-sub',
        text: role[0].toUpperCase() + role.slice(1),
      }));
    }
    if (!isAgent && u.status_text) {
      main.appendChild(ce('div', { class: 'tc-member-status', text: u.status_text }));
    }
    row.appendChild(main);
    return row;
  }

  function renderExtraAgentRow(agent) {
    const row = ce('div', {
      class: 'tc-member-row is-agent tc-member-extra',
      title: 'Not in this channel — right-click to DM',
      on: {
        contextmenu: (e) => {
          e.preventDefault();
          showCtxMenu(e.clientX, e.clientY, [
            { heading: agent.name },
            { label: 'Send DM to agent', onClick: () => startAgentDM(agent) },
            '-',
            { label: 'Copy agent name', onClick: () => copyToClipboard(agent.name) },
            { label: 'Copy ID', onClick: () => copyToClipboard(agent.id || '') },
          ]);
        },
      },
    });
    const avatarWrap = ce('div', { class: 'tc-member-avatar-wrap' });
    avatarWrap.appendChild(buildAvatar({ name: agent.name, isAgent: true, size: 28 }));
    avatarWrap.appendChild(ce('span', { class: 'tc-presence-dot is-online', title: 'Agent' }));
    row.appendChild(avatarWrap);
    const main = ce('div', { class: 'tc-member-main' });
    main.appendChild(ce('div', { class: 'tc-member-name', text: agent.name }));
    main.appendChild(ce('div', { class: 'tc-member-sub', text: 'Agent — not in channel' }));
    row.appendChild(main);
    return row;
  }

  // ----- Context menus (ported from ChannelContextMenus.tsx + Message.tsx)

  function showGroupContextMenu(e, company) {
    showCtxMenu(e.clientX, e.clientY, [
      { heading: company.name },
      {
        label: 'Browse channels',
        onClick: () => selectCompany(company.id),
      },
      '-',
      {
        label: 'Copy server ID',
        onClick: () => copyToClipboard(company.id),
      },
    ]);
  }

  function showChannelContextMenu(e, channel, isDM) {
    const cName = channel.display_name || channel.displayName || channel.name || '';
    const items = [
      { heading: '#' + (isDM ? '' : ' ') + cName.slice(0, 28) },
      { label: 'Open channel', onClick: () => selectChannel(channel.id) },
    ];
    if (!isDM) {
      items.push('-');
      items.push({ label: 'Mark as read', onClick: () => {
        window.AgixtApi.markConversationRead(channel.id).then(() => { refresh(); }).catch(() => {});
      }});
      // Notification mode submenu — simplified to a per-mode item list
      items.push({ label: 'Notifications: All', onClick: () =>
        setNotifMode(channel.id, 'all') });
      items.push({ label: 'Notifications: Mentions only', onClick: () =>
        setNotifMode(channel.id, 'mentions') });
      items.push({ label: 'Notifications: Muted', onClick: () =>
        setNotifMode(channel.id, 'none') });
      items.push('-');
      items.push({ label: 'Edit channel…', onClick: () => openEditChannelDialog(channel) });
    }
    items.push('-');
    items.push({ label: 'Copy channel ID', onClick: () => copyToClipboard(channel.id) });
    items.push({ label: 'Copy channel name', onClick: () => copyToClipboard(cName) });
    if (!isDM) {
      items.push('-');
      items.push({
        label: 'Delete channel',
        danger: true,
        onClick: () => deleteChannelConfirm(channel),
      });
    } else {
      items.push('-');
      items.push({
        label: 'Delete conversation',
        danger: true,
        onClick: () => deleteChannelConfirm(channel),
      });
    }
    showCtxMenu(e.clientX, e.clientY, items);
  }

  async function setNotifMode(channelId, mode) {
    try {
      await window.AgixtApi.updateNotificationSettings(channelId, mode);
      toast('Notification mode updated');
    } catch (e) {
      toast('Failed to update notifications', true);
    }
  }

  function deleteChannelConfirm(channel) {
    const cName = channel.display_name || channel.displayName || channel.name || 'this channel';
    if (!window.confirm('Delete "' + cName + '"? This cannot be undone.')) return;
    window.AgixtApi.deleteConversation(channel.id).then(() => {
      toast('Deleted');
      if (activeChannelId === channel.id) {
        activeChannelId = null;
        closeWs();
        renderContentHeader();
        renderMessages();
        renderMembers();
      }
      refresh();
    }).catch(() => toast('Failed to delete', true));
  }

  function showMemberContextMenu(e, participant) {
    const name = nameForParticipant(participant);
    const isAgent = participant.participant_type === 'agent';
    const uid = isAgent ? (participant.agent && participant.agent.id)
      : (participant.user && participant.user.id);
    const items = [
      { heading: name },
      {
        label: 'Mention in chat',
        onClick: () => insertMention(name, uid),
      },
    ];
    if (!isAgent && uid && (!currentUser || currentUser.id !== uid)) {
      items.push({
        label: 'Send DM',
        onClick: () => startUserDM(participant.user),
      });
    }
    if (isAgent) {
      items.push({
        label: 'Send DM to agent',
        onClick: () => startAgentDM(participant.agent),
      });
    }
    items.push('-');
    items.push({ label: 'Copy ' + (isAgent ? 'agent' : 'user') + ' name',
                 onClick: () => copyToClipboard(name) });
    if (uid) items.push({ label: 'Copy ID', onClick: () => copyToClipboard(uid) });
    if (activeChannelId && !isAgent && participant.role !== 'owner') {
      items.push('-');
      items.push({
        label: 'Remove from channel',
        danger: true,
        onClick: () => {
          window.AgixtApi.removeConversationParticipant(activeChannelId, participant.id)
            .then(() => {
              toast('Removed');
              loadParticipants(activeChannelId).then(renderMembers);
            })
            .catch(() => toast('Failed to remove', true));
        },
      });
    }
    showCtxMenu(e.clientX, e.clientY, items);
  }

  // Tiny icon factory used by the message context menu. Mirrors the
  // lucide icons the web uses inside each ContextMenuItem.
  const CTX_ICONS = {
    reply: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="m15 10-5 5 5 5M20 4v7a4 4 0 0 1-4 4H5"/></svg>',
    copy: '<svg width="14" height="14" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
    link: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
    type: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>',
    image: '<svg width="14" height="14" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="9" r="2" fill="none" stroke="currentColor" stroke-width="2"/><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="m21 15-5-5L5 21"/></svg>',
    download: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
    pin: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 17v5M9 10.76V6h6v4.76l3 1.76V14H6v-1.48z"/></svg>',
    pencil: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
    trash: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    msgPlus: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2zM12 8v6M9 11h6"/></svg>',
  };

  function showMessageContextMenu(e, msg, renderedText) {
    const role = (msg.role || '').toString();
    const isMine = isMessageFromCurrentUser(msg);
    const isUserMsg = /^user$/i.test(role);
    const sel = (window.getSelection && window.getSelection().toString()) || '';
    const onLink = e && e.target && e.target.closest ? e.target.closest('a[href]') : null;
    const onImg = e && e.target && e.target.tagName === 'IMG' ? e.target : null;

    const items = [];
    // Quick-react row at the top — 5 quick emojis + an "Add reaction"
    // button that opens the full emoji picker. Matches the row layout
    // in Message.tsx ContextMenu.
    if (msg.id) {
      const row = QUICK_REACTIONS.map((emoji) => ({
        label: emoji,
        title: 'React ' + emoji,
        onClick: () => {
          window.AgixtApi.toggleReaction(activeChannelId, msg.id, emoji)
            .catch(() => toast('Failed to react', true));
        },
      }));
      row.push({
        label: '\u{1F642}+', // smile + plus
        title: 'Add reaction…',
        onClick: () => {
          openEmojiPicker(e.clientX, e.clientY, (emoji) => {
            window.AgixtApi.toggleReaction(activeChannelId, msg.id, emoji)
              .catch(() => toast('Failed to react', true));
          });
        },
      });
      items.push({ row });
      items.push('-');
    }

    items.push({ icon: CTX_ICONS.reply, label: 'Reply',
      onClick: () => setReplyTarget(msg, renderedText), disabled: !msg.id });
    // Threads — channel context only. Agent DMs etc. don't get a
    // "Start Thread" action because there's nothing to spin off.
    if (activeCompanyId && msg.id) {
      items.push({
        icon: CTX_ICONS.msgPlus, label: 'Start thread',
        onClick: () => startThreadFromMessage(msg, renderedText),
      });
    }
    items.push({ icon: CTX_ICONS.copy, label: 'Copy message ID',
      onClick: () => copyToClipboard(msg.id || ''), disabled: !msg.id });
    items.push('-');
    if (sel) items.push({ icon: CTX_ICONS.type, label: 'Copy selection',
      onClick: () => copyToClipboard(sel) });
    if (onLink) items.push({ icon: CTX_ICONS.link, label: 'Copy link',
      onClick: () => copyToClipboard(onLink.getAttribute('href') || '') });
    if (onImg) items.push({ icon: CTX_ICONS.image, label: 'Copy image URL',
      onClick: () => copyToClipboard(onImg.getAttribute('src') || '') });
    if (onLink || onImg) items.push({ icon: CTX_ICONS.download, label: 'Download',
      onClick: () => {
        const href = (onImg && onImg.getAttribute('src'))
          || (onLink && onLink.getAttribute('href')) || '';
        if (!href) return;
        const a = document.createElement('a');
        a.href = href;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        a.remove();
      } });
    items.push({ icon: CTX_ICONS.copy, label: 'Copy message',
      onClick: () => copyToClipboard(renderedText) });
    if (msg.id) {
      items.push('-');
      items.push({
        icon: CTX_ICONS.pin,
        label: msg.pinned ? 'Unpin message' : 'Pin message',
        onClick: () => {
          window.AgixtApi.togglePinMessage(activeChannelId, msg.id)
            .then(() => toast(msg.pinned ? 'Unpinned' : 'Pinned'))
            .catch(() => toast('Failed to update pin', true));
        },
      });
    }
    if (isMine && msg.id) {
      items.push('-');
      items.push({ icon: CTX_ICONS.pencil, label: 'Edit message',
        onClick: () => { editingMessageId = msg.id; renderMessages(); }});
    }
    if ((isMine || isUserMsg) && msg.id) {
      items.push({
        icon: CTX_ICONS.trash,
        label: 'Delete message',
        danger: true,
        onClick: () => {
          if (!window.confirm('Delete this message?')) return;
          window.AgixtApi.deleteMessage(activeChannelId, msg.id)
            .then(() => {
              const arr = messageCache.get(activeChannelId) || [];
              messageCache.set(activeChannelId, arr.filter((m) => m.id !== msg.id));
              renderMessages();
            })
            .catch(() => toast('Failed to delete', true));
        },
      });
    }
    showCtxMenu(e.clientX, e.clientY, items);
  }

  // ----- Full emoji picker ----------------------------------------------
  // Opens a popover near (x, y) with a search box + grid of every
  // entry in EMOJI_SHORTCODES. Selecting fires onPick(emoji) and
  // closes. Used by the message context-menu "Add reaction" button
  // (and any future emoji-grid action).
  function openEmojiPicker(x, y, onPick) {
    const helpers = window.AgixtTeamChatHelpers;
    if (!helpers) return;
    const existing = document.querySelector('.tc-emoji-picker');
    if (existing) existing.remove();
    const pop = ce('div', { class: 'tc-emoji-picker' });
    const search = ce('input', {
      type: 'search', class: 'tc-emoji-picker-search',
      placeholder: 'Search emoji…', autocomplete: 'off',
    });
    pop.appendChild(search);
    const grid = ce('div', { class: 'tc-emoji-picker-grid' });
    pop.appendChild(grid);

    // De-duplicate emoji glyphs — many shortcodes share a glyph
    // (joy / lol etc.) and the grid would be repetitive otherwise.
    const byGlyph = new Map(); // glyph -> { code, alts[] }
    for (const [code, glyph] of Object.entries(helpers.EMOJI_SHORTCODES)) {
      if (!byGlyph.has(glyph)) byGlyph.set(glyph, { code, alts: [] });
      else byGlyph.get(glyph).alts.push(code);
    }

    function paint(query) {
      grid.innerHTML = '';
      const q = (query || '').toLowerCase().trim();
      let count = 0;
      for (const [glyph, info] of byGlyph.entries()) {
        if (q && !info.code.toLowerCase().includes(q)
            && !info.alts.some((a) => a.toLowerCase().includes(q))) continue;
        const cell = ce('button', {
          type: 'button',
          class: 'tc-emoji-picker-cell',
          title: ':' + info.code + ':',
          text: glyph,
          on: { click: () => { pop.remove(); onPick(glyph); }},
        });
        grid.appendChild(cell);
        count++;
        if (count >= 200) break; // cap dom weight
      }
      if (!count) {
        grid.appendChild(ce('div', { class: 'tc-emoji-picker-empty', text: 'No matches' }));
      }
    }
    search.addEventListener('input', () => paint(search.value));
    paint('');

    document.body.appendChild(pop);
    const r = pop.getBoundingClientRect();
    const px = Math.min(x, window.innerWidth - r.width - 8);
    const py = Math.min(y, window.innerHeight - r.height - 8);
    pop.style.left = Math.max(8, px) + 'px';
    pop.style.top = Math.max(8, py) + 'px';
    setTimeout(() => search.focus(), 30);

    const close = (e) => {
      if (e && pop.contains(e.target)) return;
      pop.remove();
      document.removeEventListener('mousedown', close, true);
      document.removeEventListener('keydown', escClose);
    };
    const escClose = (e) => { if (e.key === 'Escape') close(); };
    setTimeout(() => {
      document.addEventListener('mousedown', close, true);
      document.addEventListener('keydown', escClose);
    }, 0);
  }

  // ----- Replies + mentions ---------------------------------------------

  // When the source message is itself a reply, peel off ITS reply
  // header so we don't quote a nested-quote chain. Matches the web's
  // chat-input.tsx flattening pass (the wire format is always one
  // level deep — sender strips the parent's reply header).
  function flattenForReplyPreview(text) {
    if (!text || !window.AgixtTeamChatHelpers) return text || '';
    const parsed = window.AgixtTeamChatHelpers.parseReply(text);
    return parsed ? parsed.actualMessage : text;
  }

  function setReplyTarget(msg, renderedText) {
    if (!msg || !msg.id) return;
    const role = (msg.role || '').toString();
    const isUser = /^user$/i.test(role);
    const senderUserId = getMessageSenderId(msg);
    let authorName;
    if (isUser) {
      authorName = senderInfoForMessage(msg).name;
    } else {
      authorName = role || 'Agent';
    }
    replyTarget = {
      messageId: msg.id,
      authorName,
      authorUserId: senderUserId || null,
      // Strip an existing reply header from the source so we don't end
      // up with [ref:...] [uid:...] tokens visible in our new reply.
      preview: flattenForReplyPreview(renderedText || '').slice(0, 200),
    };
    renderReplyChip();
    renderTypingIndicator(); // web hides the typing line while replying
    const input = el('tc-composer-input');
    if (input) input.focus();
  }

  function clearReplyTarget() {
    replyTarget = null;
    renderReplyChip();
    renderTypingIndicator();
  }

  function renderReplyChip() {
    let chip = document.getElementById('tc-reply-chip');
    const composer = document.querySelector('.tc-composer');
    if (!replyTarget) {
      if (chip) chip.remove();
      return;
    }
    if (!chip) {
      chip = ce('div', { class: 'tc-reply-chip', id: 'tc-reply-chip' });
      const before = composer && composer.firstChild;
      if (composer) composer.insertBefore(chip, before);
    }
    chip.innerHTML = '';
    chip.appendChild(ce('span', { class: 'tc-reply-chip-label',
      text: 'Replying to ' + replyTarget.authorName }));
    chip.appendChild(ce('span', { class: 'tc-reply-chip-preview',
      text: replyTarget.preview.slice(0, 120) }));
    chip.appendChild(ce('button', {
      type: 'button',
      class: 'tc-reply-chip-close',
      'aria-label': 'Cancel reply',
      on: { click: clearReplyTarget },
    }, '×'));
  }

  function insertMention(name, uid) {
    const input = el('tc-composer-input');
    if (!input) return;
    // Use the stored `<@uuid>` form when we have a uid (matches the web's
    // wire format so renames flow through). Otherwise plain "@Name".
    const token = (uid && UUID_RE.test(uid)) ? '<@' + uid + '> ' : '@' + name + ' ';
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const v = input.value || '';
    input.value = v.slice(0, start) + token + v.slice(end);
    const caret = start + token.length;
    input.selectionStart = input.selectionEnd = caret;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  }

  // ----- Channel ops ----------------------------------------------------

  async function selectCompany(companyId) {
    if (companyId === activeCompanyId) return;
    activeCompanyId = companyId || null;
    lsSet(STORAGE_ACTIVE_COMPANY, activeCompanyId || 'private');
    renderCompanyRail();
    activeChannelId = null;
    closeWs();
    renderContentHeader();
    renderMembers();
    renderMessages();
    if (activeCompanyId) await loadChannelsForCompany(activeCompanyId);
    else await Promise.all([loadPrivateConversations(), loadTeammates()]);
    renderChannelList();
    const lastId = lsGet(STORAGE_LAST_CHANNEL_PREFIX + (activeCompanyId || 'private'));
    const channels = activeCompanyId
      ? (channelsByCompany.get(activeCompanyId) || [])
      : (allConversationsCache || []);
    let target = null;
    if (lastId && channels.some((c) => c.id === lastId)) target = lastId;
    // No remembered selection yet → drop the user into the most recent
    // conversation rather than an empty pane. `channels` is the company's
    // channel list (server order) or, in DM mode, allConversationsCache
    // which is sorted most-recent-first.
    else if (channels.length) target = channels[0].id;
    if (target) await selectChannel(target);
  }

  async function selectChannel(channelId) {
    if (!channelId || channelId === activeChannelId) return;
    // Snapshot the current draft so we can restore it on switch-back.
    if (activeChannelId) {
      const cur = el('tc-composer-input');
      if (cur && cur.value) drafts.set(activeChannelId, cur.value);
      else if (cur) drafts.delete(activeChannelId);
    }
    activeChannelId = channelId;
    clearReplyTarget();
    clearTypingUsers(); // typists are per-channel — reset on switch
    lastTypingSent = 0;
    lsSet(STORAGE_LAST_CHANNEL_PREFIX + (activeCompanyId || 'private'), channelId);
    renderChannelList();
    // On a phone the channel list is a drawer over the conversation —
    // close it on select so the user lands straight in the messages.
    if (isMobilePortrait() && mobileChannelsOpen) {
      mobileChannelsOpen = false;
      applyCollapseState();
    }
    renderContentHeader();
    el('tc-send-btn').disabled = false;
    el('tc-composer-input').disabled = false;
    // Restore any draft we have for the new channel.
    const input = el('tc-composer-input');
    if (input) {
      input.value = drafts.get(channelId) || '';
      input.style.height = 'auto';
      if (input.value) input.style.height = Math.min(input.scrollHeight, 132) + 'px';
    }
    renderMembers();
    renderMessages();
    await Promise.all([
      loadParticipants(channelId).then(() => {
        renderMembers();
        if (channelId === activeChannelId) renderMessages();
      }),
      loadMessages(channelId).then(renderMessages),
      // Best-effort thread fetch so message bodies that have replies
      // can render a "X replies — View Thread" chip without a per-row
      // round trip. Failure is silent — the chip just doesn't appear.
      loadThreads(channelId).then(() => renderMessages()),
    ]);
    window.AgixtApi.markConversationRead(channelId).catch(() => {});
    connectWs(channelId);
    startParticipantsPoll();
  }

  // Spawn a thread off a specific message. Matches the web's
  // handleStartThread in Message.tsx — we hand the parent message id
  // to the server, navigate into the new thread, and emit a
  // `thread:active` event so the channel list nests the thread row
  // under its parent.
  async function startThreadFromMessage(msg, renderedText) {
    if (!msg || !msg.id || !activeChannelId) return;
    const channels = channelsByCompany.get(activeCompanyId) || [];
    const parentCh = channels.find((c) => c.id === activeChannelId);
    if (!parentCh) return;
    // Use a snippet of the message body as the thread name fallback.
    const snippet = (renderedText || '').trim().slice(0, 60).replace(/\s+/g, ' ');
    const name = snippet
      ? 'Thread: ' + snippet
      : 'Thread from ' + new Date().toISOString();
    try {
      const result = await window.AgixtApi.createThread(activeChannelId, {
        conversation_name: name,
        company_id: activeCompanyId || '',
        parent_message_id: msg.id,
        parent_id: activeChannelId,
        conversation_type: 'thread',
      });
      const id = result && (result.id || result.conversation_id);
      if (!id) {
        toast('Thread created but no ID returned', true);
        return;
      }
      // Announce so the channel list nests the row.
      window.dispatchEvent(new CustomEvent('thread:active', {
        detail: { id, name, parentId: activeChannelId },
      }));
      // Refresh threads cache for the parent then jump into the new one.
      threadsByChannel.delete(activeChannelId);
      await loadThreads(activeChannelId);
      renderChannelList();
      await selectChannel(id);
    } catch (e) {
      toast('Failed to start thread', true);
    }
  }

  // Per-channel cache of thread rows. Hydrated on channel-switch so
  // the chip on each message ("3 replies → View Thread") can render
  // without an extra round trip per message.
  const threadsByChannel = new Map();
  async function loadThreads(channelId) {
    if (!channelId) return [];
    try {
      const list = await window.AgixtApi.getThreads(channelId);
      threadsByChannel.set(channelId, list);
      paintThreadsCount();
      return list;
    } catch (_) {
      threadsByChannel.set(channelId, []);
      paintThreadsCount();
      return [];
    }
  }

  function paintThreadsCount() {
    const badge = el('tc-threads-count');
    const btn = el('tc-threads-toggle');
    if (!badge || !btn) return;
    const n = ((activeChannelId && threadsByChannel.get(activeChannelId)) || []).length;
    if (n > 0) {
      badge.textContent = n > 99 ? '99+' : String(n);
      badge.hidden = false;
      btn.title = n === 1 ? '1 thread in this channel'
        : n + ' threads in this channel';
    } else {
      badge.hidden = true;
      btn.title = 'No threads in this channel';
    }
  }

  // Slide-down panel that lists every thread under the active channel.
  // Each row is clickable and jumps you into that thread. Tries to
  // anchor on the parent message in the channel after jumping back.
  function openThreadsPanel() {
    if (!activeChannelId) return;
    const threads = threadsByChannel.get(activeChannelId) || [];
    const existing = document.querySelector('.tc-threads-panel');
    if (existing) { existing.remove(); return; }
    const anchor = el('tc-threads-toggle');
    const rect = anchor ? anchor.getBoundingClientRect() : { left: 80, bottom: 80 };
    const pop = ce('div', { class: 'tc-threads-panel' });
    pop.appendChild(ce('div', { class: 'tc-threads-panel-head',
      text: threads.length === 1 ? '1 thread' : threads.length + ' threads' }));
    const scroll = ce('div', { class: 'tc-threads-panel-scroll' });
    if (!threads.length) {
      scroll.appendChild(ce('div', { class: 'tc-threads-panel-empty',
        text: 'No threads yet. Right-click a message to start one.' }));
    } else {
      for (const t of threads) {
        const row = ce('button', {
          type: 'button', class: 'tc-threads-panel-row',
          on: { click: () => {
            pop.remove();
            window.dispatchEvent(new CustomEvent('thread:active', {
              detail: { id: t.id, name: t.name || 'Thread',
                        parentId: t.parent_id || activeChannelId },
            }));
            selectChannel(t.id);
          }},
        });
        row.appendChild(ce('span', { class: 'tc-threads-panel-icon', html:
          '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        }));
        const meta = ce('div', { class: 'tc-threads-panel-meta' });
        meta.appendChild(ce('div', { class: 'tc-threads-panel-name',
          text: t.name || 'Thread' }));
        const count = t.message_count || t.messageCount || 0;
        const last = t.last_message_at || t.lastMessageAt;
        const subBits = [];
        if (count > 0) subBits.push(count + (count === 1 ? ' reply' : ' replies'));
        if (last) subBits.push(relativeTime(last));
        if (subBits.length) {
          meta.appendChild(ce('div', { class: 'tc-threads-panel-sub',
            text: subBits.join(' · ') }));
        }
        row.appendChild(meta);
        scroll.appendChild(row);
      }
    }
    pop.appendChild(scroll);
    document.body.appendChild(pop);
    const r = pop.getBoundingClientRect();
    const right = Math.min(window.innerWidth - 12,
      rect.right - r.width + (anchor ? 0 : 0));
    const left = Math.max(8, right - r.width);
    pop.style.top = (rect.bottom + 6) + 'px';
    pop.style.left = left + 'px';
    const close = (e) => {
      if (e && pop.contains(e.target)) return;
      if (anchor && anchor.contains(e && e.target)) return;
      pop.remove();
      document.removeEventListener('mousedown', close, true);
      document.removeEventListener('keydown', escClose);
    };
    const escClose = (e) => { if (e.key === 'Escape') close(); };
    setTimeout(() => {
      document.addEventListener('mousedown', close, true);
      document.addEventListener('keydown', escClose);
    }, 0);
  }

  function reorderChannel(draggedId, targetId, before) {
    if (!activeCompanyId || !draggedId || !targetId) return;
    const channels = (channelsByCompany.get(activeCompanyId) || []).slice();
    const srcIdx = channels.findIndex((c) => c.id === draggedId);
    if (srcIdx === -1) return;
    const [moved] = channels.splice(srcIdx, 1);
    const targetIdx = channels.findIndex((c) => c.id === targetId);
    if (targetIdx === -1) {
      channels.push(moved);
    } else {
      channels.splice(before ? targetIdx : targetIdx + 1, 0, moved);
    }
    // Drag-reorder snaps the dragged channel into the target's category
    // so users can drag between groups.
    const targetChannel = channels.find((c) => c.id === targetId);
    if (targetChannel && moved.category !== targetChannel.category) {
      moved.category = targetChannel.category || null;
      // Best-effort persist of the category change. The override on top
      // is local; this PATCH propagates the new grouping to other
      // clients via the standard channel-edit endpoint.
      window.AgixtApi.updateChannel(moved.id, { category: moved.category })
        .catch(() => {});
    }
    channelsByCompany.set(activeCompanyId, channels);
    saveChannelOrderFor(activeCompanyId, channels.map((c) => c.id));
    renderChannelList();
  }

  // ----- Create / edit channels -----------------------------------------

  function openCreateChannelDialog() {
    if (!activeCompanyId) {
      toast('Pick a company first', true);
      return;
    }
    const existingCategories = Array.from(new Set(
      (channelsByCompany.get(activeCompanyId) || []).map((c) => c.category).filter(Boolean),
    ));
    openModal({
      title: 'Create Channel',
      body: (form) => {
        form.appendChild(ce('label', { class: 'tc-form-label', text: 'Channel name' }));
        const nameInput = ce('input', {
          type: 'text', class: 'tc-form-input',
          placeholder: 'general', autocomplete: 'off',
        });
        form.appendChild(nameInput);

        form.appendChild(ce('label', { class: 'tc-form-label', text: 'Category (optional)' }));
        const catSelect = ce('select', { class: 'tc-form-input' });
        catSelect.appendChild(ce('option', { value: '' }, '— No category —'));
        for (const c of existingCategories) catSelect.appendChild(ce('option', { value: c }, c));
        catSelect.appendChild(ce('option', { value: '__new__' }, '+ New category…'));
        form.appendChild(catSelect);

        const newCatInput = ce('input', {
          type: 'text', class: 'tc-form-input',
          placeholder: 'New category name', autocomplete: 'off',
        });
        newCatInput.style.display = 'none';
        form.appendChild(newCatInput);
        catSelect.addEventListener('change', () => {
          newCatInput.style.display = catSelect.value === '__new__' ? '' : 'none';
        });

        const inviteRow = ce('label', { class: 'tc-form-check' });
        const inviteToggle = ce('input', { type: 'checkbox' });
        inviteRow.appendChild(inviteToggle);
        inviteRow.appendChild(ce('span', { text: 'Invite only' }));
        form.appendChild(inviteRow);

        setTimeout(() => nameInput.focus(), 30);
        form._readForm = () => ({
          name: (nameInput.value || '').trim().toLowerCase().replace(/\s+/g, '-'),
          category: catSelect.value === '__new__'
            ? (newCatInput.value || '').trim()
            : (catSelect.value || ''),
          inviteOnly: inviteToggle.checked,
        });
      },
      submitLabel: 'Create',
      onSubmit: async (form) => {
        const payload = form._readForm();
        if (!payload.name) {
          toast('Name required', true);
          return false;
        }
        try {
          await window.AgixtApi.createGroupConversation({
            conversation_name: payload.name,
            company_id: activeCompanyId,
            conversation_type: 'group',
            category: payload.category || undefined,
            invite_only: payload.inviteOnly || undefined,
          });
          toast('Channel created');
          await loadChannelsForCompany(activeCompanyId);
          renderChannelList();
          return true;
        } catch (e) {
          toast(e && e.message || 'Failed to create channel', true);
          return false;
        }
      },
    });
  }

  // Shared "tabbed picker dialog" used by New-DM and Invite — both show
  // People (company members) / Agents (company agents) / By ID. The
  // callbacks differ but the layout is identical, so we share one
  // helper rather than duplicating the markup.
  function openTabbedPicker(opts) {
    const {
      title, description,
      tabs, // [{key, label, icon, render(form, search)}]
      defaultTab,
    } = opts;
    let activeTab = defaultTab || (tabs[0] && tabs[0].key);
    openModal({
      title,
      body: (form) => {
        if (description) {
          form.appendChild(ce('div', { class: 'tc-modal-desc', text: description }));
        }
        const tabBar = ce('div', { class: 'tc-tabbar', role: 'tablist' });
        const panels = ce('div', { class: 'tc-tab-panels' });
        const search = ce('input', {
          type: 'search', class: 'tc-form-input',
          placeholder: 'Search…', autocomplete: 'off',
        });
        function paint() {
          for (const child of tabBar.children) {
            child.classList.toggle('is-active', child.dataset.tab === activeTab);
          }
          panels.innerHTML = '';
          const t = tabs.find((x) => x.key === activeTab);
          if (t && typeof t.render === 'function') t.render(panels, search);
        }
        tabs.forEach((t) => {
          const btn = ce('button', {
            type: 'button',
            class: 'tc-tab' + (t.key === activeTab ? ' is-active' : ''),
            dataset: { tab: t.key },
            on: { click: () => { activeTab = t.key; paint(); } },
          });
          if (t.icon) btn.appendChild(ce('span', { class: 'tc-tab-icon', html: t.icon }));
          btn.appendChild(ce('span', { class: 'tc-tab-label', text: t.label }));
          tabBar.appendChild(btn);
        });
        form.appendChild(tabBar);
        // Hide the search input when the active tab is "By ID" — that
        // tab has its own form fields and no list to filter.
        search.addEventListener('input', paint);
        form.appendChild(search);
        form.appendChild(panels);
        paint();
        // No submit button for the picker dialog — clicking a list row
        // is the submit action — so hide the modal footer.
        setTimeout(() => {
          const footer = form.querySelector('.tc-modal-footer');
          if (footer) footer.style.display = 'none';
          search.focus();
        }, 30);
        form._readForm = () => ({});
      },
      submitLabel: 'Close',
      onSubmit: () => true,
    });
  }

  async function openNewDMDialog() {
    // Humans-only picker. Agent DMs aren't surfaced in this panel —
    // they live in the side AI chat alongside every page.
    let members = allTeammates;
    if (!members.length) members = await loadTeammates();
    function fmtName(u) {
      const n = ((u.first_name || '') + ' ' + (u.last_name || '')).trim();
      return n || u.email || 'User';
    }
    openTabbedPicker({
      title: 'New Direct Message',
      description: 'Pick a person to message.',
      defaultTab: 'people',
      tabs: [
        {
          key: 'people', label: 'People',
          icon: '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/></svg>',
          render: (panel, search) => {
            const q = (search.value || '').toLowerCase().trim();
            const filtered = members.filter((m) => {
              if (currentUser && m.id === currentUser.id) return false;
              if (!q) return true;
              return (m.email || '').toLowerCase().includes(q)
                || (m.first_name || '').toLowerCase().includes(q)
                || (m.last_name || '').toLowerCase().includes(q);
            });
            if (!filtered.length) {
              panel.appendChild(ce('div', { class: 'tc-modal-empty',
                text: q ? 'No matching people' : 'No teammates yet.' }));
              return;
            }
            const list = ce('div', { class: 'tc-modal-list' });
            for (const m of filtered) {
              const name = fmtName(m);
              const companyNames = Array.isArray(m.company_names)
                ? m.company_names.filter(Boolean)
                : [];
              const row = ce('button', {
                type: 'button', class: 'tc-modal-list-row',
                on: { click: () => {
                  startUserDM(m);
                  const backdrop = document.querySelector('.tc-modal-backdrop');
                  if (backdrop) backdrop.remove();
                }},
              });
              row.appendChild(buildAvatar({
                name, email: m.email, avatarUrl: m.avatar_url, size: 32,
              }));
              const meta = ce('div', { class: 'tc-modal-list-meta' });
              meta.appendChild(ce('div', { class: 'tc-modal-list-name', text: name }));
              const sub = [m.email, companyNames.join(', ')].filter(Boolean).join(' · ');
              if (sub) meta.appendChild(ce('div', { class: 'tc-modal-list-sub', text: sub }));
              row.appendChild(meta);
              list.appendChild(row);
            }
            panel.appendChild(list);
          },
        },
      ],
    });
  }

  async function openInviteDialog() {
    if (!activeChannelId) { toast('Pick a channel first', true); return; }
    const companyId = activeCompanyId;
    let members = [];
    let agentsAll = [];
    if (companyId) {
      try { members = await window.AgixtApi.getCompanyMembers(companyId); } catch (_) {}
      const c = (companies.find((x) => x.id === companyId)) || {};
      agentsAll = c.agents || [];
    }
    const inChannel = participantsByChannel.get(activeChannelId) || [];
    const inUserIds = new Set(inChannel
      .filter((p) => p.participant_type === 'user' && p.user)
      .map((p) => p.user.id));
    const inAgentNames = new Set(inChannel
      .filter((p) => p.participant_type === 'agent' && p.agent)
      .map((p) => p.agent.name.toLowerCase()));
    const invitableMembers = members.filter((m) => !inUserIds.has(m.id));
    const invitableAgents = agentsAll.filter((a) => !inAgentNames.has(a.name.toLowerCase()));

    function fmtName(u) {
      const n = ((u.first_name || '') + ' ' + (u.last_name || '')).trim();
      return n || u.email || 'User';
    }
    async function inviteUser(userId, displayName) {
      try {
        await window.AgixtApi.addConversationParticipant(activeChannelId, {
          user_id: userId, participant_type: 'user', role: 'member',
        });
        toast('Invited ' + displayName);
        loadParticipants(activeChannelId).then(renderMembers);
      } catch (e) {
        toast('Failed to invite ' + displayName, true);
      }
    }
    async function inviteAgent(agentId, name) {
      try {
        await window.AgixtApi.addConversationParticipant(activeChannelId, {
          agent_id: agentId, participant_type: 'agent', role: 'member',
        });
        toast('Added ' + name);
        loadParticipants(activeChannelId).then(renderMembers);
      } catch (e) {
        toast('Failed to add ' + name, true);
      }
    }
    openTabbedPicker({
      title: 'Invite to Channel',
      description: 'Add people or agents to this channel.',
      defaultTab: 'people',
      tabs: [
        {
          key: 'people', label: 'People',
          icon: '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/></svg>',
          render: (panel, search) => {
            const q = (search.value || '').toLowerCase().trim();
            const filtered = invitableMembers.filter((m) => !q
              || (m.email || '').toLowerCase().includes(q)
              || (m.first_name || '').toLowerCase().includes(q)
              || (m.last_name || '').toLowerCase().includes(q));
            if (!filtered.length) {
              panel.appendChild(ce('div', { class: 'tc-modal-empty',
                text: q ? 'No matching people' : 'All teammates are already in this channel.' }));
              return;
            }
            const list = ce('div', { class: 'tc-modal-list' });
            for (const m of filtered) {
              const name = fmtName(m);
              const row = ce('button', {
                type: 'button', class: 'tc-modal-list-row',
                on: { click: () => inviteUser(m.id, name) },
              });
              row.appendChild(buildAvatar({ name, email: m.email, avatarUrl: m.avatar_url, size: 32 }));
              const meta = ce('div', { class: 'tc-modal-list-meta' });
              meta.appendChild(ce('div', { class: 'tc-modal-list-name', text: name }));
              if (m.email) meta.appendChild(ce('div', { class: 'tc-modal-list-sub', text: m.email }));
              row.appendChild(meta);
              row.appendChild(ce('span', { class: 'tc-modal-list-cta', text: 'Invite' }));
              list.appendChild(row);
            }
            panel.appendChild(list);
          },
        },
        {
          key: 'agents', label: 'Agents',
          icon: '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M12 8V4M5 12H3m18 0h-2M12 16v4M9 12a3 3 0 0 0 6 0M8 8h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2z"/></svg>',
          render: (panel, search) => {
            const q = (search.value || '').toLowerCase().trim();
            const filtered = invitableAgents.filter((a) => !q || a.name.toLowerCase().includes(q));
            if (!filtered.length) {
              panel.appendChild(ce('div', { class: 'tc-modal-empty',
                text: q ? 'No matching agents' : 'All agents are already in this channel.' }));
              return;
            }
            const list = ce('div', { class: 'tc-modal-list' });
            for (const a of filtered) {
              const row = ce('button', {
                type: 'button', class: 'tc-modal-list-row',
                on: { click: () => inviteAgent(a.id, a.name) },
              });
              row.appendChild(buildAvatar({ name: a.name, isAgent: true, size: 32 }));
              const meta = ce('div', { class: 'tc-modal-list-meta' });
              meta.appendChild(ce('div', { class: 'tc-modal-list-name', text: a.name }));
              meta.appendChild(ce('div', { class: 'tc-modal-list-sub', text: 'Agent' }));
              row.appendChild(meta);
              row.appendChild(ce('span', { class: 'tc-modal-list-cta', text: 'Add' }));
              list.appendChild(row);
            }
            panel.appendChild(list);
          },
        },
        {
          key: 'by-id', label: 'By ID',
          icon: '<svg width="13" height="13" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M19 8v6M22 11h-6M8.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/></svg>',
          render: (panel) => {
            const idLabel = ce('label', { class: 'tc-form-label', text: 'User ID or email' });
            const idInput = ce('input', { type: 'text', class: 'tc-form-input',
              placeholder: 'user@example.com or uuid', autocomplete: 'off' });
            const inviteBtn = ce('button', { type: 'button',
              class: 'tc-btn tc-btn-primary', text: 'Invite' });
            inviteBtn.addEventListener('click', async () => {
              const v = (idInput.value || '').trim();
              if (!v) return;
              inviteBtn.disabled = true;
              try {
                await window.AgixtApi.addConversationParticipant(activeChannelId, {
                  user_id: v, participant_type: 'user', role: 'member',
                });
                toast('Invited ' + v);
                loadParticipants(activeChannelId).then(renderMembers);
                idInput.value = '';
              } catch (e) {
                toast('Failed — check the ID/email', true);
              } finally {
                inviteBtn.disabled = false;
              }
            });
            panel.appendChild(idLabel);
            panel.appendChild(idInput);
            panel.appendChild(inviteBtn);
          },
        },
      ],
    });
  }

  function openCreateServerDialog() {
    openModal({
      title: 'Create a Server',
      body: (form) => {
        form.appendChild(ce('div', { class: 'tc-modal-desc',
          text: 'Give your new server a name. You can change it later.' }));
        const nameInput = ce('input', { type: 'text', class: 'tc-form-input',
          placeholder: 'Server name', autocomplete: 'off' });
        form.appendChild(nameInput);
        setTimeout(() => nameInput.focus(), 30);
        form._readForm = () => ({ name: (nameInput.value || '').trim() });
      },
      submitLabel: 'Create',
      onSubmit: async (form) => {
        const payload = form._readForm();
        if (!payload.name) { toast('Name required', true); return false; }
        try {
          const result = await window.AgixtApi.createCompany({ name: payload.name });
          toast('Server created');
          await loadCompanies();
          renderCompanyRail();
          if (result && result.id) await selectCompany(result.id);
          return true;
        } catch (e) {
          toast('Failed to create server', true);
          return false;
        }
      },
    });
  }

  function openEditChannelDialog(channel) {
    openModal({
      title: 'Edit Channel',
      body: (form) => {
        form.appendChild(ce('label', { class: 'tc-form-label', text: 'Name' }));
        const nameInput = ce('input', {
          type: 'text', class: 'tc-form-input',
          value: channel.name || '',
        });
        form.appendChild(nameInput);

        form.appendChild(ce('label', { class: 'tc-form-label', text: 'Category' }));
        const catInput = ce('input', {
          type: 'text', class: 'tc-form-input',
          value: channel.category || '',
          placeholder: 'No category',
        });
        form.appendChild(catInput);

        form.appendChild(ce('label', { class: 'tc-form-label', text: 'Description' }));
        const descInput = ce('textarea', {
          class: 'tc-form-input', rows: '3',
        });
        descInput.value = channel.description || '';
        form.appendChild(descInput);

        setTimeout(() => nameInput.focus(), 30);
        form._readForm = () => ({
          name: (nameInput.value || '').trim(),
          category: (catInput.value || '').trim() || null,
          description: (descInput.value || '').trim() || null,
        });
      },
      submitLabel: 'Save',
      onSubmit: async (form) => {
        const payload = form._readForm();
        try {
          await window.AgixtApi.updateChannel(channel.id, payload);
          toast('Channel updated');
          await loadChannelsForCompany(activeCompanyId);
          renderChannelList();
          return true;
        } catch (e) {
          toast(e && e.message || 'Failed to update channel', true);
          return false;
        }
      },
    });
  }

  // ----- Modal helper ---------------------------------------------------

  function openModal({ title, body, submitLabel, onSubmit }) {
    const backdrop = ce('div', { class: 'tc-modal-backdrop' });
    const close = () => {
      backdrop.remove();
      document.removeEventListener('keydown', escHandler);
    };
    const escHandler = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', escHandler);
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });

    const modal = ce('div', { class: 'tc-modal' });
    modal.appendChild(ce('header', { class: 'tc-modal-header' }, title || ''));
    const form = ce('form', { class: 'tc-modal-body' });
    if (typeof body === 'function') body(form);
    const footer = ce('footer', { class: 'tc-modal-footer' });
    const cancelBtn = ce('button', {
      type: 'button', class: 'tc-btn tc-btn-secondary',
      on: { click: close },
    }, 'Cancel');
    footer.appendChild(cancelBtn);
    const submitBtn = ce('button', {
      type: 'submit', class: 'tc-btn tc-btn-primary',
    }, submitLabel || 'Save');
    footer.appendChild(submitBtn);
    form.appendChild(footer);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submitBtn.disabled = true;
      try {
        const ok = await onSubmit(form);
        if (ok !== false) close();
      } finally {
        submitBtn.disabled = false;
      }
    });
    modal.appendChild(form);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
  }

  // ----- WebSocket ------------------------------------------------------

  function closeWs() {
    if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    if (activeWs) {
      try { activeWs.close(); } catch (_) {}
      activeWs = null;
    }
    activeWsChannelId = null;
    wsBackoffMs = 1000;
  }

  function connectWs(channelId) {
    if (!channelId) return;
    if (activeWsChannelId === channelId && activeWs && activeWs.readyState === WebSocket.OPEN) return;
    closeWs();
    Promise.resolve(window.AgixtApi.getSettings()).then((settings) => {
      if (activeChannelId !== channelId) return;
      const base = (settings.server_url || '').replace(/\/+$/, '');
      if (!base || !settings.jwt) return;
      const wsBase = base.replace(/^http/, 'ws');
      const url = `${wsBase}/v1/conversation/${encodeURIComponent(channelId)}/stream?authorization=${encodeURIComponent(settings.jwt)}&limit=200`;
      let ws;
      try { ws = new WebSocket(url); } catch (e) { return; }
      activeWs = ws;
      activeWsChannelId = channelId;
      ws.onmessage = (ev) => {
        let envelope;
        try { envelope = JSON.parse(ev.data); }
        catch (_) { return; }
        if (!envelope || !envelope.type) return;
        const data = envelope.data;
        switch (envelope.type) {
          case 'typing_indicator':
            if (activeChannelId === channelId) noteTypingUser(data);
            break;
          case 'initial_data':
            if (Array.isArray(data)) {
              const merged = mergeMessageList(messageCache.get(channelId) || [], data);
              messageCache.set(channelId, merged);
              // Reconnect re-sends the whole backlog — reconcile instead
              // of blowing the list away so an idle channel doesn't
              // visibly "reload" every time the socket flaps.
              if (activeChannelId === channelId) reconcileMessages();
            }
            break;
          case 'initial_message':
          case 'message_added':
            if (data && data.id && activeChannelId === channelId) {
              const arr = messageCache.get(channelId) || [];
              const idx = arr.findIndex((m) => m.id === data.id);
              const merged = mergeMessageRecord(idx >= 0 ? arr[idx] : null, data);
              if (idx >= 0) {
                arr[idx] = merged;
                messageCache.set(channelId, arr);
                // Already known (e.g. our own echo / a re-send): update
                // just that node in place rather than rebuilding.
                if (!replaceMessageNode(merged)) reconcileMessages();
              } else if (!consumeOptimistic(merged, channelId)) {
                // Not one of our optimistic placeholders — normal append.
                arr.push(merged);
                messageCache.set(channelId, arr);
                appendMessage(merged, true);
              }
            }
            break;
          case 'message_updated':
            if (data && data.id && activeChannelId === channelId) {
              const arr = messageCache.get(channelId) || [];
              const idx = arr.findIndex((m) => m.id === data.id);
              if (idx >= 0) {
                const merged = mergeMessageRecord(arr[idx], data);
                arr[idx] = merged;
                messageCache.set(channelId, arr);
                // Edits / reaction changes touch one message — swap that
                // single node, keep everything else (and scroll) put.
                if (!replaceMessageNode(merged)) reconcileMessages();
              }
            }
            break;
          case 'messages_deleted':
            if (activeChannelId === channelId) {
              const deletedIds = data && Array.isArray(data.deleted_message_ids)
                ? data.deleted_message_ids
                : null;
              if (deletedIds && deletedIds.length) {
                const arr = messageCache.get(channelId) || [];
                messageCache.set(
                  channelId,
                  arr.filter((m) => !deletedIds.includes(m.id)),
                );
                removeMessageNodes(deletedIds);
              } else {
                messageCache.set(channelId, []);
                renderMessages();
              }
            }
            break;
        }
      };
      ws.onclose = () => {
        if (activeChannelId !== channelId) return;
        wsBackoffMs = Math.min(wsBackoffMs * 2, 30000);
        wsReconnectTimer = setTimeout(() => connectWs(channelId), wsBackoffMs);
      };
    }).catch(() => {});
  }

  // A compact fingerprint of the participant set so the poll can tell
  // whether anything actually changed. Message nodes resolve sender
  // names/avatars from this list, so we only need to re-render messages
  // when membership genuinely shifts — NOT every 30s on a timer (that
  // unconditional rebuild was the periodic "whole list reloads" jump).
  function participantsSignature(cid) {
    const list = participantsByChannel.get(cid) || [];
    return list
      .map((p) => (p && (p.user_id || p.id || p.email || '')) + ':'
        + ((p && (p.first_name || p.display_name || '')) || '')
        + ':' + ((p && p.avatar_url) || ''))
      .sort()
      .join('|');
  }

  function startParticipantsPoll() {
    if (participantsPollTimer) clearInterval(participantsPollTimer);
    participantsPollTimer = setInterval(() => {
      const cid = activeChannelId;
      if (!cid) return;
      const before = participantsSignature(cid);
      loadParticipants(cid).then(() => {
        if (cid !== activeChannelId) return;
        renderMembers();
        // Only rebuild the message list if sender metadata actually
        // changed (a join/leave or a late-resolving profile name) — that
        // genuinely needs existing nodes re-rendered. On the common case
        // of "nothing changed" we leave the DOM and scroll fully alone.
        if (participantsSignature(cid) !== before) renderMessages();
      });
    }, 30000);
  }

  // ----- Composer (send, attachments, emoji, gif) -----------------------

  async function sendMessage() {
    const input = el('tc-composer-input');
    const sendBtn = el('tc-send-btn');
    if (!input || !activeChannelId) return;
    let text = (input.value || '').trim();
    if (!text && !pendingAttachments.length) return;

    // Inline attachments as markdown image / link blocks (matches what
    // the web does for non-image attachments). The channel-message
    // endpoint extracts data: URLs to workspace files server-side.
    if (pendingAttachments.length) {
      const blocks = pendingAttachments.map((att) => {
        const isImage = att.dataUrl.startsWith('data:image/')
          || /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(att.filename);
        return isImage
          ? `![${att.filename}](${att.dataUrl})`
          : `[${att.filename}](${att.dataUrl})`;
      });
      text = text ? text + '\n\n' + blocks.join('\n') : blocks.join('\n');
    }

    // Build the reply header (matches the web's wire format) if we have
    // a reply target staged.
    let toSend = text;
    if (replyTarget) {
      const headerBits = ['> **' + replyTarget.authorName + '** said:'];
      if (replyTarget.messageId) headerBits.push('[ref:' + replyTarget.messageId + ']');
      if (replyTarget.authorUserId) headerBits.push('[uid:' + replyTarget.authorUserId + ']');
      const header = headerBits.join(' ');
      const quote = (replyTarget.preview || '').split('\n').map((l) => '> ' + l).join('\n');
      toSend = header + '\n' + quote + '\n\n' + text;
    }

    const sendChannelId = activeChannelId;
    const hadAttachments = pendingAttachments.length > 0;
    input.value = '';
    drafts.delete(activeChannelId); // sent ⇒ clear draft
    input.style.height = 'auto';
    sendBtn.disabled = true;
    // Web parity: surface "sending" via the textarea placeholder rather
    // than a status line under the bar. The placeholder lives inside the
    // input box, so toggling it can't shift the composer or the message
    // list. The optimistic message (above) is the real feedback anyway.
    const prevPlaceholder = input.placeholder;
    input.placeholder = 'Sending…';
    pendingAttachments = [];
    renderAttachments();
    clearReplyTarget();
    // Paint the message immediately; the WebSocket echo will swap this
    // placeholder for the server's record (see consumeOptimistic).
    const optimisticId = addOptimisticMessage(sendChannelId, toSend, hadAttachments);
    try {
      const channels = activeCompanyId
        ? (channelsByCompany.get(activeCompanyId) || [])
        : (allConversationsCache || []);
      const ch = channels.find((c) => c.id === activeChannelId);
      const convName = (ch && (ch.name || ch.display_name || ch.displayName)) || activeChannelId;
      if (window.AgixtApi.postConversationMessage) {
        await window.AgixtApi.postConversationMessage(activeChannelId, toSend, 'USER');
      } else {
        await window.AgixtApi.postChannelMessage(convName, toSend, 'USER');
      }
    } catch (e) {
      // Send failed — pull the placeholder back out so we don't leave a
      // ghost message the server never accepted, and surface it via a
      // toast (web does the same; no status strip to shift the layout).
      dropOptimistic(optimisticId);
      toast((e && e.message) || 'Failed to send message', true);
      input.value = text;
    } finally {
      input.placeholder = prevPlaceholder;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // ----- Live markdown overlay (composer) -------------------------------
  // Visual preview of bold / italic / code / spoiler / strikethrough /
  // mention markers as the user types — same vocabulary Discord and
  // the web's FormattedInputOverlay use. The overlay is a transparent
  // <div> stacked behind the textarea; its children carry the actual
  // colors and font-weight so the text reads as if it were styled.
  function paintComposerOverlay() {
    const input = el('tc-composer-input');
    const overlay = el('tc-composer-overlay');
    if (!input || !overlay) return;
    const text = input.value || '';
    overlay.innerHTML = '';
    if (!text) return;
    // Segment the input string into a sequence of {kind, body} chunks,
    // walking character-by-character so we respect code-block fences.
    let i = 0;
    const len = text.length;
    function chunk(kind, raw) {
      overlay.appendChild(ce('span', { class: 'tc-cm-' + kind, text: raw }));
    }
    function findClose(start, close, limit) {
      const idx = text.indexOf(close, start);
      if (idx === -1) return -1;
      if (limit !== undefined && idx > limit) return -1;
      return idx;
    }
    while (i < len) {
      const c = text[i];
      // ``` fenced block — opens until matching ```.
      if (text.startsWith('```', i)) {
        const close = text.indexOf('```', i + 3);
        if (close !== -1) {
          chunk('code', text.slice(i, close + 3));
          i = close + 3;
        } else {
          chunk('code-open', text.slice(i));
          i = len;
        }
        continue;
      }
      // <@uuid> mention.
      if (c === '<' && text[i + 1] === '@') {
        const close = text.indexOf('>', i + 2);
        if (close !== -1) {
          chunk('mention', text.slice(i, close + 1));
          i = close + 1;
          continue;
        }
      }
      // @name mention (word-ish chars).
      if (c === '@' && /[A-Za-z0-9_]/.test(text[i + 1] || '')) {
        let j = i + 1;
        while (j < len && /[A-Za-z0-9_-]/.test(text[j])) j++;
        chunk('mention', text.slice(i, j));
        i = j;
        continue;
      }
      // Inline code.
      if (c === '`') {
        const eol = text.indexOf('\n', i + 1);
        const limit = eol === -1 ? len : eol;
        const close = findClose(i + 1, '`', limit);
        if (close !== -1) {
          chunk('code', text.slice(i, close + 1));
          i = close + 1;
        } else {
          chunk('code-open', text.slice(i, limit));
          i = limit;
        }
        continue;
      }
      // Bold (`**`) — must check before italic.
      if (text.startsWith('**', i)) {
        const close = text.indexOf('**', i + 2);
        if (close !== -1) {
          chunk('bold', text.slice(i, close + 2));
          i = close + 2;
        } else {
          chunk('bold-open', text.slice(i));
          i = len;
        }
        continue;
      }
      // Underline (`__`).
      if (text.startsWith('__', i)) {
        const close = text.indexOf('__', i + 2);
        if (close !== -1) {
          chunk('underline', text.slice(i, close + 2));
          i = close + 2;
        } else {
          chunk('underline-open', text.slice(i));
          i = len;
        }
        continue;
      }
      // Strikethrough (`~~`).
      if (text.startsWith('~~', i)) {
        const close = text.indexOf('~~', i + 2);
        if (close !== -1) {
          chunk('strike', text.slice(i, close + 2));
          i = close + 2;
        } else {
          chunk('strike-open', text.slice(i));
          i = len;
        }
        continue;
      }
      // Spoiler (`||`).
      if (text.startsWith('||', i)) {
        const close = text.indexOf('||', i + 2);
        if (close !== -1) {
          chunk('spoiler', text.slice(i, close + 2));
          i = close + 2;
        } else {
          chunk('spoiler-open', text.slice(i));
          i = len;
        }
        continue;
      }
      // Italic (single `*`).
      if (c === '*' && text[i + 1] !== '*') {
        const close = (() => {
          let j = i + 1;
          while (j < len) {
            if (text[j] === '*' && text[j + 1] !== '*') return j;
            if (text[j] === '\n') return -1;
            j++;
          }
          return -1;
        })();
        if (close !== -1) {
          chunk('italic', text.slice(i, close + 1));
          i = close + 1;
        } else {
          chunk('italic-open', text.slice(i, text.indexOf('\n', i) === -1 ? len : text.indexOf('\n', i)));
          i = text.indexOf('\n', i) === -1 ? len : text.indexOf('\n', i);
        }
        continue;
      }
      // Plain text — coalesce until the next special character.
      let j = i + 1;
      while (j < len) {
        const ch = text[j];
        if (ch === '*' || ch === '`' || ch === '~' || ch === '_'
            || ch === '|' || ch === '<' || ch === '@') break;
        j++;
      }
      chunk('plain', text.slice(i, j));
      i = j;
    }
  }

  // ----- Attachments ----------------------------------------------------

  function renderAttachments() {
    const wrap = el('tc-attachments');
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!pendingAttachments.length) { wrap.hidden = true; return; }
    wrap.hidden = false;
    pendingAttachments.forEach((att, idx) => {
      const chip = ce('div', { class: 'tc-attach-chip', title: att.filename });
      if (att.dataUrl.startsWith('data:image/')) {
        chip.appendChild(ce('img', { src: att.dataUrl, alt: '', class: 'tc-attach-thumb' }));
      } else {
        chip.appendChild(ce('span', { class: 'tc-attach-icon', text: '📎' }));
      }
      chip.appendChild(ce('span', { class: 'tc-attach-name', text: att.filename }));
      chip.appendChild(ce('button', {
        type: 'button',
        class: 'tc-attach-remove',
        'aria-label': 'Remove attachment',
        on: { click: () => {
          pendingAttachments.splice(idx, 1);
          renderAttachments();
        }},
      }, '×'));
      wrap.appendChild(chip);
    });
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onerror = () => reject(r.error || new Error('read failed'));
      r.onload = () => resolve(r.result);
      r.readAsDataURL(file);
    });
  }

  async function acceptFiles(files) {
    if (!files || !files.length) return;
    for (const file of files) {
      // Cap any single file at 20 MB — base64 inflates 33% so a much
      // larger file would balloon past the channel-message endpoint's
      // payload limits.
      if (file.size > 20 * 1024 * 1024) {
        toast('File too large (max 20 MB): ' + file.name, true);
        continue;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        pendingAttachments.push({ filename: file.name, dataUrl });
      } catch (e) {
        toast('Failed to read ' + file.name, true);
      }
    }
    renderAttachments();
  }

  function bindFileInputs() {
    // Hidden <input type=file> backing the paperclip button.
    const pick = el('tc-attach-input');
    const attachBtn = el('tc-attach-btn');
    if (pick && attachBtn) {
      attachBtn.addEventListener('click', () => pick.click());
      pick.addEventListener('change', () => {
        acceptFiles(Array.from(pick.files || []));
        pick.value = '';
      });
    }

    // Drag + drop onto the message scroller.
    const scroller = el('tc-messages-scroll');
    if (scroller) {
      ['dragenter', 'dragover'].forEach((evt) =>
        scroller.addEventListener(evt, (e) => {
          if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
            e.preventDefault();
            e.stopPropagation();
            scroller.classList.add('tc-dropzone-active');
          }
        }));
      ['dragleave', 'dragend'].forEach((evt) =>
        scroller.addEventListener(evt, () => scroller.classList.remove('tc-dropzone-active')));
      scroller.addEventListener('drop', (e) => {
        scroller.classList.remove('tc-dropzone-active');
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
          e.preventDefault();
          acceptFiles(Array.from(e.dataTransfer.files));
        }
      });
    }

    // Clipboard paste — image content in the clipboard becomes an
    // attachment (matches chat-input.tsx:handlePaste).
    const input = el('tc-composer-input');
    if (input) {
      input.addEventListener('paste', (e) => {
        const items = (e.clipboardData && e.clipboardData.items) || [];
        const files = [];
        for (const it of items) {
          if (it.kind === 'file') {
            const f = it.getAsFile();
            if (f) files.push(f);
          }
        }
        if (files.length) {
          e.preventDefault();
          acceptFiles(files);
        }
      });
    }
  }

  // ----- Emoji autocomplete --------------------------------------------

  // Generic composer autocomplete state, shared by `:` (emoji), `@`
  // (member mention), and `#` (channel jump). Each triggers builds its
  // own item list but they share rendering + keyboard handling so the
  // visual stays consistent.
  let composerAC = null;

  function ensureComposerAC() {
    if (composerAC) return composerAC;
    const popover = ce('div', { class: 'tc-emoji-popover', role: 'listbox' });
    popover.hidden = true;
    const composer = document.querySelector('.tc-composer');
    if (composer) composer.appendChild(popover);
    composerAC = { popover, items: [], index: 0, kind: null };
    return composerAC;
  }

  function paintComposerAC() {
    const ac = ensureComposerAC();
    if (!ac.items.length) { ac.popover.hidden = true; return; }
    ac.popover.innerHTML = '';
    ac.items.forEach((it, i) => {
      const row = ce('button', {
        type: 'button',
        class: 'tc-emoji-row' + (i === ac.index ? ' is-active' : ''),
        on: { click: () => applyComposerACPick(i) },
      });
      row.appendChild(ce('span', { class: 'tc-emoji-glyph', text: it.glyph }));
      row.appendChild(ce('span', { class: 'tc-emoji-code', text: it.label }));
      ac.popover.appendChild(row);
    });
    ac.popover.hidden = false;
  }

  function updateComposerAC() {
    const ac = ensureComposerAC();
    const input = el('tc-composer-input');
    if (!input || !window.AgixtTeamChatHelpers) return;
    const v = input.value || '';
    const caret = input.selectionStart || 0;
    const before = v.slice(0, caret);

    // `:shortcode` — emoji autocomplete.
    let m = before.match(/(^|[\s])(:[a-zA-Z0-9_+-]{2,})$/);
    if (m) {
      const query = m[2].slice(1).toLowerCase();
      const all = window.AgixtTeamChatHelpers.EMOJI_SHORTCODES;
      const items = [];
      for (const code in all) {
        if (code.startsWith(query) || code.includes(query)) {
          items.push({ glyph: all[code], label: ':' + code + ':',
            insert: all[code], token: m[2], kind: 'emoji' });
          if (items.length >= 8) break;
        }
      }
      ac.kind = 'emoji'; ac.items = items; ac.index = 0;
      paintComposerAC();
      return;
    }

    // `@query` — member mention autocomplete.
    m = before.match(/(^|[\s])(@[a-zA-Z0-9_-]{1,})$/);
    if (m) {
      const q = m[2].slice(1).toLowerCase();
      const list = (participantsByChannel.get(activeChannelId) || []);
      const items = [];
      for (const p of list) {
        const name = nameForParticipant(p);
        const isAgent = p.participant_type === 'agent';
        const uid = isAgent ? (p.agent && p.agent.id) : (p.user && p.user.id);
        if (!name.toLowerCase().includes(q)) continue;
        items.push({
          glyph: isAgent ? '\u{1F916}' : '@',
          label: name + (isAgent ? ' · agent' : ''),
          insert: (uid && UUID_RE.test(uid)) ? '<@' + uid + '> ' : '@' + name + ' ',
          token: m[2],
          kind: 'mention',
        });
        if (items.length >= 8) break;
      }
      ac.kind = 'mention'; ac.items = items; ac.index = 0;
      paintComposerAC();
      return;
    }

    // `#query` — channel jump autocomplete.
    m = before.match(/(^|[\s])(#[a-zA-Z0-9_-]{1,})$/);
    if (m && activeCompanyId) {
      const q = m[2].slice(1).toLowerCase();
      const channels = channelsByCompany.get(activeCompanyId) || [];
      const items = [];
      for (const ch of channels) {
        const name = (ch.display_name || ch.displayName || ch.name || '').toLowerCase();
        if (!name.includes(q)) continue;
        items.push({
          glyph: '#',
          label: ch.display_name || ch.displayName || ch.name || 'channel',
          insert: '#' + (ch.display_name || ch.displayName || ch.name) + ' ',
          token: m[2],
          kind: 'channel',
          channelId: ch.id,
        });
        if (items.length >= 8) break;
      }
      ac.kind = 'channel'; ac.items = items; ac.index = 0;
      paintComposerAC();
      return;
    }

    ac.items = []; ac.popover.hidden = true; ac.kind = null;
  }

  function applyComposerACPick(i) {
    const ac = composerAC;
    if (!ac || !ac.items[i]) return;
    const input = el('tc-composer-input');
    if (!input) return;
    const it = ac.items[i];
    // # picks are a navigation shortcut, not an insertion — the web
    // treats # as a channel jump-to (Discord's behavior). Strip the
    // partial `#foo` and navigate.
    if (it.kind === 'channel') {
      const v = input.value || '';
      const caret = input.selectionStart || 0;
      const before = v.slice(0, caret);
      if (before.endsWith(it.token)) {
        const replaceStart = caret - it.token.length;
        input.value = v.slice(0, replaceStart) + v.slice(caret);
      }
      ac.popover.hidden = true;
      ac.items = [];
      selectChannel(it.channelId);
      return;
    }
    const v = input.value || '';
    const caret = input.selectionStart || 0;
    const before = v.slice(0, caret);
    if (!before.endsWith(it.token)) return;
    const replaceStart = caret - it.token.length;
    input.value = v.slice(0, replaceStart) + it.insert + v.slice(caret);
    const newCaret = replaceStart + it.insert.length;
    input.selectionStart = input.selectionEnd = newCaret;
    ac.popover.hidden = true;
    ac.items = [];
    input.focus();
  }

  function handleComposerACKey(e) {
    const ac = composerAC;
    if (!ac || ac.popover.hidden || !ac.items.length) return false;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      ac.index = (ac.index + 1) % ac.items.length;
      paintComposerAC();
      return true;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      ac.index = (ac.index - 1 + ac.items.length) % ac.items.length;
      paintComposerAC();
      return true;
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      applyComposerACPick(ac.index);
      return true;
    }
    if (e.key === 'Escape') {
      ac.popover.hidden = true;
      ac.items = [];
      return true;
    }
    return false;
  }
  // Compat aliases — keep the old emoji-autocomplete-specific names
  // pointing at the unified helpers so callers don't break.
  const updateEmojiAutocomplete = updateComposerAC;
  const handleEmojiAutocompleteKey = handleComposerACKey;

  // ----- Composer helpers: emoji insert + voice recording ---------------

  function insertEmojiAtCursor(emoji) {
    const input = el('tc-composer-input');
    if (!input || !emoji) return;
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const v = input.value || '';
    input.value = v.slice(0, start) + emoji + v.slice(end);
    const caret = start + emoji.length;
    input.selectionStart = input.selectionEnd = caret;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  }

  // Tiny voice-recording state machine, separate from the agent-chat
  // one in app.js but using the same Tauri backend (voice_start_recording
  // → voice_stop_recording → /v1/audio/transcriptions). Transcript
  // lands in the team-chat composer; the user reviews it and chooses
  // when to send. Esc cancels in-progress recording.
  const micState = {
    state: 'idle',           // 'idle' | 'recording' | 'busy'
    native: false,
    cancelled: false,
    recorder: null,
    stream: null,
    chunks: [],
  };

  function setMicState(state) {
    micState.state = state;
    const btn = el('tc-mic-btn');
    if (btn) btn.dataset.state = state;
  }
  function setComposerNotice(text, isError) {
    const status = el('tc-composer-status');
    if (!status) return;
    status.textContent = text || '';
    status.classList.toggle('is-error', !!isError);
  }
  function pickRecorderMime() {
    const candidates = [
      'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus',
      'audio/ogg', 'audio/mp4', 'audio/mpeg',
    ];
    for (const m of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported
          && MediaRecorder.isTypeSupported(m)) return m;
    }
    return '';
  }
  function audioExtension(mime) {
    if (!mime) return 'webm';
    if (mime.includes('webm')) return 'webm';
    if (mime.includes('ogg')) return 'ogg';
    if (mime.includes('mp4')) return 'm4a';
    if (mime.includes('mpeg')) return 'mp3';
    return 'webm';
  }
  function blobFromBase64(b64, mime) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime || 'audio/webm' });
  }

  async function startMicRecording() {
    if (micState.state !== 'idle') return;
    const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    // Prefer the native recorder via Tauri (matches the agent chat's
    // approach — better mic device handling than the browser API in
    // a webview). Fall back to MediaRecorder if native isn't available.
    if (inv) {
      try {
        const info = await inv('voice_start_recording');
        micState.native = true;
        micState.cancelled = false;
        setMicState('recording');
        const label = info && info.device_name ? ' (' + info.device_name + ')' : '';
        setComposerNotice('Listening' + label + ' — tap mic to send, Esc to cancel');
        return;
      } catch (_) {
        micState.native = false;
      }
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setComposerNotice('Microphone unavailable in this webview', true);
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setComposerNotice('Microphone permission denied', true);
      return;
    }
    const mime = pickRecorderMime();
    const recorder = mime ? new MediaRecorder(stream, { mimeType: mime })
      : new MediaRecorder(stream);
    micState.stream = stream;
    micState.recorder = recorder;
    micState.chunks = [];
    micState.native = false;
    micState.cancelled = false;
    recorder.addEventListener('dataavailable', (e) => {
      if (e.data && e.data.size > 0) micState.chunks.push(e.data);
    });
    recorder.addEventListener('stop', handleWebRecorderStopped);
    recorder.start(250);
    setMicState('recording');
    setComposerNotice('Listening — tap mic to send, Esc to cancel');
  }

  async function stopMicRecording() {
    if (micState.state !== 'recording') return;
    setMicState('busy');
    setComposerNotice('Transcribing…');
    if (micState.native) {
      const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
      try {
        const result = await inv('voice_stop_recording');
        micState.native = false;
        const blob = blobFromBase64(result.audio_base64, result.mime_type);
        await transcribeBlob(blob, result.mime_type);
      } catch (e) {
        setMicState('idle');
        setComposerNotice('Recording stop failed', true);
      }
      return;
    }
    const r = micState.recorder;
    if (!r) { setMicState('idle'); return; }
    try {
      if (r.state !== 'inactive') {
        if (typeof r.requestData === 'function') {
          try { r.requestData(); } catch (_) {}
        }
        r.stop();
      }
    } catch (_) { setMicState('idle'); }
  }

  async function cancelMicRecording() {
    if (micState.state !== 'recording') return;
    micState.cancelled = true;
    const inv = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    if (micState.native) {
      try { if (inv) await inv('voice_cancel_recording'); } catch (_) {}
      micState.native = false;
      setMicState('idle');
      setComposerNotice('');
      return;
    }
    const r = micState.recorder;
    try { if (r && r.state !== 'inactive') r.stop(); } catch (_) {}
    teardownMicStream();
    micState.recorder = null;
    micState.chunks = [];
    setMicState('idle');
    setComposerNotice('');
  }

  function teardownMicStream() {
    if (micState.stream) {
      micState.stream.getTracks().forEach((t) => t.stop());
      micState.stream = null;
    }
  }

  async function handleWebRecorderStopped() {
    const chunks = micState.chunks || [];
    const cancelled = micState.cancelled;
    teardownMicStream();
    micState.recorder = null;
    micState.chunks = [];
    if (cancelled) { setMicState('idle'); setComposerNotice(''); return; }
    if (!chunks.length) {
      setMicState('idle');
      setComposerNotice('No audio captured', true);
      return;
    }
    const mime = chunks[0].type || 'audio/webm';
    const blob = new Blob(chunks, { type: mime });
    await transcribeBlob(blob, mime);
  }

  async function transcribeBlob(blob, mime) {
    if (!blob || !blob.size) {
      setMicState('idle');
      setComposerNotice('No audio captured', true);
      return;
    }
    let settings = null;
    try { settings = await window.AgixtApi.getSettings(); } catch (_) {}
    if (!settings || !settings.server_url || !settings.jwt) {
      setMicState('idle');
      setComposerNotice('Not signed in', true);
      return;
    }
    try {
      const fd = new FormData();
      fd.append('file', blob, 'recording.' + audioExtension(mime));
      // AGiXT routes the transcription to the active agent via `model`,
      // same convention chat completions uses.
      fd.append('model', settings.agent_name || 'XT');
      const url = settings.server_url.replace(/\/+$/, '') + '/v1/audio/transcriptions';
      const fetcher = window.AgixtSession && typeof window.AgixtSession.fetch === 'function'
        ? window.AgixtSession.fetch(url, {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + settings.jwt },
          body: fd,
        })
        : fetch(url, {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + settings.jwt },
          body: fd,
        });
      const resp = await fetcher;
      if (!resp.ok) {
        const body = await resp.text().catch(() => '');
        throw new Error('HTTP ' + resp.status + (body ? ': ' + body.slice(0, 160) : ''));
      }
      const data = await resp.json().catch(() => ({}));
      const transcript = ((data && (data.text || data.transcript)) || '').trim();
      if (!transcript) {
        setMicState('idle');
        setComposerNotice("Couldn't hear anything", true);
        return;
      }
      // Drop the transcript into the composer at the caret and let
      // the user review before sending. Matches Discord — voice goes
      // to text, you send when ready.
      insertEmojiAtCursor(transcript);
      setMicState('idle');
      setComposerNotice('Transcribed.');
      setTimeout(() => {
        if (micState.state === 'idle') setComposerNotice('');
      }, 1500);
    } catch (err) {
      setMicState('idle');
      setComposerNotice('Transcription failed: ' + (err && err.message || err), true);
    }
  }

  // ----- GIF picker (Tenor v2 public anon key) --------------------------
  // The web has its own /api/gif proxy with a server-side key; the
  // desktop hits Tenor directly using the public anon key the web's
  // /api/gif route falls back to when TENOR_API_KEY isn't set. We
  // route through the og_fetch IPC so a future host that blocks the
  // webview's UA still works through the Rust HTTP path.
  const TENOR_KEY = 'AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ'; // canonical Google public Tenor key
  let gifPopover = null;
  let gifSearchTimer = null;

  function ensureGifPopover() {
    if (gifPopover) return gifPopover;
    gifPopover = ce('div', { class: 'tc-gif-popover' });
    gifPopover.hidden = true;
    const composer = document.querySelector('.tc-composer');
    if (composer) composer.appendChild(gifPopover);
    return gifPopover;
  }

  function openGifPicker() {
    const pop = ensureGifPopover();
    if (!pop.hidden) { pop.hidden = true; return; }
    pop.innerHTML = '';
    pop.hidden = false;
    const search = ce('input', {
      type: 'search',
      placeholder: 'Search GIFs',
      class: 'tc-gif-search',
      autocomplete: 'off',
    });
    pop.appendChild(search);
    const grid = ce('div', { class: 'tc-gif-grid' });
    pop.appendChild(grid);
    grid.appendChild(ce('div', { class: 'tc-gif-status', text: 'Loading…' }));
    setTimeout(() => search.focus(), 30);

    async function load(query) {
      grid.innerHTML = '';
      grid.appendChild(ce('div', { class: 'tc-gif-status', text: 'Loading…' }));
      // contentfilter=medium matches the web's /api/gif proxy (the
      // older `high` value occasionally returned zero results for
      // benign queries — Tenor recommends medium for chat UIs).
      const url = query
        ? `https://tenor.googleapis.com/v2/search?key=${TENOR_KEY}&q=${encodeURIComponent(query)}&limit=20&media_filter=gif,tinygif&contentfilter=medium`
        : `https://tenor.googleapis.com/v2/featured?key=${TENOR_KEY}&limit=20&media_filter=gif,tinygif&contentfilter=medium`;
      // Route through the Rust IPC the same way OG previews do — Tenor
      // is CORS-friendly today, but going through reqwest gives us a
      // consistent error surface and lets us add headers / retries
      // without touching every call site.
      const resp = await ogFetch({ url, accept: 'application/json' });
      grid.innerHTML = '';
      if (!resp || !resp.ok || !resp.body) {
        grid.appendChild(ce('div', { class: 'tc-gif-status',
          text: 'GIF service unreachable' }));
        return;
      }
      let data;
      try { data = JSON.parse(resp.body); } catch (_) { data = null; }
      if (data && data.error) {
        // Tenor surfaces "API key not valid" as a 400 with a JSON
        // error body — show that verbatim instead of the generic
        // "Tenor unavailable" so the user knows what to fix.
        grid.appendChild(ce('div', { class: 'tc-gif-status',
          text: 'GIF service error: ' + (data.error.message || data.error.status || 'unknown') }));
        return;
      }
      const results = (data && data.results) || [];
      if (!results.length) {
        grid.appendChild(ce('div', { class: 'tc-gif-status', text: 'No results' }));
        return;
      }
      for (const g of results) {
        const media = g.media_formats || {};
        const thumb = (media.tinygif && media.tinygif.url) || (media.gif && media.gif.url);
        const full = (media.gif && media.gif.url) || thumb;
        if (!thumb || !full) continue;
        const btn = ce('button', {
          type: 'button',
          class: 'tc-gif-cell',
          on: { click: () => {
            const input = el('tc-composer-input');
            if (input) {
              input.value = (input.value ? input.value + ' ' : '') + full;
              input.focus();
            }
            pop.hidden = true;
          }},
        });
        const img = ce('img', { src: thumb, alt: g.content_description || '', loading: 'lazy' });
        img.referrerPolicy = 'no-referrer';
        btn.appendChild(img);
        grid.appendChild(btn);
      }
    }
    search.addEventListener('input', () => {
      clearTimeout(gifSearchTimer);
      gifSearchTimer = setTimeout(() => load(search.value.trim()), 300);
    });
    load('');
    // Click outside closes.
    setTimeout(() => {
      const handler = (e) => {
        if (!pop.contains(e.target) && e.target.id !== 'tc-gif-btn') {
          pop.hidden = true;
          document.removeEventListener('mousedown', handler, true);
        }
      };
      document.addEventListener('mousedown', handler, true);
    }, 50);
  }

  // ----- DMs to specific people / agents --------------------------------

  async function startUserDM(user) {
    if (!user || !user.id) return;
    const name = (user.first_name || user.last_name)
      ? ((user.first_name || '') + ' ' + (user.last_name || '')).trim()
      : (user.email || 'User');
    const companyId = (Array.isArray(user.company_ids) && user.company_ids[0])
      || activeCompanyId
      || '';
    try {
      const result = await window.AgixtApi.createGroupConversation({
        conversation_name: 'DM-' + name,
        company_id: companyId,
        conversation_type: 'dm',
      });
      const id = result && (result.id || result.conversation_id);
      if (id) {
        await window.AgixtApi.addConversationParticipant(id, {
          user_id: user.id,
          participant_type: 'user',
          role: 'member',
        }).catch(() => {});
        activeCompanyId = null;
        lsSet(STORAGE_ACTIVE_COMPANY, 'private');
        renderCompanyRail();
        await Promise.all([loadPrivateConversations(), loadTeammates()]);
        ensurePrivateConversationCached({
          id,
          name: (result && result.name) || 'DM-' + name,
          display_name: name,
          conversation_type: 'dm',
          company_id: (result && result.company_id) || companyId || null,
          updated_at: new Date().toISOString(),
        });
        renderChannelList();
        await selectChannel(id);
      }
    } catch (e) {
      toast('Failed to start DM', true);
    }
  }

  async function startAgentDM(agent) {
    if (!agent || !agent.name) return;
    const companyId = agent.company_id || activeCompanyId || '';
    try {
      const result = await window.AgixtApi.createGroupConversation({
        conversation_name: agent.name,
        company_id: companyId,
        conversation_type: 'dm',
        agent_names: [agent.name],
      });
      const id = result && (result.id || result.conversation_id);
      if (id) {
        activeCompanyId = null;
        lsSet(STORAGE_ACTIVE_COMPANY, 'private');
        renderCompanyRail();
        await loadPrivateConversations();
        ensurePrivateConversationCached({
          id,
          name: (result && result.name) || agent.name,
          display_name: agent.name,
          agent_name: agent.name,
          conversation_type: 'dm',
          company_id: (result && result.company_id) || companyId || null,
          updated_at: new Date().toISOString(),
        });
        renderChannelList();
        await selectChannel(id);
      }
    } catch (e) {
      toast('Failed to start DM', true);
    }
  }

  // ----- Collapse state -------------------------------------------------

  // On a phone the channel / member columns are slide-over drawers
  // (see styles.css) whose open state is transient — held here, NOT in
  // localStorage — so a mobile session never clobbers the desktop
  // collapse preference. Both start closed so the message surface owns
  // the screen; the user opens them via the expand strip / member
  // toggle and they auto-close again on channel select.
  let mobileChannelsOpen = false;
  let mobileMembersOpen = false;
  function isMobilePortrait() {
    return document.body.classList.contains('mobile-portrait');
  }
  function channelsCollapsed() {
    return isMobilePortrait()
      ? !mobileChannelsOpen
      : lsGet(STORAGE_COLLAPSE_CHANNELS) === '1';
  }
  function membersCollapsed() {
    // Desktop default is collapsed so the conversation owns the width;
    // only an explicit user-open (stored '0') keeps it visible.
    return isMobilePortrait()
      ? !mobileMembersOpen
      : lsGet(STORAGE_COLLAPSE_MEMBERS) !== '0';
  }

  // ----- Member list width (resizable when open) ------------------------

  function applyMemberWidth(w) {
    const n = Math.max(MEMBER_WIDTH_MIN, Math.min(MEMBER_WIDTH_MAX,
      Math.round(w || MEMBER_WIDTH_DEFAULT)));
    document.documentElement.style.setProperty('--tc-member-width', n + 'px');
    return n;
  }
  function restoreMemberWidth() {
    const saved = parseInt(lsGet(STORAGE_MEMBER_WIDTH) || '', 10);
    applyMemberWidth(Number.isFinite(saved) ? saved : MEMBER_WIDTH_DEFAULT);
  }
  function bindMemberResize() {
    const seam = el('tc-member-resize');
    const list = el('tc-member-list');
    if (!seam || !list) return;
    let dragging = false, startX = 0, startWidth = 0;
    seam.addEventListener('pointerdown', (e) => {
      dragging = true;
      seam.classList.add('is-dragging');
      startX = e.clientX;
      startWidth = list.getBoundingClientRect().width;
      try { seam.setPointerCapture(e.pointerId); } catch (_) {}
      e.preventDefault();
    });
    seam.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      // Panel is docked on the RIGHT — dragging left widens it.
      const next = applyMemberWidth(startWidth - (e.clientX - startX));
      lsSet(STORAGE_MEMBER_WIDTH, String(next));
    });
    const stop = (e) => {
      if (!dragging) return;
      dragging = false;
      seam.classList.remove('is-dragging');
      try { seam.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    seam.addEventListener('pointerup', stop);
    seam.addEventListener('pointercancel', stop);
    seam.addEventListener('dblclick', () => {
      applyMemberWidth(MEMBER_WIDTH_DEFAULT);
      lsSet(STORAGE_MEMBER_WIDTH, String(MEMBER_WIDTH_DEFAULT));
    });
  }

  function applyCollapseState() {
    const pane = document.querySelector('.view-pane-team-chat');
    if (!pane) return;
    const chCollapsed = channelsCollapsed();
    pane.classList.toggle('tc-channels-collapsed', chCollapsed);
    pane.classList.toggle('tc-members-collapsed', membersCollapsed());
    const expand = el('tc-channel-collapsed');
    if (expand) expand.hidden = !chCollapsed;
  }
  function toggleChannels(collapse) {
    if (isMobilePortrait()) {
      mobileChannelsOpen = !collapse;
      applyCollapseState();
      return;
    }
    lsSet(STORAGE_COLLAPSE_CHANNELS, collapse ? '1' : '0');
    applyCollapseState();
  }
  function toggleMembers(collapse) {
    if (isMobilePortrait()) {
      mobileMembersOpen = !collapse;
      applyCollapseState();
      return;
    }
    lsSet(STORAGE_COLLAPSE_MEMBERS, collapse ? '1' : '0');
    applyCollapseState();
  }

  // ----- Refresh + mount ------------------------------------------------

  async function refresh() {
    try {
      await loadCompanies();
      renderCompanyRail();
      if (activeCompanyId) {
        await loadChannelsForCompany(activeCompanyId);
      } else {
        await Promise.all([loadPrivateConversations(), loadTeammates()]);
      }
      renderChannelList();
    } catch (_) {}
  }

  async function mount() {
    if (mounted) {
      try {
        if (activeCompanyId) await loadChannelsForCompany(activeCompanyId);
        else await Promise.all([loadPrivateConversations(), loadTeammates()]);
        renderChannelList();
        if (activeChannelId) loadParticipants(activeChannelId).then(renderMembers);
      } catch (_) {}
      return;
    }
    mounted = true;

    el('tc-company-private').addEventListener('click', () => selectCompany(null));
    el('tc-channel-collapse').addEventListener('click', () => toggleChannels(true));
    el('tc-channel-collapsed').addEventListener('click', () => toggleChannels(false));
    el('tc-member-collapse').addEventListener('click', () => toggleMembers(true));
    el('tc-member-toggle').addEventListener('click', () => {
      toggleMembers(!membersCollapsed());
    });
    restoreMemberWidth();
    bindMemberResize();
    const inviteBtn = el('tc-member-invite');
    if (inviteBtn) inviteBtn.addEventListener('click', openInviteDialog);
    const memberSearchInput = el('tc-member-search-input');
    if (memberSearchInput) {
      memberSearchInput.addEventListener('input', () => {
        memberSearch = (memberSearchInput.value || '').trim();
        renderMembers();
      });
    }
    const addBtn = el('tc-channel-add');
    if (addBtn) addBtn.addEventListener('click', openCreateChannelDialog);
    const gifBtn = el('tc-gif-btn');
    if (gifBtn) gifBtn.addEventListener('click', openGifPicker);
    const emojiBtn = el('tc-emoji-btn');
    if (emojiBtn) {
      emojiBtn.addEventListener('click', (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        openEmojiPicker(rect.right, rect.top, (emoji) => insertEmojiAtCursor(emoji));
      });
    }
    const micBtn = el('tc-mic-btn');
    if (micBtn) {
      micBtn.addEventListener('click', () => {
        if (micState.state === 'recording') stopMicRecording();
        else if (micState.state === 'idle') startMicRecording();
      });
    }
    const newDmBtn = el('tc-new-dm-btn');
    if (newDmBtn) newDmBtn.addEventListener('click', openNewDMDialog);
    const threadsBtn = el('tc-threads-toggle');
    if (threadsBtn) threadsBtn.addEventListener('click', openThreadsPanel);
    const companyAddBtn = el('tc-company-add');
    if (companyAddBtn) companyAddBtn.addEventListener('click', openCreateServerDialog);
    // Thread:active events from elsewhere in the app nest the active
    // thread under its parent channel — mirrors ChannelList.tsx.
    window.addEventListener('thread:active', (e) => {
      const d = e && e.detail;
      activeThreadInfo = (d && d.parentId)
        ? { id: d.id, name: d.name || 'thread', parentId: d.parentId }
        : null;
      if (activeCompanyId) renderChannelList();
    });
    // Insert-mention events from elsewhere in the app (e.g. the member
    // context menu's "Mention in chat" item dispatches one too).
    window.addEventListener('insert-mention', (e) => {
      const d = e && e.detail;
      if (!d || !d.text) return;
      const input = el('tc-composer-input');
      if (!input) return;
      const start = input.selectionStart || 0;
      const v = input.value || '';
      input.value = v.slice(0, start) + d.text + v.slice(input.selectionEnd || 0);
      const caret = start + d.text.length;
      input.selectionStart = input.selectionEnd = caret;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });
    // WebSocket-driven channel notification events update the server
    // rail badges, matching GroupRail.tsx's `serverNotifications` map.
    window.addEventListener('channel:notification', (e) => {
      const d = (e && e.detail) || {};
      if (!d.companyId || d.conversationType === 'dm') return;
      const cur = serverNotifications.get(d.companyId) || 0;
      if (d.hasNotifications) {
        serverNotifications.set(d.companyId, d.increment ? cur + 1 : Math.max(cur, 1));
      } else if (cur > 0) {
        const next = cur - 1;
        if (next <= 0) serverNotifications.delete(d.companyId);
        else serverNotifications.set(d.companyId, next);
      }
      renderCompanyRail();
    });
    window.addEventListener('channel:mark-read', (e) => {
      const d = (e && e.detail) || {};
      if (!d.companyId) return;
      const cur = serverNotifications.get(d.companyId) || 0;
      if (cur <= 1) serverNotifications.delete(d.companyId);
      else serverNotifications.set(d.companyId, cur - 1);
      renderCompanyRail();
    });

    el('tc-send-btn').addEventListener('click', sendMessage);
    const input = el('tc-composer-input');
    input.addEventListener('keydown', (e) => {
      if (handleEmojiAutocompleteKey(e)) return;
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      } else if (e.key === 'Escape') {
        // Esc precedence: cancel an active recording first, then drop
        // a staged reply, otherwise let the textarea handle it.
        if (micState.state === 'recording') {
          e.preventDefault();
          cancelMicRecording();
        } else if (replyTarget) {
          e.preventDefault();
          clearReplyTarget();
        }
      }
    });
    // Esc anywhere on the page (e.g. user moved focus elsewhere) also
    // cancels a hot mic — matches the agent chat's behavior.
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && micState.state === 'recording') {
        e.preventDefault();
        cancelMicRecording();
      }
    });
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 132) + 'px';
      updateEmojiAutocomplete();
      paintComposerOverlay();
      if (input.value) sendTypingIndicator();
    });
    input.addEventListener('scroll', () => {
      const overlay = el('tc-composer-overlay');
      if (overlay) overlay.scrollTop = input.scrollTop;
    });
    bindFileInputs();

    applyCollapseState();

    // Cache the AGiXT server URL + JWT so the media-rewriter doesn't
    // have to wait on getSettings() every time a message renders.
    refreshAgixtMediaContext();

    // Register the mention resolver — markdown.js calls this for every
    // `<@uuid>` token while rendering a message, getting back the
    // display name + click/context-menu behavior.
    if (window.AgixtMarkdown
        && typeof window.AgixtMarkdown.setMentionResolver === 'function') {
      window.AgixtMarkdown.setMentionResolver((uid) => {
        const p = participantById(uid);
        const name = p ? nameForParticipant(p) : null;
        const isAgent = p && p.participant_type === 'agent';
        return {
          name: name || 'User',
          kind: isAgent ? 'agent' : 'user',
          onClick: () => {
            // Re-mention the same person in the composer — matches the
            // web's MentionHighlight click which inserts an @mention.
            insertMention(name || 'User', uid);
          },
          onContextMenu: (e) => {
            if (!p) return;
            showMemberContextMenu(e, p);
          },
        };
      });
    }

    await loadCompanies();
    renderCompanyRail();

    const remembered = lsGet(STORAGE_ACTIVE_COMPANY);
    if (remembered && remembered !== 'private' && companies.some((c) => c.id === remembered)) {
      await selectCompany(remembered);
    } else {
      activeCompanyId = null;
      renderCompanyRail();
      await Promise.all([loadPrivateConversations(), loadTeammates()]);
      renderChannelList();
      const lastId = lsGet(STORAGE_LAST_CHANNEL_PREFIX + 'private');
      const convos = allConversationsCache || [];
      let target = null;
      if (lastId && convos.some((c) => c.id === lastId)) target = lastId;
      // First-run / no tracked state → open the most recent DM
      // (allConversationsCache is sorted most-recent-first) so the user
      // never lands on a blank "no channel selected" screen.
      else if (convos.length) target = convos[0].id;
      if (target) await selectChannel(target);
    }
  }

  function unmount() {
    closeWs();
    if (participantsPollTimer) clearInterval(participantsPollTimer);
    // Clear any in-flight optimistic-send safety timers so the pane
    // doesn't keep the event loop (or a stale timer) alive after teardown.
    for (const p of pendingOptimistic) {
      if (p.timer) clearTimeout(p.timer);
    }
    pendingOptimistic = [];
    clearTypingUsers();
  }

  window.AgixtTeamChat = {
    mount,
    unmount,
    refresh,
    // Called by app.js when the viewport flips between portrait/desktop
    // so the channel/member columns re-resolve drawer-vs-column.
    applyCollapseState,
  };
})();
