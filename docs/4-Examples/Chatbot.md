# Chatbot Example
Example of a basic AGiXT chatbot.  Set your agent, make it to learn whichever urls or files, then just keep using that conversation ID to keep a conversation going with the AI where it is aware of the history of your conversation (last 5 interactions).  If you want to keep talking to it about the same docs with out the history, start a new conversation (generate a new UUID to use) and keep going with the same agent without any retraining of the documentation.

You can open this file in a Jupyter Notebook and run the code cells to see the example in action. https://github.com/Josh-XT/AGiXT/blob/main/examples/Chatbot.ipynb

## Install latest AGiXT SDK.
```
pip install -U agixtsdk
```

## Import the SDK and set your base URI and API key:
```python
import uuid
from agixtsdk import AGiXTSDK

# Your AGiXT URL and API key
base_uri = "http://localhost:7437"
api_key = None

ApiClient = AGiXTSDK(base_uri=base_uri, api_key=api_key)
```

## Set your agent name and conversation ID:
```python
# New chatbot session
conversation = uuid.uuid4()
agent_name = "OpenAI"
print(f"Conversation ID: {conversation}")
```

## Learn from some documentation:
```python
ApiClient.learn_url(agent_name=agent_name, url="https://josh-xt.github.io/AGiXT/")
```

## Chat with the chatbot:
```python
user_input = "What is AGiXT?"
response = ApiClient.chat(user_input=user_input, conversation=conversation, agent_name=agent_name)
print(response)
```

## Chat with the chatbot again:
Keep using the same conversation ID to keep the history of the conversation going.

```python
user_input = "Awesome! What could I do with it?"
response = ApiClient.chat(user_input=user_input, conversation=conversation, agent_name=agent_name)
print(response)
```

## Start a new conversation with the same agent:
```python
# New chatbot session
conversation = uuid.uuid4()
user_input = "What is AGiXT?"
response = ApiClient.chat(user_input=user_input, conversation=conversation, agent_name=agent_name)
print(response)
```
