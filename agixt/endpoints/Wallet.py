from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import verify_api_key, get_api_client, is_admin
from Models import ResponseMessage
from Models import WalletResponseModel
from Agent import Agent
from Extensions import Extensions

app = APIRouter()

@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Wallet"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet information",
    response_model=WalletResponseModel,
    description="Retrieves the private key and passphrase for an agent's Solana wallet. Requires admin access.",
)
async def get_wallet_private_info(
    agent_name: str, 
    user=Depends(verify_api_key),
    authorization: str = Header(None)
) -> dict:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    
    private_key = agent.AGENT_CONFIG["settings"].get("SOLANA_WALLET_API_KEY", "")
    passphrase = agent.AGENT_CONFIG["settings"].get("SOLANA_WALLET_PASSPHRASE_API_KEY", "")
    
    if not private_key or not passphrase:
        raise HTTPException(status_code=404, detail="Wallet information not found")
        
    return WalletResponseModel(
        private_key=private_key,
        passphrase=passphrase
    )