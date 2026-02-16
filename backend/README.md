# Memory Mix Backend

FastAPI backend for Memory Mix - combines Spotify listening history with photos.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```

4. Configure your environment variables:
   - Get Spotify API credentials from https://developer.spotify.com/dashboard
   - Get Google API credentials from https://console.cloud.google.com
   - Generate a secure SECRET_KEY

5. Run the server:
```bash
uvicorn main:app --reload
```

The API will be available at http://localhost:8000

## API Documentation

Interactive API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Key Features

- **Spotify OAuth**: Complete authentication flow
- **Listening History**: Sync and store Spotify listening history
- **Memories**: Create, read, update, delete memories with photos
- **Auto-Matching**: Time-window based track-to-photo matching algorithm
- **Mappings CRUD**: Full control over track-photo relationships
- **Playlist Export**: Create Spotify playlists from memories
- **Playback Control**: Play tracks using Spotify Web API

## Project Structure

```
backend/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration and settings
├── database.py          # Database setup and session management
├── models.py            # SQLAlchemy database models
├── schemas.py           # Pydantic schemas for request/response
├── auth.py              # Authentication utilities
├── routers/             # API route handlers
│   ├── auth.py          # Authentication endpoints
│   ├── spotify.py       # Spotify integration endpoints
│   ├── memories.py      # Memory CRUD endpoints
│   └── mappings.py      # Track-photo mapping endpoints
└── services/            # Business logic services
    ├── spotify_service.py   # Spotify API interactions
    └── matching_service.py  # Time-window matching algorithm
```
