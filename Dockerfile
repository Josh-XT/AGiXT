FROM joshxt/aicontainer:sha-646eb9a
WORKDIR /
# COPY docker-requirements.txt .
# RUN pip install --no-cache-dir -r docker-requirements.txt
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
