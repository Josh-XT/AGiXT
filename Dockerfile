FROM joshxt/aicontainer:sha-b7107e6

# Minimize layer size by clearing inherited caches before installing new deps
RUN python3 -m pip cache purge || true \
	&& rm -rf /root/.cache/pip/* /tmp/* /var/tmp/*

ENV PIP_NO_CACHE_DIR=1

WORKDIR /
COPY docker-requirements.txt .
RUN pip install --no-cache-dir -r docker-requirements.txt
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
