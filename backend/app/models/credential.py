from sqlmodel import Field, SQLModel

class SecureCredential(SQLModel, table=True):
    __tablename__ = "secure_credentials"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(default=None, index=True) # Project-level isolation (None = global)
    identifier: str = Field(unique=True, index=True)          # Unique identifier, e.g. "customer_a_ssh"
    type: str = Field(index=True)                             # e.g., "ssh", "env", "password", "api_key"
    description: str | None = None
    encrypted_payload: str                                    # AES encrypted JSON string
