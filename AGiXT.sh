#!/bin/bash
git pull
pip install poetry==1.5.1
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
export POETRY_NO_INTERACTION=1
export PLAYWRIGHT_BROWSERS_PATH=0
poetry install --with gpt4free
poetry run playwright install --with-deps
cd streamlit
poetry run streamlit run Main.py