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
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Local Install${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Docker Install${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Update${RESET}"
  echo "  ${BOLD}${RED}4.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to perform the local install
local_install() {
  echo "${BOLD}${GREEN}Running local install...${RESET}"
  display_animation

  echo "${BOLD}${YELLOW}Step 1: Updating the repository...${RESET}"
  git pull
  sleep 1

  echo "${BOLD}${YELLOW}Step 2: Upgrading pip...${RESET}"
  pip install --upgrade pip
  sleep 1

  echo "${BOLD}${YELLOW}Step 3: Installing requirements...${RESET}"
  pip install -r requirements.txt
  sleep 1

  echo "${BOLD}${YELLOW}Step 4: Installing Playwright dependencies...${RESET}"
  playwright install --with-deps
  sleep 1

  echo "${BOLD}${YELLOW}Step 5: Changing directory to 'streamlit'...${RESET}"
  cd streamlit || { echo "${RED}Error: Failed to change directory to 'streamlit'${RESET}"; exit 1; }
  sleep 1

  echo "${BOLD}${YELLOW}Step 6: Running Streamlit...${RESET}"
  streamlit run Main.py
}

# Function to perform the Docker install
docker_install() {
  echo "${BOLD}${GREEN}Running Docker install...${RESET}"
  display_animation

  echo "${BOLD}${YELLOW}Step 1: Starting Docker Compose...${RESET}"
  docker-compose up
}

# Function to perform the Update
update() {
  echo "${BOLD}${GREEN}Running Update...${RESET}"
  display_animation

  echo "${BOLD}${YELLOW}Step 1: Updating the repository...${RESET}"
  git pull
}

# Main loop to display the menu and handle user input
while true; do
  display_menu
  read -p "${BOLD}${CYAN}Enter your choice:${RESET} " choice

  case "$choice" in
    1)
      local_install
      break
      ;;
    2)
      docker_install
      break
      ;;
    3)
      update
      echo "${BOLD}${GREEN}Update complete.${RESET}"
      sleep 2
      ;;
    4)
      echo "${BOLD}${MAGENTA}Thank you for using AGiXT Installer. Goodbye!${RESET}"
      break
      ;;
    *)
      echo "${RED}Invalid option. Please try again.${RESET}"
      sleep 2
      ;;
  esac
done
