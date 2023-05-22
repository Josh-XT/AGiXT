# Custom Prompts
Custom Prompts is a feature that enables users to create, update, and delete customized prompts for their agents. By providing a prompt name and content, users can design custom interactions and tasks for the agent to perform. This feature allows users to tailor the behavior of the agent and create specialized prompts that cater to specific requirements and use cases.

## Prompt Formats

Each prompt has a specific format for providing instructions to the AI agents. Any variables you add to a prompt like `{task}` will be formatted with their input variables. For example, if you have a prompt that says `Do {task} {when}`, and you provide the input variables `task=the dishes` and `when=now`, the prompt will be formatted to `Do the dishes now`.

Any prompt in the `prompts` folder can be copied to a `model-prompts\{model_name}` folder and modified to suit your needs for that model and it will take over as the default as long as you have that model selected for your provider.

## Predefined Injection Variables
- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected.
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.