from DBConnection import User, get_session
from db.Agent import add_agent
import os
from agixtsdk import AGiXTSDK


def is_agixt_admin(email: str = "", api_key: str = ""):
    if api_key == os.environ.get("AGIXT_API_KEY", ""):
        return True
    session = get_session()
    user = session.query(User).filter_by(email=email).first()
    if user.role == "admin":
        return True
    return False


def create_user(
    api_key: str,
    email: str,
    role: str = "user",
    agent_name: str = "AGiXT",
    settings: dict = {},
    commands: dict = {},
    training_urls: list = [],
    github_repos: list = [],
    ApiClient: AGiXTSDK = AGiXTSDK(),
):
    if not is_agixt_admin(email=email, api_key=api_key):
        return {"error": "Access Denied"}, 403
    session = get_session()
    user_exists = session.query(User).filter_by(email=email).first()
    if user_exists:
        session.close()
        return {"error": "User already exists"}, 400
    user = User(email=email.lower(), role=role.lower())
    session.add(user)
    session.commit()
    session.close()
    add_agent(
        agent_name=agent_name,
        provider_settings=settings,
        commands=commands,
        user=user,
    )
    if training_urls != []:
        for url in training_urls:
            ApiClient.learn_url(agent_name=agent_name, url=url)
    if github_repos != []:
        for repo in github_repos:
            ApiClient.learn_github_repo(agent_name=agent_name, github_repo=repo)
    return {"status": "Success"}, 200
