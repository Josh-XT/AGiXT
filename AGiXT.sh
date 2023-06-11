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
    echo ""
    echo ""
    echo ""
    echo "  ////^\\\\\\\\"
    echo "  | ^   ^ |"
    echo " @|(o) (o)|@"
    echo "  |    >  |     (   )"
    echo "  |   ___ |   ( )  ( )"
    echo "   \___?__/    (  )  ("
    echo "   __|  |__ _____________"
    echo "  /        <_____________> ___"
    echo " /    ^  ^ |             |/ _ \\"
    echo "/  /|   ^  |               | | |"
    echo "\_/ |  \_/ |               |_| |"
    echo "    |   ___|             |\\___/"
    echo "    |  /    \\___________/    \\"
    echo "    |  \\_____________________/"
    sleep 0.65

    clear
    echo ""
    echo ""
    echo ""
    echo "  ////^\\\\\\\\ |*********************|"
    echo "  | ^   ^ | |AGiXT Author: Josh-XT|"
    echo " @|(o) (o)|@| ____________________|"
    echo "  |    >  | |/ (  ) ("
    echo "  |   _O_ |   )  (   )"
    echo "   \___?__/   ( )  ( )"
    echo "   __|  |__ _____________"
    echo "  /        <_____________> ___"
    echo " /    ^  ^ |             |/ _ \\"
    echo "/  /|   ^  |               | | |"
    echo "\_/ |  \_/ |               |_| |"
    echo "/   |   ___|             |\\___/"
    echo "    |  /    \\___________/    \\"
    echo "    |  \\_____________________/"
    sleep 0.65

    clear
    echo ""
    echo ""
    echo ""
    echo "  ////^\\\\\\\\ |*********************|"
    echo "  | ^   ^ | | Join Us On Discord! |"
    echo " @|(_) (_)|@| ____________________|"
    echo "  |    >  | |/   )   ("
    echo "  |   _o_ |  )   (    )"
    echo "   \___?__/  ( )    ( )"
    echo "   __|  |__ _____________"
    echo "  /        <_____________> ___"
    echo " /    ^  ^ |             |/ _ \\"
    echo "/  /|   ^  |               | | |"
    echo "\_/ |  \_/ |               |_| |"
    echo "/   |   ___|             |\\___/"
    echo "    |  /    \\___________/    \\"
    echo "    |  \\_____________________/"
    sleep 0.65

    clear
    echo ""
    echo ""
    echo ""
    echo "  ////^\\\\\\\\ |*********************|"
    echo "  | ^   ^ | |discord.gg/UCtYPvBdEC|"
    echo " @|(o) (o)|@| ____________________|"
    echo "  |    >  | |/ (  ) ("
    echo "  |   _O_ |   )  (   )"
    echo "   \___?__/  ( )   ( )"
    echo "   __|  |__ _____________"
    echo "  /        <_____________> ___"
    echo " /    ^  ^ |             |/ _ \\"
    echo "/  /|   ^  |               | | |"
    echo "\_/ |  \_/ |               |_| |"
    echo "/   |   ___|             |\\___/"
    echo "    |  /    \\___________/    \\"
    echo "    |  \\_____________________/"
    sleep 0.65
  done
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
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Local Install/Run${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Docker Install/Run${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Update pulls latest from repo & pulls latest docker${RESET}"
  echo "  ${BOLD}${RED}4.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to update the window title
update_window_title() {
  step_number="$1"
  step_description="$2"
  echo -ne "\033]0;Step $step_number: $step_description\007"
}

# Function to perform the local install
local_install() {
  clear
  echo "${BOLD}${GREEN}Running local install...${RESET}"

  steps=(
    "Updating install repos...:if command -v apt &>/dev/null; then apt update; elif command -v zypper &>/dev/null; then zypper refresh; elif command -v dnf &>/dev/null; then dnf check-update; elif command -v urpmi &>/dev/null; then urpmi.update -a; elif command -v slackpkg &>/dev/null; then slackpkg update; elif command -v slapt-get &>/dev/null; then slapt-get --update; elif command -v cards &>/dev/null; then cards sync; elif command -v pacman &>/dev/null; then pacman -Sy; elif command -v apk &>/dev/null; then apk update; elif command -v smart &>/dev/null; then smart update; elif command -v pkcon &>/dev/null; then pkcon refresh; elif command -v emerge &>/dev/null; then emerge --sync; elif command -v lin &>/dev/null; then lin moonbase; elif command -v scribe &>/dev/null; then scribe update; elif command -v nix-channel &>/dev/null; then nix-channel --update; elif command -v xbps-install &>/dev/null; then xbps-install -S; elif command -v pkg &>/dev/null; then pkg update; elif command -v csup &>/dev/null; then csup -L 2 -h cvsup.FreeBSD.org path_to_supfile; elif command -v portsnap &>/dev/null; then portsnap update; else echo 'No package manager found.'; fi"
    "Updating python Install...:if command -v apt-get &>/dev/null; then apt-get install python=3.10.12; elif command -v zypper &>/dev/null; then zypper install -t package python=3.10.12; elif command -v dnf &>/dev/null; then dnf install python=3.10.12; elif command -v urpmi &>/dev/null; then urpmi python=3.10.12; elif command -v slackpkg &>/dev/null; then slackpkg install python=3.10.12; elif command -v slapt-get &>/dev/null; then slapt-get --install python=3.10.12; elif command -v netpkg &>/dev/null; then netpkg python=3.10.12; elif command -v cards &>/dev/null; then cards install python=3.10.12; elif command -v pacman &>/dev/null; then pacman -S python=3.10.12; elif command -v apk &>/dev/null; then apk add python=3.10.12; elif command -v smart &>/dev/null; then smart install python=3.10.12; elif command -v pkcon &>/dev/null; then pkcon install python=3.10.12; elif command -v emerge &>/dev/null; then emerge python=3.10.12; elif command -v lin &>/dev/null; then lin python=3.10.12; elif command -v cast &>/dev/null; then cast python=3.10.12; elif command -v nix-env &>/dev/null; then nix-env -i python=3.10.12; elif command -v xbps-install &>/dev/null; then xbps-install python=3.10.12; elif command -v snap &>/dev/null; then snap install python=3.10.12; elif command -v pkg_add &>/dev/null; then pkg_add -r python=3.10.12; elif command -v pkg &>/dev/null; then pkg install python=3.10.12; elif command -v make &>/dev/null; then cd port_dir && make && make install python=3.10.12; else echo 'No package manager found.'; fi"
    "Updating docker-compose Install...:docker -v || if command -v apt-get &>/dev/null; then apt-get install docker-compose; elif command -v zypper &>/dev/null; then zypper install -t package docker-compose; elif command -v dnf &>/dev/null; then dnf install docker-compose; elif command -v urpmi &>/dev/null; then urpmi docker-compose; elif command -v slackpkg &>/dev/null; then slackpkg install docker-compose; elif command -v slapt-get &>/dev/null; then slapt-get --install docker-compose; elif command -v netpkg &>/dev/null; then netpkg docker-compose; elif command -v cards &>/dev/null; then cards install docker-compose; elif command -v pacman &>/dev/null; then pacman -S docker-compose; elif command -v apk &>/dev/null; then apk add docker-compose; elif command -v smart &>/dev/null; then smart install docker-compose; elif command -v pkcon &>/dev/null; then pkcon install docker-compose; elif command -v emerge &>/dev/null; then emerge docker-compose; elif command -v lin &>/dev/null; then lin docker-compose; elif command -v cast &>/dev/null; then cast docker-compose; elif command -v nix-env &>/dev/null; then nix-env -i docker-compose; elif command -v xbps-install &>/dev/null; then xbps-install docker-compose; elif command -v snap &>/dev/null; then snap install docker-compose; elif command -v pkg_add &>/dev/null; then pkg_add -r docker-compose; elif command -v pkg &>/dev/null; then pkg install docker-compose; elif command -v make &>/dev/null; then cd port_dir && make && make install docker-compose; else echo 'No package manager found.'; fi"
    "Updating git Install...:git || if command -v apt-get &>/dev/null; then apt-get install git; elif command -v zypper &>/dev/null; then zypper install -t package git; elif command -v dnf &>/dev/null; then dnf install git; elif command -v urpmi &>/dev/null; then urpmi git; elif command -v slackpkg &>/dev/null; then slackpkg install git; elif command -v slapt-get &>/dev/null; then slapt-get --install git; elif command -v netpkg &>/dev/null; then netpkg git; elif command -v cards &>/dev/null; then cards install git; elif command -v pacman &>/dev/null; then pacman -S git; elif command -v apk &>/dev/null; then apk add git; elif command -v smart &>/dev/null; then smart install git; elif command -v pkcon &>/dev/null; then pkcon install git; elif command -v emerge &>/dev/null; then emerge git; elif command -v lin &>/dev/null; then lin git; elif command -v cast &>/dev/null; then cast git; elif command -v nix-env &>/dev/null; then nix-env -i git; elif command -v xbps-install &>/dev/null; then xbps-install git; elif command -v snap &>/dev/null; then snap install git; elif command -v pkg_add &>/dev/null; then pkg_add -r git; elif command -v pkg &>/dev/null; then pkg install git; elif command -v make &>/dev/null; then cd port_dir && make && make install git; else echo 'No package manager found.'; fi"
    "Installing dbus-x11 package...:if command -v apt-get &>/dev/null; then apt-get install dbus-x11; elif command -v zypper &>/dev/null; then zypper install -t package dbus-x11; elif command -v dnf &>/dev/null; then dnf install dbus-x11; elif command -v urpmi &>/dev/null; then urpmi dbus-x11; elif command -v slackpkg &>/dev/null; then slackpkg install dbus-x11; elif command -v slapt-get &>/dev/null; then slapt-get --install dbus-x11; elif command -v netpkg &>/dev/null; then netpkg dbus-x11; elif command -v cards &>/dev/null; then cards install dbus-x11; elif command -v pacman &>/dev/null; then pacman -S dbus-x11; elif command -v apk &>/dev/null; then apk add dbus-x11; elif command -v smart &>/dev/null; then smart install dbus-x11; elif command -v pkcon &>/dev/null; then pkcon install dbus-x11; elif command -v emerge &>/dev/null; then emerge dbus-x11; elif command -v lin &>/dev/null; then lin dbus-x11; elif command -v cast &>/dev/null; then cast dbus-x11; elif command -v nix-env &>/dev/null; then nix-env -i dbus-x11; elif command -v xbps-install &>/dev/null; then xbps-install dbus-x11; elif command -v snap &>/dev/null; then snap install dbus-x11; elif command -v pkg_add &>/dev/null; then pkg_add -r dbus-x11; elif command -v pkg &>/dev/null; then pkg install dbus-x11; elif command -v make &>/dev/null; then cd port_dir && make && make install dbus-x11; else echo 'No package manager found.'; fi"
    "Checking AGiXT directory...:if [[ ! -d \"AGiXT\" ]]; then git clone https://github.com/Josh-XT/AGiXT && cd ./AGiXT; else echo \"AGiXT directory already exists.\"; fi"
    "Upgrading pip...:pip install --upgrade pip"
    "Installing requirements...:pip install -r $PWD/static-requirements.txt >./dev/null 2>&1 || pip install -r $PWD/AGiXT/static-requirements.txt >./dev/null 2>&1"
    "Installing requirements...:pip install -r $PWD/requirements.txt >./dev/null 2>&1 || pip install -r $PWD/AGiXT/requirements.txt >./dev/null 2>&1"
    "Installing Playwright dependencies...:playwright || playwright install --with-deps"
    "Running Streamlit...:x-terminal-emulator -e 'cd $PWD/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4'' || x-terminal-emulator -e 'cd $PWD/AGIXT/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4'"
    "Running Streamlit...:x-terminal-emulator -e 'streamlit run $PWD/streamlit/Main.py' || x-terminal-emulator -e 'streamlit run $PWD/AGiXT/streamlit/Main.py'"
  )
  j = 0
  for ((i = 0; i < ${#steps[@]}; i++)); do
    step=${steps[$i]}
    description=${step%%:*}
    command=${step#*:}
    step_number=$((i + 1))

    update_window_title "$step_number" "$description"

    display_animation &
    animation_pid=$!

    # Check if the command is the Streamlit run command
    if [[ $command == "x-terminal-emulator"* ]]; then
      # Sleep for a few seconds to allow Streamlit to start in the new terminal
      sleep 5
      j++
      # Remove the & at the end to run in the foreground
      eval "$command"
      if [j>1]; then
        break
      fi
    fi

    # Execute the command in the background and suppress the output
    (eval "$command" >> ./log.txt 2>&1) &

    # Wait for the animation process to complete
    wait "$animation_pid"
  done

  echo "${BOLD}${GREEN}Installation complete.${RESET}"
  update_window_title "" "Installation Complete"
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

  echo "${BOLD}${YELLOW}Step 1: Checking AGiXT directory...${RESET}"
  if [[ ! -d "AGiXT" ]]; then
    echo "${RED}AGiXT directory not found.${RESET}"
    exit 1
  fi

  echo "${BOLD}${YELLOW}Step 2: Checking Streamlit directory...${RESET}"
  if [[ ! -d "AGiXT/streamlit" ]]; then
    echo "${RED}Streamlit directory not found.${RESET}"
    exit 1
  fi

  echo "${BOLD}${YELLOW}Step 3: Updating the repository...${RESET}"
  cd AGiXT
  git pull
  cd ..

  echo "${BOLD}${YELLOW}Step 4: Pulling latest Docker Images...${RESET}"
  docker compose pull
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

