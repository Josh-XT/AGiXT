from DBConnection import User, get_session
from db.Agent import add_agent
import os


def create_user(
    api_key: str,
    email: str,
    role: str = "user",
    agent_name: str = "AGiXT",
    settings: dict = {},
    commands: dict = {},
) -> bool:
    if api_key != os.environ.get("AGIXT_API_KEY"):
        return {"error": "Invalid API key"}, 401
    session = get_session()
    user_exists = session.query(User).filter_by(email=email).first()
    if user_exists:
        session.close()
        return {"error": "User already exists"}, 400
    user = User(email=email.lower(), role=role.lower())
    session.add(user)
    session.commit()
    session.close()
    if settings != {}:
        add_agent(
            agent_name=agent_name,
            provider_settings=settings,
            commands=commands,
            user=user,
        )
    return {"status": "Success"}, 200
