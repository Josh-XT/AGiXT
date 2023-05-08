FROM python:3.10-slim-buster

RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends git build-essential g++ libgomp1 && \
    apt-get autoremove -y && \
    pip install --upgrade pip && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 flaskgroup 
RUN adduser --uid 1000 --gid 1000 --home /app flaskuser --disabled-login

USER flaskuser

WORKDIR /app

VOLUME /app/.cache

COPY --chown=flaskuser:flaskgroup . .

RUN pip install -r requirements.txt && \
    pip install hnswlib fastapi uvicorn

EXPOSE 7437
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7437"]
