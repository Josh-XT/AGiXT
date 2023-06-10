#!/bin/bash
git pull
pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps
cd streamlit
streamlit run Main.py