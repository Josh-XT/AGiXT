from fastapi import APIRouter, Request, Header, Depends, HTTPException
from Models import Detail, Login, UserInfo, Register
from MagicalAuth import MagicalAuth, verify_api_key, is_agixt_admin
from DB import get_session, User, UserPreferences
from Agent import add_agent
from ApiClient import get_api_client
from Models import WebhookUser, WebhookModel
from Globals import getenv
import pyotp
import stripe
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.post("/v1/user", tags=["User"], summary="Register a new user")
def register(register: Register):
    mfa_token = MagicalAuth().register(new_user=register)
    totp = pyotp.TOTP(mfa_token)
    otp_uri = totp.provisioning_uri(name=register.email, issuer_name=getenv("APP_NAME"))
    return {"otp_uri": otp_uri}


@app.get(
    "/v1/user/exists",
    tags=["User"],
    response_model=bool,
    summary="Check if user exists",
)
def get_user(email: str) -> bool:
    try:
        return MagicalAuth().user_exists(email=email)
    except:
        return False


@app.get(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    summary="Get user details",
)
def log_in(
    request: Request,
    authorization: str = Header(None),
):
    token = str(authorization).replace("Bearer ", "").replace("bearer ", "")
    auth = MagicalAuth(token=token)
    user_data = auth.login(ip_address=request.client.host)
    user_preferences = auth.get_user_preferences()
    return {
        "email": user_data.email,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        **user_preferences,
    }


@app.post(
    "/v1/login",
    tags=["User"],
    response_model=Detail,
    summary="Login with email and OTP token",
)
async def send_magic_link(request: Request, login: Login):
    auth = MagicalAuth()
    data = await request.json()
    referrer = None
    if "referrer" in data:
        referrer = data["referrer"]
    magic_link = auth.send_magic_link(
        ip_address=request.client.host, login=login, referrer=referrer
    )
    return Detail(detail=magic_link)


@app.put(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Update user details",
)
async def update_user(request: Request, authorization: str = Header(None)):
    data = await request.json()
    user = MagicalAuth(token=authorization).update_user(
        ip_address=request.client.host, **data
    )
    return Detail(detail=user)


# Delete user
@app.delete(
    "/v1/user",
    tags=["User"],
    dependencies=[Depends(verify_api_key)],
    response_model=Detail,
    summary="Delete user",
)
def delete_user(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    MagicalAuth(token=authorization).delete_user()
    return Detail(detail="User deleted successfully.")


# Webhook user creations from other applications
@app.post("/api/user", tags=["User"])
async def createuser(
    account: WebhookUser,
    authorization: str = Header(None),
):
    email = account.email.lower()
    if not is_agixt_admin(email=email, api_key=authorization):
        raise HTTPException(status_code=403, detail="Unauthorized")
    ApiClient = get_api_client(authorization=authorization)
    session = get_session()
    agent_name = account.agent_name
    settings = account.settings
    commands = account.commands
    training_urls = account.training_urls
    github_repos = account.github_repos
    zip_file_content = account.zip_file_content
    user_exists = session.query(User).filter_by(email=email).first()
    if user_exists:
        session.close()
        return {"status": "User already exists"}, 200
    user = User(
        email=email,
        admin=False,
        first_name="",
        last_name="",
    )
    session.add(user)
    session.commit()
    session.close()
    if agent_name != "" and agent_name is not None:
        add_agent(
            agent_name=agent_name,
            provider_settings=settings,
            commands=commands,
            user=email,
        )
    if training_urls != []:
        for url in training_urls:
            ApiClient.learn_url(agent_name=agent_name, url=url)
    if github_repos != []:
        for repo in github_repos:
            ApiClient.learn_github_repo(agent_name=agent_name, github_repo=repo)
    if zip_file_content != "":
        ApiClient.learn_file(
            agent_name=agent_name,
            file_name="training_data.zip",
            file_content=zip_file_content,
        )
    return {"status": "Success"}, 200


if getenv("STRIPE_WEBHOOK_SECRET") != "":

    @app.post(
        "/v1/webhook",
        summary="Webhook endpoint for events.",
        response_model=WebhookModel,
        tags=["Webhook"],
    )
    async def webhook(request: Request):
        event = None
        data = None
        try:
            event = stripe.Webhook.construct_event(
                payload=(await request.body()).decode("utf-8"),
                sig_header=request.headers.get("stripe-signature"),
                secret=getenv("STRIPE_WEBHOOK_SECRET"),
            )
            data = event["data"]["object"]
        except stripe.error.SignatureVerificationError as e:
            logging.debug(f"Webhook signature verification failed: {str(e)}.")
            raise HTTPException(
                status_code=400, detail="Webhook signature verification failed."
            )
        logging.debug(f"Stripe Webhook Event of type {event['type']} received")
        if event and event["type"] == "checkout.session.completed":
            session = get_session()
            logging.debug("Checkout session completed.")
            email = data["customer_details"]["email"]
            user = session.query(User).filter_by(email=email).first()
            stripe_id = data["customer"]
            name = data["customer_details"]["name"]
            status = data["payment_status"]
            if not user:
                logging.debug("User not found.")
                return {"success": "false"}
            user_preferences = (
                session.query(UserPreferences)
                .filter_by(user_id=user.id, pref_key="subscription")
                .first()
            )
            if not user_preferences:
                user_preferences = UserPreferences(
                    user_id=user.id, pref_key="subscription", pref_value=stripe_id
                )
                session.add(user_preferences)
                session.commit()
            name = name.split(" ")
            user.is_active = True
            user.first_name = name[0]
            user.last_name = name[1]
            session.commit()
            session.close()
            return {"success": "true"}
        elif event and event["type"] == "customer.subscription.updated":
            logging.debug("Customer Subscription Update session completed.")
        else:
            logging.debug("Unhandled Stripe event type {}".format(event["type"]))
        return {"success": "true"}


@app.post(
    "/v1/oauth2/{provider}",
    tags=["User"],
    response_model=Detail,
    summary="Login using OAuth2 provider",
)
async def oauth_login(request: Request, provider: str):
    data = await request.json()
    auth = MagicalAuth()
    magic_link = auth.sso(
        provider=provider.lower(),
        code=data["code"],
        ip_address=request.client.host,
        referrer=data["referrer"] if "referrer" in data else getenv("MAGIC_LINK_URL"),
    )
    return {"detail": magic_link, "email": auth.email, "token": auth.token}
