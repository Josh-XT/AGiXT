# Use Python 3.10
ARG BASE_IMAGE="python:3.10-bullseye"
FROM ${BASE_IMAGE}

# Install system packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update ; \
    apt-get upgrade -y ; \
    apt-get install -y --no-install-recommends git build-essential g++ libgomp1 ffmpeg python3 python3-pip python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Update pip
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -U pip setuptools

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    PATH="/usr/local/bin:$PATH" \
    LD_PRELOAD=libgomp.so.1 \
    UVICORN_WORKERS=4

# Set work directory
WORKDIR /

# Copy only requirements, to cache them in docker layer
COPY requirements.txt .

# Install application dependencies
ARG HNSWLIB_NO_NATIVE=1
RUN pip install -r requirements.txt
RUN pip install --force-reinstall hnswlib protobuf==3.20.*
RUN playwright install --with-deps

# Copy local code to the container image.
COPY . .

# Set work directory
WORKDIR /agixt

# Set entry point
ENTRYPOINT ["sh", "-c", "streamlit run /streamlit/Main.py & uvicorn app:app --host 0.0.0.0 --port 7437 --workers $UVICORN_WORKERS"]
