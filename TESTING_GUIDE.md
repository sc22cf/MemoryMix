# MemoryMix — Testing Guide

## Presentation Mode vs Testing Mode

MemoryMix has two modes of operation:

### Presentation Mode (Default)

Presentation mode is the full-featured version of the app. It integrates with three external APIs:

- **Spotify** — for playback of matched songs via the Spotify Web Playback SDK
- **Last.fm** — for pulling real listening history (what the user actually listened to on a given day)
- **Google Photos** — for selecting photos directly from the user's Google Photos library

These APIs are configured with OAuth credentials that are restricted to a single developer account. Only the app owner's email can authenticate through these services. **External testers cannot use Presentation Mode.**

### Testing Mode

Testing mode exists so that anyone can test the core functionality of MemoryMix — matching a photo's description to a song based on mood — without needing Spotify, Last.fm, or Google Photos credentials.

In Testing Mode:

- A temporary test user is created with **simulated listening history** seeded from the mood song database
- Photos are uploaded locally (file upload) instead of via Google Photos
- Song playback is **not available** (no Spotify SDK) — you can only see the matched song info
- The song pool comes from either **hardcoded classics** or a **random selection** from the 61K-song mood database

> **Hardcoded mode is recommended** because you will almost certainly recognise the songs (Queen, Radiohead, Adele, Oasis, etc.), making it much easier to judge whether the mood match is sensible.

---

## Step-by-Step Testing Flow

### 1. Open the Login Page & Enter Testing Mode

Navigate to the app's landing page and click the **"Testing Mode"** button. A setup panel will appear with two tabs:

- **Hardcoded (15 classics)** — a curated list of well-known songs
- **Random Selection** — 15 songs pulled at random from the mood database

#### Preview the song list (no login required)

**GET** — Hardcoded songs:

```
GET http://localhost:8000/auth/test/preview-songs?mode=hardcoded
```

**GET** — Random songs:

```
GET http://localhost:8000/auth/test/preview-songs?mode=random
```

Example response:

```json
[
  {
    "rowid": 42317,
    "track_name": "Bohemian Rhapsody",
    "artist_name": "Queen",
    "genre": "classic rock",
    "spotify_id": "7tFiyTwD0nx5a1eklYtX2J"
  },
  {
    "rowid": 8923,
    "track_name": "Creep",
    "artist_name": "Radiohead",
    "genre": "alternative",
    "spotify_id": "6b2oQwSGFkzsMtQruIWm2p"
  }
]
```

---

### 2. Start the Test Session (Login)

Click **"Start Testing Session"** in the UI, or send the following request directly.

**POST** — Login with hardcoded songs:

```
POST http://localhost:8000/auth/test/login
Content-Type: application/json

{
  "mode": "hardcoded"
}
```

**POST** — Login with specific songs (by rowid from the preview):

```
POST http://localhost:8000/auth/test/login
Content-Type: application/json

{
  "mode": "random",
  "rowids": [42317, 8923, 15204, 33012, 7741]
}
```

Example response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 10080,
  "user": {
    "id": 1,
    "display_name": "Tester",
    "is_test_user": true,
    "created_at": "2026-03-11T10:00:00"
  }
}
```

Save the `access_token` — you will need it as a `Bearer` token in the `Authorization` header for all subsequent requests.

---

### 3. Create a New Memory

After logging in, navigate to **New Memory** from the dashboard. Fill out:

| Field | Description |
|---|---|
| **Title** | A short name for the memory |
| **Description** | A vivid description of the photo / moment — this is what gets matched to a song |
| **Date** | The date of the memory. **This must match the date the test songs were "listened to"**, which defaults to **today's date**. If the dates don't match, no songs will be found. |
| **Photo** | Upload a photo from your device (file upload) |

**POST** — Create a memory:

```
POST http://localhost:8000/memories
Authorization: Bearer <your_access_token>
Content-Type: application/json

