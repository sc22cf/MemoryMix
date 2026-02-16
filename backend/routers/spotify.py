from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from auth import get_current_user
from services.spotify_service import SpotifyService

router = APIRouter(prefix="/spotify", tags=["spotify"])


@router.get("/token")
async def get_playback_token(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a valid Spotify access token for the Web Playback SDK"""
    if not user.spotify_id:
        raise HTTPException(status_code=400, detail="Spotify account not connected")

    try:
        token_data = await SpotifyService.get_playback_token(db, user)
        return token_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get playback token: {str(e)}")


@router.get("/search")
async def search_track(
    track: str = Query(..., description="Track name"),
    artist: str = Query(..., description="Artist name"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search Spotify for a track and return its URI for playback"""
    if not user.spotify_id:
        raise HTTPException(status_code=400, detail="Spotify account not connected")

    try:
        result = await SpotifyService.search_track(db, user, track, artist)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Search failed: {str(e)}")
