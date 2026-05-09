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
  const TRUSTED_MEDIA_PREFIXES = ['/outputs/', '/workspace/', '/api/workspace/', '/assets/'];
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
    if (/^data:/i.test(raw)) return '';
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
    { type: 'code', re: /`([^`\n]+)`/g },
    { type: 'bold', re: /\*\*([^*]+)\*\*|__([^_]+)__/g },
    { type: 'italic', re: /(^|[^*])\*([^*\n]+)\*/g },
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
      } else if (token.type === 'code') {
        const code = document.createElement('code');
        code.textContent = m[1] || '';
        parent.appendChild(code);
      } else if (token.type === 'bold') {
        const strong = document.createElement('strong');
        appendInline(strong, m[1] || m[2] || '');
        parent.appendChild(strong);
      } else if (token.type === 'italic') {
        const em = document.createElement('em');
        appendInline(em, m[2] || '');
        parent.appendChild(em);
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

  function appendBlocks(parent, src) {
    const lines = String(src == null ? '' : src).replace(/\r\n?/g, '\n').split('\n');
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

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
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        if (lang) code.className = `language-${lang}`;
        code.textContent = buf.join('\n');
        pre.appendChild(code);
        parent.appendChild(pre);
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

      if (/^---+\s*$/.test(line)) {
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

      if (/^\s*[-*+]\s+/.test(line)) {
        const list = document.createElement('ul');
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          const li = document.createElement('li');
          appendInline(li, lines[i].replace(/^\s*[-*+]\s+/, ''));
          list.appendChild(li);
          i++;
        }
        parent.appendChild(list);
        continue;
      }

      if (/^\s*\d+\.\s+/.test(line)) {
        const list = document.createElement('ol');
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          const li = document.createElement('li');
          appendInline(li, lines[i].replace(/^\s*\d+\.\s+/, ''));
          list.appendChild(li);
          i++;
        }
        parent.appendChild(list);
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
        && !/^\s*[-*+]\s/.test(lines[i])
        && !/^\s*\d+\.\s/.test(lines[i])
      ) {
        buf.push(lines[i]);
        i++;
      }
      const p = document.createElement('p');
      appendInline(p, buf.join(' '));
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
  };
})();
