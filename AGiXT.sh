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
        read -p "Quick Setup without advanced configuration? (Y for yes, N for No): " quick_setup
        if [[ "$quick_setup" == [Yy]* ]]; then
          db_connection = false
          auto_update = true
          github_repo = "AGiXT/hub"
          agixt_uri = "http://localhost:7437"
          api_key = ""
          agixt_workers = 10
          github_username = ""
          github_token = ""
          postgres_host = "db"
          postgres_port = 5432
          postgres_database = "postgres"
          postgres_username = "postgres"
          postgres_password = "postgres"
        else
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
              read -p "Enter your AGiXT Hub fork repo name (e.g. AGiXT/hub): " github_repo
              read -p "Is your AGiXT Hub fork private? It will require credentials if it is not public. (Y for yes, N for No): " is_private
              if [[ "$is_private" == [Yy]* ]]; then
                  read -p "Enter your GitHub username: " github_username
                  read -p "Enter your GitHub token: " github_token
              fi
          fi
          read -p "Enter the number of AGiXT workers to run with, default is 10: " workers
          if [[ "$workers" != "" ]]; then
              if [[ $workers =~ ^[0-9]+$ && $workers -gt 0 ]]; then
                  agixt_workers=$workers
              else
                  echo "Invalid number of workers, defaulting to 10"
                  agixt_workers=10
              fi
          fi
          read -p "Do you intend to run local models? (Y for yes, N for No): " local_models
          if [[ "$local_models" == [Yy]* ]]; then
              read -p "Do you want to use a local Text generation web UI? (Only works with NVIDIA currently) (Y for yes, N for No): " local_textgen
              if [[ "$local_textgen" == [Yy]* ]]; then
                  read -p "Enter your GPU Compute Capability, you can find it here: https://developer.nvidia.com/cuda-gpus (Example: RTX2000 series are 7.5): " cuda_version
                  if [[ "$cuda_version" != "" ]]; then
                      if [[ $cuda_version =~ ^[0-9]+\.[0-9]+$ ]]; then
                          echo "TORCH_CUDA_ARCH_LIST=${cuda_version:-7.5}" >> .env
                      fi
                  fi
                  cli_args_default='--listen --listen-host 0.0.0.0 --api'
                  read -p "Default Text generation web UI startup parameters: ${cli_args_default} (prese Enter for defaults or overwrite with yours): " local_textgen_startup_params
                  echo "CLI_ARGS='${local_textgen_startup_params:-${cli_args_default}}'" >> .env
              fi
          fi
          read -p "Do you want to use postgres? (Y for yes, N for No and to use file structure instead): " use_db
          if [[ "$use_db" == [Yy]* ]]; then
              db_connection="true"
              read -p "Do you want to use an existing postgres database? (Y for yes, N for No and to create a new one automatically): " use_own_db
              if [[ "$use_own_db" == [Yy]* ]]; then
                  read -p "Enter postgres host: " postgres_host
                  read -p "Enter postgres port: " postgres_port
                  read -p "Enter postgres database name: " postgres_database
                  read -p "Enter postgres username: " postgres_username
              fi
              read -p "Enter postgres password: " postgres_password
          fi
        fi
        echo "DB_CONNECTED=${db_connection:-false}" >> .env
        echo "AGIXT_AUTO_UPDATE=${auto_update:-true}" >> .env
        echo "AGIXT_HUB=${github_repo:-AGiXT/hub}" >> .env
        echo "AGIXT_URI=${agixt_uri:-http://localhost:7437}" >> .env
        echo "AGIXT_API_KEY=${api_key:-}" >> .env
        echo "UVICORN_WORKERS=${agixt_workers:-10}" >> .env
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
  echo "  ${BOLD}${YELLOW}1.${RESET} ${YELLOW}Run AGiXT (Recommended)${RESET}"
  echo "  ${BOLD}${YELLOW}2.${RESET} ${YELLOW}Run AGiXT with Text Generation Web UI (NVIDIA Only)${RESET}"
  echo "  ${BOLD}${YELLOW}3.${RESET} ${YELLOW}Run AGiXT with Text Generation Web UI and Stable Diffusion (NVIDIA Only)${RESET}"
  echo "${BOLD}${GREEN}Developer Only Options (Not recommended or supported):${RESET}"
  echo "  ${BOLD}${YELLOW}4.${RESET} ${YELLOW}Run AGiXT with Docker from Main Branch${RESET}"
  echo "  ${BOLD}${YELLOW}5.${RESET} ${YELLOW}Run AGiXT on local machine${RESET}"
  echo "${BOLD}${GREEN}Manage:${RESET}"
  echo "  ${BOLD}${YELLOW}6.${RESET} ${YELLOW}Update AGiXT ${RESET}"
  echo "  ${BOLD}${RED}7.${RESET} ${RED}Wipe AGiXT Hub (Irreversible)${RESET}"
  echo "  ${BOLD}${RED}8.${RESET} ${RED}Exit${RESET}"
  echo ""
}

