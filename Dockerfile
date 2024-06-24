# Use Python 3.10
ARG BASE_IMAGE="python:3.10-bullseye"
FROM ${BASE_IMAGE}
# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    HNSWLIB_NO_NATIVE=1 \
    PATH="/usr/local/bin:$PATH" \
    LD_PRELOAD=libgomp.so.1 \
    LD_LIBRARY_PATH="/usr/local/lib64/:$LD_LIBRARY_PATH" \
    DEBIAN_FRONTEND=noninteractive \
    CHROME_BIN=/usr/bin/chromium \
    CHROMIUM_PATH=/usr/bin/chromium \
    CHROMIUM_FLAGS="--no-sandbox"

# Install system packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update --fix-missing && \
    apt-get upgrade -y && \
    curl -sL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --fix-missing --no-install-recommends \
    git build-essential gcc g++ sqlite3 libsqlite3-dev wget libgomp1 ffmpeg \
    python3 python3-pip python3-dev curl postgresql-client libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libatspi2.0-0 libxcomposite1 nodejs \
    libportaudio2 libasound-dev libreoffice unoconv poppler-utils chromium chromium-sandbox && \
    apt-get install -y gcc-10 g++-10 && \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-10 10 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-10 10 && \
    awk '/^deb / && !seen[$0]++ {gsub(/^deb /, "deb-src "); print}' /etc/apt/sources.list | tee -a /etc/apt/sources.list && \
    apt-get update && \
    apt-get build-dep sqlite3 -y && \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -U pip setuptools

# Set work directory
WORKDIR /

# Install SQLite3
RUN wget https://www.sqlite.org/2023/sqlite-autoconf-3420000.tar.gz && \
    tar xzf sqlite-autoconf-3420000.tar.gz && \
    if [ ! -d "/usr/lib/aarch64-linux-gnu/" ]; then mkdir -p /usr/lib/aarch64-linux-gnu/; fi && \
    cd sqlite-autoconf-3420000 && \
    ./configure && \
    make && make install && \
    cp /usr/local/lib/libsqlite3.* /usr/lib/aarch64-linux-gnu/ && \
    ldconfig && \
    cd .. && \
    rm -rf sqlite*

# Install the larger Python dependencies
COPY static-requirements.txt .
RUN pip install -r static-requirements.txt

# Install Python dependencies that may change frequently
COPY requirements.txt .
RUN pip install -r requirements.txt

# Download spaCy language model
RUN pip install spacy && \
    python -m spacy download en_core_web_sm && \
    pip install textacy==0.13.0

# Install Playwright
RUN npm install -g playwright && \
    npx playwright install && \
    playwright install

COPY . .

WORKDIR /agixt
EXPOSE 7437
ENTRYPOINT ["sh", "-c", "./launch-backend.sh"]