import streamlit as st
import bcrypt
from auth_libs.Users import load_users, save_user_data
from auth_libs.Cfig import Cfig
from auth_libs.Users import check_auth_status
from components.agent_selector import agent_selector

check_auth_status()
agent_name, agent = agent_selector()
CFG = Cfig()

# Check if the user is logged in


def logout_button():
    """
    Renders the logout button.
    """
    if st.button("Logout"):
        # Clear session state and redirect to the login page
        st.session_state.clear()
        st.experimental_rerun()  # Redirect to the login page


# Toggle public registrations
def toggle_value(val, to_toggle="allow_reg"):
    setup_cfg = CFG.load_cfg_data()
    for config in setup_cfg["config"]:
        config[to_toggle] = val
    CFG.save_cfg_data(setup_cfg)

    if val == False:
        st.success("Setting Disabled!")
    else:
        st.success("Setting Enabled!")

    st.session_state["regCheck"] = val


# Change password form
def change_password_form():
    st.write("Change Password")
    current_password = st.text_input("Current Password", type="password")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm New Password", type="password")
    if st.button("Change Password"):
        user_data = load_users()
        for user in user_data["users"]:
            if user["email"] == st.session_state["email"]:
                if bcrypt.checkpw(
                    current_password.encode("utf-8"),
                    user["password_hash"].encode("utf-8"),
                ):
                    if new_password == confirm_password:
                        hashed_password = bcrypt.hashpw(
                            new_password.encode("utf-8"), bcrypt.gensalt()
                        )
                        user["password_hash"] = hashed_password.decode("utf-8")
                        save_user_data(user_data)
                        st.success("Password changed successfully!")
                    else:
                        st.error("New password and confirm password do not match.")
                else:
                    st.error("Incorrect current password.")
                break


# Create user form (admin only)
def create_user_form():
    admin_email = CFG.get_admin_email()
    if st.session_state["email"] != admin_email:
        st.error("Only the admin can create new users.")
        return
    st.write("Create User")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    if st.button("Create User"):
        if not email:
            st.error("Email is required.")
        elif password != confirm_password:
            st.error("Password and confirm password do not match.")
        else:
            user_data = load_users()
            for user in user_data["users"]:
                if user["email"] == email:
                    st.error("User with the same email already exists.")
                    return

            hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
            new_user = {
                "email": email,
                "password_hash": hashed_password.decode("utf-8"),
                "admin": "False",
            }
            user_data["users"].append(new_user)
            save_user_data(user_data)
            st.success("User created successfully!")


try:
    admin_email = CFG.get_admin_email()
    logout_button()
    if st.session_state["email"] == admin_email and CFG.auth != "SUL":
        setup_cfg = CFG.load_cfg_data()
        for config in setup_cfg["config"]:
            allow_reg = config["allow_reg"]
            allow_uac = config["allow_uac"]
            allow_ucp = config["allow_ucp"]
            allow_uaa = config["allow_uaa"]

        st.session_state["regCheck"] = allow_reg

        if allow_reg == True:
            ar_opposite = False
        else:
            ar_opposite = True

        if allow_uac == True:
            uac_opposite = False
        else:
            uac_opposite = True

        if allow_ucp == True:
            ucp_opposite = False
        else:
            ucp_opposite = True

        if allow_uaa == True:
            uaa_opposite = False
        else:
            uaa_opposite = True

        col1, col2 = st.columns(2)

        with col1:
            if CFG.auth == "MPBR":
                st.checkbox(
                    "Enable Public Registration",
                    value=allow_reg,
                    on_change=toggle_value,
                    args=(ar_opposite, "allow_reg"),
                )
            else:
                st.checkbox(
                    "Enable Public Registration",
                    value=allow_reg,
                    on_change=toggle_value,
                    args=(ar_opposite, "allow_reg"),
                    disabled=True,
                )
            st.checkbox(
                "Enable Users to Create Public Agents",
                value=allow_uac,
                on_change=toggle_value,
                args=(uac_opposite, "allow_uac"),
            )

        with col2:
            st.checkbox(
                "Enable Users To Create Private Agents",
                value=allow_ucp,
                on_change=toggle_value,
                args=(ucp_opposite, "allow_ucp"),
            )
            st.checkbox(
                "Enable Users To Use Admin's Agents",
                value=allow_uaa,
                on_change=toggle_value,
                args=(uaa_opposite, "allow_uaa"),
            )

    change_password_form()
    if st.session_state["email"] == admin_email and CFG.auth != "SUL":
        create_user_form()
except:
    st.write("You are not logged in, or login is not enabled.")
