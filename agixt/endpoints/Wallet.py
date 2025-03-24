from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from ApiClient import verify_api_key, get_api_client
from DB import AgentSetting, Agent as AgentModel, get_session
from MagicalAuth import get_user_id
app = APIRouter()

@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Wallet"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet information",
    description="Retrieves the private wallet information for an agent including private key and passphrase.",
)
def get_agent_wallet_info(agent_name: str, authorization: str = Depends(verify_api_key)) -> Dict[str, str]:
    session = get_session()
    try:
        user = get_api_client(authorization).user
        user_id = get_user_id(user)
        
        agent = session.query(AgentModel).filter(
            AgentModel.name == agent_name,
            AgentModel.user_id == user_id
        ).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        agent_settings = session.query(AgentSetting).filter(AgentSetting.agent_id == agent.id).all()
        
        wallet_info = {}
        for setting in agent_settings:
            if setting.name in ["SOLANA_WALLET_API_KEY", "SOLANA_WALLET_PASSPHRASE_API_KEY"]:
                wallet_info[setting.name] = setting.value
                
        if not wallet_info:
            raise HTTPException(status_code=404, detail="Wallet information not found")
            
        return wallet_info
    finally:
        session.close()