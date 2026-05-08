# AGiXT Web Client Wrapper

This serves the Tauri 2 desktop frontend as a browser SPA without mixing it
into the main AGiXT API container.

The image copies `clients/desktop/src`, injects `web-runtime.js` before the
desktop scripts, and serves the result with Nginx. The runtime provides the
small `window.__TAURI__` surface the desktop frontend expects, backed by
browser storage and AGiXT REST/SSE/WebSocket endpoints.

## Build

Run from the AGiXT repository root:

```bash
docker build -f clients/web/Dockerfile -t agixt-client-web .
```

## Run

If the AGiXT API is reachable from the web container as `http://agixt:7437`,
the default is enough:

```bash
docker run --rm -p 8080:80 agixt-client-web
```

For local development against the host backend:

```bash
docker run --rm -p 8080:80 \
  --add-host=host.docker.internal:host-gateway \
  -e AGIXT_API_UPSTREAM=http://host.docker.internal:7437 \
  agixt-client-web
```

Open `http://localhost:8080`. The browser talks to same-origin `/v1/...`;
Nginx proxies that to `AGIXT_API_UPSTREAM`, including WebSocket streams.

## Notes

- Desktop-only capabilities such as screenshots, shell commands, native file
  paths, sudo, local installation, and app updates are disabled in web mode.
- Conversation chat, auth, agent selection, workspace upload/download, voice
  recording through the browser, and agent settings use the AGiXT API directly.
- OAuth login redirects to `/user/close/{provider}` in this same container,
  exchanges the code with AGiXT, stores the JWT in browser local storage, and
  redirects back to `/`.
