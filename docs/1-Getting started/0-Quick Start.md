# AGiXT

## Quick Start Guide

### Operating System Prerequisites

Provide the following prerequisites based on the Operating System you use.

#### Windows and Mac Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://docs.docker.com/docker-for-windows/install/)
- [Python 3.10.x](https://www.python.org/downloads/)

#### Linux Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.10.x](https://www.python.org/downloads/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (if using local models on GPU)

## Installation

If you're using Linux, you may need to prefix the `python` command with `sudo` depending on your system configuration.

```bash
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
python start.py
```

The script will check for Docker and Docker Compose installation:

- On Linux, it will attempt to install them if missing (requires sudo privileges).
- On macOS and Windows, it will provide instructions to download and install Docker Desktop.

## Usage

Run the script with Python:

```bash
python start.py
```

To run AGiXT with ezLocalai, use the `--with-ezlocalai` flag:

```bash
python start.py --with-ezlocalai
```

You can also use command-line arguments to set specific environment variables to run in different ways. For example, to use the development branch and enable auto-updates, run:

```bash
python start.py --agixt-branch dev --agixt-auto-update true --with-ezlocalai
```

- Access the AGiXT Management interface at <http://localhost:8501> to create and manage your agents, prompts, chains, and configurations.
- Access the AGiXT Interactive interface at <http://localhost:3437> to interact with your configured agents.
- Access the AGiXT API documentation at <http://localhost:7437>

### Command-line Options

The script supports setting any of the environment variables via command-line arguments. Here's a detailed list of available options:

1. `--agixt-api-key`: Set the AGiXT API key (automatically generated if not provided)
2. `--agixt-uri`: Set the AGiXT URI (default: `http://localhost:7437`)
3. `--agixt-agent`: Set the default AGiXT agent (default: `AGiXT`)
4. `--agixt-branch`: Choose between `stable` and `dev` branches
5. `--agixt-file-upload-enabled`: Enable or disable file uploads (default: `true`)
6. `--agixt-voice-input-enabled`: Enable or disable voice input (default: `true`)
7. `--agixt-footer-message`: Set the footer message (default: `Powered by AGiXT`)
8. `--agixt-require-api-key`: Require API key for access (default: `false`)
9. `--agixt-rlhf`: Enable or disable reinforcement learning from human feedback (default: `true`)
10. `--agixt-show-selection`: Set which selectors to show in the UI (default: `conversation,agent`)
11. `--agixt-show-agent-bar`: Show or hide the agent bar in the UI (default: `true`)
12. `--agixt-show-app-bar`: Show or hide the app bar in the UI (default: `true`)
13. `--agixt-conversation-mode`: Set the conversation mode (default: `select`)
14. `--allowed-domains`: Set allowed domains for API access (default: `*`)
15. `--app-description`: Set the application description
16. `--app-name`: Set the application name (default: `AGiXT Chat`)
17. `--app-uri`: Set the application URI (default: `http://localhost:3437`)
18. `--auth-web`: Set the authentication web URI (default: `http://localhost:3437/user`)
19. `--auth-provider`: Set the authentication provider (options: `none`, `magicalauth`)
20. `--disabled-providers`: Set disabled providers (comma-separated list)
21. `--disabled-extensions`: Set disabled extensions (comma-separated list)
22. `--working-directory`: Set the working directory (default: `./WORKSPACE`)
23. `--github-client-id`: Set GitHub client ID for authentication
24. `--github-client-secret`: Set GitHub client secret for authentication
25. `--google-client-id`: Set Google client ID for authentication
26. `--google-client-secret`: Set Google client secret for authentication
27. `--microsoft-client-id`: Set Microsoft client ID for authentication
28. `--microsoft-client-secret`: Set Microsoft client secret for authentication
29. `--tz`: Set the timezone (default: system timezone)
30. `--interactive-mode`: Set the interactive mode (default: `chat`)
31. `--theme-name`: Set the UI theme (options: `default`, `christmas`, `conspiracy`, `doom`, `easter`, `halloween`, `valentines`)
32. `--allow-email-sign-in`: Allow email sign-in (default: `true`)
33. `--database-type`: Set the database type (options: `sqlite`, `postgres`)
34. `--database-name`: Set the database name (default: `models/agixt`)
35. `--log-level`: Set the logging level (default: `INFO`)
36. `--log-format`: Set the log format (default: `%(asctime)s | %(levelname)s | %(message)s`)
38. `--uvicorn-workers`: Set the number of Uvicorn workers (default: `10`)
39. `--agixt-auto-update`: Enable or disable auto-updates (default: `true`)

Options specific to ezLocalai:

1. `--with-ezlocalai`: Start AGiXT with ezLocalai integration.
2. `--ezlocalai-uri`: Set the ezLocalai URI (default: `http://{local_ip}:8091`)
3. `--default-model`: Set the default language model for ezLocalai (default: `QuantFactory/dolphin-2.9.2-qwen2-7b-GGUF`)
4. `--vision-model`: Set the vision model for ezLocalai (default: `deepseek-ai/deepseek-vl-1.3b-chat`)
5. `--llm-max-tokens`: Set the maximum number of tokens for language models (default: `32768`)
6. `--whisper-model`: Set the Whisper model for speech recognition (default: `base.en`)
7. `--gpu-layers`: Set the number of GPU layers to use (automatically determined based on available VRAM but can be modified.) (default: `-1` for all)

For a full list of options with their current values, run:

```bash
python start.py --help
```

## Docker Deployment

After setting up the environment variables and ensuring Docker and Docker Compose are installed, the script will:

1. Stop any running AGiXT Docker containers
2. Pull the latest Docker images (if auto-update is enabled)
3. Start the AGiXT services using Docker Compose

## Troubleshooting

- If the script fails to run on Linux, run it with `sudo`.
- If you encounter any issues with Docker installation:
  - On Linux, ensure you have sudo privileges and that your system is up to date.
  - On macOS and Windows, follow the instructions to install Docker Desktop manually if the script cannot install it automatically.
- Check the Docker logs for any error messages if the containers fail to start.
- Verify that all required ports are available and not in use by other services.
- If the `python` command is not recognized, try using `python3` instead.

## Security Considerations

- The `AGIXT_API_KEY` is automatically generated if not provided. Ensure to keep this key secure and do not share it publicly.
- When using authentication providers (GitHub, Google, Microsoft), ensure that the client IDs and secrets are kept confidential.
- Be cautious when enabling file uploads and voice input, as these features may introduce potential security risks if not properly managed.
