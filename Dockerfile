ARG BASE_IMAGE="python:3.10-slim-bullseye"
FROM ${BASE_IMAGE}

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update ; \
    apt-get upgrade -y ; \
    # leave python deps when BASE_IMAGE changes
    apt-get install -y --no-install-recommends git build-essential g++ libgomp1 ffmpeg python3 python3-pip python3-dev 

COPY --link agixt/ /agixt
WORKDIR /agixt

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    # try protobuf here if still fails on arm64
    pip install --force-reinstall hnswlib protobuf==3.20.*

ENV PATH="/usr/local/bin:$PATH"
ENV LD_PRELOAD=libgomp.so.1

ENTRYPOINT ["uvicorn", "app:app"]
CMD ["--host", "0.0.0.0", "--port", "7437"]