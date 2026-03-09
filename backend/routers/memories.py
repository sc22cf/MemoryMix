from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
import httpx
import os
import base64
import uuid
import mimetypes
import logging

from database import get_db
from models import User, Memory, Photo, TrackPhotoMapping, ListeningHistory
from schemas import (
    MemoryCreate, MemoryUpdate, MemoryResponse, PhotoResponse,
    PhotoSuggestionResponse, TrackSuggestion
)
from auth import get_current_user
from services.matching_service import MatchingService
from services.mood_matching.matcher import MoodMatcher
from services.mood_matching.spotify_resolver import SpotifyResolver
from services.mood_matching.join import MemoryJoiner
from config import get_settings

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Base directory for locally stored photos
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "photos")

# Singletons
_mood_matcher = MoodMatcher()
_resolver = SpotifyResolver()
_joiner = MemoryJoiner()

router = APIRouter(prefix="/memories", tags=["memories"])


def _photo_local_url(photo: Photo) -> str | None:
    """Return the backend-served URL for a locally stored photo, or None."""
    if photo.local_path:
        return f"/photos/file/{photo.id}"
    return None


def _memory_response(memory: Memory) -> MemoryResponse:
    """Build MemoryResponse with local_url populated on each photo."""
    resp = MemoryResponse.model_validate(memory)
    resp.photos = [
        PhotoResponse(
            **{
                **PhotoResponse.model_validate(p).model_dump(exclude={"local_url"}),
                "local_url": _photo_local_url(p),
            }
        )
        for p in memory.photos
    ]
    return resp


async def _download_and_store_photo(
    photo: Photo,
    user_id: int,
    memory_id: int,
    google_access_token: str | None,
) -> None:
    """Download photo bytes and save to disk. Updates photo.local_path in place."""
    user_dir = os.path.join(UPLOAD_DIR, str(user_id), str(memory_id))
    os.makedirs(user_dir, exist_ok=True)

    # Determine file extension
    ext = mimetypes.guess_extension(photo.mime_type) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    safe_name = f"{photo.id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(user_dir, safe_name)

    if photo.base_url and photo.base_url.startswith("data:"):
        # ── Handle data: URI (local file upload) ───────────────────────
        try:
            header, b64data = photo.base_url.split(",", 1)
            file_bytes = base64.b64decode(b64data)
        except Exception as e:
            logger.warning("Failed to decode data URI for photo %s: %s", photo.id, e)
            return
    elif photo.base_url and google_access_token:
        # ── Fetch from Google Photos ───────────────────────────────────
        fetch_url = f"{photo.base_url}=w{photo.width or 2048}-h{photo.height or 2048}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    fetch_url,
                    headers={"Authorization": f"Bearer {google_access_token}"},
                )
                resp.raise_for_status()
                file_bytes = resp.content
        except Exception as e:
            logger.warning("Failed to download photo %s from Google: %s", photo.id, e)
            return
    else:
        return

    # Write to disk
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Store relative path from UPLOAD_DIR
    photo.local_path = os.path.relpath(file_path, UPLOAD_DIR)


