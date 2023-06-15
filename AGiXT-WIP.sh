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
  for i in {1..5}; do
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
    echo "/   |   ___|             |\\___/"
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
    echo "  |    >  | |/  )   (  )"
    echo "  |   _o_ |  )  (  (  ("
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
    echo "  |   _O_ |   ) (    )"
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
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Install Locally & Run Streamlit${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Run Local Install${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Install Docker & Run Container${RESET}"
  echo "  ${BOLD}${YELLOW}4.${RESET} ${YELLOW}Run Docker Container${RESET}"
  echo "  ${BOLD}${YELLOW}5.${RESET} ${YELLOW}Update Repo & Docker Container${RESET}"
  echo "  ${BOLD}${RED}6.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to update the window title
update_window_title() {
  step_number="$1"
  step_description="$2"
  echo -ne "\033]0;Step $step_number: $step_description\007"
}

# Function containing the local install steps
local_install() {
  
  local_steps=(
    "Updating install repos...:if command -v apt &>/dev/null; then sudo apt-get update; elif command -v zypper &>/dev/null; then zypper refresh; elif command -v dnf &>/dev/null; then dnf check-update; elif command -v urpmi &>/dev/null; then urpmi.update -a; elif command -v slackpkg &>/dev/null; then slackpkg update; elif command -v slapt-get &>/dev/null; then slapt-get --update; elif command -v cards &>/dev/null; then cards sync; elif command -v pacman &>/dev/null; then pacman -Sy; elif command -v apk &>/dev/null; then apk update; elif command -v smart &>/dev/null; then smart update; elif command -v pkcon &>/dev/null; then pkcon refresh; elif command -v emerge &>/dev/null; then emerge --sync; elif command -v lin &>/dev/null; then lin moonbase; elif command -v scribe &>/dev/null; then scribe update; elif command -v nix-channel &>/dev/null; then nix-channel --update; elif command -v xbps-install &>/dev/null; then xbps-install -S; elif command -v pkg &>/dev/null; then pkg update; elif command -v csup &>/dev/null; then csup -L 2 -h cvsup.FreeBSD.org path_to_supfile; elif command -v portsnap &>/dev/null; then portsnap update; else echo 'No package manager found.'; fi"
    "Updating xterm depedencies...:if command -v apt-get &>/dev/null; then sudo apt-get install xorg-mkfontscale xorg-font-utils tts-ms-fonts -y || sudo apt-get install xorg-mkfontscale xorg-font-utils tts-ms-fonts -y; elif command -v zypper &>/dev/null; then zypper install -t package xterm; elif command -v dnf &>/dev/null; then dnf install xterm; elif command -v urpmi &>/dev/null; then urpmi xterm; elif command -v slackpkg &>/dev/null; then slackpkg install xterm; elif command -v slapt-get &>/dev/null; then slapt-get --install xterm; elif command -v netpkg &>/dev/null; then netpkg xterm; elif command -v cards &>/dev/null; then cards install xterm; elif command -v pacman &>/dev/null; then pacman -S xterm; elif command -v apk &>/dev/null; then apk add xterm; elif command -v smart &>/dev/null; then smart install xterm; elif command -v pkcon &>/dev/null; then pkcon install xterm; elif command -v emerge &>/dev/null; then emerge xterm; elif command -v lin &>/dev/null; then lin xterm; elif command -v cast &>/dev/null; then cast xterm; elif command -v nix-env &>/dev/null; then nix-env -i xterm; elif command -v xbps-install &>/dev/null; then xbps-install xterm; elif command -v snap &>/dev/null; then snap install xterm; elif command -v pkg_add &>/dev/null; then pkg_add -r xterm; elif command -v pkg &>/dev/null; then pkg install xterm; elif command -v make &>/dev/null; then cd port_dir && make && make install xterm; else echo 'No package manager found.'; fi"
    "Updating xterm Install...:if command -v apt-get &>/dev/null; then sudo apt-get install xterm -y || sudo apt-get install xterm -y; elif command -v zypper &>/dev/null; then zypper install -t package xterm; elif command -v dnf &>/dev/null; then dnf install xterm; elif command -v urpmi &>/dev/null; then urpmi xterm; elif command -v slackpkg &>/dev/null; then slackpkg install xterm; elif command -v slapt-get &>/dev/null; then slapt-get --install xterm; elif command -v netpkg &>/dev/null; then netpkg xterm; elif command -v cards &>/dev/null; then cards install xterm; elif command -v pacman &>/dev/null; then pacman -S xterm; elif command -v apk &>/dev/null; then apk add xterm; elif command -v smart &>/dev/null; then smart install xterm; elif command -v pkcon &>/dev/null; then pkcon install xterm; elif command -v emerge &>/dev/null; then emerge xterm; elif command -v lin &>/dev/null; then lin xterm; elif command -v cast &>/dev/null; then cast xterm; elif command -v nix-env &>/dev/null; then nix-env -i xterm; elif command -v xbps-install &>/dev/null; then xbps-install xterm; elif command -v snap &>/dev/null; then snap install xterm; elif command -v pkg_add &>/dev/null; then pkg_add -r xterm; elif command -v pkg &>/dev/null; then pkg install xterm; elif command -v make &>/dev/null; then cd port_dir && make && make install xterm; else echo 'No package manager found.'; fi"
    "Updating python Install...:if command -v apt-get &>/dev/null; then sudo apt-get install python=3.10.12 -y || sudo apt-get install -y python3.10 python3-pip -y; elif command -v zypper &>/dev/null; then zypper install -t package python=3.10.12; elif command -v dnf &>/dev/null; then dnf install python=3.10.12; elif command -v urpmi &>/dev/null; then urpmi python=3.10.12; elif command -v slackpkg &>/dev/null; then slackpkg install python=3.10.12; elif command -v slapt-get &>/dev/null; then slapt-get --install python=3.10.12; elif command -v netpkg &>/dev/null; then netpkg python=3.10.12; elif command -v cards &>/dev/null; then cards install python=3.10.12; elif command -v pacman &>/dev/null; then pacman -S python=3.10.12; elif command -v apk &>/dev/null; then apk add python=3.10.12; elif command -v smart &>/dev/null; then smart install python=3.10.12; elif command -v pkcon &>/dev/null; then pkcon install python=3.10.12; elif command -v emerge &>/dev/null; then emerge python=3.10.12; elif command -v lin &>/dev/null; then lin python=3.10.12; elif command -v cast &>/dev/null; then cast python=3.10.12; elif command -v nix-env &>/dev/null; then nix-env -i python=3.10.12; elif command -v xbps-install &>/dev/null; then xbps-install python=3.10.12; elif command -v snap &>/dev/null; then snap install python=3.10.12; elif command -v pkg_add &>/dev/null; then pkg_add -r python=3.10.12; elif command -v pkg &>/dev/null; then pkg install python=3.10.12; elif command -v make &>/dev/null; then cd port_dir && make && make install python=3.10.12; else echo 'No package manager found.'; fi"
    "Updating docker-compose Install...:docker -v || if command -v apt-get &>/dev/null; then sudo apt-get install docker-compose -y; elif command -v zypper &>/dev/null; then zypper install -t package docker-compose; elif command -v dnf &>/dev/null; then dnf install docker-compose; elif command -v urpmi &>/dev/null; then urpmi docker-compose; elif command -v slackpkg &>/dev/null; then slackpkg install docker-compose; elif command -v slapt-get &>/dev/null; then slapt-get --install docker-compose; elif command -v netpkg &>/dev/null; then netpkg docker-compose; elif command -v cards &>/dev/null; then cards install docker-compose; elif command -v pacman &>/dev/null; then pacman -S docker-compose; elif command -v apk &>/dev/null; then apk add docker-compose; elif command -v smart &>/dev/null; then smart install docker-compose; elif command -v pkcon &>/dev/null; then pkcon install docker-compose; elif command -v emerge &>/dev/null; then emerge docker-compose; elif command -v lin &>/dev/null; then lin docker-compose; elif command -v cast &>/dev/null; then cast docker-compose; elif command -v nix-env &>/dev/null; then nix-env -i docker-compose; elif command -v xbps-install &>/dev/null; then xbps-install docker-compose; elif command -v snap &>/dev/null; then snap install docker-compose; elif command -v pkg_add &>/dev/null; then pkg_add -r docker-compose; elif command -v pkg &>/dev/null; then pkg install docker-compose; elif command -v make &>/dev/null; then cd port_dir && make && make install docker-compose; else echo 'No package manager found.'; fi"
    "Updating git Install...:git || if command -v apt-get &>/dev/null; then sudo apt-get install git; elif command -v zypper &>/dev/null; then zypper install -t package git; elif command -v dnf &>/dev/null; then dnf install git; elif command -v urpmi &>/dev/null; then urpmi git; elif command -v slackpkg &>/dev/null; then slackpkg install git; elif command -v slapt-get &>/dev/null; then slapt-get --install git; elif command -v netpkg &>/dev/null; then netpkg git; elif command -v cards &>/dev/null; then cards install git; elif command -v pacman &>/dev/null; then pacman -S git; elif command -v apk &>/dev/null; then apk add git; elif command -v smart &>/dev/null; then smart install git; elif command -v pkcon &>/dev/null; then pkcon install git; elif command -v emerge &>/dev/null; then emerge git; elif command -v lin &>/dev/null; then lin git; elif command -v cast &>/dev/null; then cast git; elif command -v nix-env &>/dev/null; then nix-env -i git; elif command -v xbps-install &>/dev/null; then xbps-install git; elif command -v snap &>/dev/null; then snap install git; elif command -v pkg_add &>/dev/null; then pkg_add -r git; elif command -v pkg &>/dev/null; then pkg install git; elif command -v make &>/dev/null; then cd port_dir && make && make install git; else echo 'No package manager found.'; fi"
    "Installing dbus-x11 package...:if command -v apt-get &>/dev/null; then sudo apt-get install dbus-x11; elif command -v zypper &>/dev/null; then zypper install -t package dbus-x11; elif command -v dnf &>/dev/null; then dnf install dbus-x11; elif command -v urpmi &>/dev/null; then urpmi dbus-x11; elif command -v slackpkg &>/dev/null; then slackpkg install dbus-x11; elif command -v slapt-get &>/dev/null; then slapt-get --install dbus-x11; elif command -v netpkg &>/dev/null; then netpkg dbus-x11; elif command -v cards &>/dev/null; then cards install dbus-x11; elif command -v pacman &>/dev/null; then pacman -S dbus-x11; elif command -v apk &>/dev/null; then apk add dbus-x11; elif command -v smart &>/dev/null; then smart install dbus-x11; elif command -v pkcon &>/dev/null; then pkcon install dbus-x11; elif command -v emerge &>/dev/null; then emerge dbus-x11; elif command -v lin &>/dev/null; then lin dbus-x11; elif command -v cast &>/dev/null; then cast dbus-x11; elif command -v nix-env &>/dev/null; then nix-env -i dbus-x11; elif command -v xbps-install &>/dev/null; then xbps-install dbus-x11; elif command -v snap &>/dev/null; then snap install dbus-x11; elif command -v pkg_add &>/dev/null; then pkg_add -r dbus-x11; elif command -v pkg &>/dev/null; then pkg install dbus-x11; elif command -v make &>/dev/null; then cd port_dir && make && make install dbus-x11; else echo 'No package manager found.'; fi"
    "Checking AGiXT directory...:[ -d \"$PWD/agixt/\" ] && echo \"AGiXT directory already exists.\" || [ -d \"$PWD/AGiXT/\"gixt/' ] && echo \"AGiXT directory already exists.\" || git clone https://github.com/Josh-XT/AGiXT && cd ./AGiXT"
    "Upgrading pip...:pip install --upgrade pip"
    "Installing requirements...:[ -d \"$PWD/agixt/\" ] && pip install -r $PWD/static-requirements.txt >./stat_req_logs.txt 2>&1 || pip install -r $PWD/AGiXT/static-requirements.txt >./stat_req_logs.txt 2>&1"
    "Installing requirements...:[ -d \"$PWD/agixt/\" ] && pip install -r $PWD/requirements.txt >./req_logs.txt 2>&1 || pip install -r $PWD/AGiXT/requirements.txt >./req_logs.txt 2>&1"
    "Installing Playwright dependencies...:sudo playwright || sudo playwright install --with-deps"
    "Running Backend...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'cd $PWD/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4' || x-terminal-emulator -e 'cd $PWD/AGiXT/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4'"
    "Running Streamlit...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'streamlit run $PWD/streamlit/Main.py' || x-terminal-emulator -e 'streamlit run $PWD/AGiXT/streamlit/Main.py'"
  )
  
  execute_steps "${local_steps[@]}"

}

# Function containing the local run steps
local_run() {
  
  local_run_steps=(
    "Checking AGiXT directory...:([ -d \"$PWD/agixt/\" ] || [ -d \"$PWD/AGiXT/\" ]) || if [[ ! -d \"AGiXT\" ]]; then git clone https://github.com/Josh-XT/AGiXT && cd ./AGiXT; else echo \"AGiXT directory already exists.\"; fi"
    "Running Backend...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'cd $PWD/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4' || x-terminal-emulator -e 'cd $PWD/AGiXT/agixt/ && uvicorn app:app --host 0.0.0.0 --port 7437 --workers 4'"
    "Running Streamlit...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'streamlit run $PWD/streamlit/Main.py' || x-terminal-emulator -e 'streamlit run $PWD/AGiXT/streamlit/Main.py'"
  )
  
  execute_steps "${local_run_steps[@]}"

}

# Function to perform the Docker install
docker_install() {
  docker_steps=(
  "Updating install repos...:if command -v apt &>/dev/null; then apt update; elif command -v zypper &>/dev/null; then zypper refresh; elif command -v dnf &>/dev/null; then dnf check-update; elif command -v urpmi &>/dev/null; then urpmi.update -a; elif command -v slackpkg &>/dev/null; then slackpkg update; elif command -v slapt-get &>/dev/null; then slapt-get --update; elif command -v cards &>/dev/null; then cards sync; elif command -v pacman &>/dev/null; then pacman -Sy; elif command -v apk &>/dev/null; then apk update; elif command -v smart &>/dev/null; then smart update; elif command -v pkcon &>/dev/null; then pkcon refresh; elif command -v emerge &>/dev/null; then emerge --sync; elif command -v lin &>/dev/null; then lin moonbase; elif command -v scribe &>/dev/null; then scribe update; elif command -v nix-channel &>/dev/null; then nix-channel --update; elif command -v xbps-install &>/dev/null; then xbps-install -S; elif command -v pkg &>/dev/null; then pkg update; elif command -v csup &>/dev/null; then csup -L 2 -h cvsup.FreeBSD.org path_to_supfile; elif command -v portsnap &>/dev/null; then portsnap update; else echo 'No package manager found.'; fi"
  "Installing docker...:if command -v sudo &>/dev/null; then if command -v apt &>/dev/null; then sudo apt install docker-compose; elif command -v zypper &>/dev/null; then sudo zypper in docker-compose; elif command -v dnf &>/dev/null; then sudo dnf install docker-compose; elif command -v urpmi &>/dev/null; then sudo urpmi docker-compose; elif command -v slackpkg &>/dev/null; then sudo slackpkg install docker-compose; elif command -v slapt-get &>/dev/null; then sudo slapt-get --install docker-compose; elif command -v cards &>/dev/null; then sudo cards install docker-compose; elif command -v pacman &>/dev/null; then sudo pacman -S docker-compose; elif command -v apk &>/dev/null; then sudo apk add docker-compose; elif command -v smart &>/dev/null; then sudo smart install docker-compose; elif command -v pkcon &>/dev/null; then sudo pkcon install docker-compose; elif command -v emerge &>/dev/null; then sudo emerge app-emulation/docker-compose; elif command -v xbps-install &>/dev/null; then sudo xbps-install docker-compose; elif command -v pkg &>/dev/null; then sudo pkg install docker-compose; else echo 'sudo or docker-compose not found or docker-compose might not be available.'; fi else echo 'sudo not found.'; fi"
  "Checking AGiXT directory...:[ -d \"$PWD/agixt/\" ] && echo \"AGiXT directory already exists.\" || git clone https://github.com/Josh-XT/AGiXT && cd ./AGiXT"
  "Building docker container...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'docker-compose up' || cd ./AGiXT/ && x-terminal-emulator -e 'docker-compose up'"
  )
  
  execute_steps "${docker_steps[@]}"
  
}

# Function to perform the Docker run
docker_run() {
  docker_run_steps=(
  "Building docker container...:[ -d \"$PWD/agixt/\" ] && x-terminal-emulator -e 'docker-compose up' || cd ./AGiXT/ && x-terminal-emulator -e 'docker-compose up'"
  )
  
  execute_steps "${docker_run_steps[@]}"
  
}

# Function to perform the Update
update() {
 
  update_steps=(
  "Downloading latest repo updates...:[ -d \"$PWD/agixt/\" ] && git pull || [ -d \"$PWD/AGiXT/\" ] && (cd ./AGiXT/ && git pull) || git clone https://github.com/Josh-XT/AGiXT"
  "Updating docker container...:[ -d \"$PWD/agixt/\" ] && docker-compose pull || cd ./AGiXT/ && docker-compose pull"
  )
  execute_steps "${update_steps[@]}"
  
}

# Function to perform the steps
execute_steps() {
  steps=("$@")
    for i in "${arr[@]}";
      do
        echo $i
      done
  clear
  echo "${BOLD}${GREEN}Running Steps...${RESET}"

  j=0
  for ((i = 0; i < ${#steps[@]}; i++)); do
    step=${steps[$i]}
    description=${step%%:*}
    command=${step#*:}
    step_number=$((i + 1))

    update_window_title "$step_number" "$description"

    display_animation &
    animation_pid=$!

    # Check if the command is the Streamlit run command
    if [[ $command == "x-terminal-emulator -e 'streamlit run"* ]]; then
      # Sleep for a few seconds to allow Streamlit to start in the new terminal
      sleep 5
      $j++
      # Remove the & at the end to run in the foreground
      eval "$command"
      if $j -gt 0; then
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
  sleep 2
  show_main
}

# Main loop to display the menu and handle user input
show_main() {
  update_window_title "" "Main Menu Select"
  while true; do
    display_menu
    read -p "${BOLD}${CYAN}Enter your choice:${RESET} " choice

    case "$choice" in
      1)
        local_install
        break
        ;;
      2)
        local_run
        break
        ;;
      3)
        docker_install
        break
        ;;
      4)
        docker_run
        break
        ;;
      5)
        update
        echo "${BOLD}${GREEN}Update complete.${RESET}"
        sleep 2
        ;;
      6)
        echo "${BOLD}${MAGENTA}Thank you for using AGiXT Installer. Goodbye!${RESET}"
        break
        ;;
      *)
        echo "${RED}Invalid option. Please try again.${RESET}"
        sleep 2
        ;;
    esac
  done
}

show_main

