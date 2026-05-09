/* AGiXT conversation workspace HTTP client.
 *
 * Mirrors web/components/api/conversation.ts workspace functions 1:1.
 * Uses direct fetch against the configured AGiXT server with the user's
 * JWT — same pattern chat.js uses for /v1/conversation/{id}/stop.
 *
 * Endpoint patterns: /v1/conversation/{conversationId}/workspace/...
 *
 * All functions take a `cfg` object: { serverUrl, jwt }.
 */
(function () {
  // Path-preserving encoder for workspace path query params.
  // Matches the Rust `urlencode_path` helper — '/' and '.' must be
  // preserved because AGiXT routes treat them as path separators.
  function encodePath(p) {
    return String(p || '')
      .split('/')
      .map((seg) => encodeURIComponent(seg))
      .join('/');
  }

  function trimSlash(s) {
    return String(s || '').replace(/\/+$/, '');
  }

  function authHeaders(jwt, extra) {
    const h = { Authorization: `Bearer ${jwt}` };
    if (extra) Object.assign(h, extra);
    return h;
  }

  async function jsonFetch(url, opts) {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
    }
    if (resp.status === 204) return null;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp.text();
  }

  /** GET /v1/conversation/{id}/workspace?path={path}&recursive={bool}
   *  Returns { path, items: WorkspaceItem[] }
   */
  async function getWorkspace(cfg, conversationId, opts) {
    const recursive = opts && opts.recursive !== undefined ? opts.recursive : true;
    const params = new URLSearchParams();
    if (opts && opts.path) params.set('path', opts.path);
    params.set('recursive', String(recursive));
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace?${params}`;
    const body = await jsonFetch(url, { method: 'GET', headers: authHeaders(cfg.jwt) });
    // Normalise: server may return array directly, or {items:[]}, or {files:[]}
    if (Array.isArray(body)) return { path: '/', items: body };
    if (body && Array.isArray(body.items)) return { path: body.path || '/', items: body.items };
    if (body && Array.isArray(body.files)) return { path: body.path || '/', items: body.files };
    return { path: '/', items: [] };
  }

  /** POST /v1/conversation/{id}/workspace/upload (multipart)
   *  files: File[], destinationPath: string|undefined
   */
  async function uploadFiles(cfg, conversationId, files, destinationPath) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace/upload`;
    const form = new FormData();
    for (const f of files) form.append('files', f, f.name);
    if (destinationPath) form.append('destination_path', destinationPath);
    const resp = await fetch(url, { method: 'POST', headers: authHeaders(cfg.jwt), body: form });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`upload HTTP ${resp.status}: ${text}`);
    }
    return resp.json().catch(() => ({}));
  }

  /** POST /v1/conversation/{id}/workspace/folder
   *  { folder_name, parent_path? }
   */
  async function createFolder(cfg, conversationId, folderName, parentPath) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace/folder`;
    const body = { folder_name: folderName };
    if (parentPath) body.parent_path = parentPath;
    return jsonFetch(url, {
      method: 'POST',
      headers: authHeaders(cfg.jwt, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
  }

  /** DELETE /v1/conversation/{id}/workspace/item
   *  body: { path }
   */
  async function deleteItem(cfg, conversationId, path) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace/item`;
    return jsonFetch(url, {
      method: 'DELETE',
      headers: authHeaders(cfg.jwt, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ path }),
    });
  }

  /** PUT /v1/conversation/{id}/workspace/item
   *  body: { source_path, destination_path }
   */
  async function moveItem(cfg, conversationId, sourcePath, destinationPath) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace/item`;
    return jsonFetch(url, {
      method: 'PUT',
      headers: authHeaders(cfg.jwt, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ source_path: sourcePath, destination_path: destinationPath }),
    });
  }

  /** GET /v1/conversation/{id}/workspace/download?path={path}
   *  Returns { blob, filename } — filename comes from Content-Disposition
   *  header, falling back to the basename of the path.
   */
  async function downloadFile(cfg, conversationId, path) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/conversation/${encodeURIComponent(conversationId)}/workspace/download?path=${encodePath(path)}`;
    const resp = await fetch(url, { method: 'GET', headers: authHeaders(cfg.jwt) });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`download HTTP ${resp.status}: ${text}`);
    }
    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    let filename = path.split('/').filter(Boolean).pop() || 'file';
    const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    if (m) {
      try { filename = decodeURIComponent(m[1]); } catch { filename = m[1]; }
    }
    return { blob, filename };
  }

  /** POST /v1/chat/completions — used by the AI Edit bar.
   *  Returns the assistant message content string.
   */
  async function aiEditCompletion(cfg, opts) {
    const url = `${trimSlash(cfg.serverUrl)}/v1/chat/completions`;
    const body = {
      messages: [
        {
          role: 'user',
          content: [{ type: 'text', text: opts.prompt }],
          disable_commands: 'true',
        },
      ],
      model: opts.model || 'XT',
      user: opts.conversationId,
    };
    const resp = await fetch(url, {
      method: 'POST',
      headers: authHeaders(cfg.jwt, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`AI edit HTTP ${resp.status}`);
    const data = await resp.json();
    return data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
  }

  window.AgixtWorkspaceApi = {
    getWorkspace,
    uploadFiles,
    createFolder,
    deleteItem,
    moveItem,
    downloadFile,
    aiEditCompletion,
  };
})();