# Function to perform the Update
update_local() {
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
  # Check if TORCH_CUDA_ARCH_LIST is defined from the env, only update Text generation web UI if it is.
  if [[ -z "${TORCH_CUDA_ARCH_LIST}" ]]; then
    echo "${BOLD}${YELLOW}Please wait...${RESET}"
  else
    if [ ! -d "text-generation-webui" ]; then
        echo "${BOLD}${YELLOW}Updating Oobabooga Text generation web UI Repository...${RESET}"
        git clone https://github.com/oobabooga/text-generation-webui
    fi
    cd text-generation-webui
    git pull
    cd ..
  fi
  echo "${BOLD}${YELLOW}Updates Completed...${RESET}"
}

update_docker() {
  echo "${BOLD}${GREEN}Running Updates...${RESET}"
  echo "${BOLD}${YELLOW}Updating AGiXT Core...${RESET}"
  git pull
  # Check if TORCH_CUDA_ARCH_LIST is defined from the env, only update Text generation web UI if it is.
  if [[ -z "${TORCH_CUDA_ARCH_LIST}" ]]; then
    echo "${BOLD}${YELLOW}Please wait...${RESET}"
  else
    if [ ! -d "text-generation-webui" ]; then
        echo "${BOLD}${YELLOW}Updating Oobabooga Text generation web UI Repository...${RESET}"
        git clone https://github.com/oobabooga/text-generation-webui
    fi
    cd text-generation-webui
    git pull
    echo "${BOLD}${YELLOW}Updating Text generation web UI Docker image...${RESET}"
    cd ..
    if [[ "$DB_CONNECTED" == "true" ]]; then
      docker-compose -f docker-compose-postgres-local-nvidia.yml build text-generation-webui
    else
      docker-compose -f docker-compose-local-nvidia.yml build text-generation-webui
    fi
  fi
  echo "${BOLD}${YELLOW}Current directory: ${PWD}${RESET}"
  docker-compose pull
  echo "${BOLD}${YELLOW}Updates Completed...${RESET}"
}

