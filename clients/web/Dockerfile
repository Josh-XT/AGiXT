FROM nginx:1.30.1-alpine

ENV AGIXT_API_UPSTREAM=http://agixt:7437

COPY clients/desktop/src/ /usr/share/nginx/html/
COPY clients/web/web-runtime.js /usr/share/nginx/html/web-runtime.js
COPY clients/web/oauth-close.html /usr/share/nginx/html/oauth-close.html
COPY clients/web/nginx.conf.template /etc/nginx/templates/default.conf.template

RUN set -eux; \
    grep -q 'web-runtime.js' /usr/share/nginx/html/index.html || \
    sed -i '/<script src="frontend-log.js"><\/script>/i\    <script src="web-runtime.js"></script>' /usr/share/nginx/html/index.html

EXPOSE 80
