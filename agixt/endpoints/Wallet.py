from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from ApiClient import verify_api_key
from Agent import get_agent
from DB import get_session, AgentSettingModel

app = APIRouter()

@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Wallet"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet information",
    description="Retrieves the private wallet information for an agent including private key and passphrase.",
)
async def get_agent_wallet_info(agent_name: str) -> Dict[str, str]:
    session = get_session()
    try:
        agent = get_agent(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        agent_settings = session.query(AgentSettingModel).filter(
            AgentSettingModel.agent_id == agent.get_agent_id()
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