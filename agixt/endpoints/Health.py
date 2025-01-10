from fastapi import APIRouter

app = APIRouter()


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "UP"}
