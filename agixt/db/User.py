from DBConnection import User
import os


def create_user(api_key: str, email: str, role: str) -> bool:
    if api_key != os.environ.get("AGIXT_API_KEY"):
        return {"error": "Invalid API key"}, 401
    user = User(email=email, role=role)
    user.save()
    return {"status": "Success"}, 200
