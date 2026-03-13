"""
Unit tests for all MemoryMix endpoints accessible in testing mode.

Covers:
  - Root / Health
  - Auth: test login, test preview-songs, /me, lastfm/login, spotify/login
  - Memories: CRUD + upload
  - Mappings: CRUD
  - Last.fm history: list, paginated, by-date
  - Photos: file serving
"""

import io
import os
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import TestSessionLocal
from models import User, ListeningHistory, Memory, Photo, TrackPhotoMapping


# ═══════════════════════════════════════════════════════════════════════════
# Root & Health
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Welcome to Memory Mix API"
    assert "version" in data


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


# ═══════════════════════════════════════════════════════════════════════════
# Auth — Test Mode
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_preview_songs_hardcoded(client):
    """GET /auth/test/preview-songs?mode=hardcoded returns songs from mood DB."""
    import sqlite3
    from pathlib import Path

    mood_db = Path(__file__).resolve().parents[1] / "services" / "mood_songs.db"
    if not mood_db.exists():
        pytest.skip("mood_songs.db not present — skipping preview-songs test")

    resp = await client.get("/auth/test/preview-songs?mode=hardcoded")
    assert resp.status_code == 200
    songs = resp.json()
    assert isinstance(songs, list)
    assert len(songs) == 15
    # Each song should have required fields
    for song in songs:
        assert "track_name" in song
        assert "artist_name" in song
        assert "spotify_id" in song


@pytest.mark.asyncio
async def test_preview_songs_random(client):
    """GET /auth/test/preview-songs?mode=random returns random songs."""
    from pathlib import Path

    mood_db = Path(__file__).resolve().parents[1] / "services" / "mood_songs.db"
    if not mood_db.exists():
        pytest.skip("mood_songs.db not present — skipping preview-songs test")

    resp = await client.get("/auth/test/preview-songs?mode=random")
    assert resp.status_code == 200
    songs = resp.json()
    assert isinstance(songs, list)
    assert len(songs) == 15


