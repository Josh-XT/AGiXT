FROM joshxt/aicontainer:sha-ca37c5b
WORKDIR /

# Install uv package manager for browser-use integration
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY docker-requirements.txt .
RUN pip install -r docker-requirements.txt
COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
