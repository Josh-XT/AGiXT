#!/bin/sh
set -eu

escape_js() {
  printf '%s' "$1" \
    | sed \
      -e 's/\\/\\\\/g' \
      -e 's/"/\\"/g' \
      -e 's/</\\u003c/g' \
      -e 's/>/\\u003e/g' \
      -e 's/&/\\u0026/g'
}

server_url="${AGIXT_SERVER:-}"
web_url="${APP_URI:-}"
app_name="${APP_NAME:-AGiXT}"

cat > /usr/share/nginx/html/web-config.js <<EOF
window.AGIXT_WEB_CONFIG = {
  serverUrl: "$(escape_js "$server_url")",
  webUrl: "$(escape_js "$web_url")",
  appName: "$(escape_js "$app_name")"
};
EOF
