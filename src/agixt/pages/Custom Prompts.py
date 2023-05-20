import streamlit as st
from CustomPrompt import CustomPrompt

st.header("Manage Custom Prompts")
prompt_name = st.text_input("Prompt Name")
prompt_content = st.text_area("Prompt Content")
prompt_action = st.selectbox("Action", ["Add Prompt", "Update Prompt", "Delete Prompt"])

if st.button("Perform Action"):
    if prompt_name and prompt_content:
        custom_prompt = CustomPrompt()
        if prompt_action == "Add Prompt":
            custom_prompt.add_prompt(prompt_name, prompt_content)
            st.success(f"Prompt '{prompt_name}' added.")
        elif prompt_action == "Update Prompt":
            custom_prompt.update_prompt(prompt_name, prompt_content)
            st.success(f"Prompt '{prompt_name}' updated.")
        elif prompt_action == "Delete Prompt":
            custom_prompt.delete_prompt(prompt_name)
            st.success(f"Prompt '{prompt_name}' deleted.")
    else:
        st.error("Prompt name and content are required.")
