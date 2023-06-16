import streamlit as st
from ApiClient import ApiClient
from components.verify_backend import verify_backend
from components.docs import agixt_docs

verify_backend()

st.set_page_config(
    page_title="Prompt Templates",
    page_icon=":scroll:",
    layout="wide",
)
agixt_docs()

st.header("Prompt Templates")

prompt_list = ApiClient.get_prompts()

action = st.selectbox("Action", ["Create New Prompt", "Modify Prompt", "Delete Prompt"])

if action == "Create New Prompt":
    # Import prompt button
    prompt_file = st.file_uploader("Import Prompt", type=["txt"])
    if prompt_file:
        prompt_name = prompt_file.name.split(".")[0]
        prompt_content = prompt_file.read().decode("utf-8")
        ApiClient.add_prompt(prompt_name=prompt_name, prompt=prompt_content)
        st.success(f"Prompt '{prompt_name}' added.")
    prompt_name = st.text_input("Prompt Name")
    prompt_content = st.text_area("Prompt Content", height=300)

elif action == "Modify Prompt":
    prompt_name = st.selectbox("Existing Prompts", prompt_list)
    prompt_content = st.text_area(
        "Prompt Content",
        ApiClient.get_prompt(prompt_name=prompt_name) if prompt_name else "",
        height=300,
    )
    export_button = st.download_button(
        "Export Prompt", data=prompt_content, file_name=f"{prompt_name}.txt"
    )
elif action == "Delete Prompt":
    prompt_name = st.selectbox("Existing Prompts", prompt_list)
    prompt_content = None

if st.button("Perform Action"):
    if prompt_name and (prompt_content or action == "Delete Prompt"):
        if action == "Create New Prompt":
            ApiClient.add_prompt(prompt_name=prompt_name, prompt=prompt_content)
            st.success(f"Prompt '{prompt_name}' added.")
        elif action == "Modify Prompt":
            ApiClient.update_prompt(prompt_name=prompt_name, prompt=prompt_content)
            st.success(f"Prompt '{prompt_name}' updated.")
        elif action == "Delete Prompt":
            ApiClient.delete_prompt(prompt_name)
            st.success(f"Prompt '{prompt_name}' deleted.")
    else:
        st.error("Prompt name and content are required.")

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
- `{context}` will cause the current context from memory to be injected. This will only work if you have `{user_input}` in your prompt arguments for the memory search.
- `{date}` will cause the current date and timestamp to be injected.
- `{COMMANDS}` will cause the available commands list to be injected and for automatic commands execution from the agent based on its suggestions.
- `{command_list}` will cause the available commands list to be injected, but will not execute any commands the AI chooses. Useful on validation steps.
- `{STEPx}` will cause the step `x` response from a chain to be injected. For example, `{STEP1}` will inject the first step's response in a chain.
"""
)
