# Examples

We welcome community examples! If you have an example you would like to share, please submit a pull request.

## Quick Start with Python SDK

```python
from agixtsdk import AGiXTSDK

# Connect to AGiXT
agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_api_key")

# Chat with an agent
response = agixt.chat(
    agent_name="XT",
    user_input="Hello! What can you help me with?",
    conversation_name="my_chat"
)
print(response)
```

## OpenAI-Compatible Chat Completions

AGiXT provides an OpenAI-compatible API, so you can use the standard OpenAI Python package:

```python
import openai

openai.base_url = "http://localhost:7437/v1/"
openai.api_key = "your_agixt_api_key"

response = openai.chat.completions.create(
    model="XT",  # Agent name
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    max_tokens=4096,
    temperature=0.7,
)
print(response.choices[0].message.content)
```

## Multi-Modal Chat (Images, Audio, Files)

Send images, audio, or files through the chat completions endpoint:

```python
import openai

response = openai.chat.completions.create(
    model="XT",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What can you tell me about this image?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image.jpg"
                    },
                },
            ],
        },
    ],
    user="my_conversation",  # Conversation name
)
print(response.choices[0].message.content)
```

### Additional Content Types

```python
# Web URL scraping
{
    "type": "text_url",
    "text_url": {"url": "https://agixt.com"},
}

# PDF or document upload (base64 encoded)
{
    "type": "application_url",
    "application_url": {
        "url": "data:application/pdf;base64,base64_encoded_pdf_here"
    },
}

# Audio transcription (base64 encoded)
{
    "type": "audio_url",
    "audio_url": {
        "url": "data:audio/wav;base64,base64_encoded_audio_here"
    },
}
```

## Training an Agent on Documents

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

# Learn from a website
agixt.learn_url(
    agent_name="XT",
    url="https://docs.example.com",
    collection_number="0"
)

# Learn from a GitHub repository
agixt.learn_github_repo(
    agent_name="XT",
    github_repo="Josh-XT/AGiXT",
    collection_number="0"
)

# Now ask questions about the learned content
response = agixt.chat(
    agent_name="XT",
    user_input="What is AGiXT?",
    conversation_name="research"
)
```

## Running a Chain (Workflow)

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

# Run a predefined chain
result = agixt.run_chain(
    chain_name="Research and Summarize",
    user_input="Analyze the latest trends in AI",
    agent_name="XT",
    all_responses=False  # Return only final result
)
print(result)
```

## Enabling Agent Commands

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

# Enable specific commands for an agent
agixt.update_agent_commands(
    agent_name="XT",
    commands={
        "Web Search": True,
        "Read Website Content": True,
        "Write to File": True,
    }
)
```

## CLI Usage Examples

```bash
# Start a new conversation
agixt conversations -

# Send a prompt to the default agent
agixt prompt "Explain quantum computing in simple terms"

# Specify an agent
agixt prompt "Write a Python function to sort a list" --agent XT

# View conversation history
agixt conversations
```

## Voice Chat Example

For voice interaction capabilities, see the Jupyter notebook example:
- [Voice Chat Example](https://github.com/Josh-XT/AGiXT/blob/main/examples/Voice.ipynb)

## Expert Agent Example

Create an expert agent that learns from your documentation:
- [ezLocalai Example](https://github.com/Josh-XT/AGiXT/blob/main/examples/AGiXT-Expert-ezLocalai.ipynb)
- [OpenAI Example](https://github.com/Josh-XT/AGiXT/blob/main/examples/AGiXT-Expert-OAI.ipynb)

## More Examples

Check the [examples directory](https://github.com/Josh-XT/AGiXT/tree/main/examples) in the AGiXT repository for more Jupyter notebooks and sample code.
