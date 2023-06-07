#!/bin/bash
git clone https://github.com/Josh-XT/AGiXT
pip install poetry==1.5.1
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
cd AGiXT
poetry install --with gpt4free
poetry run playwright install
cd agixt
poetry run python app.py
cd ../streamlit
poetry run streamlit run Main.py