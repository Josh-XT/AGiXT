ARG BASE_IMAGE="python:3.10-bullseye"
FROM ${BASE_IMAGE}

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update ; \
    apt-get upgrade -y ; \
    apt-get install -y --no-install-recommends git build-essential g++ libgomp1 ffmpeg python3 python3-pip python3-dev 


RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -U pip setuptools && \
    pip install poetry==1.5.1


ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    POETRY_NO_INTERACTION=1 \
    PLAYWRIGHT_BROWSERS_PATH=0

WORKDIR /
COPY pyproject.toml .
COPY poetry.lock .
ARG HNSWLIB_NO_NATIVE=1
RUN poetry install --no-root --with gpt4free
RUN poetry run playwright install --with-deps
COPY . .

ENV PATH="/usr/local/bin:$PATH"
ENV LD_PRELOAD=libgomp.so.1

WORKDIR /agixt
ENTRYPOINT ["sh", "-c", "poetry run streamlit run /streamlit/Main.py & poetry run uvicorn app:app --host 0.0.0.0 --port 7437 --workers 2"]
