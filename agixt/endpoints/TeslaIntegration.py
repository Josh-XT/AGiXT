import os
import logging
import requests
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from Globals import getenv

# Create a router for Tesla integration
tesla_router = APIRouter(tags=["Tesla Integration"])

# Store keys in the models folder for persistence
MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)
TESLA_DIR = os.path.join(MODELS_DIR, "tesla")
PRIVATE_KEY_PATH = os.path.join(TESLA_DIR, "tesla_private_key.pem")
PUBLIC_KEY_PATH = os.path.join(TESLA_DIR, "tesla_public_key.pem")
REGISTRATION_FILE = os.path.join(TESLA_DIR, "registration_status.json")
TESLA_DOMAIN = (
    getenv("AGIXT_URI").replace("https://", "").replace("http://", "").rstrip("/")
)


def ensure_keys_exist():
    """Generate the EC key pair if it doesn't exist - called at startup time"""
    try:
        # Create tesla directory in models if it doesn't exist
        os.makedirs(TESLA_DIR, exist_ok=True)

        # Check if keys already exist
        if os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH):
            return

        # Generate new keys using OpenSSL
        logging.info("Generating new Tesla API key pair in models directory...")

        # Generate private key
        private_key_cmd = (
            f"openssl ecparam -name prime256v1 -genkey -noout -out {PRIVATE_KEY_PATH}"
        )
        private_key_result = os.system(private_key_cmd)

        if private_key_result != 0:
            logging.error("Failed to generate Tesla private key")
            raise Exception("Failed to generate Tesla private key")

        # Generate public key
        public_key_cmd = (
            f"openssl ec -in {PRIVATE_KEY_PATH} -pubout -out {PUBLIC_KEY_PATH}"
        )
        public_key_result = os.system(public_key_cmd)

        if public_key_result != 0:
            logging.error("Failed to generate Tesla public key")
            raise Exception("Failed to generate Tesla public key")

        # Set proper permissions
        os.chmod(PRIVATE_KEY_PATH, 0o600)  # Read/write for owner only
        os.chmod(PUBLIC_KEY_PATH, 0o644)  # Read for everyone, write for owner

    except Exception as e:
        logging.error(f"Error generating Tesla API keys: {str(e)}")
        raise


# Function to handle registration with Tesla
def register_with_tesla():
    """Register with Tesla Fleet API - should be called at startup time"""
    if not TESLA_DOMAIN:
        logging.warning("Tesla domain not set, skipping registration")
        return False
    try:
        # Check if already registered
        if os.path.exists(REGISTRATION_FILE):
            try:
                with open(REGISTRATION_FILE, "r") as f:
                    status = json.load(f)
                    if status.get("registered", False):
                        return True
            except Exception as e:
                logging.warning(f"Error reading Tesla registration status: {str(e)}")

        # Get API credentials
        client_id = getenv("TESLA_CLIENT_ID")
        client_secret = getenv("TESLA_CLIENT_SECRET")

        if not client_id or not client_secret:
            logging.warning("Tesla API credentials not set, skipping registration")
            return False

        # Get partner token
        audience = getenv(
            "TESLA_AUDIENCE", "https://fleet-api.prd.na.vn.cloud.tesla.com"
        )
        auth_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"

        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds",
            "audience": audience,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logging.info("Requesting Tesla partner token for registration...")
        response = requests.post(auth_url, data=payload, headers=headers)

        if response.status_code != 200:
            logging.error(
                f"Failed to get Tesla token: {response.status_code} - {response.text}"
            )
            return False

        token = response.json().get("access_token")

        # Attempt registration
        register_url = f"{audience}/api/1/partner_accounts"

        register_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        register_payload = {"domain": TESLA_DOMAIN}

        logging.info(f"Registering with Tesla Fleet API using domain: {TESLA_DOMAIN}")
        register_response = requests.post(
            register_url, headers=register_headers, json=register_payload
        )

        if register_response.status_code in [200, 201]:
            logging.info("Tesla Fleet API registration successful!")

            # Mark as registered
            import datetime

            status = {
                "registered": True,
                "date": datetime.datetime.now().isoformat(),
                "domain": TESLA_DOMAIN,
            }

            with open(REGISTRATION_FILE, "w") as f:
                json.dump(status, f)

            return True
        else:
            logging.error(
                f"Tesla Fleet API registration failed: {register_response.status_code} - {register_response.text}"
            )
            return False

    except Exception as e:
        logging.error(f"Error during Tesla registration: {str(e)}")
        return False


# Route to serve the public key at the required path
@tesla_router.get(
    "/.well-known/appspecific/com.tesla.3p.public-key.pem",
    response_class=PlainTextResponse,
)
async def serve_tesla_public_key():
    """Serve the Tesla public key at the required path"""
    try:
        # Ensure keys exist
        if not os.path.exists(PUBLIC_KEY_PATH):
            ensure_keys_exist()

        # Read and return the public key
        with open(PUBLIC_KEY_PATH, "r") as f:
            public_key = f.read()

        return PlainTextResponse(
            content=public_key,
            media_type="application/x-pem-file",
            headers={
                "Content-Disposition": "inline; filename=com.tesla.3p.public-key.pem",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        logging.error(f"Error serving Tesla public key: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving Tesla public key")


# Function to get the private key content (for signing commands)
def get_tesla_private_key():
    """Get the Tesla private key content"""
    try:
        if not os.path.exists(PRIVATE_KEY_PATH):
            ensure_keys_exist()

        with open(PRIVATE_KEY_PATH, "r") as f:
            return f.read()
    except Exception as e:
        logging.error(f"Error reading Tesla private key: {str(e)}")
        raise


def register_tesla_routes(app):
    """Register Tesla routes with the main FastAPI app"""
    tesla_client_id = getenv("TESLA_CLIENT_ID")
    tesla_client_secret = getenv("TESLA_CLIENT_SECRET")
    if tesla_client_id != "" and tesla_client_secret != "" and TESLA_DOMAIN != "":
        app.include_router(tesla_router)
        # Generate keys on startup
        ensure_keys_exist()
        import threading

        threading.Timer(10.0, register_with_tesla).start()
