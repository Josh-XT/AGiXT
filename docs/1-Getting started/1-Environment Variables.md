# Environment Variables

The script sets up various environment variables for AGiXT. Some key variables and their purposes include:

- `AGIXT_API_KEY`: API key for AGiXT (**automatically generated if not provided**)
- `AGIXT_URI`: URI for the AGiXT API
- `AGIXT_BRANCH`: AGiXT version to use (`stable` or `dev`)
- `AGIXT_AUTO_UPDATE`: Whether to automatically update AGiXT
- `AGIXT_RLHF`: Enable reinforcement learning from human feedback (thumbs up/down buttons in UI)
- `AGIXT_SHOW_SELECTION`: Controls which dropdowns are shown in the UI. Comma separated values. (default is `agent,conversation`)
- `AUTH_PROVIDER`: Authentication provider (`none` or `magicalauth`)
- `INTERACTIVE_MODE`: Should always be set to `chat` (`form` mode is experimental)
- `THEME_NAME`: UI color scheme (`default`, `christmas`, `conspiracy`, `doom`, `easter`, `halloween`, `valentines`)
- `DATABASE_TYPE`: Type of database to use (`sqlite` or `postgres`)
- `UVICORN_WORKERS`: Number of workers running on the application. Default is `10`.

Environment variables specific to ezLocalai:

Note: If you do not have an NVIDIA GPU, the correct CUDA drivers, or enough VRAM, ezLocalai will still work running on CPU, but it will be slower.

- `EZLOCALAI_URI`: URI for ezLocalai. Default is `http://{local_ip}:8091`.
- `DEFAULT_MODEL`: Default language model for ezLocalai. Default is `QuantFactory/dolphin-2.9.2-qwen2-7b-GGUF`. This model takes ~9GB VRAM at 32k max tokens, lower the max tokens if you have less VRAM or use a different model.
- `VISION_MODEL`: Vision model for ezLocalai. Default is `deepseek-ai/deepseek-vl-1.3b-chat`. This model takes ~3GB VRAM in addition to the language model.
- `LLM_MAX_TOKENS`: Maximum number of tokens for language models. Default is `32768`. Lower this value if you have less VRAM.
- `WHISPER_MODEL`: Whisper model for speech recognition. Default is `base.en` for a fast English model.
- `GPU_LAYERS`: Number of GPU layers to use. Default is `-1` for all.

For a complete list of environment variables and their default values, please refer to the `get_default_env_vars()` function in the `start.py` script.
