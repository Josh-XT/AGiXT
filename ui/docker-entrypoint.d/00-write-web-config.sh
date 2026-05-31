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
service_brand="${SERVICE_BRAND:-${AGIXT_SERVICE_BRAND:-${APP_SLUG:-${SITE_SLUG:-}}}}"
theme="${AGIXT_THEME:-${APP_THEME:-}}"

app_name_lc="$(printf '%s' "$app_name" | tr '[:upper:]' '[:lower:]')"
service_brand_lc="$(printf '%s' "$service_brand" | tr '[:upper:]' '[:lower:]')"
web_url_lc="$(printf '%s' "$web_url" | tr '[:upper:]' '[:lower:]')"

if [ "$service_brand_lc" = "xtschool" ] \
  || [ "$app_name_lc" = "xtschool" ] \
  || [ "$app_name_lc" = "xt school" ] \
  || printf '%s' "$web_url_lc" | grep -q 'xt\.school'; then
  service_brand="xtschool"
  theme="${theme:-gray}"
fi

cat > /usr/share/nginx/html/web-config.js <<EOF
window.AGIXT_WEB_CONFIG = {
  serverUrl: "$(escape_js "$server_url")",
  webUrl: "$(escape_js "$web_url")",
  appName: "$(escape_js "$app_name")",
  serviceBrand: "$(escape_js "$service_brand")",
  theme: "$(escape_js "$theme")"
};
EOF
