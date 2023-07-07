#!/bin/bash

# Define colors and formatting
BOLD=$(tput bold)
GREEN=$(tput setaf 2)
CYAN=$(tput setaf 6)
YELLOW=$(tput setaf 3)
RED=$(tput setaf 1)
MAGENTA=$(tput setaf 5)
BLUE=$(tput setaf 4)
RESET=$(tput sgr0)

# Check if .env file exists
environment_setup() {
    if [[ ! -f ".env" ]]; then
        clear
        echo "${BOLD}${CYAN}"
        echo "    ___   _______ _  ________"
        echo "   /   | / ____(_) |/ /_  __/"
        echo "  / /| |/ / __/ /|   / / /   "
        echo " / ___ / /_/ / //   | / /    "
        echo "/_/  |_\____/_//_/|_|/_/     "
        echo "                              "
        echo "----------------------------------------------------${RESET}"
        echo "${BOLD}${MAGENTA}Visit our documentation at https://AGiXT.com ${RESET}"
        echo "${BOLD}${MAGENTA}Welcome to the AGiXT Environment Setup!${RESET}"
        read -p "Do you want AGiXT to automatically update when launched? AGiXT Hubs always update automatically. (Y for yes, N for No): " auto_update
        if [[ "$auto_update" == [Yy]* ]]; then
            auto_update="true"
        else
            auto_update="false"
        fi
        read -p "Do you want to set an API key for AGiXT? (Y for yes, N for No): " use_api_key
        if [[ "$use_api_key" == [Yy]* ]]; then
            read -p "Enter API key: " api_key
        fi
        read -p "Do you have your own AGiXT Hub fork that you would like to install with? (Y for yes, N for No): " hub_repo
        if [[ "$hub_repo" == [Yy]* ]]; then
            read -p "Enter your AGiXT Hub fork repo name (e.g. AGiXT/light-hub): " github_repo
            read -p "Is your AGiXT Hub fork private? It will require credentials if it is not public. (Y for yes, N for No): " is_private
            if [[ "$is_private" == [Yy]* ]]; then
                read -p "Enter your GitHub username: " github_username
                read -p "Enter your GitHub token: " github_token
            fi
        fi
        read -p "Enter the number of AGiXT workers to run with, default is 4: " workers
        if [[ "$workers" != "" ]]; then
            if [[ $workers =~ ^[0-9]+$ && $workers -gt 0 ]]; then
                agixt_workers=$workers
            else
                echo "Invalid number of workers, defaulting to 4"
                agixt_workers=4
            fi
        fi
        read -p "Do you want to use postgres? (Y for yes, N for No and to use file structure instead): " use_db
        if [[ "$use_db" == [Yy]* ]]; then
            read -p "Do you want to use an existing postgres database? (Y for yes, N for No and to create a new one automatically): " use_own_db
            if [[ "$use_own_db" == [Yy]* ]]; then
                db_connection="true"
                read -p "Enter postgres host: " postgres_host
                read -p "Enter postgres port: " postgres_port
                read -p "Enter postgres database name: " postgres_database
                read -p "Enter postgres username: " postgres_username
            fi
            read -p "Enter postgres password: " postgres_password
        fi
        echo "DB_CONNECTED=${db_connection:-false}" >> .env
        echo "AGIXT_AUTO_UPDATE=${auto_update:-true}" >> .env
        echo "AGIXT_HUB=${github_repo:-AGiXT/light-hub}" >> .env
        echo "AGIXT_URI=${agixt_uri:-http://localhost:7437}" >> .env
        echo "AGIXT_API_KEY=${api_key:-}" >> .env
        echo "UVICORN_WORKERS=${agixt_workers:-4}" >> .env
        echo "GITHUB_USER=${github_username:-}" >> .env
        echo "GITHUB_TOKEN=${github_token:-}" >> .env
        echo "POSTGRES_SERVER=${postgres_host:-db}" >> .env
        echo "POSTGRES_PORT=${postgres_port:-5432}" >> .env
        echo "POSTGRES_DB=${postgres_database:-postgres}" >> .env
        echo "POSTGRES_USER=${postgres_username:-postgres}" >> .env
        echo "POSTGRES_PASSWORD=${postgres_password:-postgres}" >> .env
    fi
    source .env
}
# Function to display the menu
display_menu() {
  clear
  echo "${BOLD}${CYAN}"
  echo "    ___   _______ _  ________"
  echo "   /   | / ____(_) |/ /_  __/"
  echo "  / /| |/ / __/ /|   / / /   "
  echo " / ___ / /_/ / //   | / /    "
  echo "/_/  |_\____/_//_/|_|/_/     "
  echo "                              "
  echo "----------------------------------------------------${RESET}"
  echo "${BOLD}${MAGENTA}Visit our documentation at https://AGiXT.com ${RESET}"
  echo "${BOLD}${MAGENTA}Welcome to the AGiXT Installer!${RESET}"
  echo "${BOLD}${GREEN}Please choose an option:${RESET}"
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Run AGiXT with Docker (Recommended)${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Run AGiXT Locally (Developers Only - Not Recommended or Supported) ${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Update AGiXT ${RESET}"
  echo "  ${BOLD}${RED}4.${RESET} ${RED}Wipe AGiXT Hub (Irreversible)${RESET}"
  echo "  ${BOLD}${RED}5.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to perform the Update
update() {
  echo "${BOLD}${GREEN}Running Updates...${RESET}"
  echo "${BOLD}${YELLOW}Updating AGiXT Core...${RESET}"
  git pull
  echo "${BOLD}${YELLOW}Updating AGiXT Streamlit Web UI...${RESET}"
  if [ ! -d "streamlit" ]; then
    git clone https://github.com/AGiXT/streamlit
  fi
  cd streamlit
  git pull
  cd ..
  echo "${BOLD}${YELLOW}Updating Docker Images...${RESET}"
  docker-compose pull
}

# Function to perform the Docker install
docker_install() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://agixt:7437" >> .env
  source .env
  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    update
  fi

  if [ ! -d "streamlit" ]; then
      echo "${BOLD}${YELLOW}Cloning Streamlit Repository...${RESET}"
      git clone https://github.com/AGiXT/streamlit
  fi

  echo "${BOLD}${GREEN}Running Docker install...${RESET}"
  echo "${BOLD}${YELLOW}Starting Docker Compose...${RESET}"
  if [[ "$DB_CONNECTED" == "true" ]]; then
    docker-compose -f docker-compose-postgres.yml up
  else
    docker-compose up
  fi
}

# Function to perform the local install
local_install() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://localhost:7437" >> .env
  source .env
  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    echo "${BOLD}${YELLOW}Checking for updates...${RESET}"
    git pull
    if [ ! -d "streamlit" ]; then
      echo "${BOLD}${YELLOW}Installing Streamlit dependencies...${RESET}"
      git clone https://github.com/AGiXT/streamlit
    fi
    cd streamlit
    git pull
    cd ..
  fi

  echo "${BOLD}${GREEN}Running local install...${RESET}"
  echo "${BOLD}${YELLOW}Updating the repository...${RESET}"
  git pull
  sleep 1

  # Check if the directory exists
  if [ ! -d "agixt/providers" ]; then
      echo "${BOLD}${YELLOW}Upgrading pip...${RESET}"
      pip install --upgrade pip
      sleep 1

      echo "${BOLD}${YELLOW}Installing requirements...${RESET}"
      pip install -r static-requirements.txt
      sleep 1
      pip install -r requirements.txt
      sleep 1

      echo "${BOLD}${YELLOW}Installing Playwright dependencies...${RESET}"
      playwright install --with-deps
      sleep 1
  fi

  if [ ! -d "streamlit" ]; then
      echo "${BOLD}${YELLOW}Installing Streamlit dependencies...${RESET}"
      git clone https://github.com/AGiXT/streamlit
      cd streamlit
      pip install -r requirements.txt
      sleep 1
  fi

  echo "${BOLD}${YELLOW}Running AGiXT Core...${RESET}"
  cd agixt && ./launch-backend.sh &
  echo "${BOLD}${YELLOW}Please wait...${RESET}"
  sleep 10
  echo "${BOLD}${YELLOW}Running Streamlit Web UI...${RESET}"
  cd streamlit && streamlit run Main.py
}

wipe_hub() {
  read -p "Are you sure you want to wipe your AGiXT Hub? This is irreversible. (Y for yes, N for No): " wipe_hub
  if [[ "$wipe_hub" == [Yy]* ]]; then
    docker-compose down --remove-orphans
    echo "${BOLD}${YELLOW}Wiping AGiXT Hub...${RESET}"
    files=(
      "agixt/extensions"
      "agixt/chains"
      "agixt/.github"
      "agixt/prompts"
      "agixt/providers"
      "agixt/LICENSE"
      "agixt/README.md"
      "agixt/"*_main.zip
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
  fi
}

environment_setup
# Main loop to display the menu and handle user input
while true; do
  display_menu
  read -p "${BOLD}${CYAN}Enter your choice:${RESET} " choice

  case "$choice" in
    1)
      docker_install
      break
      ;;
    2)
      local_install
      break
      ;;
    3)
      update
      echo "${BOLD}${GREEN}Update complete.${RESET}"
      sleep 2
      ;;
    4)
      wipe_hub
      break
      ;;
    *)
      echo "${BOLD}${MAGENTA}Thank you for using AGiXT Installer. Goodbye!${RESET}"
      break
      ;;
  esac
done