{
  "title": "Sunset at the Beach",
  "description": "Golden hour on a quiet beach, warm light reflecting off the water, waves gently rolling in. A peaceful, contemplative evening alone.",
  "memory_date": "2026-03-11T18:00:00",
  "photo": {
    "google_photo_id": "local-upload",
    "base_url": "data:image/jpeg;base64,/9j/4AAQ...",
    "filename": "beach-sunset.jpg",
    "mime_type": "image/jpeg",
    "creation_time": "2026-03-11T18:00:00",
    "width": 1920,
    "height": 1080
  }
}
```

> **Note:** When using the UI, the photo is converted to a base64 `data:` URI automatically. If testing via HTTP directly, you need to base64-encode the image file and embed it in `base_url`.

#### Examples of Good Photo Descriptions

The description is the most important field — it drives the mood matching. Be vivid and emotional. Here are some examples:

| Description | Expected mood |
|---|---|
| *"Golden hour on a quiet beach, warm light reflecting off the water, waves gently rolling in. A peaceful, contemplative evening alone."* | Calm, melancholic, reflective |
| *"A packed stadium at night, everyone singing along, confetti falling from the ceiling. Pure electric energy."* | Energetic, euphoric, happy |
| *"Walking through a foggy forest path at dawn, everything silent except for birdsong. Mysterious and still."* | Atmospheric, mysterious, calm |
| *"Friends laughing around a bonfire on a summer night, sparks floating into the sky. Warm and carefree."* | Happy, warm, nostalgic |
| *"Sitting alone at a rainy window with a cup of tea, watching the city lights blur through the glass."* | Melancholic, introspective, lonely |
| *"Sprinting through rain to catch the last train, heart pounding, out of breath but laughing."* | Energetic, anxious, exhilarated |
| *"A dark, crowded club with deep bass shaking the floor. Neon lights cutting through smoke."* | Intense, dark, electronic |
| *"An empty classroom after everyone has left, late afternoon sun streaming through the windows."* | Nostalgic, bittersweet, calm |

> **Tip:** The more descriptive and emotionally specific you are, the better the match. Short or generic descriptions like "a photo of my dog" will produce weaker results.

---

### 4. View Your Memories

**GET** — List all memories:

```
GET http://localhost:8000/memories
Authorization: Bearer <your_access_token>
```

**GET** — View a specific memory:

```
GET http://localhost:8000/memories/1
Authorization: Bearer <your_access_token>
```

The response will include the matched song under `mapping`, along with up to 3 `mood_candidates` showing the top matches and their similarity scores.

---

### 5. Edit the Matched Track

If you want to swap the auto-matched song for a different one, use the mapping `PUT` endpoint with the `mapping.id` from the memory response.

**PUT** — Update the associated track:

```
PUT http://localhost:8000/mappings/1
Authorization: Bearer <your_access_token>
Content-Type: application/json

{
  "track_id": 42
}
```

The `track_id` refers to a `listening_history` entry ID (visible in `mood_candidates` or from the memory detail). Setting `track_id` automatically marks the mapping as `is_auto_suggested: false` (i.e. manually chosen).

---

### 6. Delete a Memory

**DELETE** — Remove a memory and all its associated data:

```
DELETE http://localhost:8000/memories/1
Authorization: Bearer <your_access_token>
```

Example response:

```json
{
  "message": "Memory deleted successfully"
}
```

---

## Quick Reference

| Action | Method | Endpoint |
|---|---|---|
| Preview hardcoded songs | `GET` | `/auth/test/preview-songs?mode=hardcoded` |
| Preview random songs | `GET` | `/auth/test/preview-songs?mode=random` |
| Start test session | `POST` | `/auth/test/login` |
| Create a memory | `POST` | `/memories` |
| List all memories | `GET` | `/memories` |
| View a memory | `GET` | `/memories/{id}` |
| Update a memory | `PUT` | `/memories/{id}` |
| Swap matched track | `PUT` | `/mappings/{mapping_id}` |
| Delete a memory | `DELETE` | `/memories/{id}` |

All endpoints except the two `GET /auth/test/preview-songs` routes require `Authorization: Bearer <token>` in the header.
