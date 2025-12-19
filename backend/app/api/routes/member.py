from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.external.imagicbox import imagicbox_client

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(req: LoginRequest):
    result = imagicbox_client.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("message", "Login failed"))
    return result

@router.get("/status")
async def status():
    return imagicbox_client.get_status()

@router.post("/logout")
async def logout():
    imagicbox_client.logout()
    return {"message": "Logged out"}
