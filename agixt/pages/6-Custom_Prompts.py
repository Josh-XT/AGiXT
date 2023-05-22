import streamlit as st
from CustomPrompt import CustomPrompt
from auth_libs.Users import check_auth_status

check_auth_status()

st.header("Manage Custom Prompts")
st.markdown("### Usage Instructions")
st.markdown(
    """
To create dynamic prompts that can have user inputs, you can use curly braces `{}` in your prompt content. 
Anything between the curly braces will be considered as an input field. For example:

```python
"Hello, my name is {name} and I'm {age} years old."
```
In the above prompt, `name` and `age` will be the input arguments. These arguments can be used in chains.
"""
)
st.markdown("### Predefined Injection Variables")
st.markdown(
    """
- `{agent_name}` will cause the agent name to be injected.
- `{context}` will cause the current context from memory to be injected.
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.
"""
)

custom_prompt = CustomPrompt()
prompt_list = custom_prompt.get_prompts()

if st.checkbox("Add New Prompt"):
    action = "Add Prompt"
    prompt_name = st.text_input("Prompt Name")
    prompt_content = st.text_area("Prompt Content", height=300)
else:
    action = st.selectbox("Action", ["Update Prompt", "Delete Prompt"])
    prompt_name = st.selectbox("Existing Prompts", prompt_list)
    prompt_content = st.text_area(
        "Prompt Content",
        custom_prompt.get_prompt(prompt_name) if prompt_name else "",
        height=300,
    )

if st.button("Perform Action"):
    if prompt_name and (prompt_content or action == "Delete Prompt"):
        if action == "Add Prompt":
            custom_prompt.add_prompt(prompt_name, prompt_content)
            st.success(f"Prompt '{prompt_name}' added.")
        elif action == "Update Prompt":
            custom_prompt.update_prompt(prompt_name, prompt_content)
            st.success(f"Prompt '{prompt_name}' updated.")
        elif action == "Delete Prompt":
            custom_prompt.delete_prompt(prompt_name)
            st.success(f"Prompt '{prompt_name}' deleted.")
    else:
        st.error("Prompt name and content are required.")