@router.post("", response_model=List[MemoryResponse])
async def create_memory(
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Create memories from photos.
    
    Each photo becomes its own individual memory with one auto-matched track.
    If no photos are provided a single memory is created with no photo.
    Returns a list of the created memories.
    """
    print("\n" + "="*80)
    print("🎬 CREATE MEMORY ENDPOINT CALLED")
    print(f"User ID: {user.id}")
    print(f"Title: {memory.title}")
    print(f"Description: {memory.description}")
    print(f"Memory Date: {memory.memory_date}")
    print(f"Number of photos: {len(memory.photos) if memory.photos else 0}")
    print("="*80 + "\n")
    
    logger.info(f"🎬 CREATE MEMORY: User {user.id}, Title: '{memory.title}', Date: {memory.memory_date}")
    
    created_memories: list[Memory] = []

    photos_to_create = memory.photos if memory.photos else [None]  # type: ignore[list-item]

    for idx, photo_data in enumerate(photos_to_create):
        # Title: use base title; if multiple photos append a number
        title = memory.title
        if len(photos_to_create) > 1 and photo_data is not None:
            title = f"{memory.title} #{idx + 1}"

        db_memory = Memory(
            user_id=user.id,
            title=title,
            description=memory.description,
            memory_date=memory.memory_date,
        )
        db.add(db_memory)
        await db.flush()

        if photo_data is not None:
            photo = Photo(
                memory_id=db_memory.id,
                **photo_data.model_dump(),
            )
            db.add(photo)
            await db.flush()

            # Download / store photo to disk
            await _download_and_store_photo(
                photo=photo,
                user_id=user.id,
                memory_id=db_memory.id,
                google_access_token=memory.google_access_token,
            )

            # ── Auto-match: resolve → join → rank pipeline ──────────
            matched_track_id = None
            match_strategy = "none"
            match_score = None

            memory_date_only = memory.memory_date.date() if hasattr(memory.memory_date, 'date') else memory.memory_date
            date_str = str(memory_date_only)
            description = memory.description or memory.title

            # ── Step 0: Fetch candidate tracks from that day ──
            tracks_query = await db.execute(
                select(ListeningHistory)
                .where(
                    ListeningHistory.user_id == user.id,
                    func.date(ListeningHistory.played_at) == memory_date_only,
                )
            )
            candidate_tracks = tracks_query.scalars().all()

            if not candidate_tracks:
                print(
                    f"📭 No listening history for user {user.id} on {memory_date_only}\n"
                    f"   💡 Tip: Sync your Last.fm history for this date"
                )
            else:
                print(f"🔍 Found {len(candidate_tracks)} tracks on {memory_date_only}")

                # ── Step 1: Resolve missing Spotify IDs ──
                try:
                    resolve_stats = await _resolver.resolve_and_backfill(
                        db, user, date_str
                    )
                    print(f"🔗 Spotify resolution: {resolve_stats}")
                except Exception as e:
                    print(f"⚠️ Spotify resolution error (continuing): {e}")

                # Re-query to pick up back-filled spotify_uri values
                tracks_query = await db.execute(
                    select(ListeningHistory)
                    .where(
                        ListeningHistory.user_id == user.id,
                        func.date(ListeningHistory.played_at) == memory_date_only,
                    )
                )
                candidate_tracks = tracks_query.scalars().all()

                # ── Step 2: Join to mood dataset ──
                track_tuples = [
                    (t.spotify_uri, t.track_name, t.artist_name, t.id)
                    for t in candidate_tracks
                    if t.track_name and t.artist_name
                ]

                if track_tuples:
                    joined_tracks, join_stats = _joiner.join_day(track_tuples)
                    print(f"📊 Join: {join_stats}")

                    # Log each track's join result
                    status_icons = {
                        "spotify_id": "🆔",
                        "soft_match": "🔤",
                        "unmatched": "❌",
                    }
                    for jt in joined_tracks:
                        icon = status_icons.get(jt.join_method, "?")
                        mood_label = ""
                        if jt.mood:
                            tags = ", ".join(jt.mood.seed_tags[:3]) if jt.mood.seed_tags else ""
                            mood_label = f" → mood: {tags}"
                        print(
                            f"  {icon} {jt.track_name} - {jt.artist_name} "
                            f"[{jt.join_method}, conf={jt.confidence:.2f}]{mood_label}"
                        )

                    # ── Step 3: Rank matched tracks by embedding similarity ──
                    matched_ids = [
                        jt.mood.spotify_id
                        for jt in joined_tracks
                        if jt.mood
                    ]
                    # Build a map: mood spotify_id → JoinedTrack(s)
                    mood_id_to_jt = {}
                    for jt in joined_tracks:
                        if jt.mood:
                            mood_id_to_jt[jt.mood.spotify_id] = jt

                    if matched_ids and description and description.strip():
                        try:
                            mood_result = _mood_matcher.match(
                                description, matched_ids, top_n=1
                            )
                            if mood_result and mood_result.ranked:
                                best = mood_result.ranked[0]
                                jt = mood_id_to_jt.get(best.spotify_id)
                                if jt:
                                    matched_track_id = jt.listening_history_id
                                    match_strategy = f"mood+{jt.join_method}"
                                    match_score = best.similarity
                                    print(
                                        f"🎵 Best match: '{best.track}' by {best.artist} "
                                        f"(sim={match_score:.4f}, join={jt.join_method})\n"
                                        f"   📝 Description: \"{description}\"\n"
                                        f"   💡 Why: {best.explanation}"
                                    )
                        except Exception as e:
                            import traceback
                            print(f"⚠️ Embedding ranking failed: {e}")
                            traceback.print_exc()

                    # If embedding ranking found nothing, pick any joined track
                    if not matched_track_id:
                        for jt in joined_tracks:
                            if jt.mood:
                                matched_track_id = jt.listening_history_id
                                match_strategy = f"join+{jt.join_method}"
                                match_score = jt.confidence
                                print(
                                    f"🎵 Fallback join match: '{jt.track_name}' by "
                                    f"{jt.artist_name} [{jt.join_method}]"
                                )
                                break

                # ── Step 4: Time-based fallback ──
                if not matched_track_id:
                    print("🕐 Falling back to time-based matching...")
                    suggestions = await MatchingService.suggest_tracks_for_photo(
                        db=db,
                        photo=photo,
                        user_id=user.id,
                        time_window_hours=3,
                        max_suggestions=1,
                    )
                    if suggestions:
                        best = suggestions[0]
                        matched_track_id = best["track_id"]
                        match_strategy = "time"
                        match_score = best["confidence_score"] / 100.0
                        print(
                            f"⏰ Time match: '{best.get('track_name', '?')}' by "
                            f"{best.get('artist_name', '?')} (score={match_score:.4f})"
                        )

            # Create mapping if we found a match
            if matched_track_id:
                mapping = TrackPhotoMapping(
                    memory_id=db_memory.id,
                    photo_id=photo.id,
                    track_id=matched_track_id,
                    is_auto_suggested=True,
                    confidence_score=int((match_score or 0) * 100),  # store as 0-100
                )
                db.add(mapping)
                await db.flush()
                print(
                    f"✅ Created mapping: memory={db_memory.id}, strategy={match_strategy}"
                )
            else:
                print(
                    f"❌ No track match found for memory '{title}'\n"
                    f"   💡 Reason: No tracks from that day found in mood dataset, "
                    f"and time-based matching returned no results"
                )

        created_memories.append(db_memory)

    await db.commit()

    # Re-fetch all with eager loading
    result = await db.execute(
        select(Memory)
        .where(Memory.id.in_([m.id for m in created_memories]))
        .options(
            selectinload(Memory.photos),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.track),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.photo),
        )
        .order_by(Memory.id)
    )
    return [_memory_response(m) for m in result.scalars().all()]


@router.get("", response_model=List[MemoryResponse])
async def get_memories(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get all memories for the current user"""
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user.id)
        .options(
            selectinload(Memory.photos),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.track),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.photo),
        )
        .order_by(Memory.memory_date.desc())
        .offset(skip)
        .limit(limit)
    )
    memories = result.scalars().all()
    return [_memory_response(memory) for memory in memories]


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get a specific memory"""
    result = await db.execute(
        select(Memory)
        .where(Memory.id == memory_id, Memory.user_id == user.id)
        .options(
            selectinload(Memory.photos),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.track),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.photo),
        )
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return _memory_response(memory)


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    memory_update: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update a memory"""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Update fields
    update_data = memory_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(memory, field, value)
    
    await db.commit()
    # Re-fetch with eager loading
    result = await db.execute(
        select(Memory)
        .where(Memory.id == memory_id)
        .options(
            selectinload(Memory.photos),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.track),
            selectinload(Memory.mappings).selectinload(TrackPhotoMapping.photo),
        )
    )
    memory = result.scalar_one()
    
    return _memory_response(memory)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Delete a memory"""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    await db.delete(memory)
    await db.commit()
    
    return {"message": "Memory deleted successfully"}


# ── Photo file serving (separate prefix) ──────────────────────────────
photos_router = APIRouter(tags=["photos"])


@photos_router.get("/photos/file/{photo_id}")
async def serve_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Serve a locally stored photo file. No auth required — photos are
    accessed via opaque numeric ID and are not enumerable."""
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id)
    )
    photo = result.scalar_one_or_none()

    if not photo or not photo.local_path:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = os.path.join(UPLOAD_DIR, photo.local_path)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Photo file missing from disk")

    return FileResponse(
        file_path,
        media_type=photo.mime_type or "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{memory_id}/suggestions", response_model=List[PhotoSuggestionResponse])
async def get_track_suggestions(
    memory_id: int,
    time_window_hours: int = 3,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get auto-suggested track mappings for all photos in a memory"""
    # Get memory with photos
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Get photos
    result = await db.execute(
        select(Photo).where(Photo.memory_id == memory_id)
    )
    photos = result.scalars().all()
    
    if not photos:
        return []
    
    # Get suggestions for all photos
    suggestions_by_photo = await MatchingService.auto_suggest_mappings_for_memory(
        db=db,
        photos=photos,
        user_id=user.id,
        time_window_hours=time_window_hours
    )
    
    # Format response
    response = []
    for photo in photos:
        suggestions = suggestions_by_photo.get(photo.id, [])
        response.append(
            PhotoSuggestionResponse(
                photo_id=photo.id,
                photo=photo,
                suggested_tracks=[TrackSuggestion(**s) for s in suggestions]
            )
        )
    
    return response
