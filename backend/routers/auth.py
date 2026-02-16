from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from database import get_db
from models import User
from schemas import LastfmAuthResponse, LastfmCallbackRequest, UserResponse, SpotifyCallbackRequest
from auth import get_lastfm_auth_url, create_access_token, get_current_user
from config import get_settings
from services.lastfm_service import LastfmService
from services.spotify_service import SpotifyService

router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()


@router.get("/lastfm/login")
async def lastfm_login():
    """Get Last.fm authorization URL"""
    auth_url = get_lastfm_auth_url()
    return {"auth_url": auth_url}


@router.post("/lastfm/callback", response_model=LastfmAuthResponse)
async def lastfm_callback(
    callback_data: LastfmCallbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """Handle Last.fm OAuth callback"""
    print(f"Received token: {callback_data.token[:20]}..." if len(callback_data.token) > 20 else callback_data.token)
    try:
        # Exchange token for session key
        session_info = await LastfmService.get_session_key(callback_data.token)
        print(f"Session info received for user: {session_info.get('name')}")
    except Exception as e:
        print(f"Last.fm auth error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to authenticate with Last.fm: {str(e)}"
        )
    
    lastfm_username = session_info["name"]
    session_key = session_info["key"]

    # Get user info from Last.fm
    try:
        user_info = await LastfmService.get_user_info(session_key)
    except Exception:
        user_info = {}
    
    # Check if user exists
    result = await db.execute(
        select(User).where(User.lastfm_username == lastfm_username)
    )
    user = result.scalar_one_or_none()
    
    # Create or update user
    if not user:
        user = User(
            lastfm_username=lastfm_username,
            display_name=user_info.get("realname") or lastfm_username,
            profile_image_url=None,
        )
        # Try to get profile image
        images = user_info.get("image", [])
        for img in images:
            if isinstance(img, dict) and img.get("size") == "large":
                user.profile_image_url = img.get("#text")
                break
        db.add(user)
    
    # Update session key
    user.lastfm_session_key = session_key
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(user)
    
    # Create JWT token for our app
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return LastfmAuthResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get current user information"""
    return UserResponse.model_validate(user)


# ─── Spotify ───────────────────────────────────────────────────

@router.get("/spotify/login")
async def spotify_login():
    """Get Spotify authorization URL (for connecting Spotify to an existing account)"""
    auth_url = SpotifyService.get_auth_url()
    return {"auth_url": auth_url}


@router.post("/spotify/connect")
async def connect_spotify(
    callback_data: SpotifyCallbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Connect Spotify to an existing (logged-in) user account"""
    try:
        token_data = await SpotifyService.exchange_code(callback_data.code)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to authenticate with Spotify: {str(e)}",
        )

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    try:
        profile = await SpotifyService.get_user_profile(access_token)
    except Exception:
        profile = {}

    spotify_id = profile.get("id", "")

    # If another user already has this spotify_id linked, unlink it
    if spotify_id:
        existing = await db.execute(
            select(User).where(User.spotify_id == spotify_id, User.id != user.id)
        )
        old_user = existing.scalar_one_or_none()
        if old_user:
            old_user.spotify_id = None
            old_user.spotify_access_token = None
            old_user.spotify_refresh_token = None
            old_user.spotify_token_expires_at = None

    user.spotify_id = spotify_id
    user.spotify_access_token = access_token
    user.spotify_refresh_token = refresh_token
    user.spotify_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    if not user.profile_image_url:
        images = profile.get("images", [])
        if images:
            user.profile_image_url = images[0].get("url", "")
    user.updated_at = datetime.utcnow()

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Spotify connection: {str(e)}",
        )

    return {"message": "Spotify connected successfully", "user": UserResponse.model_validate(user)}
