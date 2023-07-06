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

# Function to display a show opening style animation
display_animation() {
  # More dynamic smoke animation above ASCII art
  for i in {1..10}; do
    clear
    echo "          (   )"
    echo "        ( )  ( )"
    echo "         (  )  ("
    echo "      _____________"
    echo "     <_____________> ___"
    echo "     |             |/ _ \\"
    echo "     |               | | |"
    echo "     |               |_| |"
    echo "  ___|             |\\___/"
    echo " /    \\___________/    \\"
    echo " \\_____________________/"
    sleep 0.2

    clear
    echo "         (  ) ("
    echo "        )  (   )"
    echo "       ( )   ( )"
    echo "      _____________"
    echo "     <_____________> ___"
    echo "     |             |/ _ \\"
    echo "     |               | | |"
    echo "     |               |_| |"
    echo "  ___|             |\\___/"
    echo " /    \\___________/    \\"
    echo " \\_____________________/"
    sleep 0.2

    clear
    echo "        (  )   ("
    echo "       )   (    )"
    echo "      ( )    ( )"
    echo "      _____________"
    echo "     <_____________> ___"
    echo "     |             |/ _ \\"
    echo "     |               | | |"
    echo "     |               |_| |"
    echo "  ___|             |\\___/"
    echo " /    \\___________/    \\"
    echo " \\_____________________/"
    sleep 0.2

    clear
    echo "         (  ) ("
    echo "        )  (   )"
    echo "       ( )   ( )"
    echo "      _____________"
    echo "     <_____________> ___"
    echo "     |             |/ _ \\"
    echo "     |               | | |"
    echo "     |               |_| |"
    echo "  ___|             |\\___/"
    echo " /    \\___________/    \\"
    echo " \\_____________________/"
    sleep 0.2
  done

  # Spinning loading indicator
  echo "${BOLD}${GREEN}Loading...${RESET}"
  for i in {1..10}; do
    for s in / - \\ \|; do
      printf "\r${BOLD}${GREEN}Loading %s${RESET}" "$s"
      sleep 0.1
    done
  done
  echo
}

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
        echo "${BOLD}${MAGENTA}Welcome to the AGiXT Environment Setup!${RESET}"
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
  echo "${BOLD}${MAGENTA}Welcome to the AGiXT Installer!${RESET}"
  echo "${BOLD}${GREEN}Please choose an option:${RESET}"
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Run AGiXT Core and Streamlit Web UI with Docker (Recommended)${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Run AGiXT Core and Streamlit Web UI Locally${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Run AGiXT Core Locally${RESET}"
  echo "  ${BOLD}${YELLOW}4.${RESET} ${YELLOW}Update pulls latest from repo & pulls latest docker${RESET}"
  echo "  ${BOLD}${RED}5.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to perform the local install
local_install() {
    echo "${BOLD}${GREEN}Running local install...${RESET}"
    display_animation
    echo "AGIXT_URI=http://localhost:7437" >> .env
    echo "${BOLD}${YELLOW}Step 1: Updating the repository...${RESET}"
    git pull
    sleep 1

    # Check if the directory exists
    if [ ! -d "agixt/providers" ]; then
        echo "${BOLD}${YELLOW}Step 2: Upgrading pip...${RESET}"
        pip install --upgrade pip
        sleep 1

        echo "${BOLD}${YELLOW}Step 3: Installing requirements...${RESET}"
        pip install -r static-requirements.txt
        sleep 1
        pip install -r requirements.txt
        sleep 1

        echo "${BOLD}${YELLOW}Step 4: Installing Playwright dependencies...${RESET}"
        playwright install --with-deps
        sleep 1
    fi

    echo "${BOLD}${YELLOW}Running AGiXT Core...${RESET}"
    cd agixt && ./launch-backend.sh &
    sleep 1
}

# Function to perform the local install
local_install_with_streamlit() {
    echo "${BOLD}${GREEN}Running local install...${RESET}"
    display_animation
    echo "AGIXT_URI=http://localhost:7437" >> .env
    echo "${BOLD}${YELLOW}Step 1: Updating the repository...${RESET}"
    git pull
    sleep 1

    if [ ! -d "agixt/providers" ]; then
        echo "${BOLD}${YELLOW}Step 2: Upgrading pip...${RESET}"
        pip install --upgrade pip
        sleep 1

        echo "${BOLD}${YELLOW}Step 3: Installing requirements...${RESET}"
        pip install -r static-requirements.txt
        sleep 1
        pip install -r requirements.txt
        sleep 1

        echo "${BOLD}${YELLOW}Step 4: Installing Playwright dependencies...${RESET}"
        playwright install --with-deps
        sleep 1
    fi

    if [ ! -d "streamlit" ]; then
        echo "${BOLD}${YELLOW}Step 5: Installing Streamlit dependencies...${RESET}"
        git clone https://github.com/AGiXT/streamlit
        cd streamlit
        pip install -r requirements.txt
        sleep 1
    fi

    echo "${BOLD}${YELLOW}Step 6: Running AGiXT Core...${RESET}"
    cd agixt && ./launch-backend.sh &
    sleep 6

    echo "${BOLD}${YELLOW}Step 7: Running Streamlit Web UI...${RESET}"
    cd ../streamlit && streamlit run Main.py
}
# Function to perform the Docker install
docker_install() {
  echo "${BOLD}${GREEN}Running Docker install...${RESET}"
  display_animation
  echo "AGIXT_URI=http://agixt:7437" >> .env

  echo "${BOLD}${YELLOW}Step 1: Starting Docker Compose...${RESET}"
  docker-compose up
}

# Function to perform the Update
update() {
  echo "${BOLD}${GREEN}Running Update...${RESET}"
  display_animation

  echo "${BOLD}${YELLOW}Step 1: Updating the repository...${RESET}"
  git pull
 
    echo "${BOLD}${YELLOW}Step 2: Pulling latest Docker Images...${RESET}"
  docker-compose pull
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
      local_install_with_streamlit
      break
      ;;
    3)
      local_install
      break
      ;;
    4)
      update
      echo "${BOLD}${GREEN}Update complete.${RESET}"
      sleep 2
      ;;
    5)
      echo "${BOLD}${MAGENTA}Thank you for using AGiXT Installer. Goodbye!${RESET}"
      break
      ;;
    *)
      echo "${RED}Invalid option. Please try again.${RESET}"
      sleep 2
      ;;
  esac
done