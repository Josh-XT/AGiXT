# Custom Prompts
Custom Prompts is a feature that enables users to create, update, and delete customized prompts for their agents. By providing a prompt name and content, users can design custom interactions and tasks for the agent to perform. This feature allows users to tailor the behavior of the agent and create specialized prompts that cater to specific requirements and use cases.

## Prompt Formats

Each prompt has a specific format for providing instructions to the AI agents. Any variables you add to a prompt like `{task}` will be formatted with their input variables. For example, if you have a prompt that says `Do {task} {when}`, and you provide the input variables `task=the dishes` and `when=now`, the prompt will be formatted to `Do the dishes now`.

Any prompt in the `prompts` folder can be copied to a `model-prompts\{model_name}` folder and modified to suit your needs for that model and it will take over as the default as long as you have that model selected for your provider.
