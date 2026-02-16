'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/lib/api-client';
import { Music, Camera, Sparkles } from 'lucide-react';

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

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
          </div>

          <p className="mt-6 text-sm text-muted/60">
            Free to use · No credit card required
          </p>
        </div>
      </div>
    </div>
  );
}
