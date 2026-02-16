from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Base directory for locally stored photos
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "photos")

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

            # Auto-match the best track for this photo
            suggestions = await MatchingService.suggest_tracks_for_photo(
                db=db,
                photo=photo,
                user_id=user.id,
                time_window_hours=3,
                max_suggestions=1,
            )
            if suggestions:
                best = suggestions[0]
                mapping = TrackPhotoMapping(
                    memory_id=db_memory.id,
                    photo_id=photo.id,
                    track_id=best["track_id"],
                    is_auto_suggested=True,
                    confidence_score=best["confidence_score"],
                )
                db.add(mapping)
                await db.flush()

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
