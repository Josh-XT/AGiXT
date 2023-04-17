# Build React app
FROM node:14 AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Serve React app with Nginx
FROM nginx:alpine AS nginx
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Install Flask app dependencies
FROM python:3.8-slim AS base
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Run Flask app with Gunicorn
FROM base AS gunicorn
COPY . /app
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
