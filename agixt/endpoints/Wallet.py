from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from ApiClient import verify_api_key, get_api_client
from Agent import get_agent
from DB import AgentSetting, get_session
app = APIRouter()

@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Wallet"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet information",
    description="Retrieves the private wallet information for an agent including private key and passphrase.",
)
async def get_agent_wallet_info(agent_name: str, authorization: str = Depends(verify_api_key)) -> Dict[str, str]:
    session = get_session()
    try:
        api_client = get_api_client(authorization)
        agent = await get_agent(agent_name, ApiClient=api_client)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        agent_settings = session.query(AgentSetting).filter(
            AgentSetting.agent_id == agent.agent_id
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