update() {
  if [[ "$AGIXT_URI" == "http://agixt:7437" ]]; then
    update_docker
  else
    update_local
  fi
  echo "${BOLD}${GREEN}Update complete.${RESET}"
  sleep 2
}
# Function to perform the Docker install
docker_install() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://agixt:7437" >> .env
  sed -i '/^TEXTGEN_URI=/d' .env
  echo "TEXTGEN_URI=http://text-generation-webui:5000" >> .env
  source .env
  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    update
  fi
  echo "${BOLD}${YELLOW}Starting Docker Compose...${RESET}"
  if [[ "$DB_CONNECTED" == "true" ]]; then
    docker-compose -f docker-compose-postgres.yml up
  else
    docker-compose up
  fi
}
docker_install_dev() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://agixt:7437" >> .env
  sed -i '/^TEXTGEN_URI=/d' .env
  echo "TEXTGEN_URI=http://text-generation-webui:5000" >> .env
  source .env
  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    update
  fi
  echo "${BOLD}${YELLOW}Starting Docker Compose...${RESET}"
  docker-compose -f docker-compose-dev.yml up
}
# Function to perform the Docker install
docker_install_local_nvidia() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://agixt:7437" >> .env
  sed -i '/^TEXTGEN_URI=/d' .env
  echo "TEXTGEN_URI=http://text-generation-webui:5000" >> .env
  source .env
  # Check if TORCH_CUDA_ARCH_LIST is defined from the env, ask user to enter it if not.
  if [[ -z "${TORCH_CUDA_ARCH_LIST}" ]]; then
    read -p "Enter your GPU Compute Capability, you can find it here: https://developer.nvidia.com/cuda-gpus (Example: RTX2000 series are 7.5): " cuda_version
    if [[ "$cuda_version" != "" ]]; then
        if [[ $cuda_version =~ ^[0-9]+\.[0-9]+$ ]]; then
            echo "TORCH_CUDA_ARCH_LIST=${cuda_version:-7.5}" >> .env
        fi
    fi
    cli_args_default='--listen --listen-host 0.0.0.0 --api'
    read -p "Default Text generation web UI startup parameters: ${cli_args_default} (prese Enter for defaults or overwrite with yours): " local_textgen_startup_params
    echo "CLI_ARGS='${local_textgen_startup_params:-${cli_args_default}}'" >> .env
  fi

  # Check if nvidia-container-toolkit is installed
  if dpkg -l | grep -iq "nvidia-container-toolkit"; then
      echo "Confirmed NVIDIA Container Toolkit is installed."
  else
      echo "NVIDIA Container Toolkit is not installed. Installing now..."
      # Install a new GPU Docker container
      distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
      curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
      curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
      sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
      sudo systemctl restart docker
      echo "NVIDIA Container Toolkit has been installed."
  fi

  if [ ! -d "text-generation-webui" ]; then
      echo "${BOLD}${YELLOW}Cloning Oobabooga Text generation web UI Repository...${RESET}"
      git clone https://github.com/oobabooga/text-generation-webui
  fi

  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    update
  fi

  echo "${BOLD}${GREEN}Running Docker install...${RESET}"
  echo "${BOLD}${YELLOW}Starting Docker Compose...${RESET}"
  if [[ "$DB_CONNECTED" == "true" ]]; then
    docker-compose -f docker-compose-postgres-local-nvidia.yml up
  else
    docker-compose -f docker-compose-local-nvidia.yml up
  fi
}
docker_install_local_nvidia_sd() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://agixt:7437" >> .env
  sed -i '/^TEXTGEN_URI=/d' .env
  echo "TEXTGEN_URI=http://text-generation-webui:5000" >> .env
  source .env
  # Check if TORCH_CUDA_ARCH_LIST is defined from the env, ask user to enter it if not.
  if [[ -z "${TORCH_CUDA_ARCH_LIST}" ]]; then
    read -p "Enter your GPU Compute Capability, you can find it here: https://developer.nvidia.com/cuda-gpus (Example: RTX2000 series are 7.5): " cuda_version
    if [[ "$cuda_version" != "" ]]; then
        if [[ $cuda_version =~ ^[0-9]+\.[0-9]+$ ]]; then
            echo "TORCH_CUDA_ARCH_LIST=${cuda_version:-7.5}" >> .env
        fi
    fi
    cli_args_default='--listen --listen-host 0.0.0.0 --api'
    read -p "Default Text generation web UI startup parameters: ${cli_args_default} (prese Enter for defaults or overwrite with yours): " local_textgen_startup_params
    echo "CLI_ARGS='${local_textgen_startup_params:-${cli_args_default}}'" >> .env
  fi

  # Check if nvidia-container-toolkit is installed
  if dpkg -l | grep -iq "nvidia-container-toolkit"; then
      echo "Confirmed NVIDIA Container Toolkit is installed."
  else
      echo "NVIDIA Container Toolkit is not installed. Installing now..."
      # Install a new GPU Docker container
      distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
      curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
      curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
      sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
      sudo systemctl restart docker
      echo "NVIDIA Container Toolkit has been installed."
  fi

  if [ ! -d "text-generation-webui" ]; then
      echo "${BOLD}${YELLOW}Cloning Oobabooga Text generation web UI Repository...${RESET}"
      git clone https://github.com/oobabooga/text-generation-webui
  fi

  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    update
  fi

  echo "${BOLD}${GREEN}Running Docker install...${RESET}"
  echo "${BOLD}${YELLOW}Starting Docker Compose...${RESET}"
  if [[ "$DB_CONNECTED" == "true" ]]; then
    if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
      docker-compose -f docker-compose-postgres-local-nvidia-sd.yml pull
    fi
    docker-compose -f docker-compose-postgres-local-nvidia-sd.yml up
  else
    if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
      docker-compose -f docker-compose-local-nvidia-sd.yml pull
    fi
    docker-compose -f docker-compose-local-nvidia-sd.yml up
  fi
}
# Function to perform the local install
local_install() {
  sed -i '/^AGIXT_URI=/d' .env
  echo "AGIXT_URI=http://localhost:7437" >> .env
  sed -i '/^TEXTGEN_URI=/d' .env
  echo "TEXTGEN_URI=http://localhost:5000" >> .env
  source .env
  echo "${BOLD}${YELLOW}Updating the repository...${RESET}"
  if [[ "$AGIXT_AUTO_UPDATE" == "true" ]]; then
    echo "${BOLD}${YELLOW}Upgrading pip...${RESET}"
    pip install --upgrade pip
    sleep 1

    echo "${BOLD}${YELLOW}Installing requirements...${RESET}"
    pip install -r requirements.txt --upgrade
    sleep 1

    echo "${BOLD}${YELLOW}Checking for updates...${RESET}"
    git pull
    if [ ! -d "streamlit" ]; then
      echo "${BOLD}${YELLOW}Installing Streamlit dependencies...${RESET}"
      git clone https://github.com/AGiXT/streamlit
    fi
    cd streamlit
    git pull
    pip install -r requirements.txt --upgrade
    cd ..
  fi

  echo "${BOLD}${GREEN}Running local install...${RESET}"

  git pull
  sleep 1

  # Check if the directory exists
  if [ ! -d "agixt/extensions" ]; then
      echo "${BOLD}${YELLOW}Upgrading pip...${RESET}"
      pip install --upgrade pip
      sleep 1

      echo "${BOLD}${YELLOW}Installing requirements...${RESET}"
      pip install -r requirements.txt --upgrade
      sleep 1

      echo "${BOLD}${YELLOW}Installing Playwright dependencies...${RESET}"
      playwright install --with-deps
      sleep 1
  fi

  if [ ! -d "streamlit" ]; then
      echo "${BOLD}${YELLOW}Installing Streamlit dependencies...${RESET}"
      git clone https://github.com/AGiXT/streamlit
      cd streamlit
      pip install -r requirements.txt --upgrade
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
      docker_install_local_nvidia
      break
      ;;
    3)
      docker_install_local_nvidia_sd
      break
      ;;
    4)
      docker_install_dev
      break
      ;;
    5)
      local_install
      break
      ;;
    6)
      update
      sleep 2
      ;;
    7)
      wipe_hub
      break
      ;;
    *)
      echo "${BOLD}${MAGENTA}Thank you for using AGiXT Installer. Goodbye!${RESET}"
      break
      ;;
  esac
done