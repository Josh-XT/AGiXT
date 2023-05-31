import streamlit as st
import auth_libs.Redirect as redir
import bcrypt
import logging
from auth_libs.Cfig import Cfig
from auth_libs.Users import load_users, save_user_data

CFIG = Cfig()
conf = CFIG.load_config()

# Check if the user is logged in
if st.session_state.get("logged_in"):
    # Redirect to the Profile page if so
    redir.nav_page("Profile")


def registration_form(auth):
    user_data = load_users()

    if auth and not conf["auth_setup_config"] == "No Login":
        st.write("Registration Form")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")

        if st.button("Register"):
            if password == confirm_password:
                if email not in [user["email"] for user in user_data["users"]]:
                    hashed_password = bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    )
                    user_data["users"].append(
                        {
                            "email": email,
                            "password_hash": hashed_password.decode("utf-8"),
                        }
                    )
                    save_user_data(user_data)
                    st.success("Registration successful!")
                    st.experimental_rerun()  # Redirect to UI
                else:
                    st.error("Email already registered.")
            else:
                st.error("Passwords do not match.")

        st.stop()
    else:
        st.write("Registration Is Not Enabled!")


setup_CFIG = CFIG.load_config()
config = setup_CFIG["config"]
logging.info(config[0])
if config[0]:
    registration_form(auth=config[0])
else:
    st.write("Registration Is Not Enabled!")
