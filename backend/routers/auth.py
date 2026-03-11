from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
import json
import sqlite3
import random
from pathlib import Path
from typing import Literal, Optional

from database import get_db
from models import User, ListeningHistory
from schemas import LastfmAuthResponse, LastfmCallbackRequest, UserResponse, SpotifyCallbackRequest, TestLoginRequest
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


# ─── Testing Mode ──────────────────────────────────────────────

MOOD_DB = Path(__file__).resolve().parents[1] / "services" / "mood_songs.db"
TEST_SONGS_PER_SESSION = 15

# 15 tracks verified present in mood_songs.db — spotify_id included to skip lookups
HARDCODED_TEST_TRACKS = [
    {"track_name": "Bohemian Rhapsody",           "artist_name": "Queen",              "genre": "classic rock",     "spotify_id": "7tFiyTwD0nx5a1eklYtX2J"},
    {"track_name": "Creep",                       "artist_name": "Radiohead",          "genre": "alternative",      "spotify_id": "6b2oQwSGFkzsMtQruIWm2p"},
    {"track_name": "Someone Like You",            "artist_name": "Adele",              "genre": "soul",             "spotify_id": "4kflIGfjdZJW4ot2ioixTB"},
    {"track_name": "Happy",                       "artist_name": "Pharrell Williams",  "genre": "pop",              "spotify_id": "60nZcImufyMA1MKQY3dcCH"},
    {"track_name": "'Till I Collapse",            "artist_name": "Eminem",             "genre": "rap",              "spotify_id": "4xkOaSrkexMciUUogZKVTS"},
    {"track_name": "Do I Wanna Know?",            "artist_name": "Arctic Monkeys",     "genre": "indie rock",       "spotify_id": "5FVd6KXrgO9B3JPmC8OPst"},
    {"track_name": "Stop Crying Your Heart Out",  "artist_name": "Oasis",              "genre": "britpop",          "spotify_id": "0JbVh3zDHYgVb1QxoNG0hu"},
    {"track_name": "Apocalypse Please",           "artist_name": "Muse",               "genre": "alternative rock", "spotify_id": "6z0QCh7CTU9bE5C7TAHK4R"},
    {"track_name": "Angel",                       "artist_name": "Massive Attack",     "genre": "trip-hop",         "spotify_id": "7uv632EkfwYhXoqf8rhYrg"},
    {"track_name": "Walking in My Shoes",         "artist_name": "Depeche Mode",       "genre": "electronic",       "spotify_id": "0VokHXtSNOpnlMWDMT9kPD"},
    {"track_name": "Violently Happy",             "artist_name": "Bjork",              "genre": "electronic",       "spotify_id": "1oyRhrmdRoJj0rUe7b22FS"},
    {"track_name": "There Is A Light That Never Go", "artist_name": "The Smiths",      "genre": "indie",            "spotify_id": "0WQiDwKJclirSYG9v5tayI"},
    {"track_name": "November Rain",               "artist_name": "Guns N' Roses",      "genre": "rock",             "spotify_id": "3YRCqOhFifThpSRFJ1VWFM"},
    {"track_name": "Threads",                     "artist_name": "Portishead",         "genre": "trip-hop",         "spotify_id": "6LV9M06RS0sAMihWxsdLYX"},
    {"track_name": "Hey You!!!",                  "artist_name": "The Cure",           "genre": "happy",            "spotify_id": "1WUSs195It8jj78gYMD9CT"},
]


def _resolve_hardcoded_songs(conn) -> list:
    """Return hardcoded tracks with rowids looked up from mood_songs.db."""
    results = []
    for entry in HARDCODED_TEST_TRACKS:
        cur = conn.execute(
            "SELECT rowid FROM mood_songs WHERE spotify_id = ? LIMIT 1",
            (entry["spotify_id"],),
        )
        row = cur.fetchone()
        results.append({**entry, "rowid": row[0] if row else None})
    return results


def _get_random_songs(conn, count: int) -> list:
    cur = conn.execute("SELECT COUNT(*) FROM mood_songs")
    total = cur.fetchone()[0]
    offsets = random.sample(range(total), min(count, total))
    results = []
    for offset in offsets:
        row = conn.execute(
            "SELECT rowid, spotify_id, track, artist, genre FROM mood_songs LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        if row:
            rowid, spotify_id, track, artist, genre = row
            results.append({"rowid": rowid, "track_name": track, "artist_name": artist,
                            "genre": genre, "spotify_id": spotify_id})
    return results


def _get_songs_by_rowids(conn, rowids: list) -> list:
    results = []
    for rowid in rowids:
        row = conn.execute(
            "SELECT rowid, spotify_id, track, artist, genre FROM mood_songs WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        if row:
            r, spotify_id, track, artist, genre = row
            results.append({"rowid": r, "track_name": track, "artist_name": artist,
                            "genre": genre, "spotify_id": spotify_id})
    return results


@router.get("/test/preview-songs")
async def test_preview_songs(mode: Literal["hardcoded", "random"] = "random"):
    """Return the song list for a test session without logging in (no side effects)."""
    conn = sqlite3.connect(str(MOOD_DB))
    songs = _resolve_hardcoded_songs(conn) if mode == "hardcoded" else _get_random_songs(conn, TEST_SONGS_PER_SESSION)
    conn.close()
    return songs


@router.post("/test/login")
async def test_login(
    db: AsyncSession = Depends(get_db),
    body: Optional[TestLoginRequest] = Body(default=None),
):
    """Create (or reuse) a temporary test user and seed listening history from mood_songs.db."""
    mode = body.mode if body else "random"
    rowids = body.rowids if body else None

    # Reuse existing test user to avoid clutter
    result = await db.execute(
        select(User).where(User.is_test_user == True).order_by(User.id.desc())
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(display_name="Tester", is_test_user=True)
        db.add(user)
        await db.flush()

    # Always reseed — the tester may have changed their song selection
    today = datetime.utcnow().date()
    conn = sqlite3.connect(str(MOOD_DB))
    if mode == "hardcoded":
        song_data = _resolve_hardcoded_songs(conn)
    elif rowids:
        song_data = _get_songs_by_rowids(conn, rowids)
    else:
        song_data = _get_random_songs(conn, TEST_SONGS_PER_SESSION)
    conn.close()

    # Delete any existing today rows, then insert fresh
    result_old = await db.execute(
        select(ListeningHistory).where(
            ListeningHistory.user_id == user.id,
            func.date(ListeningHistory.played_at) == today,
        )
    )
    for old_row in result_old.scalars().all():
        await db.delete(old_row)
    await db.flush()

    base_time = datetime.combine(today, datetime.min.time().replace(hour=9))
    for i, song in enumerate(song_data[:TEST_SONGS_PER_SESSION]):
        spotify_id = song["spotify_id"]
        lh = ListeningHistory(
            user_id=user.id,
            track_id=spotify_id or f"test_{i}",
            track_name=song["track_name"],
            artist_name=song["artist_name"],
            album_name=song["genre"] or "Unknown Album",
            album_image_url=None,
            played_at=base_time + timedelta(minutes=i * 15),
            duration_ms=210000,
            track_url="",
            source="test",
            spotify_uri=f"spotify:track:{spotify_id}" if spotify_id else None,
        )
        db.add(lh)

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": UserResponse.model_validate(user),
    }
