/* Tiny markdown renderer with media support.
 *
 * The AGiXT NextJS web client uses react-markdown + remark-gfm with custom
 * renderers for images, video, audio, and GIFs. We keep this dependency-free
 * for the desktop webview, but build DOM nodes directly so user-provided
 * message text never has to flow through an HTML sink.
 */
(function () {
  const IMG_EXT = /\.(png|jpe?g|gif|webp|avif|bmp|svg)(\?[^\s)]*)?$/i;
  const VIDEO_EXT = /\.(mp4|webm|mov|m4v|ogv)(\?[^\s)]*)?$/i;
  const AUDIO_EXT = /\.(mp3|wav|ogg|m4a|flac|aac)(\?[^\s)]*)?$/i;
  const GIF_HOST = /(tenor\.com|giphy\.com|media\.tenor\.|media\.giphy\.)/i;
  const TRUSTED_MEDIA_PREFIXES = ['/outputs/', '/workspace/', '/assets/'];
  const EXTERNAL_LINK_HREF = '#agixt-external-link';
  const trustedMediaOriginPrefixes = new Set();

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function normalizeSafeUrl(url, media) {
    const raw = String(url || '').trim();
    if (!raw || /[\u0000-\u001f\u007f]/.test(raw)) return '';
    if (/^data:/i.test(raw)) {
      // Allow data:image/* / data:audio/* / data:video/* only as media
      // sources (never as link hrefs). SVG inside data:image/svg+xml
      // can carry inline scripts so it's still refused. Pasted /
      // attached files arrive through this path; without it, image
      // attachments rendered as their alt text instead of an <img>.
      if (!media) return '';
      if (/^data:(image\/(?!svg\+xml)|audio\/|video\/)[a-z0-9.+-]+[;,]/i.test(raw)) {
        return raw;
      }
      return '';
    }
    if (media && raw.startsWith('/') && !raw.startsWith('//')) {
      return encodeURI(raw);
    }
    try {
      const base = (typeof document !== 'undefined' && document.baseURI)
        || (typeof window !== 'undefined' && window.location && window.location.href)
        || 'http://localhost/';
      const parsed = new URL(raw, base);
      if (media && (parsed.protocol === 'http:' || parsed.protocol === 'https:' || parsed.protocol === 'blob:')) {
        return encodeURI(parsed.href);
      }
      if (!media && (
        parsed.protocol === 'http:'
        || parsed.protocol === 'https:'
        || parsed.protocol === 'mailto:'
        || parsed.protocol === 'tel:'
      )) {
        return encodeURI(parsed.href);
      }
      return '';
    } catch (_) {
      return '';
    }
  }

  function safeUrl(url, media) {
    return normalizeSafeUrl(url, media);
  }

  function sameOriginPrefix() {
    try {
      const base = (typeof window !== 'undefined' && window.location && window.location.origin) || '';
      return base ? `${base}/` : '';
    } catch (_) {
      return '';
    }
  }

  // Mention resolver: when the renderer hits a `<@uuid>` token, it
  // calls this with the uid and gets back { name, kind, onClick? }.
  // Without a resolver, mentions render as `@user-id` for visibility.
  // team-chat sets a resolver that maps to channel-participant display
  // names + opens a DM on click; the chat (agent) pane leaves it
  // unset so old conversations still render readably.
  let mentionResolver = null;
  function setMentionResolver(fn) {
    mentionResolver = typeof fn === 'function' ? fn : null;
  }

  function setTrustedMediaOrigins(origins) {
    trustedMediaOriginPrefixes.clear();
    (origins || []).forEach((origin) => {
      try {
        const parsed = new URL(origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
          trustedMediaOriginPrefixes.add(`${parsed.origin}/`);
        }
      } catch (_) {}
    });
  }

  function setTrustedUrlAttribute(node, attr, value) {
    const safe = String(value || '');
    // data: URLs that passed normalizeSafeUrl's media-only allowlist
    // already have their MIME type validated; pass them through here
    // so attached images / audio / video actually render.
    if (/^data:(image\/(?!svg\+xml)|audio\/|video\/)/i.test(safe)) {
      node.setAttribute(attr, safe);
      return true;
    }
    // Media element src/href on a remote http(s) URL — this is what
    // covers Tenor / Giphy / generic image hosts. The web app accepts
    // these freely for media tags (img, video, audio) because they
    // can't execute scripts. We restrict the same way: this branch only
    // fires for media attribute setters (caller marks them via the
    // node.tagName check), never for anchor hrefs (where they could
    // proxy a phishing destination).
    const tag = (node && node.tagName) ? node.tagName.toLowerCase() : '';
    const isMediaTag = tag === 'img' || tag === 'video' || tag === 'audio' || tag === 'source';
    if (isMediaTag && /^https?:\/\//i.test(safe)) {
      node.setAttribute(attr, safe);
      return true;
    }
    for (const prefix of TRUSTED_MEDIA_PREFIXES) {
      if (safe.startsWith(prefix)) {
        node.setAttribute(attr, safe);
        return true;
      }
    }
    for (const prefix of trustedMediaOriginPrefixes) {
      if (prefix && safe.startsWith(prefix)) {
        node.setAttribute(attr, safe);
        return true;
      }
    }
    const originPrefix = sameOriginPrefix();
    if (originPrefix && safe.startsWith(originPrefix)) {
      node.setAttribute(attr, safe);
      return true;
    }
    return false;
  }

  function openExternalUrl(url) {
    const href = safeUrl(url, false);
    if (!href) return;
    const tauri = window.__TAURI__ || {};
    const opener = tauri.opener || tauri.shell || {};
    const open = opener.openUrl || opener.open;
    if (typeof open === 'function') {
      Promise.resolve(open(href)).catch(() => {});
    }
  }

  function classifyMedia(url) {
    const clean = String(url || '').split('#')[0];
    if (!safeUrl(clean, true)) return null;
    if (/^data:image\//i.test(clean)) return 'image';
    if (/^data:video\//i.test(clean)) return 'video';
    if (/^data:audio\//i.test(clean)) return 'audio';
    if (VIDEO_EXT.test(clean)) return 'video';
    if (AUDIO_EXT.test(clean)) return 'audio';
    if (IMG_EXT.test(clean) || GIF_HOST.test(clean)) return 'image';
    return null;
  }

  function textNode(text) {
    return document.createTextNode(text == null ? '' : String(text));
  }

  function appendText(parent, text) {
    if (text) parent.appendChild(textNode(text));
  }

  function mediaNode(kind, url, alt) {
    const src = safeUrl(url, true);
    if (!src) return textNode(alt || url || '');
    const fallback = linkNode(alt || url || '', url, true);
    let node;
    if (kind === 'video') {
      node = document.createElement('video');
      node.setAttribute('controls', '');
      node.setAttribute('preload', 'metadata');
    } else if (kind === 'audio') {
      node = document.createElement('audio');
      node.setAttribute('controls', '');
      node.setAttribute('preload', 'metadata');
    } else {
      node = document.createElement('img');
      node.setAttribute('alt', alt || '');
      node.setAttribute('loading', 'lazy');
      // Don't leak the user's location to third-party image hosts when
      // someone pastes an external URL into the chat. Matches the
      // referrerPolicy the web's MediaLightbox / MarkdownBlock applies.
      node.setAttribute('referrerpolicy', 'no-referrer');
      // Tag so team-chat / other consumers can attach a click-to-expand
      // lightbox without re-parsing the message DOM.
      node.classList.add('md-image');
      return setTrustedUrlAttribute(node, 'src', src) ? node : fallback;
    }
    if (alt && kind !== 'image') node.setAttribute('aria-label', alt);
    return setTrustedUrlAttribute(node, 'src', src) ? node : fallback;
  }

  function linkNode(label, url, plainLabel) {
    const href = safeUrl(url, false);
    if (!href) {
      const span = document.createElement('span');
      appendInline(span, label);
      return span;
    }
    const a = document.createElement('a');
    if (!setTrustedUrlAttribute(a, 'href', href)) {
      a.setAttribute('href', EXTERNAL_LINK_HREF);
      a.dataset.externalUrl = href;
      a.addEventListener('click', (event) => {
        event.preventDefault();
        openExternalUrl(href);
      });
    }
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noreferrer noopener');
    if (plainLabel) a.textContent = label || href;
    else appendInline(a, label);
    return a;
  }

  const INLINE_PATTERNS = [
    {
      type: 'image',
      re: /!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g,
    },
    {
      type: 'link',
      re: /\[([^\]\n]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,
    },
    // <@uuid> mention token. Resolved through the registered mention
    // resolver (see setMentionResolver) so the renderer can paint a
    // styled @DisplayName chip without a markdown-level rewrite of the
    // raw text. UUIDv4 form matches the wire format the server stores.
    {
      type: 'mention',
      re: /<@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>/gi,
    },
    { type: 'code', re: /`([^`\n]+)`/g },
    // Discord-style spoilers — must come BEFORE bold so `||` doesn't
    // try to match as nothing-then-italic. Allows newlines in the body
    // for short multi-line spoilers (longer ones become block spoilers
    // at the parser-block level).
    { type: 'spoiler', re: /\|\|([^|]+(?:\|[^|]+)*)\|\|/g },
    { type: 'bold', re: /\*\*([^*]+)\*\*|__([^_]+)__/g },
    { type: 'strike', re: /~~([^~\n]+)~~/g },
    { type: 'italic', re: /(^|[^*])\*([^*\n]+)\*/g },
    { type: 'break', re: /  +\n/g },
    { type: 'url', re: /https?:\/\/[^\s<)]+/g },
  ];

  function nextInlineToken(text, offset) {
    let best = null;
    for (const pattern of INLINE_PATTERNS) {
      pattern.re.lastIndex = offset;
      const match = pattern.re.exec(text);
      if (!match) continue;
      let start = match.index;
      if (pattern.type === 'italic') start += (match[1] || '').length;
      const end = match.index + match[0].length;
      if (!best || start < best.start) {
        best = { type: pattern.type, match, start, end };
      }
    }
    return best;
  }

  function appendInline(parent, text) {
    const src = String(text == null ? '' : text);
    let pos = 0;
    while (pos < src.length) {
      const token = nextInlineToken(src, pos);
      if (!token) {
        appendText(parent, src.slice(pos));
        break;
      }
      appendText(parent, src.slice(pos, token.start));
      const m = token.match;
      if (token.type === 'image') {
        const alt = m[1] || '';
        const url = m[2] || '';
        parent.appendChild(mediaNode(classifyMedia(url) || 'image', url, alt));
      } else if (token.type === 'link') {
        parent.appendChild(linkNode(m[1] || '', m[2] || ''));
      } else if (token.type === 'mention') {
        const uid = m[1] || '';
        const resolved = mentionResolver ? mentionResolver(uid) : null;
        const name = (resolved && resolved.name) || 'User';
        const kind = (resolved && resolved.kind) || 'user';
        const span = document.createElement('span');
        span.className = 'md-mention md-mention-' + kind;
        span.setAttribute('role', 'button');
        span.setAttribute('tabindex', '0');
        span.dataset.userId = uid;
        span.textContent = '@' + name;
        const onClick = resolved && typeof resolved.onClick === 'function'
          ? resolved.onClick : null;
        const onCtx = resolved && typeof resolved.onContextMenu === 'function'
          ? resolved.onContextMenu : null;
        if (onClick) {
          span.addEventListener('click', (e) => { e.preventDefault(); onClick(e); });
          span.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault(); onClick(e);
            }
          });
        }
        if (onCtx) {
          span.addEventListener('contextmenu', (e) => { e.preventDefault(); onCtx(e); });
        }
        parent.appendChild(span);
      } else if (token.type === 'code') {
        const code = document.createElement('code');
        code.textContent = m[1] || '';
        parent.appendChild(code);
      } else if (token.type === 'bold') {
        const strong = document.createElement('strong');
        appendInline(strong, m[1] || m[2] || '');
        parent.appendChild(strong);
      } else if (token.type === 'strike') {
        const del = document.createElement('del');
        appendInline(del, m[1] || '');
        parent.appendChild(del);
      } else if (token.type === 'spoiler') {
        // Discord-style spoiler — hidden until clicked. The body still
        // gets a recursive inline-render pass so bold / code / etc.
        // inside the spoiler stay formatted once revealed.
        const span = document.createElement('span');
        span.className = 'md-spoiler';
        span.setAttribute('role', 'button');
        span.setAttribute('tabindex', '0');
        span.setAttribute('aria-label', 'Spoiler — click to reveal');
        const inner = document.createElement('span');
        inner.className = 'md-spoiler-inner';
        appendInline(inner, m[1] || '');
        span.appendChild(inner);
        const reveal = (e) => {
          e.preventDefault();
          e.stopPropagation();
          span.classList.add('is-revealed');
        };
        span.addEventListener('click', reveal);
        span.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') reveal(e);
        });
        parent.appendChild(span);
      } else if (token.type === 'italic') {
        const em = document.createElement('em');
        appendInline(em, m[2] || '');
        parent.appendChild(em);
      } else if (token.type === 'break') {
        parent.appendChild(document.createElement('br'));
      } else if (token.type === 'url') {
        const url = m[0] || '';
        const kind = classifyMedia(url);
        if (kind) {
          parent.appendChild(mediaNode(kind, url, ''));
        } else {
          // Bare URLs are their own label — don't recurse through linkNode,
          // because that would re-match the URL inline pattern on the
          // label and infinitely nest <a> elements (RangeError: Maximum
          // call stack size exceeded). Build the anchor directly with
          // the URL as plain text content.
          const href = safeUrl(url, false);
          if (href) {
            const a = document.createElement('a');
            if (!setTrustedUrlAttribute(a, 'href', href)) {
              a.setAttribute('href', EXTERNAL_LINK_HREF);
              a.dataset.externalUrl = href;
              a.addEventListener('click', (event) => {
                event.preventDefault();
                openExternalUrl(href);
              });
            }
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noreferrer noopener');
            a.textContent = url;
            parent.appendChild(a);
          } else {
            appendText(parent, url);
          }
        }
      }
      pos = token.end;
    }
  }

  const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

  function listItemInfo(line) {
    const m = line.match(LIST_RE);
    if (!m) return null;
    const indent = m[1].replace(/\t/g, '    ').length;
    const ordered = /\d/.test(m[2]);
    return { indent, ordered, marker: m[2], content: m[3] };
  }

  function isTableSeparator(line) {
    return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  }

  function parseTableRow(line) {
    let s = line.trim();
    if (s.startsWith('|')) s = s.slice(1);
    if (s.endsWith('|')) s = s.slice(0, -1);
    return s.split('|').map((c) => c.trim());
  }

  function parseAlignments(line) {
    return parseTableRow(line).map((cell) => {
      const left = cell.startsWith(':');
      const right = cell.endsWith(':');
      if (left && right) return 'center';
      if (right) return 'right';
      if (left) return 'left';
      return null;
    });
  }

  function appendList(parent, lines, startIdx, baseIndent) {
    const first = listItemInfo(lines[startIdx]);
    const list = document.createElement(first.ordered ? 'ol' : 'ul');
    let i = startIdx;
    while (i < lines.length) {
      const info = listItemInfo(lines[i]);
      if (!info || info.indent < baseIndent) break;
      if (info.indent > baseIndent) {
        const nested = appendList(list.lastElementChild || list, lines, i, info.indent);
        i = nested.next;
        continue;
      }
      const li = document.createElement('li');
      // Collect continuation lines belonging to this item. Continuation
      // content is anything indented past `baseIndent` (the marker
      // column). We dedent each line by the item's continuation indent
      // (the indent of its first continuation line) so nested block
      // constructs — fenced code blocks, sub-lists, blockquotes — see
      // the indentation they expect when rendered recursively.
      //
      // Fenced code blocks are a special case: they can contain blank
      // lines and arbitrary (even un-indented) body lines, so once we
      // open a fence we keep consuming until its closing ``` regardless
      // of indentation.
      const itemLines = [info.content];
      let sawBlock = /```/.test(info.content);
      i++;
      // Dedent removes up to `cols` columns of leading whitespace,
      // expanding tabs to 4 spaces so indent math matches listItemInfo.
      const dedentBy = (s, cols) => {
        let stripped = 0;
        let idx = 0;
        while (idx < s.length && stripped < cols) {
          const ch = s[idx];
          if (ch === ' ') { stripped += 1; idx += 1; }
          else if (ch === '\t') { stripped += 4; idx += 1; }
          else break;
        }
        return s.slice(idx);
      };
      // The indentation continuation content is dedented by. Captured
      // from the first continuation line so e.g. a `  ```bash` block
      // under a top-level bullet (baseIndent 0) is normalised to a
      // column-0 fence the block parser recognises.
      let contIndent = null;
      while (i < lines.length) {
        const cur = lines[i];
        const blank = /^\s*$/.test(cur);
        const leadMatch = cur.match(/^(\s*)/);
        const lead = leadMatch ? leadMatch[1].replace(/\t/g, '    ').length : 0;
        const nextInfo = listItemInfo(cur);

        // An indented list marker belongs to a nested list — let the
        // recursive call below handle it.
        if (nextInfo && nextInfo.indent > baseIndent) break;
        // A list marker at or below our indent ends this item.
        if (nextInfo && nextInfo.indent <= baseIndent) break;

        if (blank) {
          // Peek past the blank run: continuation only continues if the
          // next non-blank line is still indented past baseIndent.
          let k = i + 1;
          while (k < lines.length && /^\s*$/.test(lines[k])) k++;
          if (k >= lines.length) break;
          const peekInfo = listItemInfo(lines[k]);
          if (peekInfo && peekInfo.indent <= baseIndent) break;
          const peekLead = (lines[k].match(/^(\s*)/)[1] || '').replace(/\t/g, '    ').length;
          if (!peekInfo && peekLead <= baseIndent) break;
          itemLines.push('');
          i++;
          continue;
        }

        if (lead <= baseIndent) break;
        if (contIndent === null) contIndent = lead;

        const dedented = dedentBy(cur, contIndent);
        // Opening a fenced code block: consume through the closing fence
        // so blank lines / un-indented body inside the block don't end
        // the item prematurely.
        const fenceOpen = dedented.match(/^```/);
        if (fenceOpen) {
          sawBlock = true;
          itemLines.push(dedented);
          i++;
          while (i < lines.length) {
            const fbody = dedentBy(lines[i], contIndent);
            itemLines.push(fbody);
            i++;
            if (/^```\s*$/.test(fbody)) break;
          }
          continue;
        }
        itemLines.push(dedented);
        i++;
      }

      const body = itemLines.join('\n');
      // If the item body contains block-level markdown (fenced code,
      // headings, blockquotes, tables, or its own sub-list), render it
      // recursively so those constructs work. A simple single-paragraph
      // item still goes through appendInline (joined with hard breaks)
      // to avoid wrapping short items in a <p>.
      const hasBlock = sawBlock
        || /^\s*```/m.test(body)
        || /^\s*>/m.test(body)
        || /^\s*#{1,6}\s/m.test(body)
        || itemLines.some((l) => listItemInfo(l));
      if (hasBlock) {
        appendBlocks(li, body);
      } else {
        appendInline(li, itemLines.join('  \n'));
      }
      list.appendChild(li);
      // Look ahead past blank lines for nested list children.
      let j = i;
      while (j < lines.length && /^\s*$/.test(lines[j])) j++;
      if (j < lines.length) {
        const nextInfo = listItemInfo(lines[j]);
        if (nextInfo && nextInfo.indent > baseIndent) {
          const nested = appendList(li, lines, j, nextInfo.indent);
          i = nested.next;
        }
      }
    }
    parent.appendChild(list);
    return { next: i };
  }

  function buildBlockSpoiler(innerText) {
    // Block spoiler — wraps a fully-recursive markdown render of the
    // body so fenced code blocks, lists, tables, etc., all work once
    // revealed. Mirrors the web's Spoiler.tsx behavior for block
    // content. Inline spoilers (`||text||` with no newlines) still go
    // through appendInline.
    const span = document.createElement('div');
    span.className = 'md-spoiler md-spoiler-block';
    span.setAttribute('role', 'button');
    span.setAttribute('tabindex', '0');
    span.setAttribute('aria-label', 'Spoiler — click to reveal');
    const inner = document.createElement('div');
    inner.className = 'md-spoiler-inner';
    appendBlocks(inner, innerText);
    span.appendChild(inner);
    const reveal = (e) => {
      // Don't capture clicks INSIDE revealed content (Copy / Download
      // buttons on nested code blocks, etc.).
      if (span.classList.contains('is-revealed')) return;
      e.preventDefault();
      e.stopPropagation();
      span.classList.add('is-revealed');
    };
    span.addEventListener('click', reveal);
    span.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ')
          && !span.classList.contains('is-revealed')) reveal(e);
    });
    return span;
  }

  function appendBlocks(parent, src) {
    const lines = String(src == null ? '' : src).replace(/\r\n?/g, '\n').split('\n');
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // Block-level spoiler: opener line is exactly `||` (or `||\n`).
      // Body collects every line until the closing `||` line. Body is
      // rendered recursively so it can include fenced code blocks,
      // lists, etc.
      if (/^\|\|\s*$/.test(line)) {
        const buf = [];
        i++;
        let closed = false;
        while (i < lines.length) {
          if (/^\|\|\s*$/.test(lines[i])) { closed = true; i++; break; }
          buf.push(lines[i]);
          i++;
        }
        if (closed) {
          parent.appendChild(buildBlockSpoiler(buf.join('\n')));
          continue;
        }
        // Unclosed — fall through; the bare `||` shows as text.
      }

      // `||...||` on one line — single-line block spoiler. If the body
      // contains ``` it's promoted to block so fenced code renders;
      // otherwise we hand it off to appendInline (which already does
      // the right thing for short single-line spoilers).
      if (line.startsWith('||') && line.endsWith('||') && line.length > 4) {
        const body = line.slice(2, -2);
        if (body.includes('```')) {
          // Reshape `\`\`\`lang code \`\`\`` into the canonical
          // multi-line form so the fenced-code parser inside
          // appendBlocks can pick it up correctly. Without this the
          // inline-code regex chews up two of the three backticks
          // (matching `` `js code ` `` as inline) and the user sees a
          // half-formatted blob.
          const fenced = body.match(/^```(\w*)\s*([\s\S]*?)\s*```\s*$/);
          if (fenced) {
            const reformatted = '```' + (fenced[1] || '') + '\n'
              + fenced[2] + '\n```';
            parent.appendChild(buildBlockSpoiler(reformatted));
            i++;
            continue;
          }
          // Multiple fences in a row, or fences with surrounding text
          // we can't cleanly re-split — fall back to splitting on
          // every ``` and letting appendBlocks handle the run.
          const exploded = body.replace(/```/g, '\n```\n').replace(/\n{3,}/g, '\n\n');
          parent.appendChild(buildBlockSpoiler(exploded.trim()));
          i++;
          continue;
        }
        // No fenced code; let the inline path render it.
      }

      // `||...` opener without a closing `||` on the same line — body
      // continues to a later line that ends with `||`. Common shape:
      // `||\`\`\`js` then `foo()` then `\`\`\`||`. Reshape any inline
      // fence markers (``` glued to the body) into block fences so
      // appendBlocks lights up the code-block path.
      if (line.startsWith('||') && !line.endsWith('||')) {
        let j = i;
        const buf = [lines[j].slice(2)];
        j++;
        let closed = false;
        while (j < lines.length) {
          const cur = lines[j];
          const closeIdx = cur.indexOf('||');
          if (closeIdx !== -1) {
            if (closeIdx > 0) buf.push(cur.slice(0, closeIdx));
            closed = true;
            j++;
            break;
          }
          buf.push(cur);
          j++;
        }
        if (closed) {
          let body = buf.join('\n').trim();
          if (body.includes('```')) {
            // Break inline `\`\`\`lang` openers into block form.
            body = body.replace(/```(\w*)/g, '\n```$1\n').replace(/\n{3,}/g, '\n\n');
          }
          if (body.includes('\n') || body.includes('```')) {
            parent.appendChild(buildBlockSpoiler(body.trim()));
            i = j;
            continue;
          }
        }
        // Otherwise fall through to the regular paragraph path.
      }

      const fence = line.match(/^```\s*([\w+-]*)\s*$/);
      if (fence) {
        const lang = (fence[1] || '').replace(/[^\w+-]/g, '');
        const buf = [];
        i++;
        while (i < lines.length) {
          const cur = lines[i];
          if (/^```\s*$/.test(cur)) {
            i++;
            break;
          }
          const trail = cur.match(/^([\s\S]*?)```\s*$/);
          if (trail) {
            if (trail[1].length) buf.push(trail[1]);
            i++;
            break;
          }
          buf.push(cur);
          i++;
        }
        // Fenced code block container: <div.md-codeblock> wraps a
        // header (language label + copy + download buttons) and the
        // <pre><code>. Mirrors the chrome the web's CodeBlock.tsx
        // renders so users get the same "pretty" code surface.
        const wrap = document.createElement('div');
        wrap.className = 'md-codeblock';
        const header = document.createElement('div');
        header.className = 'md-codeblock-head';
        const langLabel = document.createElement('span');
        langLabel.className = 'md-codeblock-lang';
        langLabel.textContent = lang || 'text';
        header.appendChild(langLabel);
        const codeText = buf.join('\n');
        const actions = document.createElement('div');
        actions.className = 'md-codeblock-actions';
        // Inline lucide-style icons keep the toolbar compact and match
        // the web's CodeBlock chrome (icon-only buttons with tooltip).
        const COPY_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">'
          + '<rect x="9" y="9" width="13" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
          + '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M5 15V5a2 2 0 0 1 2-2h10"/>'
          + '</svg>';
        const COPIED_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">'
          + '<path fill="none" stroke="#10b981" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="M20 6 9 17l-5-5"/>'
          + '</svg>';
        const DL_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">'
          + '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>'
          + '</svg>';
        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'md-codeblock-btn';
        copyBtn.title = 'Copy';
        copyBtn.setAttribute('aria-label', 'Copy');
        copyBtn.innerHTML = COPY_ICON;
        copyBtn.addEventListener('click', (e) => {
          e.preventDefault();
          try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(codeText).then(() => {
                copyBtn.innerHTML = COPIED_ICON;
                copyBtn.classList.add('is-copied');
                setTimeout(() => {
                  copyBtn.innerHTML = COPY_ICON;
                  copyBtn.classList.remove('is-copied');
                }, 1200);
              });
            }
          } catch (_) {}
        });
        const dlBtn = document.createElement('button');
        dlBtn.type = 'button';
        dlBtn.className = 'md-codeblock-btn';
        dlBtn.title = 'Download';
        dlBtn.setAttribute('aria-label', 'Download');
        dlBtn.innerHTML = DL_ICON;
        dlBtn.addEventListener('click', (e) => {
          e.preventDefault();
          const extByLang = {
            javascript: 'js', typescript: 'ts', python: 'py', rust: 'rs',
            go: 'go', java: 'java', kotlin: 'kt', swift: 'swift',
            c: 'c', cpp: 'cpp', csharp: 'cs', html: 'html', css: 'css',
            json: 'json', yaml: 'yml', toml: 'toml', xml: 'xml',
            sh: 'sh', bash: 'sh', zsh: 'sh', sql: 'sql', md: 'md',
            markdown: 'md',
          };
          const ext = extByLang[(lang || '').toLowerCase()] || 'txt';
          const blob = new Blob([codeText], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `snippet.${ext}`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 500);
        });
        actions.appendChild(copyBtn);
        actions.appendChild(dlBtn);
        header.appendChild(actions);
        wrap.appendChild(header);

        const pre = document.createElement('pre');
        pre.className = 'md-codeblock-pre';
        const code = document.createElement('code');
        if (lang) code.className = `language-${lang}`;
        code.textContent = codeText;
        pre.appendChild(code);
        wrap.appendChild(pre);
        parent.appendChild(wrap);
        continue;
      }

      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        const h = document.createElement(`h${heading[1].length}`);
        appendInline(h, heading[2]);
        parent.appendChild(h);
        i++;
        continue;
      }

      if (/^---+\s*$/.test(line) || /^\*{3,}\s*$/.test(line) || /^_{3,}\s*$/.test(line)) {
        parent.appendChild(document.createElement('hr'));
        i++;
        continue;
      }

      if (/^>\s?/.test(line)) {
        const buf = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) {
          buf.push(lines[i].replace(/^>\s?/, ''));
          i++;
        }
        const quote = document.createElement('blockquote');
        appendBlocks(quote, buf.join('\n'));
        parent.appendChild(quote);
        continue;
      }

      // GFM tables: header row, separator row, then body rows.
      if (line.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        const headers = parseTableRow(line);
        const aligns = parseAlignments(lines[i + 1]);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes('|') && !/^\s*$/.test(lines[i])) {
          if (listItemInfo(lines[i]) || /^#{1,6}\s/.test(lines[i]) || /^```/.test(lines[i])) break;
          rows.push(parseTableRow(lines[i]));
          i++;
        }
        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const trh = document.createElement('tr');
        headers.forEach((h, idx) => {
          const th = document.createElement('th');
          appendInline(th, h);
          if (aligns[idx]) th.style.textAlign = aligns[idx];
          trh.appendChild(th);
        });
        thead.appendChild(trh);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        for (const row of rows) {
          const tr = document.createElement('tr');
          row.forEach((cell, idx) => {
            const td = document.createElement('td');
            appendInline(td, cell);
            if (aligns[idx]) td.style.textAlign = aligns[idx];
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        parent.appendChild(table);
        continue;
      }

      const liInfo = listItemInfo(line);
      if (liInfo) {
        const result = appendList(parent, lines, i, liInfo.indent);
        i = result.next;
        continue;
      }

      if (/^\s*$/.test(line)) {
        i++;
        continue;
      }

      const buf = [line];
      i++;
      while (
        i < lines.length
        && !/^\s*$/.test(lines[i])
        && !/^```/.test(lines[i])
        && !/^#{1,6}\s/.test(lines[i])
        && !/^>\s/.test(lines[i])
        && !listItemInfo(lines[i])
        && !(lines[i].includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1]))
      ) {
        buf.push(lines[i]);
        i++;
      }
      const p = document.createElement('p');
      // Preserve single newlines within a paragraph as hard breaks — matches
      // the web client's MarkdownBlock preprocessor which converts soft
      // breaks to "  \n" so they render as <br>.
      appendInline(p, buf.join('  \n'));
      parent.appendChild(p);
    }
  }

  function renderFragment(src) {
    const fragment = document.createDocumentFragment();
    appendBlocks(fragment, src);
    return fragment;
  }

  function render(src) {
    if (typeof document === 'undefined') return `<p>${escapeHtml(src || '')}</p>`;
    const div = document.createElement('div');
    div.appendChild(renderFragment(src));
    return div.innerHTML;
  }

  function renderInline(text) {
    if (typeof document === 'undefined') return escapeHtml(text || '');
    const span = document.createElement('span');
    appendInline(span, text);
    return span.innerHTML;
  }

  function renderInto(target, src) {
    if (!target) return;
    target.replaceChildren(renderFragment(src));
  }

  window.AgixtMarkdown = {
    render,
    renderInline,
    renderFragment,
    renderInto,
    escapeHtml,
    classifyMedia,
    setTrustedMediaOrigins,
    setMentionResolver,
  };
})();
