FROM joshxt/aicontainer:sha-f9793e7
WORKDIR /

# Install uv package manager for browser-use integration
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY docker-requirements.txt .
# Install AGiXT Requirements
RUN pip install -r docker-requirements.txt

# Force reinstall entire spacy/numpy/thinc stack to fix binary compatibility
RUN pip uninstall -y spacy spacy-legacy spacy-loggers thinc numpy
RUN pip install --no-cache-dir numpy==1.24.3 thinc spacy spacy-legacy spacy-loggers

COPY . .
WORKDIR /agixt
EXPOSE 7437
ENV RUNNING_IN_DOCKER=true
ENTRYPOINT ["python3", "run-local.py"]
