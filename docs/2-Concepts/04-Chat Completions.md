# AGiXT Chat Completions

The [Chat Completions Endpoint](https://platform.openai.com/docs/guides/text-generation/chat-completions-api) matches the behavior of the OpenAI Chat Completions API, but with the additional features and functionality of running prompt templates, commands, and chains based on the agent's settings and `mode`. You can set your agent `mode` in your agent configuration to change the behavior of the `/v1/chat/completions` endpoint.

## Agent Modes

The agent `mode` changes the behavior of the chat completions endpoint when interacting with the agent to either use a prompt template, command, or chain depending on the agent settings.

- Agent setting `mode` can be `prompt`, `command`, or `chain` in the agent's settings.
- If an agent mode is not defined, the chat completions endpoint will use the `Chat` prompt template.

### `prompt` mode

Executes the designated prompt template when interacted with on the chat completions endpoint.

- Requires `prompt_name` and `prompt_category` to also be defined in the agent settings.
- Will use the `user_input` variable in prompt templates to inject the user's input from their message content.

### `command` mode

Executes the designated command when interacted with on the chat completions endpoint.

- Requires `command_name`, `command_args`, and `command_variable` to be defined in the agent settings.
- `command_variable` is the command to inject the message content into for the command arguments.

### `chain` mode

Executes the designated chain when interacted with on the chat completions endpoint.

- Requires `chain_name`, `chain_args` to be defined in the agent settings.
- Message content will be injected into the `user_input` for running the chain.

## Usage Example

To use the `openai` python package to directly interact with your AGiXT agents, you can use the following code snippet to interact with the chat completions endpoint.

Important notes about additional functionality:

- `model` should be the agent's name you want to interact with.
- `user` should be the conversation name you want to use.
- If files are uploaded to the chat completions endpoint, they will be stored in the agent's memory and can be referenced by the agent's prompt templates, commands, and chains.
- You can define additional functionality if you would like to override how many memories are injected with `context_results`, enable websearch with `websearch`, set the depth of the websearch with `websearch_depth`, enable the agent to browse links with `browse_links`, and `create_image` to generate an image with the agent's designated image provider and send the image with the response.
- Otherwise, follow the [OpenAI Chat Completions API Documentation.](https://platform.openai.com/docs/guides/text-generation/chat-completions-api)

```python
import openai

openai.base_url = "http://localhost:7437/v1/"
openai.api_key = "Your AGiXT API Key"

response = openai.chat.completions.create(
    model="THE AGENTS NAME GOES HERE",
    messages=[
        {
            "role": "user",
            "create_image": "true",  # Generates an image with the agents designated image_provider and sends image with response.
            "context_results": 5,  # Optional, default will be 5 if not set.
            "websearch": False,  # Set to true to enable websearch, false to disable. Default is false if not set.
            "websearch_depth": 0,  # Set to the number of depth you want to websearch to go (3 would go 3 links deep per link it scrapes)
            "browse_links": True,  # Will make the agent scrape any web URLs the user puts in chat.
            "content": [
                {"type": "text", "text": "YOUR USER INPUT TO THE AGENT GOES HERE"},
                {
                    "type": "image_url",
                    "image_url": {  # Will download the image and send it to the vision model
                        "url": f"https://www.visualwatermark.com/images/add-text-to-photos/add-text-to-image-3.webp"
                    },
                },
                {
                    "type": "text_url",  # Or just "url"
                    "text_url": {  # Content of the text or URL for it to be scraped
                        "url": "https://agixt.com"
                    },
                    "collection_number": 0,  # Optional field, defaults to 0.
                },
                {
                    "type": "application_url",
                    "application_url": {  # Will scrape mime type `application` into the agent's memory
                        "url": "data:application/pdf;base64,base64_encoded_pdf_here"
                    },
                    "collection_number": 0,  # Optional field, defaults to 0.
                },
                {
                    "type": "audio_url",
                    "audio_url": {  # Will transcribe the audio and send it to the agent
                        "url": "data:audio/wav;base64,base64_encoded_audio_here"
                    },
                },
            ],
        },
    ],
    max_tokens=4096,
    temperature=0.7,
    top_p=0.9,
    user="THE CONVERSATION NAME", # Set to the conversation name you want to use
)
print(response.choices[0].message.content)
```

GitHub and YouTube captions can be read in the chat completions pipeline. The associated endpoint for YouTube captions reader is `/api/agent/{agent_name}/learn/youtube`. If `browse_links` is enabled and a YouTube video link is given in the chat, the agent will read the content of the captions for the YouTube video linked into memory.

If you pass images to the chat completions endpoint, it will send them to the vision model first, get the vision model's response, and pass that response in context to the LLM model with the context injected and wrapped in the selected prompt template.
