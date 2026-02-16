from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    lastfm_username = Column(String, unique=True, index=True, nullable=True)
    lastfm_session_key = Column(Text, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    display_name = Column(String)
    profile_image_url = Column(String, nullable=True)
    
    # Spotify fields
    spotify_id = Column(String, unique=True, index=True, nullable=True)
    spotify_access_token = Column(Text, nullable=True)
    spotify_refresh_token = Column(Text, nullable=True)
    spotify_token_expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    listening_history = relationship("ListeningHistory", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")


class ListeningHistory(Base):
    __tablename__ = "listening_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    track_id = Column(String, index=True)
    track_name = Column(String)
    artist_name = Column(String)
    album_name = Column(String)
    album_image_url = Column(String)
    played_at = Column(DateTime, index=True)
    duration_ms = Column(Integer)
    track_url = Column(String)
    track_mbid = Column(String, nullable=True)
    source = Column(String, default="lastfm")  # "lastfm" or "spotify"
    spotify_uri = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="listening_history")
    track_mappings = relationship("TrackPhotoMapping", back_populates="track")


class Memory(Base):
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    description = Column(Text, nullable=True)
    memory_date = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="memories")
    photos = relationship("Photo", back_populates="memory", cascade="all, delete-orphan")
    mappings = relationship("TrackPhotoMapping", back_populates="memory", cascade="all, delete-orphan")


class Photo(Base):
    __tablename__ = "photos"
    
    id = Column(Integer, primary_key=True, index=True)
    memory_id = Column(Integer, ForeignKey("memories.id"))
    google_photo_id = Column(String)
    base_url = Column(String)
    filename = Column(String)
    mime_type = Column(String)
    creation_time = Column(DateTime, index=True)
    width = Column(Integer)
    height = Column(Integer)
    photo_metadata = Column(JSON, nullable=True)
    local_path = Column(String, nullable=True)  # Path to locally stored photo file
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    memory = relationship("Memory", back_populates="photos")
    mappings = relationship("TrackPhotoMapping", back_populates="photo", cascade="all, delete-orphan")


class TrackPhotoMapping(Base):
    __tablename__ = "track_photo_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    memory_id = Column(Integer, ForeignKey("memories.id"))
    photo_id = Column(Integer, ForeignKey("photos.id"))
    track_id = Column(Integer, ForeignKey("listening_history.id"))
    is_auto_suggested = Column(Boolean, default=False)
    confidence_score = Column(Integer, nullable=True)  # For auto-suggestions
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    memory = relationship("Memory", back_populates="mappings")
    photo = relationship("Photo", back_populates="mappings")
    track = relationship("ListeningHistory", back_populates="track_mappings")
