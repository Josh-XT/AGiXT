FROM joshxt/aicontainer:sha-ca37c5b
WORKDIR /
COPY docker-requirements.txt .
RUN pip install -r docker-requirements.txt
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "healthcheck.py"]
