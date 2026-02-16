from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db
from models import User, ListeningHistory
from schemas import ListeningHistoryResponse
from auth import get_current_user
from services.lastfm_service import LastfmService

router = APIRouter(prefix="/lastfm", tags=["lastfm"])


@router.post("/sync")
async def sync_listening_history(
    pages: int = Query(default=1, ge=1, le=50, description="Number of pages to sync (200 tracks per page)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sync user's recent listening history from Last.fm"""
    if not user.lastfm_username:
        raise HTTPException(status_code=400, detail="Last.fm username not set")

    tracks_added = await LastfmService.sync_listening_history(
        db, user, limit=200, pages=pages
    )

    return {
        "message": f"Successfully synced {tracks_added} new tracks",
        "tracks_added": tracks_added,
    }


@router.get("/history", response_model=List[ListeningHistoryResponse])
async def get_listening_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user's listening history from the database"""
    result = await db.execute(
        select(ListeningHistory)
        .where(ListeningHistory.user_id == user.id)
        .order_by(ListeningHistory.played_at.desc())
        .limit(limit)
        .offset(offset)
    )

    tracks = result.scalars().all()
    return [ListeningHistoryResponse.model_validate(track) for track in tracks]


@router.get("/history/count")
async def get_history_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get total count of listening history entries"""
    count = await LastfmService.get_history_count(db, user.id)
    return {"count": count}


@router.get("/history/all")
async def get_full_listening_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get paginated full listening history with total count"""
    offset = (page - 1) * per_page

    # Get total count 
    total = await LastfmService.get_history_count(db, user.id)

    # Get tracks
    tracks = await LastfmService.get_full_history(
        db, user.id, limit=per_page, offset=offset
    )

    return {
        "tracks": [ListeningHistoryResponse.model_validate(t) for t in tracks],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.post("/sync/full")
async def sync_full_history(
    max_pages: int = Query(default=10, ge=1, le=100, description="Max pages to fetch (200 tracks each)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sync a large amount of listening history from Last.fm"""
    if not user.lastfm_username:
        raise HTTPException(status_code=400, detail="Last.fm username not set")

    tracks_added = await LastfmService.sync_full_history(
        db, user, max_pages=max_pages
    )

    return {
        "message": f"Successfully synced {tracks_added} new tracks across {max_pages} pages",
        "tracks_added": tracks_added,
    }


@router.get("/history/by-date", response_model=List[ListeningHistoryResponse])
async def get_tracks_by_date(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all unique tracks listened to on a specific date.
    
    Used by the memory editor to show tracks available for
    associating with a photo taken on that date.
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    result = await db.execute(
        select(ListeningHistory)
        .where(
            ListeningHistory.user_id == user.id,
            ListeningHistory.played_at >= day_start,
            ListeningHistory.played_at < day_end,
        )
        .order_by(ListeningHistory.played_at.asc())
    )
    tracks = result.scalars().all()

    # Deduplicate by track_name + artist_name, keeping the first play
    seen: set[tuple[str, str]] = set()
    unique_tracks: list[ListeningHistory] = []
    for t in tracks:
        key = (t.track_name.lower(), t.artist_name.lower())
        if key not in seen:
            seen.add(key)
            unique_tracks.append(t)

    return [ListeningHistoryResponse.model_validate(t) for t in unique_tracks]
