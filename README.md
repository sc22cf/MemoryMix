# MemoryMix

MemoryMix is a web application that pairs your personal photos with the songs you were listening to on the same day — creating a mood-matched musical soundtrack for your memories.

Upload a photo, describe the moment, and MemoryMix analyses the mood of your description against your listening history using sentence embeddings and cosine similarity to find the song that best fits how that memory feels.

## API Full Documentation 
https://documenter.getpostman.com/view/53107994/2sBXiestu1

## Features

- **Mood-based song matching** — photo descriptions are embedded and ranked against a 61K-song dataset using sentence-transformer similarity
- **Listening history integration** — connects to Last.fm to pull your real play history (Presentation Mode)
- **Spotify playback** — plays the matched song in-browser via the Spotify Web Playback SDK (Presentation Mode)
- **Google Photos support** — pick photos directly from your Google Photos library (Presentation Mode)
- **Testing Mode** — fully functional demo mode that works without any API keys, using a curated set of well-known songs

## Modes

| Mode | Description |
|---|---|
| **Presentation Mode** | Full experience with real Spotify, Last.fm, and Google Photos integration. Requires API credentials configured for a specific account. |
| **Testing Mode** | Standalone demo with simulated listening history. No external API keys needed. Anyone can use this. |

---

## Running with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed
- A `backend/.env` file with your credentials (see below)

### 1. Configure environment variables

> **Testing Mode** works without any of the above keys set. You can leave them as placeholder strings if you only need the testing demo.

**Backend** — copy the example and fill in your values:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# Last.fm
LASTFM_API_KEY=your_lastfm_api_key
LASTFM_SHARED_SECRET=your_lastfm_shared_secret

# Spotify
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:3000/callback

# Google
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_PICKER_API_KEY=your_google_picker_api_key

# App
SECRET_KEY=a-long-random-secret-string
```

**Frontend** — copy the example and fill in your values:

```bash
cp frontend/.env.example frontend/.env.local
```

Edit `frontend/.env.local`:

```env
# Backend API URL (defaults to http://localhost:8000 if not set)
NEXT_PUBLIC_API_URL=http://localhost:8000

# Google API Credentials (required for Google Photos integration)
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id
NEXT_PUBLIC_GOOGLE_PICKER_API_KEY=your_google_picker_api_key
```


### 2. Build and start

```bash
docker compose up --build
```

First build will take a few minutes. Subsequent starts are fast:

```bash
docker compose up
```

### 3. Open the app

| Service | URL |
|---|---|
| Frontend | http://127.0.0.1:3000 |
| Backend API | http://localhost:8000 |
> **localhost** will not work on frontend due to CORS configurations and restrictions with Spotify API 

### 4. Testing the App

```bash
Refer to the TESTING_GUIDE.md file for instructions to use the application when testing. This will give you examples on mood descriptions recommended to get the best match between a song and a memory.
```

### 5. Stop

```bash
docker compose down
```

Your database and uploaded photos are stored in named Docker volumes (`db_data`, `uploads_data`) and will persist across restarts. To wipe all data:

```bash
docker compose down -v
```

---

## Running locally (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cp frontend/.env.example frontend/.env.local
# Edit frontend/.env.local with your values
cd frontend
npm install
npm run dev
```

---

## Project structure

```
MemoryMix/
├── backend/               # FastAPI application
│   ├── main.py            # App entry point
│   ├── models.py          # SQLAlchemy models
│   ├── schemas.py         # Pydantic schemas
│   ├── routers/           # Route handlers (auth, memories, mappings, …)
│   └── services/
│       └── mood_matching/  # Embedding pipeline + 61K-song SQLite dataset
├── frontend/              # Next.js 14 application
│   ├── app/               # App Router pages
│   ├── components/        # UI components
│   ├── contexts/          # Auth + Spotify player context
│   └── lib/               # API client, types, utilities
├── docker-compose.yml
├── TESTING_GUIDE.md       # Step-by-step tester walkthrough
└── POSTMAN_REQUESTS.md    # Ready-to-use HTTP request examples
```

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React 19, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, Pydantic v2 |
| Database | SQLite (via aiosqlite) |
| Mood matching | Sentence embeddings + cosine similarity over 61K songs |
| Auth | JWT (python-jose) |
| External APIs | Spotify Web API + Playback SDK, Last.fm API, Google Photos Picker |
