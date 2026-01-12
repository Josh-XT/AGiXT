# ezLocalai Provider

[ezLocalai](https://github.com/DevXT-LLC/ezlocalai) provides complete local AI inference capabilities for AGiXT. It runs a suite of local models and handles pipelines for multimodal AI operations.

## Features

- **Local LLM**: Run large language models locally (GGUF format)
- **Vision**: Image analysis with local vision models
- **Text-to-Speech**: Voice synthesis with voice cloning support
- **Speech-to-Text**: Audio transcription with Whisper
- **Image Generation**: Local Stable Diffusion support
- **OpenAI-Compatible API**: Drop-in replacement for OpenAI endpoints

## Quick Start

ezLocalai is automatically started with AGiXT by default:

```bash
pip install agixt
agixt start
```

To disable ezLocalai:
```bash
agixt env WITH_EZLOCALAI=false
agixt restart
```

To manage ezLocalai separately:
```bash
agixt start --ezlocalai    # Start only ezLocalai
agixt stop --ezlocalai     # Stop only ezLocalai
agixt logs --ezlocalai     # View ezLocalai logs
```

## Configuration

Configure ezLocalai using the `agixt env` command:

```bash
# Set the default model
agixt env DEFAULT_MODEL="bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF"

# Configure token limits
agixt env LLM_MAX_TOKENS=32768

# Set vision model
agixt env VISION_MODEL="deepseek-ai/deepseek-vl-1.3b-chat"

# Configure GPU usage
agixt env GPU_LAYERS=-1  # -1 for all layers on GPU
```

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EZLOCALAI_URI` | `http://{local_ip}:8091` | ezLocalai API endpoint |
| `DEFAULT_MODEL` | `bartowski/deepseek-ai_DeepSeek-R1-0528-Qwen3-8B-GGUF` | Default LLM model |
| `VISION_MODEL` | `deepseek-ai/deepseek-vl-1.3b-chat` | Vision model |
| `LLM_MAX_TOKENS` | `32768` | Maximum token context |
| `WHISPER_MODEL` | `base.en` | Speech-to-text model |
| `GPU_LAYERS` | `-1` | GPU layers (-1 = all) |

## Hardware Requirements

ezLocalai automatically detects and configures GPU settings, but approximate requirements are:

| Configuration | VRAM Needed | Notes |
|--------------|-------------|-------|
| 8B model @ 32k tokens | ~23GB | Requires high-end GPU |
| 8B model @ 16k tokens | ~14GB | Mid-range gaming GPU |
| 7B model @ 8k tokens | ~8GB | Entry-level GPU |
| CPU only | N/A | Works but significantly slower |

### Reducing VRAM Usage

- Lower `LLM_MAX_TOKENS` to reduce context size
- Adjust `GPU_LAYERS` to offload some layers to CPU
- Use smaller quantized models (Q4, Q5)
- Disable vision model if not needed

## Agent Configuration

To use ezLocalai with an agent:

1. In agent settings, set:
   - `AI_PROVIDER` = `ezlocalai`
   - `EZLOCALAI_API_URL` = ezLocalai endpoint (default: `http://localhost:8091`)
   - `EZLOCALAI_MODEL` = your model name

2. Or use the AGiXT Python SDK:

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

agixt.update_agent_settings(
    agent_name="MyAgent",
    settings={
        "AI_PROVIDER": "ezlocalai",
        "EZLOCALAI_API_URL": "http://localhost:8091",
        "EZLOCALAI_MODEL": "your-model-name",
        "MAX_TOKENS": 4096,
    }
)
```

## Voice Cloning

ezLocalai supports voice cloning for text-to-speech:

1. Place a ~10 second WAV file of the voice to clone in the `voices` directory
2. Set `EZLOCALAI_VOICE` to the filename (without `.wav` extension)

Example:
```bash
# Copy voice sample
cp my_voice.wav ~/.ezlocalai/voices/

# Configure agent to use the voice
agixt env EZLOCALAI_VOICE=my_voice
```

## Troubleshooting

### No GPU detected
- Ensure NVIDIA drivers are installed
- Install NVIDIA Container Toolkit for Docker mode
- Check `nvidia-smi` works on your system

### Out of memory errors
- Reduce `LLM_MAX_TOKENS`
- Lower `GPU_LAYERS` to offload to CPU
- Use a smaller model

### Slow responses
- Running on CPU is significantly slower than GPU
- Consider using a smaller model or upgrading hardware

## More Information

For detailed ezLocalai documentation, see the [ezLocalai repository](https://github.com/DevXT-LLC/ezlocalai).
