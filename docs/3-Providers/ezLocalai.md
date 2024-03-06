# ezLocalai

- [DevXT](https://devxt.com)
- [ezLocalai](https://github.com/DevXT-LLC/ezlocalai)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

ezLocalai will run a suite of local models for you and automatically handle the pipelines for using them. It is an API that turns any model multimodal. Additional functionality is built in for voice cloning text to speech (drop in a ~10 second voice clip of the person you want to clone the voice of) and a voice to text for easy voice communication as well as image generation entirely offline after the initial setup. It exposes OpenAI style endpoints for ease of use as a drop in OpenAI API replacement with more capabilities. Wrapping AGiXT around it turns your computer into an automation machine.

ezLocalai automatically scales to whatever your desired max tokens is. You just have to set them in your ezlocalai `.env` file before running it.

Hardware requirements to run ezLocalai may be steep! Running 32k context with `Mistral-7B-instruct-v0.2` in ezLocalai requires 23GB VRAM and only running on CPU or NVIDIA GPU is supported by ezLocalai at this time. I often run ezLocalai on my laptop with 16GB VRAM running `phi-2-dpo` with 16k max context and it works very well. You can reduce your VRAM usage by reducing your max tokens. Adjust your `GPU_LAYERS` in your ezLocalai `.env` file to reduce VRAM usage and offload to CPU.

## Quick Start Guide

Follow the instructions for setting up ezLocalai at <https://github.com/DevXT-LLC/ezlocalai>. Once you have it installed and running with your desired models, you can use it with AGiXT by following the instructions below.

### Update your agent settings

1. Set `AI_PROVIDER` to `ezlocalai`.
2. Set `OPENAI_API_KEY` to your API key that you set up with ezLocalai. This is not actually an OpenAI API key, but it is used to authenticate with the ezLocalai API which uses OpenAI style endpoints for ease of integration.
3. Set `AI_MODEL` to whichever model you are running with `ezlocalai`.
4. Set `MAX_TOKENS` to the maximum number of tokens you want to generate.
5. Set `AI_TEMPERATURE` to the temperature you want to use for generation. This is a float value between 0 and 1. The default is `1.33`.
6. Set `AI_TOP_P` to the top_p value you want to use for generation. This is a float value between 0 and 1. The default is `0.95`.
7. Set `SYSTEM_MESSAGE` to the message you want to use for the system message. It is useful to put things like the agents persona and rules for usage here.
8. Set `VOICE` to the voice you want to use for the generated audio. The default is `DukeNukem`. You can add cloning TTS voices to `ezlocalai` by putting any ~10 second wav file in the `voices` directory of the `ezlocalai` repository and then setting the `VOICE` variable to the name of the file without the `.wav` extension.
