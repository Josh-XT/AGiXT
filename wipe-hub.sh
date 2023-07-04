#!/bin/bash

# Define the files and folders to be deleted
files=(
    "agixt/extensions"
    "agixt/chains"
    "agixt/.github"
    "agixt/prompts"
    "agixt/LICENSE"
    "agixt/README.md"
    "agixt/hub_main.zip"
)

# Recursively delete files and folders
for file in "${files[@]}"; do
    if [ -e "$file" ]; then
        echo "Deleting: $file"
        rm -rf "$file"
    else
        echo "File or folder not found: $file"
    fi
done
docker-compose down --remove-orphans
rm -rf ./data