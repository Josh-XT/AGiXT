#!/bin/sh
echo "Starting AGiXT..."
sed -i 's/GptGo,//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/GptGo//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/GptForLove,//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/GptForLove//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/Chatgpt4Online,//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/Chatgpt4Online//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/ChatBase,//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/ChatBase//g' /usr/local/lib/python3.10/site-packages/g4f/models.py
sed -i 's/You,//g' /usr/local/lib/python3.10/site-packages/g4f/models.py

if [ "$DB_CONNECTED" = "true" ]; then
    sleep 5
    echo "Connecting to DB..."
    python3 DBConnection.py
fi
workers="${UVICORN_WORKERS:-10}"
uvicorn app:app --host 0.0.0.0 --port 7437 --workers $workers --proxy-headers