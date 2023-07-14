# Use Python 3.10
ARG BASE_IMAGE="python:3.10-bullseye"
FROM ${BASE_IMAGE}

# Install system packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update ; \
    apt-get upgrade -y ; \
    apt-get install -y --no-install-recommends git build-essential g++ libgomp1 ffmpeg python3 python3-pip python3-dev curl postgresql-client libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libatspi2.0-0 libxcomposite1 && \
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

# Copy only static-requirements, to cache them in docker layer
COPY static-requirements.txt .
# Install static dependencies
RUN pip install -r static-requirements.txt

# Copy only requirements, to cache them in docker layer
COPY requirements.txt .
# Install application dependencies
ARG HNSWLIB_NO_NATIVE=1
RUN pip install -r requirements.txt
RUN pip install --force-reinstall hnswlib protobuf==3.20.*

# Install Node.js
RUN curl -sL https://deb.nodesource.com/setup_14.x | bash -
RUN apt-get install -y nodejs

# Install Playwright
RUN npm install -g playwright
RUN npx playwright install

RUN playwright install

COPY . .

WORKDIR /agixt

CMD ["python", "/agixt/Hub.py"]

EXPOSE 7437
ENTRYPOINT ["sh", "-c", "./launch-backend.sh"]