@pytest.mark.asyncio
async def test_login_creates_user_and_returns_token(client):
    """POST /auth/test/login creates a test user with seeded history."""
    from pathlib import Path

    mood_db = Path(__file__).resolve().parents[1] / "services" / "mood_songs.db"
    if not mood_db.exists():
        pytest.skip("mood_songs.db not present — skipping test login")

    resp = await client.post(
        "/auth/test/login",
        json={"mode": "hardcoded"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["is_test_user"] is True


@pytest.mark.asyncio
async def test_login_returns_listening_history(client):
    """After test login, the user should have listening history for today."""
    from pathlib import Path

    mood_db = Path(__file__).resolve().parents[1] / "services" / "mood_songs.db"
    if not mood_db.exists():
        pytest.skip("mood_songs.db not present")

    # Login
    login_resp = await client.post(
        "/auth/test/login",
        json={"mode": "hardcoded"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Check history
    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await client.get(
        f"/lastfm/history/by-date?date={today}",
        headers=headers,
    )
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Auth — Current User
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_me(client, auth_headers):
    resp = await client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "TestUser"
    assert data["lastfm_username"] == "test_lastfm"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client):
    resp = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Auth — Last.fm & Spotify login URLs
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lastfm_login_url(client):
    resp = await client.get("/auth/lastfm/login")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "last.fm" in data["auth_url"]


@pytest.mark.asyncio
async def test_spotify_login_url(client):
    resp = await client.get("/auth/spotify/login")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "spotify" in data["auth_url"].lower() or "accounts.spotify" in data["auth_url"]


# ═══════════════════════════════════════════════════════════════════════════
# Memories — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_memory_no_photo(client, auth_headers):
    """POST /memories with no photo."""
    with patch("routers.memories._auto_match_track", new_callable=AsyncMock):
        resp = await client.post(
            "/memories",
            json={
                "title": "Test Memory",
                "description": "A test memory",
                "memory_date": "2026-03-12T12:00:00",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Memory"
    assert data["description"] == "A test memory"
    assert data["photo"] is None


@pytest.mark.asyncio
async def test_create_memory_with_data_uri_photo(client, auth_headers):
    """POST /memories with a base64 data: URI photo."""
    # 1x1 red pixel PNG as base64
    tiny_png_b64 = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
        "2mP8/58BAwAI/AL+hc2rNAAAAABJRU5ErkJggg=="
    )

    with patch("routers.memories._auto_match_track", new_callable=AsyncMock), \
         patch("routers.memories._download_and_store_photo", new_callable=AsyncMock):
        resp = await client.post(
            "/memories",
            json={
                "title": "Photo Memory",
                "description": "Memory with a photo",
                "memory_date": "2026-03-12T15:00:00",
                "photo": {
                    "google_photo_id": "local_test",
                    "base_url": tiny_png_b64,
                    "filename": "test.png",
                    "mime_type": "image/png",
                    "creation_time": "2026-03-12T15:00:00",
                },
            },
            headers=auth_headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Photo Memory"
    assert data["photo"] is not None
    assert data["photo"]["filename"] == "test.png"


@pytest.mark.asyncio
async def test_create_memory_invalid_date(client, auth_headers):
    """memory_date as a number should be rejected."""
    resp = await client.post(
        "/memories",
        json={
            "title": "Bad Date",
            "memory_date": 12345,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_memories_empty(client, auth_headers):
    resp = await client.get("/memories", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_memories_returns_created(client, auth_headers):
    # Create a memory first
    with patch("routers.memories._auto_match_track", new_callable=AsyncMock):
        await client.post(
            "/memories",
            json={
                "title": "Listed Memory",
                "memory_date": "2026-03-12T10:00:00",
            },
            headers=auth_headers,
        )

    resp = await client.get("/memories", headers=auth_headers)
    assert resp.status_code == 200
    memories = resp.json()
    assert len(memories) == 1
    assert memories[0]["title"] == "Listed Memory"


@pytest.mark.asyncio
async def test_get_memory_by_id(client, auth_headers):
    with patch("routers.memories._auto_match_track", new_callable=AsyncMock):
        create_resp = await client.post(
            "/memories",
            json={
                "title": "Single Memory",
                "memory_date": "2026-03-12T10:00:00",
            },
            headers=auth_headers,
        )
    memory_id = create_resp.json()["id"]

    resp = await client.get(f"/memories/{memory_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Single Memory"


@pytest.mark.asyncio
async def test_get_memory_not_found(client, auth_headers):
    resp = await client.get("/memories/99999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_memory_wrong_user(client, auth_headers, db):
    """A user cannot access another user's memory."""
    other_user = User(display_name="OtherUser", is_test_user=True)
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    memory = Memory(
        user_id=other_user.id,
        title="Private Memory",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    resp = await client.get(f"/memories/{memory.id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_memory(client, auth_headers):
    with patch("routers.memories._auto_match_track", new_callable=AsyncMock):
        create_resp = await client.post(
            "/memories",
            json={
                "title": "Original Title",
                "memory_date": "2026-03-12T10:00:00",
            },
            headers=auth_headers,
        )
    memory_id = create_resp.json()["id"]

    resp = await client.put(
        f"/memories/{memory_id}",
        json={"title": "Updated Title", "description": "New description"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"
    assert resp.json()["description"] == "New description"


@pytest.mark.asyncio
async def test_update_memory_not_found(client, auth_headers):
    resp = await client.put(
        "/memories/99999",
        json={"title": "Nope"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_memory(client, auth_headers):
    with patch("routers.memories._auto_match_track", new_callable=AsyncMock):
        create_resp = await client.post(
            "/memories",
            json={
                "title": "To Delete",
                "memory_date": "2026-03-12T10:00:00",
            },
            headers=auth_headers,
        )
    memory_id = create_resp.json()["id"]

    resp = await client.delete(f"/memories/{memory_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["message"] == "Memory deleted successfully"

    # Confirm it's gone
    resp = await client.get(f"/memories/{memory_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_memory_not_found(client, auth_headers):
    resp = await client.delete("/memories/99999", headers=auth_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Memories — File Upload
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_upload_memory(client, auth_headers, tmp_path):
    """POST /memories/upload with a multipart file."""
    # Create a small test image
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    with patch("routers.memories._auto_match_track", new_callable=AsyncMock), \
         patch("routers.memories.UPLOAD_DIR", str(tmp_path)):
        resp = await client.post(
            "/memories/upload",
            data={
                "title": "Uploaded Memory",
                "description": "Photo from disk",
                "memory_date": "2026-03-12T14:00:00",
            },
            files={"photo": ("test_photo.png", fake_image, "image/png")},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Uploaded Memory"
    assert data["photo"] is not None
    assert data["photo"]["filename"] == "test_photo.png"
    assert data["photo"]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_upload_memory_unauthorized(client):
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    resp = await client.post(
        "/memories/upload",
        data={
            "title": "No Auth",
            "memory_date": "2026-03-12T14:00:00",
        },
        files={"photo": ("test.png", fake_image, "image/png")},
    )
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Memories — Suggestions
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_suggestions_no_photo(client, auth_headers, db, test_user):
    """Suggestions for a memory with no photo should return empty list."""
    user, _ = test_user
    memory = Memory(
        user_id=user.id,
        title="No Photo",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    resp = await client.get(
        f"/memories/{memory.id}/suggestions", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_suggestions_not_found(client, auth_headers):
    resp = await client.get("/memories/99999/suggestions", headers=auth_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Photos — File Serving
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_serve_photo_not_found(client):
    resp = await client.get("/photos/file/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_photo_no_local_path(client, db, test_user):
    """Photo record exists but has no local_path — should 404."""
    user, _ = test_user
    memory = Memory(
        user_id=user.id,
        title="M",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.flush()

    photo = Photo(
        memory_id=memory.id,
        google_photo_id="g123",
        base_url="https://example.com/photo",
        filename="photo.jpg",
        mime_type="image/jpeg",
        creation_time=datetime.utcnow(),
        local_path=None,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    resp = await client.get(f"/photos/file/{photo.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_photo_success(client, db, test_user, tmp_path):
    """Photo with a valid local_path returns the file."""
    user, _ = test_user

    # Write a fake image file
    fake_file = tmp_path / "test_photo.jpg"
    fake_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

    memory = Memory(
        user_id=user.id,
        title="M",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.flush()

    photo = Photo(
        memory_id=memory.id,
        google_photo_id="g456",
        base_url="",
        filename="test_photo.jpg",
        mime_type="image/jpeg",
        creation_time=datetime.utcnow(),
        local_path="test_photo.jpg",
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    with patch("routers.memories.UPLOAD_DIR", str(tmp_path)):
        resp = await client.get(f"/photos/file/{photo.id}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


# ═══════════════════════════════════════════════════════════════════════════
# Mappings — CRUD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_mapping(client, auth_headers, db, seeded_user):
    """POST /mappings creates a track-photo mapping."""
    user, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    # Create memory + photo
    memory = Memory(
        user_id=user.id,
        title="Mapping Test",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.flush()

    photo = Photo(
        memory_id=memory.id,
        google_photo_id="map_test",
        base_url="",
        filename="m.jpg",
        mime_type="image/jpeg",
        creation_time=datetime.utcnow(),
    )
    db.add(photo)
    await db.flush()

    # Get a track ID from listening history
    from sqlalchemy import select
    result = await db.execute(
        select(ListeningHistory).where(ListeningHistory.user_id == user.id)
    )
    track = result.scalars().first()
    await db.commit()

    resp = await client.post(
        "/mappings",
        json={
            "memory_id": memory.id,
            "photo_id": photo.id,
            "track_id": track.id,
            "is_auto_suggested": False,
            "confidence_score": 85,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["photo_id"] == photo.id
    assert data["track_id"] == track.id
    assert data["confidence_score"] == 85


@pytest.mark.asyncio
async def test_create_mapping_wrong_user(client, auth_headers, db):
    """Cannot create a mapping for another user's memory."""
    other = User(display_name="Other", is_test_user=True)
    db.add(other)
    await db.flush()

    memory = Memory(
        user_id=other.id,
        title="Not Mine",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    resp = await client.post(
        "/mappings",
        json={
            "memory_id": memory.id,
            "photo_id": 1,
            "track_id": 1,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_mapping(client, db, seeded_user):
    user, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    memory = Memory(
        user_id=user.id,
        title="Update Map",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.flush()

    photo = Photo(
        memory_id=memory.id,
        google_photo_id="up",
        base_url="",
        filename="u.jpg",
        mime_type="image/jpeg",
        creation_time=datetime.utcnow(),
    )
    db.add(photo)
    await db.flush()

    from sqlalchemy import select
    result = await db.execute(
        select(ListeningHistory).where(ListeningHistory.user_id == user.id)
    )
    tracks = result.scalars().all()

    mapping = TrackPhotoMapping(
        memory_id=memory.id,
        photo_id=photo.id,
        track_id=tracks[0].id,
        is_auto_suggested=True,
        confidence_score=70,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    # Update to a different track
    resp = await client.put(
        f"/mappings/{mapping.id}",
        json={"track_id": tracks[1].id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["track_id"] == tracks[1].id
    # Manual edit should clear auto-suggested
    assert data["is_auto_suggested"] is False


@pytest.mark.asyncio
async def test_update_mapping_not_found(client, auth_headers):
    resp = await client.put(
        "/mappings/99999",
        json={"track_id": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_mapping(client, db, seeded_user):
    user, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    memory = Memory(
        user_id=user.id,
        title="Del Map",
        memory_date=datetime.utcnow(),
    )
    db.add(memory)
    await db.flush()

    photo = Photo(
        memory_id=memory.id,
        google_photo_id="del",
        base_url="",
        filename="d.jpg",
        mime_type="image/jpeg",
        creation_time=datetime.utcnow(),
    )
    db.add(photo)
    await db.flush()

    from sqlalchemy import select
    result = await db.execute(
        select(ListeningHistory).where(ListeningHistory.user_id == user.id)
    )
    track = result.scalars().first()

    mapping = TrackPhotoMapping(
        memory_id=memory.id,
        photo_id=photo.id,
        track_id=track.id,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    resp = await client.delete(f"/mappings/{mapping.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["message"] == "Mapping deleted successfully"

    # Confirm it's gone
    resp = await client.delete(f"/mappings/{mapping.id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_mapping_not_found(client, auth_headers):
    resp = await client.delete("/mappings/99999", headers=auth_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Last.fm History
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_history_empty(client, auth_headers):
    resp = await client.get("/lastfm/history", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_history_with_tracks(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/lastfm/history", headers=headers)
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 3
    # Should be ordered by played_at desc
    assert tracks[0]["track_name"] == "Happy"


@pytest.mark.asyncio
async def test_get_history_pagination(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/lastfm/history?limit=2&offset=0", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = await client.get("/lastfm/history?limit=2&offset=2", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_full_history(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/lastfm/history/all?page=1&per_page=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert len(data["tracks"]) == 3


@pytest.mark.asyncio
async def test_get_full_history_page_2(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/lastfm/history/all?page=1&per_page=2", headers=headers)
    data = resp.json()
    assert data["total"] == 3
    assert data["total_pages"] == 2
    assert len(data["tracks"]) == 2

    resp = await client.get("/lastfm/history/all?page=2&per_page=2", headers=headers)
    data = resp.json()
    assert len(data["tracks"]) == 1


@pytest.mark.asyncio
async def test_get_history_by_date(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await client.get(
        f"/lastfm/history/by-date?date={today}", headers=headers
    )
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 3


@pytest.mark.asyncio
async def test_get_history_by_date_no_tracks(client, seeded_user):
    _, token = seeded_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        "/lastfm/history/by-date?date=2020-01-01", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_history_by_date_invalid_format(client, auth_headers):
    resp = await client.get(
        "/lastfm/history/by-date?date=not-a-date", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_history_unauthorized(client):
    resp = await client.get("/lastfm/history")
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Memories — Authorization checks
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_memory_unauthorized(client):
    resp = await client.post(
        "/memories",
        json={
            "title": "No Auth",
            "memory_date": "2026-03-12T10:00:00",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_memories_unauthorized(client):
    resp = await client.get("/memories")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_memory_unauthorized(client):
    resp = await client.put("/memories/1", json={"title": "X"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_memory_unauthorized(client):
    resp = await client.delete("/memories/1")
    assert resp.status_code == 401
