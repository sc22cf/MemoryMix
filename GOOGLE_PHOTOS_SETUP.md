# Google Photos Setup Guide

## What I've Done

1. ✅ Added `NEXT_PUBLIC_GOOGLE_PICKER_API_KEY` to frontend `.env.local`
2. ✅ Added Google API scripts to the layout
3. ✅ Created `useGoogleAuth` hook for OAuth flow
4. ✅ Updated new memory page with:
   - Google Photos picker integration
   - File upload as an alternative
   - Proper OAuth sign-in flow

## What You Need to Do

### 1. Get Google OAuth Client ID

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure:
   - **Application type**: Web application
   - **Name**: Memory Mix
   - **Authorized JavaScript origins**: 
     - `http://localhost:3000`
     - `http://localhost:8000`
   - **Authorized redirect URIs**: 
     - `http://localhost:3000/callback`
6. Copy the **Client ID** (looks like: `12345-abcdef.apps.googleusercontent.com`)

### 2. Update Frontend Environment Variables

Replace `your_google_oauth_client_id_here` in `/frontend/.env.local`:

```bash
NEXT_PUBLIC_GOOGLE_CLIENT_ID=YOUR_ACTUAL_CLIENT_ID_HERE
```

### 3. Enable Required APIs

In Google Cloud Console, enable:
- ✅ **Google Picker API** (already done if you have the API key)
- ✅ **Google Photos Library API** (needed to access user photos)

Go to: **APIs & Services** → **Library** → Search for each API → Click **Enable**

### 4. Restart Your Frontend Dev Server

```bash
cd frontend
npm run dev
```

## How It Works Now

### Option 1: Google Photos Picker
1. User clicks "Sign in to Google Photos"
2. Google OAuth popup appears
3. User grants permission
4. User clicks "Pick from Google Photos" again
5. Google Photos picker opens
6. User selects photos
7. Photos are added to the memory

### Option 2: Direct File Upload
1. User clicks "Upload Files"
2. File picker opens
3. User selects image files from their computer
4. Photos are added to the memory

## Testing Without Google OAuth

If you want to test the app without completing Google OAuth setup, you can:
- Use the **"Upload Files"** button - this works immediately without any Google setup
- Users can upload photos directly from their computer

## Troubleshooting

### "Google API not loaded yet"
- Wait a moment after page load for scripts to initialize
- Check browser console for script loading errors

### "Please configure NEXT_PUBLIC_GOOGLE_CLIENT_ID"
- Make sure you've updated `.env.local` with your actual Client ID
- Restart the dev server after changing environment variables

### Google Photos picker doesn't open
- Verify the Picker API is enabled in Google Cloud Console
- Check that your API key is valid
- Make sure you're signed in to Google first

### CORS errors
- Verify `http://localhost:3000` is in "Authorized JavaScript origins"
- Verify `http://localhost:8000` is in "Authorized JavaScript origins"
