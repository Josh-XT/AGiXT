# Chains
## What are Chains?
Imagine a chain of dominoes. When you knock over the first one, it sets off a series of actions, with each domino affecting the next. In AI, a chain is a series of steps or commands that are linked together. The output of one step becomes the input for the next. This allows you to create complex workflows, where the AI performs a series of actions in a specific order, like a recipe. It's a way of automating processes, so you can get the AI to do more complex jobs without needing to supervise every step.

Chains are a sequence of Agent actions such as running prompt templates, commands from extensions, or other chains.  Think of them like a workflow, where each step is a task that needs to be completed for the overall objective to be achieved. The AI follows this roadmap, executing each task in the chain in the order they appear, and using the output of one task as the input for the next. This allows the AI to handle complex objectives that require multiple steps to complete.

You can set a different agent per step if you would like, but you can also override the agent used for running the whole chain at run time if you would like.

Chains take one input by default, `user_input`, but it is not required if your chain does not reference it. You can override every input used in the chain at chain run time. The Chains feature allows users to create and manage chains by specifying a chain name. Users can create new chains, delete existing ones, and organize tasks to be executed in a specific order, providing a powerful way to automate complex processes and workflows using agents.

### Predefined Injection Variables
Any of these variables can be used in command arguments or prompt arguments to inject data into the prompt. These can also be used inside of any Custom Prompt.

- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected. This will only work if you have `{user_input}` in your prompt arguments for the memory search. (Only applies to prompts but is still a reserved variable name.)
- `{date}` will cause the current date and timestamp to be injected.
- `{conversation_history}` will cause the conversation history to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.