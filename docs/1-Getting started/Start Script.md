# AGiXT Start Script

This Python script automates the setup and configuration process for AGiXT, a powerful AI agent framework. It handles environment variable configuration, Docker and Docker Compose installation checks, and deployment using Docker Compose.

## Features

- Checks for Docker and Docker Compose installation
- Attempts to install Docker and Docker Compose on Linux systems if missing
- Provides installation instructions for Docker Desktop on macOS and Windows
- Sets up environment variables with default values and user customization options
- Supports both stable and development versions of AGiXT
- Handles automatic updates (optional)
- Provides command-line interface for easy configuration

## Prerequisites

- [Python 3.10.x](https://www.python.org/downloads/)

The script will check for and attempt to install or guide you through the installation of:

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Installation

1. Clone this repository or download the script:

    ```bash
    git clone https://github.com/Josh-XT/AGiXT
    cd AGiXT
    ```

2. Run the script:

    ```bash
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

You can also use command-line arguments to set specific environment variables to run in different ways. For example, to use the development branch and enable auto-updates, run:

```bash
python start.py --agixt-branch dev --agixt-auto-update true
```

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
18. `--streamlit-app-uri`: Set the Streamlit app URI (default: `http://localhost:8501`)
19. `--auth-web`: Set the authentication web URI (default: `http://localhost:3437/user`)
20. `--auth-provider`: Set the authentication provider (options: `none`, `magicalauth`)
21. `--disabled-providers`: Set disabled providers (comma-separated list)
22. `--disabled-extensions`: Set disabled extensions (comma-separated list)
23. `--working-directory`: Set the working directory (default: `./WORKSPACE`)
24. `--github-client-id`: Set GitHub client ID for authentication
25. `--github-client-secret`: Set GitHub client secret for authentication
26. `--google-client-id`: Set Google client ID for authentication
27. `--google-client-secret`: Set Google client secret for authentication
28. `--microsoft-client-id`: Set Microsoft client ID for authentication
29. `--microsoft-client-secret`: Set Microsoft client secret for authentication
30. `--tz`: Set the timezone (default: system timezone)
31. `--interactive-mode`: Set the interactive mode (default: `chat`)
32. `--theme-name`: Set the UI theme (options: `default`, `christmas`, `conspiracy`, `doom`, `easter`, `halloween`, `valentines`)
33. `--allow-email-sign-in`: Allow email sign-in (default: `true`)
34. `--database-type`: Set the database type (options: `sqlite`, `postgres`)
35. `--database-name`: Set the database name (default: `models/agixt`)
36. `--log-level`: Set the logging level (default: `INFO`)
37. `--log-format`: Set the log format (default: `%(asctime)s | %(levelname)s | %(message)s`)
38. `--uvicorn-workers`: Set the number of Uvicorn workers (default: `10`)
39. `--agixt-auto-update`: Enable or disable auto-updates (default: `true`)

For a full list of options with their current values, run:

```bash
python start.py --help
```

## Environment Variables

The script sets up various environment variables for AGiXT. Some key variables and their purposes include:

- `AGIXT_API_KEY`: API key for AGiXT (automatically generated if not provided)
- `AGIXT_URI`: URI for the AGiXT API
- `AGIXT_BRANCH`: AGiXT version to use (stable or dev)
- `AGIXT_AUTO_UPDATE`: Whether to automatically update AGiXT
- `AGIXT_RLHF`: Enable reinforcement learning from human feedback (thumbs up/down buttons in UI)
- `AGIXT_SHOW_SELECTION`: Controls which dropdowns are shown in the UI (agent, conversation)
- `AUTH_PROVIDER`: Authentication provider (none or magicalauth)
- `INTERACTIVE_MODE`: Should always be set to "chat" (form mode is experimental)
- `THEME_NAME`: UI color scheme (christmas, conspirac, doom, easter, halloween, valentines, default)
- `DATABASE_TYPE`: Type of database to use (sqlite or postgres)
- `UVICORN_WORKERS`: Number of workers running on the application

For a complete list of environment variables and their default values, please refer to the `get_default_env_vars()` function in the script.

## Docker Deployment

After setting up the environment variables and ensuring Docker and Docker Compose are installed, the script will:

1. Stop any running AGiXT Docker containers
2. Pull the latest Docker images (if auto-update is enabled)
3. Start the AGiXT services using Docker Compose

## Troubleshooting

- If you encounter any issues with Docker installation:
  - On Linux, ensure you have sudo privileges and that your system is up to date.
  - On macOS and Windows, follow the instructions to install Docker Desktop manually if the script cannot install it automatically.
- Check the Docker logs for any error messages if the containers fail to start.
- Verify that all required ports are available and not in use by other services.

## Security Considerations

- The `AGIXT_API_KEY` is automatically generated if not provided. Ensure to keep this key secure and do not share it publicly.
- When using authentication providers (GitHub, Google, Microsoft), ensure that the client IDs and secrets are kept confidential.
- Be cautious when enabling file uploads and voice input, as these features may introduce potential security risks if not properly managed.
