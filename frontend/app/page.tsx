'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/lib/api-client';
import { TestSongPreview } from '@/lib/types';
import { Music, Camera, Sparkles, FlaskConical, RefreshCw, ChevronRight } from 'lucide-react';

export default function Home() {
  const { user, loading, testLogin } = useAuth();
  const router = useRouter();

  const [showTestSetup, setShowTestSetup] = useState(false);
  const [testMode, setTestMode] = useState<'hardcoded' | 'random'>('hardcoded');
  const [testSongs, setTestSongs] = useState<TestSongPreview[]>([]);
  const [testSongsLoading, setTestSongsLoading] = useState(false);
  const [startingTest, setStartingTest] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.push('/dashboard');
    }
  }, [user, loading, router]);

  const handleLastfmLogin = async () => {
    try {
      const { auth_url } = await apiClient.getLastfmLoginUrl();
      window.location.href = auth_url;
    } catch (error) {
      console.error('Failed to get login URL:', error);
    }
  };

  const fetchTestSongs = async (mode: 'hardcoded' | 'random') => {
    setTestSongsLoading(true);
    try {
      const songs = await apiClient.getTestPreviewSongs(mode);
      setTestSongs(songs);
    } catch (error) {
      console.error('Failed to fetch test songs:', error);
    } finally {
      setTestSongsLoading(false);
    }
  };

  const handleTestingModeClick = () => {
    if (showTestSetup) {
      setShowTestSetup(false);
      return;
    }
    setShowTestSetup(true);
    fetchTestSongs(testMode);
  };

  const handleTestModeToggle = (mode: 'hardcoded' | 'random') => {
    setTestMode(mode);
    fetchTestSongs(mode);
  };

  const handleStartTesting = async () => {
    setStartingTest(true);
    try {
      const rowids = testSongs.map((s) => s.rowid).filter((id): id is number => id != null);
      await testLogin(testMode, rowids.length > 0 ? rowids : undefined);
    } catch (error) {
      console.error('Failed to start testing:', error);
      setStartingTest(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-accent/5 blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[400px] h-[400px] rounded-full bg-teal-500/5 blur-[100px]" />
      </div>

      <div className="relative container mx-auto px-4 py-20">
        <div className="max-w-4xl mx-auto text-center">
          {/* Hero */}
          <div className="mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent-subtle border border-accent/20 text-accent text-sm font-medium mb-8">
              <Sparkles className="w-3.5 h-3.5" />
              Music meets memories
            </div>
            <h1 className="text-5xl md:text-7xl font-bold mb-6 tracking-tight">
              Memory<span className="text-accent">Mix</span>
            </h1>
            <p className="text-xl md:text-2xl text-muted mb-4 max-w-2xl mx-auto leading-relaxed">
              Your listening history, your photos — perfectly synced into moments worth reliving.
            </p>
          </div>

          {/* Features */}
          <div className="grid md:grid-cols-3 gap-6 mb-16">
            <div className="group bg-surface border border-border rounded-xl p-6 hover:border-accent/30 hover:bg-surface-hover transition-all">
              <div className="w-12 h-12 rounded-lg bg-accent-subtle flex items-center justify-center mb-4 mx-auto group-hover:scale-110 transition-transform">
                <Music className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-lg font-semibold mb-2">Track Your Tunes</h3>
              <p className="text-muted text-sm leading-relaxed">
                Sync your Last.fm listening history and see exactly what was playing at any moment.
              </p>
            </div>
            <div className="group bg-surface border border-border rounded-xl p-6 hover:border-accent/30 hover:bg-surface-hover transition-all">
              <div className="w-12 h-12 rounded-lg bg-accent-subtle flex items-center justify-center mb-4 mx-auto group-hover:scale-110 transition-transform">
                <Camera className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-lg font-semibold mb-2">Add Your Photos</h3>
              <p className="text-muted text-sm leading-relaxed">
                Pull in photos from Google Photos and build memories around moments that matter.
              </p>
            </div>
            <div className="group bg-surface border border-border rounded-xl p-6 hover:border-accent/30 hover:bg-surface-hover transition-all">
              <div className="w-12 h-12 rounded-lg bg-accent-subtle flex items-center justify-center mb-4 mx-auto group-hover:scale-110 transition-transform">
                <Sparkles className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-lg font-semibold mb-2">Auto-Match Magic</h3>
              <p className="text-muted text-sm leading-relaxed">
                Smart time-matching suggests which songs were playing when you took each photo.
              </p>
            </div>
          </div>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={handleLastfmLogin}
              className="inline-flex items-center gap-3 bg-accent hover:bg-accent-hover text-background font-semibold py-4 px-8 rounded-xl text-lg transition-all hover:shadow-[0_0_30px_rgba(20,184,166,0.3)] active:scale-[0.98]"
            >
              <Music className="w-5 h-5" />
              Sign in with Last.fm
            </button>
            <button
              onClick={handleTestingModeClick}
              className="inline-flex items-center gap-3 bg-surface hover:bg-surface-hover border border-border hover:border-accent/30 text-foreground font-semibold py-4 px-8 rounded-xl text-lg transition-all active:scale-[0.98]"
            >
              <FlaskConical className="w-5 h-5 text-accent" />
              Testing Mode
            </button>
          </div>

          <p className="mt-6 text-sm text-muted/60">
            Free to use · No credit card required
          </p>

          {/* Test Setup Panel */}
          {showTestSetup && (
            <div className="mt-10 max-w-2xl mx-auto bg-surface border border-amber-500/30 rounded-2xl p-6 text-left">
              <div className="flex items-center gap-2 mb-5">
                <FlaskConical className="w-5 h-5 text-amber-400" />
                <h2 className="text-lg font-semibold text-foreground">Test Setup</h2>
              </div>

              {/* Mode Toggle */}
              <div className="flex rounded-lg bg-background border border-border overflow-hidden mb-5">
                <button
                  onClick={() => handleTestModeToggle('hardcoded')}
                  className={`flex-1 py-2.5 px-4 text-sm font-medium transition-all ${
                    testMode === 'hardcoded'
                      ? 'bg-amber-500/20 text-amber-300 border-r border-amber-500/30'
                      : 'text-muted hover:text-foreground border-r border-border'
                  }`}
                >
                  Hardcoded (15 classics)
                </button>
                <button
                  onClick={() => handleTestModeToggle('random')}
                  className={`flex-1 py-2.5 px-4 text-sm font-medium transition-all ${
                    testMode === 'random'
                      ? 'bg-amber-500/20 text-amber-300'
                      : 'text-muted hover:text-foreground'
                  }`}
                >
                  Random Selection
                </button>
              </div>

              {/* Song List */}
              <div className="rounded-lg border border-border bg-background max-h-80 overflow-y-auto mb-5">
                {testSongsLoading ? (
                  <div className="flex items-center justify-center py-10">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
                  </div>
                ) : testSongs.length === 0 ? (
                  <p className="text-muted text-sm text-center py-10">No songs loaded</p>
                ) : (
                  <ul className="divide-y divide-border">
                    {testSongs.map((song, i) => (
                      <li key={song.rowid ?? i} className="flex items-center gap-3 px-4 py-2.5">
                        <span className="text-xs text-muted w-5 text-right shrink-0">{i + 1}</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-foreground truncate">{song.track_name}</p>
                          <p className="text-xs text-muted truncate">{song.artist_name}</p>
                        </div>
                        {song.genre && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-subtle text-accent shrink-0">
                            {song.genre}
                          </span>
                        )}
                        {!song.spotify_id && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 shrink-0">
                            no ID
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3">
                {testMode === 'random' && (
                  <button
                    onClick={() => fetchTestSongs('random')}
                    disabled={testSongsLoading}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border bg-background hover:bg-surface-hover text-sm font-medium text-foreground transition-all disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${testSongsLoading ? 'animate-spin' : ''}`} />
                    Randomize
                  </button>
                )}
                <button
                  onClick={handleStartTesting}
                  disabled={startingTest || testSongsLoading || testSongs.length === 0}
                  className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 text-amber-300 text-sm font-semibold transition-all disabled:opacity-50"
                >
                  {startingTest ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-amber-300 border-t-transparent" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  Start Testing with {testSongs.length} songs
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
