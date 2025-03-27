# agixt/endpoints/Wallet.py
from fastapi import APIRouter, Depends, HTTPException, Query
from DB import get_session, AgentSetting as AgentSettingModel, Agent as AgentModel, User
from Models import WalletResponseModel, ResponseMessage
from MagicalAuth import MagicalAuth, get_user_id
import logging

app = APIRouter()


@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Agent"],
    response_model=WalletResponseModel,
    responses={
        401: {"model": ResponseMessage},
        403: {"model": ResponseMessage},
        404: {"model": ResponseMessage},
    },
)
async def get_agent_wallet(
    agent_name: str,
    api_key: str = Query(..., description="User's API Key for authentication"),
):
    """
    Retrieves the private key and passphrase for the agent's Solana wallet.
    Strictly enforces one wallet per agent. Assumes wallet exists if agent exists.
    Authenticates using the provided API key.
    """
    session = get_session()
    try:
        # Authenticate using the API key
        auth = MagicalAuth(token=api_key)
        user_id = auth.user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid API Key: {e}")

    try:
        # Find the agent first to ensure it belongs to the user
        agent = (
            session.query(AgentModel)
            .filter(AgentModel.name == agent_name, AgentModel.user_id == user_id)
            .first()
        )

        if not agent:
            raise HTTPException(
                status_code=404, detail=f"Agent '{agent_name}' not found for this user."
            )

        # Retrieve wallet settings using the agent_id
        private_key_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == agent.id,
                AgentSettingModel.name == "SOLANA_WALLET_API_KEY",
            )
            .first()
        )

        passphrase_setting = (
            session.query(AgentSettingModel)
            .filter(
                AgentSettingModel.agent_id == agent.id,
                AgentSettingModel.name == "SOLANA_WALLET_PASSPHRASE_API_KEY",
            )
            .first()
        )

        if not private_key_setting or not passphrase_setting:
            # This case should ideally not happen if the creation logic in Agent.py works correctly
            logging.error(
                f"Wallet details incomplete or missing for agent {agent_name} ({agent.id})."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Wallet details not found for agent '{agent_name}'. Wallet might not have been created yet.",
            )

        return WalletResponseModel(
            private_key=private_key_setting.value,
            passphrase=passphrase_setting.value,
        )
    except HTTPException as e:
        session.rollback()
        raise e  # Re-raise HTTPException
    except Exception as e:
        session.rollback()
        logging.error(f"Error retrieving wallet for agent {agent_name}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error retrieving wallet details."
        )
    finally:
        session.close()
