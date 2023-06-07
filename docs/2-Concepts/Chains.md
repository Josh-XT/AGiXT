# Chains
Chains are a sequence of Agent actions such as running prompt templates or commands from extensions.  Chains take one input for running, which is `user_input`, but it is not required if your chain does not reference it. The Chains feature allows users to create and manage chains by specifying a chain name. Users can create new chains, delete existing ones, and organize tasks to be executed in a specific order, providing a powerful way to automate complex processes and workflows using agents.

### Predefined Injection Variables
Any of these variables can be used in command arguments or prompt arguments to inject data into the prompt. These can also be used inside of any Custom Prompt.

- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected. This will only work if you have `{user_input}` in your prompt arguments for the memory search. (Only applies to prompts but is still a reserved variable name.)
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.