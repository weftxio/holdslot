from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(TokenPair):
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8)
