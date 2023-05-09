#!/bin/bash

# Get the local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

# Run the Docker command
docker run -it --pull always -p 3000:3000 -e NEXT_PUBLIC_API_URI=http://$LOCAL_IP:7437 ghcr.io/jamesonrgrieve/agent-llm-frontend:main
