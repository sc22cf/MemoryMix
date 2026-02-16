from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# User Schemas
class UserBase(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None


class UserCreate(UserBase):
    lastfm_username: str


class UserResponse(UserBase):
    id: int
    lastfm_username: Optional[str] = None
    profile_image_url: Optional[str] = None
    spotify_id: Optional[str] = None
    spotify_connected: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def model_validate(cls, obj, **kwargs):
        # Add computed spotify_connected field
        result = super().model_validate(obj, **kwargs)
        if hasattr(obj, 'spotify_id') and obj.spotify_id:
            result.spotify_connected = True
        return result


# Listening History Schemas
class ListeningHistoryBase(BaseModel):
    track_id: str
    track_name: str
    artist_name: str
    album_name: str
    album_image_url: Optional[str] = None
    played_at: datetime
    duration_ms: int
    track_url: str
    track_mbid: Optional[str] = None
    source: str = "lastfm"
    spotify_uri: Optional[str] = None


class ListeningHistoryCreate(ListeningHistoryBase):
    pass


class ListeningHistoryResponse(ListeningHistoryBase):
    id: int
    user_id: int
    source: str = "lastfm"
    spotify_uri: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# Photo Schemas
class PhotoBase(BaseModel):
    google_photo_id: str
    base_url: str
    filename: str
    mime_type: str
    creation_time: datetime
    width: Optional[int] = None
    height: Optional[int] = None
    photo_metadata: Optional[dict] = None


class PhotoCreate(PhotoBase):
    memory_id: int


class PhotoResponse(PhotoBase):
    id: int
    memory_id: int
    local_url: Optional[str] = None  # Backend-served URL for locally stored photo
    created_at: datetime
    
    class Config:
        from_attributes = True


# Track Photo Mapping Schemas
class TrackPhotoMappingBase(BaseModel):
    photo_id: int
    track_id: int
    is_auto_suggested: bool = False
    confidence_score: Optional[int] = None


class TrackPhotoMappingCreate(TrackPhotoMappingBase):
    memory_id: int


class TrackPhotoMappingUpdate(BaseModel):
    track_id: Optional[int] = None
    is_auto_suggested: Optional[bool] = None


class TrackPhotoMappingResponse(TrackPhotoMappingBase):
    id: int
    memory_id: int
    created_at: datetime
    updated_at: datetime
    track: Optional[ListeningHistoryResponse] = None
    photo: Optional[PhotoResponse] = None
    
    class Config:
        from_attributes = True


# Memory Schemas
class MemoryBase(BaseModel):
    title: str
    description: Optional[str] = None
    memory_date: datetime


class MemoryCreate(MemoryBase):
    photos: List[PhotoBase] = []
    google_access_token: Optional[str] = None  # Token for downloading Google Photos at creation time


class MemoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    memory_date: Optional[datetime] = None


class MemoryResponse(MemoryBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    photos: List[PhotoResponse] = []
    mappings: List[TrackPhotoMappingResponse] = []
    
    class Config:
        from_attributes = True


# Last.fm Auth Schemas
class LastfmAuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse


class LastfmCallbackRequest(BaseModel):
    token: str


# Suggestion Schemas
class TrackSuggestion(BaseModel):
    track_id: int
    track_name: str
    artist_name: str
    album_name: str
    album_image_url: Optional[str] = None
    played_at: datetime
    confidence_score: int
    time_difference_minutes: int


class PhotoSuggestionResponse(BaseModel):
    photo_id: int
    photo: PhotoResponse
    suggested_tracks: List[TrackSuggestion]


# Spotify Auth Schemas
class SpotifyCallbackRequest(BaseModel):
    code: str


class SpotifyTokenResponse(BaseModel):
    access_token: str
    expires_in: int


class SpotifySearchResult(BaseModel):
    found: bool
    uri: Optional[str] = None
    name: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    image: Optional[str] = None



