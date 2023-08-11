# Use Python 3.10
ARG BASE_IMAGE="python:3.10-bullseye"
FROM ${BASE_IMAGE}
# Set environment variables
ARG HNSWLIB_NO_NATIVE=1
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    PATH="/usr/local/bin:$PATH" \
    LD_PRELOAD=libgomp.so.1

# Install system packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update --fix-missing ; \
    apt-get upgrade -y ; \
    apt-get install -y --fix-missing --no-install-recommends git build-essential gcc g++ sqlite3 libsqlite3-dev wget libgomp1 ffmpeg python3 python3-pip python3-dev curl postgresql-client libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libatspi2.0-0 libxcomposite1 && \
    awk '/^deb / && !seen[$0]++ {gsub(/^deb /, "deb-src "); print}' /etc/apt/sources.list | tee -a /etc/apt/sources.list && \
    apt-get update && \
    apt-get build-dep sqlite3 -y && \
    rm -rf /var/lib/apt/lists/* && \
    wget https://www.sqlite.org/2023/sqlite-autoconf-3420000.tar.gz && \
    tar vvvvvxzf sqli* && \
    cd sqlite-autoconf-3420000 && \
    ./configure && \
    make && make install && \
    cp /usr/local/lib/libsqlite3.* /usr/lib/aarch64-linux-gnu/ && \
    ldconfig

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -U pip setuptools

# Set work directory
WORKDIR /

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

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
