FROM python:3.10-slim-buster

COPY . .
WORKDIR /agixt

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends git build-essential ffmpeg g++ libgomp1 \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r agixt/requirements.txt \
    && pip install pipreqs \
    && pipreqs ./ --savepath gen_requirements.txt --ignore bin,etc,include,lib,lib64,env,venv \
    && pip install --no-cache-dir -r gen_requirements.txt \
    && rm gen_requirements.txt \
    && pip install --force-reinstall --no-cache-dir hnswlib \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install

EXPOSE 7437
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7437"]
