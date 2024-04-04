# Agent Interactions
On the Agent Interactions page, there are 4 modes.
- Chat
- Chains
- Prompt
- Instruct

## Chat
Chatting with an AI is like having a conversation with a friend, but your friend is a computer. You can talk about all sorts of topics, ask questions, and get responses. The AI doesn't just do one thing and stop; it keeps the conversation going. It's more interactive and open-ended than just giving an instruction.

The Chat feature is an interactive interface that enables users to communicate with a selected agent in a conversational manner. Users can type messages and send them to the agent, which will then generate responses based on its configuration and training.

If you have done any agent training to allow the agent to learn from files, websites, or other sources, then the agent will be able to answer questions about information from those sources.  If you have not done any training, then the agent will be able to answer questions about the default training data only.

## Instruct
**Instructions are not questions or conversations, use the Chat for those!**
Think of an instruction as giving a simple, specific command to your pet. For instance, you might tell your dog to "fetch the ball". The dog knows what each of these words means, and it can perform this single task for you. In the world of AI, an instruction could be something like "Translate this sentence into Spanish". It's a single, straightforward command that the AI can execute immediately.

The Instruct feature is designed to allow users to provide specific instructions or tasks to a selected agent. The Agent will choose to run commands from its list of available commands (if any) to complete whatever task was given to it in the instructions.

## Prompt
The Prompt feature allows users to generate responses from a selected agent using a prompt template.

In the Prompt mode, users can select a prompt template from the dropdown menu. The prompt template will be used to generate a prompt, which will then be sent to the agent to generate a response. The response will be displayed in the chat area.

You can view the predefined injection variables by checking the `Show Prompt Injection Variable Documentation` checkbox on the Agent Interactions page.

## Advanced Options for Chat, Instruct, and Prompt

| Option | Description |
| --- | --- |
| `How many conversation results to inject` | This allows you to select how many previous conversations to inject into the agent's memory.  Default is 5. |
| `Shots` | How many times to send the prompt to the agent to generate a responses, this is useful for evaluating multiple responses for decision making. |
| `Inject memories from collection number` | Agents can have multiple collections of memories, this allows you to select a secondary collection to inject context from in addition to the default collection, which is 0. |
| `How many long term memories to inject` | This allows you to select how many memories to inject from the selected collection and from the default collection.  Default is 5. |
| `Enable Browsing Links in the user input` | This will enable the agent to browse any links that you put in the user input and read the content of the page into its memory. |
| `Enable Websearch` | This will enable the agent to perform websearches to find information to answer your questions. Any websites it visits will have their information read into memory collection 0. |
| `Websearch Depth` | If websearch is enabled, this will determine how many pages deep the agent will go when searching for information. |
| `Enable Memory Training` | Any messages sent to or from the agent will be added to the selected memory collection. Recommend to keep this disabled to avoid unintended context pollution. |


## Chains
### What are Chains?
Imagine a chain of dominoes. When you knock over the first one, it sets off a series of actions, with each domino affecting the next. In AI, a chain is a series of steps or commands that are linked together. The output of one step becomes the input for the next. This allows you to create complex workflows, where the AI performs a series of actions in a specific order, like a recipe. It's a way of automating processes, so you can get the AI to do more complex jobs without needing to supervise every step.

Chains are a sequence of Agent actions such as running prompt templates, commands from extensions, or other chains.  Think of them like a workflow, where each step is a task that needs to be completed for the overall objective to be achieved. The AI follows this roadmap, executing each task in the chain in the order they appear, and using the output of one task as the input for the next. This allows the AI to handle complex objectives that require multiple steps to complete.

You can set a different agent per step if you would like, but you can also override the agent used for running the whole chain at run time if you would like.

Chains take one input by default, `user_input`, but it is not required if your chain does not reference it. You can override every input used in the chain at chain run time. The Chains feature allows users to create and manage chains by specifying a chain name. Users can create new chains, delete existing ones, and organize tasks to be executed in a specific order, providing a powerful way to automate complex processes and workflows using agents.

### Advanced Options for Chains

| Option | Description |
| --- | --- |
| `Run a Single Step` | This will run only the selected step in the chain. |
| `Step Number to Run` | This is only available when `Run a Single Step` is enabled. This will allow you to select which step to run. |
| `Start from Step` | This will start the chain from the selected step, it is not available if `Run a Single Step` is checked. |
| `Show All Responses` | By default, chains only output the last response at the end of the chain.  This will show all responses from all steps in the chain. |
