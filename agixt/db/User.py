from DBConnection import User, get_session
import os


def create_user(api_key: str, email: str, role: str = "user") -> bool:
    if api_key != os.environ.get("AGIXT_API_KEY"):
        return {"error": "Invalid API key"}, 401
    session = get_session()
    user = User(email=email.lower(), role=role.lower())
    session.add(user)
    session.commit()
    session.close()
    return {"status": "Success"}, 200
