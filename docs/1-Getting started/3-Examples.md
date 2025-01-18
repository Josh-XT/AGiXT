# Examples

We plan to build more examples but would love to see what you build with AGiXT.  If you have an example you would like to share, please submit a pull request to add it to this page.

## Expert Agent Example

Example of a basic AGiXT expert agent:  Create your agent, make it learn from whichever files or websites you want. You can try it out in the same notebook and in the web interface.

You can open this file in a Jupyter Notebook and run the code cells to see the example in action.

- [ezLocalai Example](https://github.com/Josh-XT/AGiXT/blob/main/examples/AGiXT-Expert-ezLocalai.ipynb)
- [OpenAI Example](https://github.com/Josh-XT/AGiXT/blob/main/examples/AGiXT-Expert-OAI.ipynb)

## Voice Chat Example

Example of a basic AGiXT voice chat: Make the agent listen to you saying a specific word that makes it take what you say, send it to the agent, and then execute an AGiXT function. In this example, you can use two different wake functions, `chat` and `instruct`. When this example is running, and you say each of the wake words, it will take the words you say after that, send them to the agent, and respond back to you with an audio response.

You can open this file in a Jupyter Notebook and run the code cells to see the example in action. <https://github.com/Josh-XT/AGiXT/blob/main/examples/Voice.ipynb>

## OpenAI Style Chat Completions Endpoint Example

See the details of this [pull request](https://github.com/Josh-XT/AGiXT/pull/1149) for example usage of the chat completions endpoint in AGiXT.

- Built in accommodations for uploading audio, files, or images to the pipeline of chat completions.
- Adds support for the `gpt-4-vision-preview` model allowing images to be uploaded with the same syntax. Follow syntax from OpenAI documentation on how your request should look to send images <https://platform.openai.com/docs/guides/vision>
- Adds support for vision models being used with [ezLocalai](https://github.com/DevXT-LLC/ezlocalai) using the same OpenAI endpoint syntax mentioned above.
- Audio upload support through the chat completions endpoint has been implemented.
- File upload support through the chat completions endpoint has been implemented.
- Website scraping by giving the URL through the chat completions endpoint as been implemented.

Example of URL scraping, file, image, and audio uploads below in a single endpoint that also prompts the agent:

```python
import openai

response = openai.chat.completions.create(
    model="THE AGENTS NAME GOES HERE",
    messages=[
        {
            "conversation_name": "The conversation name", # The conversation name goes here
            "prompt_category": "Default",  # Optional, default will be "Default"
            "prompt_name": "Chat",  # Optional, the prompt template name goes here, default will be "Chat"
            "context_results": 5,  # Optional, default will be 5
            "websearch": false, # Set to true to enable websearch, default is false
            "websearch_depth": 0, # Set to the number of depth you want to websearch to go (3 would go 3 links deep per link it scrapes)
        },
        {
            "role": "user",
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
                    "url": {  # Content of the text or URL for it to be scraped
                        "url": "https://agixt.com"
                    },
                    "collection_number": 0,  # Optional field, defaults to 0.
                },
                {
                    "type": "application_url",
                    "url": {  # Will scrape mime type `application` into the agent's memory
                        "url": "data:application/pdf;base64,base64_encoded_pdf_here"
                    },
                    "collection_number": 0,  # Optional field, defaults to 0.
                },
                {
                    "type": "audio_url",
                    "url": {  # Will transcribe the audio and send it to the agent in the same way as text. Enables easy voice chat.
                        "url": "data:audio/wav;base64,base64_encoded_audio_here"
                    },
                },
            ],
        },
    ],
    max_tokens=4096,
    temperature=0.7,
    top_p=0.9,
)
print(response.choices[0].message.content)
```
