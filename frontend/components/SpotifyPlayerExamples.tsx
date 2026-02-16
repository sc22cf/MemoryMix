/**
 * Example: Custom Spotify Player Controls
 * 
 * This example shows how to build custom UI components
 * that use the global Spotify player context.
 */

'use client';

import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';
import { Play, Pause, SkipForward, Volume2 } from 'lucide-react';

/**
 * Example 1: Simple Play Button
 * 
 * A minimal component that plays a specific track.
 */
export function SimplePlayButton({ trackUri, trackName }: { trackUri: string; trackName: string }) {
  const { isReady, playTrack, playerState } = useSpotifyPlayer();
  
  const handleClick = async () => {
    if (!isReady) {
      alert('Player not ready yet');
      return;
    }
    
    try {
      await playTrack(trackUri);
    } catch (err) {
      console.error('Failed to play:', err);
    }
  };
  
  const isCurrentTrack = playerState.track?.uri === trackUri;
  const isPlaying = isCurrentTrack && playerState.isPlaying;
  
  return (
    <button
      onClick={handleClick}
      disabled={!isReady}
      className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-full disabled:opacity-50"
    >
      {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
      {isPlaying ? 'Playing' : 'Play'} {trackName}
    </button>
  );
}

/**
 * Example 2: Mini Player Controls
 * 
 * A compact player control panel that can be placed anywhere.
 */
export function MiniPlayerControls() {
  const {
    isReady,
    playerState,
    togglePlay,
    nextTrack,
    setVolume,
  } = useSpotifyPlayer();
  
  if (!isReady) return null;
  
  const { track, isPlaying } = playerState;
  
  return (
    <div className="flex items-center gap-4 p-3 bg-gray-800 rounded-lg">
      {/* Track Info */}
      <div className="flex-1 min-w-0">
        {track ? (
          <>
            <p className="text-sm font-medium truncate">{track.name}</p>
            <p className="text-xs text-gray-400 truncate">{track.artist}</p>
          </>
        ) : (
          <p className="text-xs text-gray-500">No track playing</p>
        )}
      </div>
      
      {/* Controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={togglePlay}
          className="p-2 hover:bg-gray-700 rounded-full"
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>
        <button
          onClick={nextTrack}
          className="p-2 hover:bg-gray-700 rounded-full"
        >
          <SkipForward className="w-4 h-4" />
        </button>
      </div>
      
      {/* Volume */}
      <div className="flex items-center gap-2">
        <Volume2 className="w-4 h-4 text-gray-400" />
        <input
          type="range"
          min="0"
          max="100"
          defaultValue="50"
          onChange={(e) => setVolume(Number(e.target.value) / 100)}
          className="w-20"
        />
      </div>
    </div>
  );
}

/**
 * Example 3: Track List with Play Buttons
 * 
 * Shows how to create a list of tracks where each can be played.
 */
export function TrackList({ tracks }: { tracks: Array<{ uri: string; name: string; artist: string }> }) {
  const { isReady, playTrack, playerState } = useSpotifyPlayer();
  
  const handlePlay = async (trackUri: string) => {
    if (!isReady) return;
    
    try {
      await playTrack(trackUri);
    } catch (err) {
      console.error('Playback failed:', err);
    }
  };
  
  return (
    <div className="space-y-2">
      {tracks.map((track) => {
        const isCurrentTrack = playerState.track?.uri === track.uri;
        const isPlaying = isCurrentTrack && playerState.isPlaying;
        
        return (
          <div
            key={track.uri}
            className={`flex items-center gap-3 p-3 rounded-lg ${
              isCurrentTrack ? 'bg-green-900/20' : 'bg-gray-800'
            }`}
          >
            <button
              onClick={() => handlePlay(track.uri)}
              disabled={!isReady}
              className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-green-600 hover:bg-green-700 rounded-full disabled:opacity-50"
            >
              {isPlaying ? (
                <Pause className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4 ml-0.5" />
              )}
            </button>
            
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{track.name}</p>
              <p className="text-sm text-gray-400 truncate">{track.artist}</p>
            </div>
            
            {isCurrentTrack && (
              <div className="flex-shrink-0">
                <div className="flex gap-1 items-end h-4">
                  {[...Array(3)].map((_, i) => (
                    <div
                      key={i}
                      className={`w-1 bg-green-500 rounded-full ${
                        isPlaying ? 'animate-pulse' : ''
                      }`}
                      style={{
                        height: `${30 + i * 35}%`,
                        animationDelay: `${i * 0.15}s`,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Example 4: Hook for Custom Player Logic
 * 
 * Shows how to create a custom hook that uses the player context.
 */
export function useTrackPlayback(trackUri: string) {
  const { isReady, playTrack, playerState } = useSpotifyPlayer();
  
  const isCurrentTrack = playerState.track?.uri === trackUri;
  const isPlaying = isCurrentTrack && playerState.isPlaying;
  
  const play = async () => {
    if (!isReady) {
      throw new Error('Player not ready');
    }
    await playTrack(trackUri);
  };
  
  return {
    play,
    isReady,
    isCurrentTrack,
    isPlaying,
    currentPosition: isCurrentTrack ? playerState.position : 0,
    duration: isCurrentTrack ? playerState.duration : 0,
  };
}

/**
 * Example 5: Using the Custom Hook
 */
export function TrackCard({ track }: { track: { uri: string; name: string; image: string } }) {
  const { play, isReady, isPlaying } = useTrackPlayback(track.uri);
  
  return (
    <div className="relative group">
      <img src={track.image} alt={track.name} className="w-full aspect-square rounded-lg" />
      
      <button
        onClick={play}
        disabled={!isReady}
        className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <div className="w-16 h-16 flex items-center justify-center bg-green-500 rounded-full">
          {isPlaying ? (
            <Pause className="w-8 h-8" />
          ) : (
            <Play className="w-8 h-8 ml-1" />
          )}
        </div>
      </button>
      
      <p className="mt-2 font-medium">{track.name}</p>
    </div>
  );
}

/**
 * BEST PRACTICES:
 * 
 * 1. Always check `isReady` before calling playback methods
 * 2. Handle errors gracefully with try/catch
 * 3. Show loading states while player initializes
 * 4. Use playerState to show current track info
 * 5. Don't create your own player instance - use the context
 * 6. The player persists across route changes automatically
 * 7. One playTrack() call per user action (don't call in loops)
 */
