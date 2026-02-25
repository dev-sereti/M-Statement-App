import re
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    is_encrypted: bool
    file_size_kb: float
    message: str


class ProcessRequest(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=100)
    pin: Optional[str] = Field(None, max_length=20)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9_\-]+$", v):
            raise ValueError("Invalid session ID format")
        return v

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v and not re.match(r"^[\d\+\s\-]{4,20}$", v):
            raise ValueError("Invalid PIN format")
        return v


class ProcessResponse(BaseModel):
    success: bool
    download_token: Optional[str] = None
    transaction_count: int = 0
    parsing_warnings: List[str] = []
    statement_period: Optional[str] = None
    account_name: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str