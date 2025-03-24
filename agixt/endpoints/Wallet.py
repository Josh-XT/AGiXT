from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from ApiClient import verify_api_key, get_api_client
from DB import AgentSetting, Agent, get_session
from Models import (
    WalletResponseModel,
)
from MagicalAuth import MagicalAuth
app = APIRouter()

@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Wallet"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet information",
    description="Retrieves the private wallet information for an agent including private key and passphrase.",
)
def get_agent_wallet_info(agent_name: str, authorization: str = Depends(verify_api_key)) -> WalletResponseModel:
    session = get_session()
    try:
        auth = MagicalAuth(authorization)
        user_id = auth.user_id
        
        # First get the agent ID
        agent = session.query(Agent).filter(
            Agent.name == agent_name,
            Agent.user_id == user_id
        ).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        # Query settings using agent_id
        agent_settings = session.query(AgentSetting).filter(
            AgentSetting.agent_id == agent.id
        ).all()
        
        wallet_info = {}
        for setting in agent_settings:
            if setting.name in ["SOLANA_WALLET_API_KEY", "SOLANA_WALLET_PASSPHRASE_API_KEY"]:
                wallet_info[setting.name] = setting.value
                
        if not wallet_info:
            raise HTTPException(status_code=404, detail="Wallet information not found")
            
        return wallet_info
    finally:
        session.close()