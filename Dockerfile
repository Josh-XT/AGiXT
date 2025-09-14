FROM joshxt/aicontainer:sha-f9793e7
WORKDIR /

# Install uv package manager for browser-use integration
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Fix numpy/spacy compatibility issues by updating to compatible versions
# This ensures spacy/thinc work with the numpy version
RUN pip install --upgrade numpy==1.26.4 scipy spacy thinc spacy-legacy spacy-loggers

COPY docker-requirements.txt .
# Install AGiXT Requirements
RUN pip install -r docker-requirements.txt

COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
