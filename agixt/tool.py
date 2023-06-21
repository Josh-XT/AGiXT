from tools import CustomAgent, OpenAiAgentClient, HfAgentClient

# Use the starcoder client
client = HfAgentClient(
    "https://api-inference.huggingface.co/models/bigcode/starcoder",
    "hf_xxxxxxxxxxxxxxxxxxxxxx"
)
# Or use the Open AI client
client = OpenAiAgentClient(api_key="", api_base="https://gpt4.gravityengine.cc/api/openai/v1")

# Use a own explanation to have more control.
# Or let generate one for you.
explanation = """
I will use the following tool: `search` to find 5 websites with current marketing trends.
# The custom agent support for loops
I iterate the found websites.
I use `srcape_text` to get the complete text.
# If we use the open ai client, we use open ai for summarize too.
I use `summarizer` for the text.
I use `image_generator` to create a image, which match to the title.
Create a `filename` without spaces for a image with jpg extension.
I use `create_thumbnail` to create a thumbnail with `filename` and size `(200, 200)`.
# Create a file with markdown syntax:
I append `f"## {title}\\n\\n"` to result.
I append `![image]({filename})` to result.
I append the text to result.
I append `f"\\n\\nSource: {link}\\n\\n"` to result.
# Finally we write the created content to a file:
I use `write_to_file` to write result to `marketing.md`.
"""

# Init our custom agent with the selected client
agent = CustomAgent(client)

# Run agent with the given task
print(agent.run("Create a blog post about marketing.", explanation=explanation, remote=True))