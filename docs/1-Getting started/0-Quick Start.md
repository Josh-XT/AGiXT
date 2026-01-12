# AGiXT Quick Start Guide

## Prerequisites

**Windows and Mac:**

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://docs.docker.com/docker-for-windows/install/)
- [Python 3.10+](https://www.python.org/downloads/)

**Linux:**

- [Git](https://git-scm.com/downloads)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Python 3.10+](https://www.python.org/downloads/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) *(for local GPU models)*

## Installation

### Option 1: PyPI Installation (Recommended)

The simplest way to get started with AGiXT:

```bash
pip install agixt
agixt start
```

That's it! AGiXT will automatically:

- Set up Docker containers (or run locally with `--local`)
- Start [ezLocalai](https://github.com/DevXT-LLC/ezlocalai) for local AI inference
- Configure all necessary services

### Option 2: Development Installation

For development or customization:

```bash
git clone https://github.com/Josh-XT/AGiXT
cd AGiXT
pip install -e .
agixt start
```

### Local Mode (Without Docker)

If you prefer to run AGiXT without Docker:

```bash
agixt start --local
```

## Access AGiXT

After installation, access these interfaces:

- **🌐 AGiXT Interface**: [http://localhost:3437](http://localhost:3437) - Complete management and chat interface
- **📚 API Documentation**: [http://localhost:7437](http://localhost:7437) - Complete API reference

## CLI Commands

### Basic Server Management

```bash
# Start AGiXT (Docker mode by default, includes ezLocalai)
agixt start

# Start in local mode (without Docker)
agixt start --local

# Stop all services
agixt stop

# Restart services
agixt restart

# View logs
agixt logs [-f]     # -f to follow logs
```

### Service-Specific Commands

```bash
# Web interface only
agixt start --web [--local]
agixt stop --web [--local]
agixt restart --web [--local]

# ezLocalai only (local AI models)
agixt start --ezlocalai
agixt stop --ezlocalai
agixt restart --ezlocalai
agixt logs --ezlocalai [-f]

# All services (AGiXT + ezLocalai + Web)
agixt start --all [--local]
agixt stop --all [--local]
agixt restart --all [--local]
```

### Environment Configuration

```bash
# View all available environment variables
agixt env help

# Set environment variables
agixt env KEY=VALUE
agixt env OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-...

# Common configurations
agixt env DEFAULT_MODEL="bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF"
agixt env WITH_EZLOCALAI=false  # Disable local AI inference
```

### Client Commands

```bash
# Register a new user
agixt register --server http://localhost:7437 --email user@example.com --firstname John --lastname Doe

# Login to server
agixt login --server http://localhost:7437 --email user@example.com --otp 123456

# Chat with an agent
agixt prompt "What is the weather like today?"

# Manage conversations
agixt conversations        # List/select conversations
agixt conversations -      # Start new conversation
```

## Configuration Tips

- **📂 Log Files**: Local logs are stored in `~/.agixt/agixt-local-*.log` (keeps 5 most recent)
- **🤖 ezLocalai Default**: ezLocalai starts automatically with AGiXT (disable with `agixt env WITH_EZLOCALAI=false`)
- **🎮 GPU Detection**: ezLocalai automatically detects NVIDIA GPU and enables GPU acceleration
- **🔄 Auto-Updates**: Environment changes in backend automatically sync to web and ezLocalai
- **🔐 API Key**: An `AGIXT_API_KEY` is automatically generated if not provided

## Port Configuration

| Service | Default Port | Description |
|---------|--------------|-------------|
| AGiXT API | 7437 | REST API and documentation |
| Web Interface | 3437 | Interactive web UI |
| ezLocalai | 8091 | Local AI inference |

## Troubleshooting

- **Linux users**: May need to prefix commands with `sudo` for Docker operations
- **Port conflicts**: Ensure ports 7437, 3437, and 8091 are available
- **Docker issues**: Check `agixt logs` for error messages
- **Python not found**: Try using `python3` instead of `python`

## Security Considerations

- The `AGIXT_API_KEY` is automatically generated if not provided. Keep this key secure and do not share it publicly.
- When using OAuth providers (GitHub, Google, Microsoft), keep client IDs and secrets confidential.
- Be cautious when enabling file uploads and voice input in production environments.

## Next Steps

1. **Configure an AI Provider**: Set up API keys for OpenAI, Anthropic, or use the included ezLocalai for local inference
2. **Create an Agent**: Use the web interface or API to create your first AI agent
3. **Explore Extensions**: AGiXT includes 40+ built-in extensions for various integrations
4. **Build Workflows**: Create chains to automate complex multi-step processes

For more detailed documentation, see the [Concepts](../2-Concepts/0-Core%20Concepts.md) section.
