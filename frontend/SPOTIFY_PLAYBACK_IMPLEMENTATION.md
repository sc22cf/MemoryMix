# Spotify Web Playback SDK Implementation

This document explains how the Spotify Web Playback SDK is correctly implemented in this Next.js application.

## Architecture Overview

The implementation follows these key principles:

1. **Single Global Player Instance** - One player is created and managed at the application level
2. **Provider Pattern** - Player state and controls are shared via React Context
3. **Proper Lifecycle Management** - Player is initialized once and persists across route changes
4. **Race Condition Prevention** - Strict initialization sequence ensures device readiness

## File Structure

```
frontend/
├── contexts/
│   └── SpotifyPlayerContext.tsx    # Global player instance and state management
├── components/
│   ├── Providers.tsx                # Wraps app with SpotifyPlayerProvider
│   └── SpotifyPlayer.tsx            # UI component that consumes player context
└── app/
    └── layout.tsx                   # Root layout that includes Providers
```

## Implementation Details

### 1. SpotifyPlayerContext (Global Player Manager)

**File:** `contexts/SpotifyPlayerContext.tsx`

This context provider:
- Loads the Spotify SDK script once
- Creates a single `Spotify.Player` instance
- Follows the correct initialization sequence:
  1. Instantiate player
  2. Add event listeners
  3. Call `player.connect()`
  4. Wait for `ready` event
  5. Store `device_id` from ready event
  6. Transfer playback to device
- Exposes player state and control methods via context
- Handles cleanup on unmount (disconnect, remove listeners)

**Key State:**
```typescript
interface SpotifyPlayerContextType {
  deviceId: string | null;           // Device ID from ready event
  playerState: SpotifyPlayerState;   // Current track, play state, position
  isReady: boolean;                  // Player ready and connected
  error: string | null;              // Error messages
  playTrack: (uri: string) => Promise<void>;
  togglePlay: () => Promise<void>;
  nextTrack: () => Promise<void>;
  previousTrack: () => Promise<void>;
  setVolume: (volume: number) => Promise<void>;
  seek: (positionMs: number) => Promise<void>;
}
```

**Initialization Flow:**
```typescript
// 1. Create player
const player = new window.Spotify.Player({
  name: 'MemoryMix Web Player',
  getOAuthToken: async (cb) => {
    const token = await getToken();
    cb(token);
  },
  volume: 0.5,
});

// 2. Add listeners BEFORE connecting
player.addListener('ready', async ({ device_id }) => {
  setDeviceId(device_id);
  setIsReady(true);
  
  // 3. Transfer playback AFTER ready
  await transferPlayback(device_id);
});

// 4. Connect to Spotify
const connected = await player.connect();
```

**Race Condition Prevention:**
- Uses `initializingRef` to prevent duplicate initialization
- Only transfers playback after `ready` event fires
- `playTrack()` checks `isReady` and `deviceId` before attempting playback

### 2. Providers Component

**File:** `components/Providers.tsx`

Wraps the application with all context providers in the correct order:

```tsx
<QueryClientProvider client={queryClient}>
  <AuthProvider>
    <SpotifyPlayerProvider>
      {children}
    </SpotifyPlayerProvider>
  </AuthProvider>
</QueryClientProvider>
```

This ensures the player instance is created once at the top level and persists across all route changes.

### 3. SpotifyPlayer UI Component

**File:** `components/SpotifyPlayer.tsx`

A lightweight UI component that:
- Consumes the global player context via `useSpotifyPlayer()`
- Displays current track info, playback controls, and progress
- Calls `playTrack()` when `spotifyUri` prop changes
- Does NOT create its own player instance
- Works across all pages without recreating the device

**Usage:**
```tsx
import SpotifyPlayer from '@/components/SpotifyPlayer';

function MyPage() {
  const [trackUri, setTrackUri] = useState<string>();
  
  return (
    <SpotifyPlayer
      spotifyUri={trackUri}
      playId={Date.now()}  // Bump to replay same URI
      onReady={() => console.log('Player ready')}
    />
  );
}
```

## Benefits of This Implementation

✅ **Single Device** - Only one Spotify device is created for the entire session
✅ **No Recreation** - Player instance persists across route changes
✅ **Proper Sequencing** - Follows Spotify's recommended initialization flow
✅ **Race Condition Free** - Prevents premature playback transfer attempts
✅ **Clean Separation** - Provider handles logic, component handles UI
✅ **Type Safe** - Full TypeScript support with proper typing
✅ **Production Ready** - Includes error handling and cleanup logic

## Usage in Pages

Any page can use the player in two ways:

### Option 1: Use the UI Component
```tsx
import SpotifyPlayer from '@/components/SpotifyPlayer';

export default function MyPage() {
  return (
    <div>
      <SpotifyPlayer spotifyUri="spotify:track:..." />
    </div>
  );
}
```

### Option 2: Use the Context Directly
```tsx
import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';

export default function MyPage() {
  const { isReady, playTrack, playerState } = useSpotifyPlayer();
  
  const handlePlay = async () => {
    if (isReady) {
      await playTrack('spotify:track:...');
    }
  };
  
  return (
    <div>
      <p>Status: {isReady ? 'Ready' : 'Initializing'}</p>
      <p>Playing: {playerState.track?.name}</p>
      <button onClick={handlePlay}>Play Track</button>
    </div>
  );
}
```

## Testing

To test the implementation:

1. Start the app and navigate to a page with the player
2. Check browser console for initialization logs:
   - "Spotify SDK loaded"
   - "Initializing Spotify player..."
   - "✓ Player connected, waiting for ready event..."
   - "✓ Player ready with device_id: ..."
   - "✓ Playback transferred to device"
3. Navigate to different pages - player should NOT reinitialize
4. Play a track - should work immediately without 404 errors
5. Close tab - player should disconnect cleanly

## Common Pitfalls Avoided

❌ **Creating player in component** - Would recreate on every render/navigation
❌ **Calling transfer before ready** - Results in 404 errors
❌ **Not waiting for ready event** - Race conditions and stale device IDs
❌ **Missing cleanup** - Memory leaks and duplicate instances
❌ **Ignoring isReady state** - Premature playback attempts

## Requirements

- Spotify Premium account (required for Web Playback SDK)
- Valid Spotify access token with `streaming` and `user-modify-playback-state` scopes
- Modern browser with Web Playback SDK support

## References

- [Spotify Web Playback SDK Documentation](https://developer.spotify.com/documentation/web-playback-sdk)
- [Web Playback SDK Quick Start](https://developer.spotify.com/documentation/web-playback-sdk/quick-start)
