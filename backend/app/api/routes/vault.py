from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.infrastructure.config.vault import SecureVaultService

router = APIRouter(prefix="/vault", tags=["vault"])

class CredentialCreate(BaseModel):
    identifier: str
    type: str
    payload: dict[str, Any]
    project_id: int | None = None
    description: str | None = None

class CredentialListItem(BaseModel):
    id: int | None
    identifier: str
    type: str
    project_id: int | None
    description: str | None

@router.get("/credentials", response_model=list[CredentialListItem], dependencies=[Depends(get_current_user)])
def list_credentials(project_id: int | None = Query(None)) -> list[dict[str, Any]]:
    """
    List secure credentials metadata filtered by project context.
    Decrypted passwords and private keys are never returned.
    """
    return SecureVaultService.list_credentials(project_id=project_id)

@router.post("/credentials", dependencies=[Depends(get_current_user)])
def add_credential(data: CredentialCreate) -> dict[str, Any]:
    """
    Add or update a secure credential. Encrypts payload at the backend.
    """
    try:
        credential = SecureVaultService.add_credential(
            identifier=data.identifier,
            type=data.type,
            payload=data.payload,
            project_id=data.project_id,
            description=data.description
        )
        return {"success": True, "identifier": credential.identifier}
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/credentials/{identifier}", dependencies=[Depends(get_current_user)])
def delete_credential(identifier: str, project_id: int | None = Query(None)) -> dict[str, Any]:
    """
    Delete a secure credential. Enforces project context permission.
    """
    try:
        success = SecureVaultService.delete_credential(identifier, project_id=project_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Credential '{identifier}' not found.")
        return {"success": True}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=str(e))
