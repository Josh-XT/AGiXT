FROM python:3.10-slim-buster 

WORKDIR /app
COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    apt-get install g++ -y && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --force-reinstall --no-cache-dir hnswlib && \
    apt-get remove -y git build-essential && \
    apt-get install libgomp1 -y && \
    apt-get install git -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY --link . .
EXPOSE 7437
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7437"]
