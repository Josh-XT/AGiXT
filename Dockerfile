# Install Flask app dependencies
FROM python:3.8-slim-buster AS base
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update
RUN apt-get install -y --no-install-recommends git build-essential
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get remove -y git build-essential
RUN apt-get autoremove -y
RUN rm -rf /var/lib/apt/lists/*

# Run Flask app with Gunicorn
FROM base AS gunicorn
COPY . /app
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]