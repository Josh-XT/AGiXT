import streamlit as st
from CustomPrompt import CustomPrompt

st.header("Manage Custom Prompts")

# Check if the user is logged in
if not st.session_state.get("logged_in"):
    # Redirect to the login page using JavaScript
    redirect_code = '''
        <script>
            window.location.href = window.location.origin + "/Login"
        </script>
    '''
    st.markdown(redirect_code, unsafe_allow_html=True)

def logout_button():
    """
    Renders the logout button.
    """
    if st.button("Logout"):
        # Clear session state and redirect to the login page
        st.session_state.clear()
        st.experimental_rerun()  # Redirect to the login page

logout_button()


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

st.markdown("## Usage Instructions")
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
