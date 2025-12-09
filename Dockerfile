FROM joshxt/aicontainer:sha-e4bd219
WORKDIR /
COPY docker-requirements.txt .
RUN pip install --no-cache-dir -r docker-requirements.txt
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
