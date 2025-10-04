FROM joshxt/aicontainer:sha-b7107e6

# Minimize layer size by clearing inherited caches before installing new deps
RUN python3 -m pip cache purge || true \
	&& rm -rf /root/.cache/pip/* /tmp/* /var/tmp/*

ENV PIP_NO_CACHE_DIR=1

WORKDIR /
COPY docker-requirements.txt .
RUN mkdir -p /var/tmp/pip-build \
	&& TMPDIR=/var/tmp/pip-build PIP_TMPDIR=/var/tmp/pip-build \
	   pip install --no-cache-dir -r docker-requirements.txt \
	&& rm -rf /var/tmp/pip-build
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
