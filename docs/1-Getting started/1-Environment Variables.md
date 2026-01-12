# Environment Variables

AGiXT uses environment variables for configuration. You can manage these using the `agixt env` command.

## Viewing Configuration

```bash
# Show all available environment variables with descriptions
agixt env help
```

This will display all 154+ configuration variables organized by category.

## Setting Variables

```bash
# Set a single variable
agixt env KEY=VALUE

# Set multiple variables
agixt env KEY1=VALUE1 KEY2=VALUE2

# Examples
agixt env OPENAI_API_KEY="sk-xxxxx"
agixt env LOG_LEVEL="DEBUG" UVICORN_WORKERS="20"
```

## Key Configuration Categories

### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGIXT_API_KEY` | *auto-generated* | API key for AGiXT authentication |
| `AGIXT_URI` | `http://localhost:7437` | URI for the AGiXT API |
| `AGIXT_AGENT` | `XT` | Default agent name |
| `AGIXT_BRANCH` | `stable` | AGiXT version to use (`stable` or `dev`) |
| `AGIXT_AUTO_UPDATE` | `true` | Enable automatic updates |
| `AGIXT_RUN_TYPE` | `docker` | Run mode (`docker` or `local`) |

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `AGiXT` | Application display name |
| `APP_URI` | `http://localhost:3437` | Web interface URI |
| `AUTH_PROVIDER` | `magicalauth` | Authentication provider (`none` or `magicalauth`) |
| `ALLOW_EMAIL_SIGN_IN` | `true` | Allow email-based login |
| `AGIXT_RLHF` | `true` | Enable reinforcement learning from human feedback |
| `INTERACTIVE_MODE` | `chat` | Interaction mode (`chat` or `form`) |
| `THEME_NAME` | `default` | UI theme |

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_TYPE` | `sqlite` | Database type (`sqlite` or `postgres`) |
| `DATABASE_NAME` | `models/agixt` | Database name/path |
| `DB_CONNECTED` | `false` | PostgreSQL connection status |
| `POSTGRES_SERVER` | - | PostgreSQL server address |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | - | PostgreSQL database name |
| `POSTGRES_USER` | - | PostgreSQL username |
| `POSTGRES_PASSWORD` | - | PostgreSQL password |

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `UVICORN_WORKERS` | `10` | Number of API workers |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `%(asctime)s \| %(levelname)s \| %(message)s` | Log message format |
| `ALLOWED_DOMAINS` | `*` | CORS allowed domains |
| `WORKING_DIRECTORY` | `./WORKSPACE` | Agent working directory |

### ezLocalai Configuration

> **Note**: If you do not have an NVIDIA GPU, the correct CUDA drivers, or enough VRAM, ezLocalai will still work running on CPU, but it will be slower.

| Variable | Default | Description |
|----------|---------|-------------|
| `WITH_EZLOCALAI` | `true` | Start ezLocalai with AGiXT |
| `EZLOCALAI_URI` | `http://{local_ip}:8091` | ezLocalai API URI |
| `DEFAULT_MODEL` | `bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF` | Default LLM model |
| `VISION_MODEL` | `deepseek-ai/deepseek-vl-1.3b-chat` | Vision model |
| `LLM_MAX_TOKENS` | `32768` | Maximum tokens for LLM |
| `WHISPER_MODEL` | `base.en` | Speech-to-text model |
| `GPU_LAYERS` | `-1` | GPU layers to use (`-1` for all) |

### AI Provider API Keys

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_API_KEY` | Google AI API key |
| `AZURE_OPENAI_KEY` | Azure OpenAI key |
| `XAI_API_KEY` | xAI (Grok) API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |

### OAuth Configuration

| Variable | Description |
|----------|-------------|
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `MICROSOFT_CLIENT_ID` | Microsoft OAuth client ID |
| `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth client secret |

### Payment Configuration

| Variable | Description |
|----------|-------------|
| `STRIPE_API_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook secret |

## Configuration File Locations

- **AGiXT Backend**: `~/.agixt/.env` or `AGiXT/.env`
- **ezLocalai**: `~/.ezlocalai/.env`
- **Web Interface**: Auto-generated from backend settings
- **Credentials**: `~/.agixt/credentials.json`

## Tips

- Changes made with `agixt env` are automatically saved and applied on next restart
- Sensitive values (keys, secrets, passwords) are masked when displayed
- Environment changes in the backend automatically sync to web and ezLocalai
- Use `agixt restart` after changing configuration to apply changes
