# Memory Mix - Quick Start Guide

Welcome to Memory Mix! This guide will help you get started quickly.

## What You'll Need

Before you begin, make sure you have:

1. **Python 3.10 or higher** - [Download](https://www.python.org/downloads/)
2. **Node.js 18 or higher** - [Download](https://nodejs.org/)
3. **Spotify Developer Account** - [Sign up](https://developer.spotify.com/)
4. **Google Cloud Account** - [Sign up](https://console.cloud.google.com/)

## Quick Setup (5 minutes)

### 1. Run the Setup Script

```bash
./setup.sh
```

This will install all dependencies for both backend and frontend.

### 2. Get Spotify Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create App"
3. Fill in:
   - App name: "Memory Mix"
   - App description: "Musical memory app"
   - Redirect URI: `http://localhost:3000/callback`
4. Copy your **Client ID** and **Client Secret**
5. Add them to `backend/.env`:
   ```
   SPOTIFY_CLIENT_ID=your_client_id_here
   SPOTIFY_CLIENT_SECRET=your_client_secret_here
   ```

### 3. Get Google Client ID

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "Google Picker API"
4. Go to "Credentials" → "Create Credentials" → "OAuth client ID"
5. Application type: "Web application"
6. Add authorized JavaScript origins: `http://localhost:3000`
7. Copy your **Client ID**
8. Add it to `frontend/.env.local`:
   ```
   NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_client_id_here
   ```

### 4. Generate a Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output to `backend/.env`:
```
SECRET_KEY=your_generated_key_here
```

### 5. Start the Application

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 6. Open Memory Mix

Visit [http://localhost:3000](http://localhost:3000) in your browser!

## First Steps

1. **Connect Spotify**: Click the "Connect with Spotify" button
2. **Sync History**: From the dashboard, click "Sync Spotify History"
3. **Create Memory**: Click "Create New Memory"
   - Add a title and date
   - Select photos (Google Photos integration)
   - Save the memory
4. **View Suggestions**: Open the memory and click "Show Auto-Suggestions"
5. **Add Mappings**: Click "Add" on suggested tracks to map them to photos
6. **Export Playlist**: Enter a playlist name and click "Create Playlist"

## Troubleshooting

### Backend won't start
- Make sure Python virtual environment is activated
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify `.env` file exists and has all required values

### Frontend won't start
- Run `npm install` in the frontend directory
- Check that `.env.local` exists
- Make sure backend is running on port 8000

### Spotify OAuth errors
- Verify redirect URI matches exactly: `http://localhost:3000/callback`
- Check that Client ID and Secret are correct in `.env`
- Make sure you're using the correct Spotify account

### Google Photos not working
- Verify Client ID is correct in `.env.local`
- Check that authorized JavaScript origins includes `http://localhost:3000`
- You may need to implement full Google OAuth flow for photos access

## Architecture Overview

```
┌─────────────┐      ┌─────────────┐      ┌──────────────┐
│             │      │             │      │              │
│  Next.js    │─────▶│  FastAPI    │─────▶│  Spotify API │
│  Frontend   │◀─────│  Backend    │◀─────│              │
│             │      │             │      └──────────────┘
└─────────────┘      └─────────────┘
       │                    │
       │                    │
       ▼                    ▼
┌─────────────┐      ┌─────────────┐
│   Google    │      │   SQLite    │
│ Photos API  │      │  Database   │
└─────────────┘      └─────────────┘
```

## Key Features to Try

1. **Auto-Matching**: The app uses time-window matching to suggest which songs you were listening to when each photo was taken
2. **Confidence Scores**: Each suggestion shows how confident the match is based on time proximity
3. **Playlist Export**: Turn any memory into a Spotify playlist
4. **Playback Control**: Play tracks directly from the app

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Need Help?

- Check the main README.md for detailed documentation
- Review the backend/README.md for API details
- Review the frontend/README.md for frontend specifics
- Open an issue on GitHub if you encounter problems

## What's Next?

- Customize the time window for matching (default: 3 hours)
- Adjust confidence score thresholds
- Add more photos to your memories
- Share your memories with friends
- Export multiple playlists

Enjoy creating your musical memories! 🎵📸
