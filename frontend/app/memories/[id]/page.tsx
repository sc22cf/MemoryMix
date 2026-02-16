'use client';

import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { ArrowLeft, Music, Trash2, Plus, ExternalLink, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import { getPhotoProxyUrl } from '@/lib/photo-utils';
import { useState, useCallback } from 'react';
import SpotifyPlayer from '@/components/SpotifyPlayer';

export default function MemoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const memoryId = parseInt(params.id as string);
  
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [playingUri, setPlayingUri] = useState<string | undefined>(undefined);
  const [playId, setPlayId] = useState(0);
  const [playerReady, setPlayerReady] = useState(false);

  /**
   * Resolve a Spotify URI for a track and start playback.
   * If the track already has a spotify_uri, use it directly.
   * Otherwise, search Spotify by name + artist.
   */
  const playTrack = useCallback(async (track: any) => {
    if (!track) return;

    if (track.spotify_uri) {
      setPlayingUri(track.spotify_uri);
      setPlayId((n) => n + 1);
      return;
    }

    // Search Spotify for a URI
    try {
      const result = await apiClient.searchSpotifyTrack(
        track.track_name,
        track.artist_name,
      );
      if (result.found && result.uri) {
        setPlayingUri(result.uri);
        setPlayId((n) => n + 1);
      }
    } catch (err) {
      console.error('Failed to find track on Spotify:', err);
    }
  }, []);

  const { data: memory, isLoading } = useQuery({
    queryKey: ['memory', memoryId],
    queryFn: () => apiClient.getMemory(memoryId),
    enabled: !!user && !!memoryId,
  });

  const { data: suggestions } = useQuery({
    queryKey: ['suggestions', memoryId],
    queryFn: () => apiClient.getTrackSuggestions(memoryId, 3),
    enabled: !!user && !!memoryId && showSuggestions,
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiClient.deleteMemory(memoryId),
    onSuccess: () => {
      router.push('/dashboard');
    },
  });

  const createMappingMutation = useMutation({
    mutationFn: (params: { mapping: any; track?: any }) =>
      apiClient.createMapping(params.mapping),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['memory', memoryId] });
      // Auto-play the track that was just added
      if (variables.track) {
        playTrack(variables.track);
      }
    },
  });

  const deleteMappingMutation = useMutation({
    mutationFn: (mappingId: number) => apiClient.deleteMapping(mappingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memory', memoryId] });
    },
  });

  const handleDelete = () => {
    if (confirm('Are you sure you want to delete this memory? This cannot be undone.')) {
      deleteMutation.mutate();
    }
  };

  const handleAddSuggestedMapping = (
    photoId: number,
    trackId: number,
    confidenceScore: number,
    track?: any,
  ) => {
    createMappingMutation.mutate({
      mapping: {
        memory_id: memoryId,
        photo_id: photoId,
        track_id: trackId,
        is_auto_suggested: true,
        confidence_score: confidenceScore,
      },
      track,
    });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent"></div>
      </div>
    );
  }

  if (!memory) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-3">Memory not found</h2>
          <Link href="/dashboard" className="text-accent hover:text-accent-hover text-sm">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-md sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-muted hover:text-foreground transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Dashboard
          </Link>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Memory Header */}
        <div className="bg-surface border border-border rounded-xl p-6 mb-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h1 className="text-2xl font-bold mb-1.5">{memory.title}</h1>
              <p className="text-sm text-muted">
                {format(new Date(memory.memory_date), 'MMMM dd, yyyy')}
              </p>
              {memory.description && (
                <p className="text-sm text-muted/80 mt-3 leading-relaxed">{memory.description}</p>
              )}
            </div>
            <button
              onClick={handleDelete}
              className="text-muted hover:text-danger hover:bg-danger/10 p-2 rounded-lg transition-colors"
              title="Delete memory"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          <div className="flex gap-4 text-xs text-muted">
            <span>{memory.photos?.length || 0} photos</span>
            <span className="w-1 h-1 rounded-full bg-border self-center" />
            <span>{memory.mappings?.length || 0} track mappings</span>
          </div>
        </div>

        {/* Suggestions Toggle */}
        <div className="mb-6">
          <button
            onClick={() => setShowSuggestions(!showSuggestions)}
            className="bg-accent hover:bg-accent-hover text-background px-5 py-2.5 rounded-lg font-medium text-sm flex items-center gap-2 transition-all hover:shadow-[0_0_20px_rgba(20,184,166,0.2)]"
          >
            <Sparkles className="w-4 h-4" />
            {showSuggestions ? 'Hide' : 'Show'} Auto-Suggestions
          </button>
        </div>

        {/* Auto-Suggestions */}
        {showSuggestions && suggestions && (
          <div className="bg-accent-subtle border border-accent/20 rounded-xl p-6 mb-6">
            <h2 className="text-lg font-semibold mb-4 text-accent">Suggested Tracks</h2>
            {suggestions.map((photoSuggestion: any) => (
              <div key={photoSuggestion.photo_id} className="mb-6 last:mb-0">
                <div className="flex items-center gap-3 mb-3">
                  <img
                    src={getPhotoProxyUrl(photoSuggestion.photo.base_url, 200, 200, photoSuggestion.photo.local_url)}
                    alt={photoSuggestion.photo.filename}
                    className="w-14 h-14 rounded-lg object-cover"
                  />
                  <div className="flex-1">
                    <h3 className="font-medium text-sm">{photoSuggestion.photo.filename}</h3>
                    <p className="text-xs text-muted">
                      {format(new Date(photoSuggestion.photo.creation_time), 'MMM dd, yyyy hh:mm a')}
                    </p>
                  </div>
                </div>
                {photoSuggestion.suggested_tracks.length > 0 ? (
                  <div className="space-y-2 ml-[68px]">
                    {photoSuggestion.suggested_tracks.map((track: any) => (
                      <div
                        key={track.track_id}
                        className="bg-surface border border-border rounded-lg p-3 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-3">
                          {track.album_image_url && (
                            <img
                              src={track.album_image_url}
                              alt={track.album_name}
                              className="w-9 h-9 rounded-md"
                            />
                          )}
                          <div>
                            <div className="text-sm font-medium">{track.track_name}</div>
                            <div className="text-xs text-muted">{track.artist_name}</div>
                            <div className="text-[10px] text-muted/50 mt-0.5">
                              {track.confidence_score}% match · {track.time_difference_minutes}m apart
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => handleAddSuggestedMapping(
                            photoSuggestion.photo_id,
                            track.track_id,
                            track.confidence_score,
                            track,
                          )}
                          className="bg-accent hover:bg-accent-hover text-background px-3 py-1.5 rounded-md flex items-center gap-1.5 text-xs font-medium"
                        >
                          <Plus className="w-3 h-3" />
                          Add
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted ml-[68px]">No tracks found within time window</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Photos and Mappings */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {memory.photos && memory.photos.map((photo: any) => {
            const photoMappings = memory.mappings?.filter((m: any) => m.photo_id === photo.id) || [];
            
            return (
              <div key={photo.id} className="bg-surface border border-border rounded-xl overflow-hidden group">
                <div className="aspect-square bg-surface relative overflow-hidden">
                  <img
                    src={getPhotoProxyUrl(photo.base_url, 600, 600, photo.local_url)}
                    alt={photo.filename}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                </div>
                <div className="p-4">
                  <h3 className="font-medium text-sm mb-1 truncate">{photo.filename}</h3>
                  <p className="text-[10px] text-muted/50 mb-3">
                    {format(new Date(photo.creation_time), 'MMM dd, yyyy hh:mm a')}
                  </p>

                  {/* Track Mappings */}
                  {photoMappings.length > 0 ? (
                    <div className="space-y-2">
                      {photoMappings.map((mapping: any) => (
                        <div
                          key={mapping.id}
                          className="bg-surface-hover border border-border/50 rounded-lg p-2.5 relative group/mapping cursor-pointer hover:border-accent/30 transition-colors"
                          onClick={() => mapping.track && playTrack(mapping.track)}
                        >
                          <div className="flex items-center gap-2">
                            <Music className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-xs truncate">
                                {mapping.track?.track_name}
                              </div>
                              <div className="text-[10px] text-muted truncate">
                                {mapping.track?.artist_name}
                              </div>
                            </div>
                          </div>
                          {mapping.is_auto_suggested && (
                            <span className="text-[10px] text-accent/70 mt-1 block">
                              Auto-suggested · {mapping.confidence_score}%
                            </span>
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteMappingMutation.mutate(mapping.id);
                            }}
                            className="absolute top-2 right-2 opacity-0 group-hover/mapping:opacity-100 text-danger hover:bg-danger/10 p-1 rounded transition-opacity"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted/40 italic">No tracks mapped</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Spotify Player — fixed to bottom */}
      {user?.spotify_connected && (
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-background/80 backdrop-blur-lg border-t border-border">
          <div className="container mx-auto max-w-4xl">
            <SpotifyPlayer
              spotifyUri={playingUri}
              playId={playId}
              onReady={() => setPlayerReady(true)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
