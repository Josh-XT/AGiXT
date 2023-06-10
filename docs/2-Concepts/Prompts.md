# Prompts
Prompts is a feature that enables users to create, update, and delete customized prompts for their agents. By providing a prompt name and content, users can design custom interactions and tasks for the agent to perform. This feature allows users to tailor the behavior of the agent and create specialized prompts that cater to specific requirements and use cases.

## Prompt Formats

Each prompt has a specific format for providing instructions to the AI agents. Any variables you add to a prompt like `{user_input}` will be formatted with their input variables. For example, if you have a prompt that says `Do {user_input} {when}`, and you provide the input variables `task=the dishes` and `when=now`, the prompt will be formatted to `Do the dishes now`.

## Specific Model Prompts for Overrides

Inside of the `agixt\prompts` folder, you can add a folder with the name you set in your agent settings for `AI_MODEL` and it will use those prompts instead of the default ones. This allows you to have different prompts for different models that essentially do the same thing but with different wording that might be more optimized for that model.

For example, `GPT-4` has an 8K token limit, so we over ride the `instruct` prompt to let it know that it has a `4000 word limit` instead of the default prompt that says `500 word limit.`

There is currently not an interface for this other than your folder structure.

## Predefined Injection Variables
- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected. This will only work if you have `{user_input}` in your prompt arguments for the memory search.
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.

