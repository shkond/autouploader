"""Pydantic schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, Field


class TokenData(BaseModel):
    """OAuth token data."""

    access_token: str
    refresh_token: str | None = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str
    client_secret: str
    scopes: list[str] = Field(default_factory=list)
    expiry: datetime | None = None


class UserInfo(BaseModel):
    """Google user information."""

    id: str
    email: str
    name: str | None = None
    picture: str | None = None


class AuthStatus(BaseModel):
    """Authentication status response."""

    authenticated: bool
    user: UserInfo | None = None
    scopes: list[str] = Field(default_factory=list)


class AuthURL(BaseModel):
    """OAuth authorization URL response."""

    authorization_url: str
    state: str
