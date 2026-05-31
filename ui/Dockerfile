FROM nginx:1.30.1-alpine

ARG UI_ASSET_VERSION=dev
ENV AGIXT_API_UPSTREAM=http://agixt-api:7437
LABEL workconductor.ui_asset_version="${UI_ASSET_VERSION}"

COPY ui/src/ /usr/share/nginx/html/
COPY ui/public/ /usr/share/nginx/html/public/
COPY ui/web-runtime.js /usr/share/nginx/html/web-runtime.js
COPY ui/oauth-close.html /usr/share/nginx/html/oauth-close.html
COPY ui/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY ui/docker-entrypoint.d/00-write-web-config.sh /docker-entrypoint.d/00-write-web-config.sh

RUN set -eux; \
    ASSET_VERSION="${UI_ASSET_VERSION}"; \
    chmod +x /docker-entrypoint.d/00-write-web-config.sh; \
    grep -q 'web-config.js' /usr/share/nginx/html/index.html || \
    sed -i '/<!-- Theme bootstrap/i\    <script src="web-config.js"></script>' /usr/share/nginx/html/index.html; \
    grep -q 'web-runtime.js' /usr/share/nginx/html/index.html || \
    sed -i '/<script src="frontend-log.js"><\/script>/i\    <script src="web-runtime.js"></script>' /usr/share/nginx/html/index.html; \
    sed -i -E "s#(href|src)=\"([^\"?]+\\.(js|css))(\\?v=[^\"]*)?\"#\\1=\"\\2?v=${ASSET_VERSION}\"#g" /usr/share/nginx/html/index.html

EXPOSE 80
