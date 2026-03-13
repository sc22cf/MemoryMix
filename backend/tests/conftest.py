"""
Shared fixtures for MemoryMix backend tests.

Sets environment variables before any app modules are imported, then provides
an async test client, an in-memory database, and a pre-authenticated test user.
"""

import os

# ── Environment variables (MUST come before any app-level imports) ──────────
os.environ.update({
    "LASTFM_API_KEY": "test_lastfm_key",
    "LASTFM_SHARED_SECRET": "test_lastfm_secret",
    "SPOTIFY_CLIENT_ID": "test_spotify_id",
    "SPOTIFY_CLIENT_SECRET": "test_spotify_secret",
    "GOOGLE_CLIENT_ID": "test_google_id",
    "GOOGLE_CLIENT_SECRET": "test_google_secret",
    "GOOGLE_PICKER_API_KEY": "test_picker_key",
    "SECRET_KEY": "test_secret_key_for_unit_tests",
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
})

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock, patch

# Patch heavy ML singletons BEFORE importing app modules
_mock_matcher = MagicMock()
_mock_resolver = MagicMock()
_mock_joiner = MagicMock()

# ── Now safe to import app modules ──────────────────────────────────────────
from database import Base, get_db
from config import get_settings
from auth import create_access_token
from models import User, ListeningHistory, Memory, Photo, TrackPhotoMapping
from main import app

# ── Async engine for tests (in-memory SQLite) ──────────────────────────────
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    future=True,
)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


# Override the DB dependency globally
app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Provide a DB session for direct data setup in tests."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client talking to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """Create a test user and return (user, jwt_token)."""
    user = User(
        display_name="TestUser",
        lastfm_username="test_lastfm",
        is_test_user=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(data={"sub": str(user.id)})
    return user, token


@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Authorization headers for the test user."""
    _, token = test_user
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seeded_user(db: AsyncSession, test_user):
    """Test user with listening history seeded for today."""
    user, token = test_user
    today = datetime.utcnow().date()
    base_time = datetime.combine(today, datetime.min.time().replace(hour=9))

    tracks = [
        ("Bohemian Rhapsody", "Queen", "spotify:track:7tFiyTwD0nx5a1eklYtX2J"),
        ("Creep", "Radiohead", "spotify:track:6b2oQwSGFkzsMtQruIWm2p"),
        ("Happy", "Pharrell Williams", "spotify:track:60nZcImufyMA1MKQY3dcCH"),
    ]
    for i, (track, artist, uri) in enumerate(tracks):
        lh = ListeningHistory(
            user_id=user.id,
            track_id=uri.split(":")[-1],
            track_name=track,
            artist_name=artist,
            album_name="Test Album",
            played_at=base_time + timedelta(minutes=i * 15),
            duration_ms=210000,
            track_url="",
            source="test",
            spotify_uri=uri,
        )
        db.add(lh)

    await db.commit()
    return user, token
