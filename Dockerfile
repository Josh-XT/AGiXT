# Install Flask app dependencies
FROM python:3.8-slim AS base
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get remove -y git && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Run Flask app with Gunicorn
FROM base AS gunicorn
COPY . /app
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]