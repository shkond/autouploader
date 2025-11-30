"""Authentication routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.auth.oauth import get_oauth_service
from app.auth.schemas import AuthStatus, AuthURL, UserInfo

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login", response_model=AuthURL)
async def login() -> AuthURL:
    """Get OAuth authorization URL for Google login.

    Returns:
        AuthURL with authorization URL and state
    """
    oauth_service = get_oauth_service()
    auth_url, state = oauth_service.get_authorization_url()
    return AuthURL(authorization_url=auth_url, state=state)


@router.get("/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="OAuth state parameter"),
) -> dict:
    """Handle OAuth callback from Google.

    Args:
        code: Authorization code
        state: OAuth state parameter

    Returns:
        Success message with user info
    """
    oauth_service = get_oauth_service()
    try:
        oauth_service.exchange_code(code, state)
        user_info = oauth_service.get_user_info()
        return {
            "message": "Authentication successful",
            "user": user_info,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {e!s}",
        ) from e


@router.get("/status", response_model=AuthStatus)
async def auth_status() -> AuthStatus:
    """Check current authentication status.

    Returns:
        AuthStatus with authentication state and user info
    """
    oauth_service = get_oauth_service()

    if not oauth_service.is_authenticated():
        return AuthStatus(authenticated=False)

    user_info_data = oauth_service.get_user_info()
    user_info = None
    if user_info_data:
        user_info = UserInfo(
            id=user_info_data.get("id", ""),
            email=user_info_data.get("email", ""),
            name=user_info_data.get("name"),
            picture=user_info_data.get("picture"),
        )

    creds = oauth_service.get_credentials()
    scopes = list(creds.scopes) if creds and creds.scopes else []

    return AuthStatus(authenticated=True, user=user_info, scopes=scopes)


@router.post("/logout")
async def logout() -> dict:
    """Logout and clear stored credentials.

    Returns:
        Success message
    """
    oauth_service = get_oauth_service()
    oauth_service.logout()
    return {"message": "Logged out successfully"}
