from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from database import get_db
from models import User, TrackPhotoMapping, Photo, Memory
from schemas import (
    TrackPhotoMappingCreate,
    TrackPhotoMappingUpdate,
    TrackPhotoMappingResponse
)
from auth import get_current_user

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.post("", response_model=TrackPhotoMappingResponse)
async def create_mapping(
    mapping: TrackPhotoMappingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Create a track-photo mapping"""
    # Verify the memory belongs to the user
    result = await db.execute(
        select(Memory).where(Memory.id == mapping.memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Create mapping
    db_mapping = TrackPhotoMapping(**mapping.model_dump())
    db.add(db_mapping)
    await db.commit()
    await db.refresh(db_mapping)
    
    # Eagerly load relationships for serialization
    result = await db.execute(
        select(TrackPhotoMapping)
        .options(selectinload(TrackPhotoMapping.track), selectinload(TrackPhotoMapping.photo))
        .where(TrackPhotoMapping.id == db_mapping.id)
    )
    db_mapping = result.scalar_one()
    
    return TrackPhotoMappingResponse.model_validate(db_mapping)


@router.get("/{mapping_id}", response_model=TrackPhotoMappingResponse)
async def get_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get a specific mapping"""
    result = await db.execute(
        select(TrackPhotoMapping)
        .options(selectinload(TrackPhotoMapping.track), selectinload(TrackPhotoMapping.photo))
        .join(Memory)
        .where(
            TrackPhotoMapping.id == mapping_id,
            Memory.user_id == user.id
        )
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    return TrackPhotoMappingResponse.model_validate(mapping)


@router.put("/{mapping_id}", response_model=TrackPhotoMappingResponse)
async def update_mapping(
    mapping_id: int,
    mapping_update: TrackPhotoMappingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update a track-photo mapping"""
    result = await db.execute(
        select(TrackPhotoMapping)
        .join(Memory)
        .where(
            TrackPhotoMapping.id == mapping_id,
            Memory.user_id == user.id
        )
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    # Update fields
    update_data = mapping_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mapping, field, value)
    
    # If user manually edits, mark as not auto-suggested
    if 'track_id' in update_data:
        mapping.is_auto_suggested = False
    
    await db.commit()
    await db.refresh(mapping)
    
    # Re-fetch with eager loading
    result = await db.execute(
        select(TrackPhotoMapping)
        .options(selectinload(TrackPhotoMapping.track), selectinload(TrackPhotoMapping.photo))
        .where(TrackPhotoMapping.id == mapping.id)
    )
    mapping = result.scalar_one()
    
    return TrackPhotoMappingResponse.model_validate(mapping)


@router.delete("/{mapping_id}")
async def delete_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Delete a track-photo mapping"""
    result = await db.execute(
        select(TrackPhotoMapping)
        .join(Memory)
        .where(
            TrackPhotoMapping.id == mapping_id,
            Memory.user_id == user.id
        )
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    await db.delete(mapping)
    await db.commit()
    
    return {"message": "Mapping deleted successfully"}


@router.get("/memory/{memory_id}", response_model=List[TrackPhotoMappingResponse])
async def get_memory_mappings(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get all mappings for a specific memory"""
    # Verify memory belongs to user
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Get mappings with eager-loaded relationships
    result = await db.execute(
        select(TrackPhotoMapping)
        .options(selectinload(TrackPhotoMapping.track), selectinload(TrackPhotoMapping.photo))
        .where(TrackPhotoMapping.memory_id == memory_id)
    )
    mappings = result.scalars().all()
    
    return [TrackPhotoMappingResponse.model_validate(mapping) for mapping in mappings]
