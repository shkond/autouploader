"""Authentication routes."""

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.oauth import OAuthService
from app.auth.schemas import AuthStatus, UserInfo
from app.auth.simple_auth import get_session_manager
from app.core.dependencies import get_oauth_service_dep, get_session_data

router = APIRouter(prefix="/auth", tags=["authentication"])

# Templates setup
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: str = Query(None),
    session_data: dict | None = Depends(get_session_data),
) -> HTMLResponse:
    """Display login page or redirect if already authenticated.

    Args:
        request: FastAPI request
        error: Optional error message to display
        session_data: Session data (injected via DI)

    Returns:
        Login page HTML or redirect to dashboard
    """
    # If already authenticated, redirect to dashboard
    if session_data:
        return RedirectResponse(url="/auth/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """Process login form submission.

    Args:
        username: Form username
        password: Form password

    Returns:
        Redirect to dashboard on success, login page on failure
    """
    session_manager = get_session_manager()

    if not session_manager.verify_credentials(username, password):
        return RedirectResponse(
            url="/auth/login?error=ユーザー名またはパスワードが正しくありません",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Create session and set cookie
    token = session_manager.create_session_token(username)
    response = RedirectResponse(url="/auth/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    session_data: dict | None = Depends(get_session_data),
    oauth_service: OAuthService = Depends(get_oauth_service_dep),
) -> HTMLResponse:
    """Display dashboard page.

    Args:
        request: FastAPI request
        session_data: Session data (injected via DI)
        oauth_service: OAuth service (injected via DI)

    Returns:
        Dashboard page HTML or redirect to login
    """
    if not session_data:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    # Get user_id from session
    user_id = session_data.get("user_id") or session_data.get("username")

    # Check Google auth status
    google_authenticated = await oauth_service.is_authenticated(user_id)
    google_user = None

    if google_authenticated:
        google_user = await oauth_service.get_user_info(user_id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "session": session_data,
            "google_authenticated": google_authenticated,
            "google_user": google_user,
        },
    )


@router.get("/google")
async def google_login(
    session_data: dict | None = Depends(get_session_data),
    oauth_service: OAuthService = Depends(get_oauth_service_dep),
) -> RedirectResponse:
    """Redirect to Google OAuth authorization.

    Args:
        session_data: Session data (injected via DI)
        oauth_service: OAuth service (injected via DI)

    Returns:
        Redirect to Google OAuth URL
    """
    # Require app authentication first
    if not session_data:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    auth_url, _ = oauth_service.get_authorization_url()
    return RedirectResponse(url=auth_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="OAuth state parameter"),
    session_data: dict | None = Depends(get_session_data),
    oauth_service: OAuthService = Depends(get_oauth_service_dep),
) -> RedirectResponse:
    """Handle OAuth callback from Google.

    Args:
        code: Authorization code
        state: OAuth state parameter
        session_data: Session data (injected via DI)
        oauth_service: OAuth service (injected via DI)

    Returns:
        Redirect to dashboard on success
    """
    if not session_data:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    user_id = session_data.get("user_id") or session_data.get("username")

    try:
        await oauth_service.exchange_code(code, user_id, state)
        return RedirectResponse(url="/auth/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {e!s}",
        ) from e


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    session_data: dict | None = Depends(get_session_data),
    oauth_service: OAuthService = Depends(get_oauth_service_dep),
) -> AuthStatus:
    """Check current authentication status.

    Args:
        session_data: Session data (injected via DI)
        oauth_service: OAuth service (injected via DI)

    Returns:
        AuthStatus with authentication state and user info
    """
    if not session_data:
        return AuthStatus(authenticated=False)

    user_id = session_data.get("user_id") or session_data.get("username")

    if not await oauth_service.is_authenticated(user_id):
        return AuthStatus(authenticated=False)

    user_info_data = await oauth_service.get_user_info(user_id)
    user_info = None
    if user_info_data:
        user_info = UserInfo(
            id=user_info_data.get("id", ""),
            email=user_info_data.get("email", ""),
            name=user_info_data.get("name"),
            picture=user_info_data.get("picture"),
        )

    creds = await oauth_service.get_credentials(user_id)
    scopes = list(creds.scopes) if creds and creds.scopes else []

    return AuthStatus(authenticated=True, user=user_info, scopes=scopes)


@router.get("/logout")
async def logout(
    session_data: dict | None = Depends(get_session_data),
    oauth_service: OAuthService = Depends(get_oauth_service_dep),
) -> RedirectResponse:
    """Logout and clear stored credentials.

    Args:
        session_data: Session data (injected via DI)
        oauth_service: OAuth service (injected via DI)

    Returns:
        Redirect to login page
    """
    if session_data:
        user_id = session_data.get("user_id") or session_data.get("username")
        await oauth_service.logout(user_id)

    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session")
    return response

