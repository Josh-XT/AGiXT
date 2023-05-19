# Install FastAPI app dependencies
FROM python:3.10-slim-buster AS base
WORKDIR /app
ADD . /app
COPY requirements.txt ./
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    apt-get install g++ -y && \
    pip install --upgrade pip && \
    pip uninstall flask-bcrypt && \
    pip uninstall bcrypt && \
    pip uninstall py-bcrypt && \
    pip install flask-bcrypt --ignore-installed --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install pipreqs && \
    pipreqs pipreqs ./ --savepath gen_requirements.txt --ignore bin,etc,include,lib,lib64,env,venv && \
    pip pip install --no-cache-dir -r gen_requirements.txt && \
    rm gen_requirements.txt && \
    pip install --force-reinstall --no-cache-dir hnswlib && \
    apt-get remove -y git build-essential && \
    apt-get install libgomp1 -y && \
    apt-get install git -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

#Run FastAPI app with Uvicorn
FROM scratch AS uvicorn
COPY --from=base / /
WORKDIR /app
COPY . .
EXPOSE 7437
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7437"]
