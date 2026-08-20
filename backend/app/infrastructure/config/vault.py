import json
import logging
from typing import Any

from sqlmodel import Session, or_, select

from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.credential import SecureCredential
from app.utils.crypto import decrypt_payload, encrypt_payload

logger = logging.getLogger(__name__)


class SecureVaultService:
    @staticmethod
    def _merge_payloads(old_payload: dict[str, Any], new_payload: dict[str, Any]) -> dict[str, Any]:
        """Merge a partial-update payload into the existing one.

        - value is None -> delete the field
        - value is an empty string -> keep the existing field untouched
        - otherwise -> overwrite (or add) the field
        """
        merged = dict(old_payload)
        for key, value in new_payload.items():
            if value is None:
                merged.pop(key, None)
            elif isinstance(value, str) and value == "":
                continue
            else:
                merged[key] = value
        return merged

    @staticmethod
    def add_credential(
        identifier: str,
        type: str,
        payload: dict[str, Any],
        project_id: int | None = None,
        description: str | None = None,
    ) -> SecureCredential:
        """
        Encrypt and save a new secure credential in the database.

        When the credential already exists, the payload is merged with the
        existing one (partial update): non-empty values overwrite, None values
        delete the field, missing keys are preserved.
        """
        if not db_resource_manager.sync_engine:
            raise RuntimeError("Database engine not initialized")

        with Session(db_resource_manager.sync_engine) as session:
            # Check if identifier already exists
            statement = select(SecureCredential).where(SecureCredential.identifier == identifier)
            config = session.exec(statement).first()

            if config:
                existing = json.loads(decrypt_payload(config.encrypted_payload))
                merged = SecureVaultService._merge_payloads(existing, payload)
                config.type = type
                config.project_id = project_id
                config.description = description
                config.encrypted_payload = encrypt_payload(json.dumps(merged))
                logger.info(f"[SecureVault] Updated existing credential: {identifier}")
            else:
                config = SecureCredential(
                    identifier=identifier,
                    type=type,
                    project_id=project_id,
                    description=description,
                    encrypted_payload=encrypt_payload(json.dumps(payload)),
                )
                session.add(config)
                logger.info(f"[SecureVault] Added new credential: {identifier}")

            session.commit()
            session.refresh(config)
            return config

    @staticmethod
    def get_credential_payload(identifier: str, project_id: int | None = None) -> dict[str, Any]:
        """
        Retrieve and decrypt a credential payload.
        Enforces project-level isolation: a credential is only accessible if it matches
        the given project_id or is a global credential (project_id is None).
        """
        if not db_resource_manager.sync_engine:
            raise RuntimeError("Database engine not initialized")

        with Session(db_resource_manager.sync_engine) as session:
            statement = select(SecureCredential).where(SecureCredential.identifier == identifier)
            config = session.exec(statement).first()

            if not config:
                raise KeyError(f"Credential not found: {identifier}")

            # Enforce project-level isolation
            # A project can access its own credentials or global credentials (project_id is None)
            if config.project_id is not None and config.project_id != project_id:
                logger.warning(
                    f"[SecureVault] Access Denied: Project {project_id} attempted to access "
                    f"credential {identifier} owned by Project {config.project_id}"
                )
                raise PermissionError(
                    f"Access Denied: Credential '{identifier}' does not belong to the current project context."
                )

            decrypted = decrypt_payload(config.encrypted_payload)
            return json.loads(decrypted)

    @staticmethod
    def list_credential_fields(identifier: str, project_id: int | None = None) -> list[str]:
        """
        Return the field names (keys) of a credential payload without the values.
        Enforces the same project-level isolation as get_credential_payload.
        """
        payload = SecureVaultService.get_credential_payload(identifier, project_id=project_id)
        return list(payload.keys())

    @staticmethod
    def delete_credential(identifier: str, project_id: int | None = None) -> bool:
        """
        Delete a credential. Enforces project-level isolation.
        """
        if not db_resource_manager.sync_engine:
            raise RuntimeError("Database engine not initialized")

        with Session(db_resource_manager.sync_engine) as session:
            statement = select(SecureCredential).where(SecureCredential.identifier == identifier)
            config = session.exec(statement).first()

            if not config:
                return False

            if config.project_id is not None and config.project_id != project_id:
                raise PermissionError(
                    f"Access Denied: Cannot delete credential '{identifier}' from another project context."
                )

            session.delete(config)
            session.commit()
            logger.info(f"[SecureVault] Deleted credential: {identifier}")
            return True

    @staticmethod
    def list_credentials(project_id: int | None = None) -> list[dict[str, Any]]:
        """
        List all credentials. Enforces project-level isolation.
        Returns only metadata (id, identifier, type, description, project_id).
        NEVER returns the encrypted or decrypted payloads.
        """
        if not db_resource_manager.sync_engine:
            return []

        with Session(db_resource_manager.sync_engine) as session:
            # Filter by project: show credentials matching project_id OR global credentials (None)
            if project_id is not None:
                statement = select(SecureCredential).where(
                    or_(
                        SecureCredential.project_id == project_id,
                        SecureCredential.project_id.is_(None),
                    )
                )
            else:
                statement = select(SecureCredential)

            results = session.exec(statement).all()
            return [
                {
                    "id": c.id,
                    "identifier": c.identifier,
                    "type": c.type,
                    "description": c.description,
                    "project_id": c.project_id,
                }
                for c in results
            ]
