FROM python:3.10-slim-buster 

WORKDIR /app
COPY agixt/requirements.txt .
COPY --link agixt/ .

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y --no-install-recommends git build-essential ffmpeg
RUN apt-get install g++ -y
RUN pip install --upgrade pip
RUN pip install flask-bcrypt --ignore-installed --no-cache-dir
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pipreqs
RUN pipreqs ./ --savepath gen_requirements.txt --ignore bin,etc,include,lib,lib64,env,venv
RUN pip install --no-cache-dir -r gen_requirements.txt
RUN rm gen_requirements.txt
RUN pip install --force-reinstall --no-cache-dir hnswlib
RUN apt-get install libgomp1 -y
RUN apt-get install git -y
RUN apt-get autoremove -y
RUN rm -rf /var/lib/apt/lists/*

EXPOSE 7437
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7437"]
