import os
import logging
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


def ensure_keys_exist():
    """Generate the EC key pair if it doesn't exist"""
    try:
        # Create tesla directory in models if it doesn't exist
        os.makedirs(TESLA_DIR, exist_ok=True)

        # Check if keys already exist
        if os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH):
            logging.info("Tesla API keys already exist")
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

        logging.info(f"Tesla API key pair generated successfully in {TESLA_DIR}")

    except Exception as e:
        logging.error(f"Error generating Tesla API keys: {str(e)}")
        raise


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


# Function to register the Tesla routes with the main FastAPI app
def register_tesla_routes(app):
    """Register Tesla routes with the main FastAPI app"""
    tesla_client_id = getenv("TESLA_CLIENT_ID")
    tesla_client_secret = getenv("TESLA_CLIENT_SECRET")
    tesla_domain = getenv("TESLA_DOMAIN")
    if tesla_client_id != "" and tesla_client_secret != "" and tesla_domain != "":
        app.include_router(tesla_router)
        # Generate keys on startup
        ensure_keys_exist()
