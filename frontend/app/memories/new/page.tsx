'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useGoogleAuth } from '@/hooks/useGoogleAuth';
import { apiClient } from '@/lib/api-client';
import { ArrowLeft, Camera, Calendar, Upload, Image as ImageIcon } from 'lucide-react';
import Link from 'next/link';
import { useGooglePhotosPicker, PickerStatusOverlay } from '@/components/GooglePhotosPicker';
import { getPhotoProxyUrl } from '@/lib/photo-utils';

declare global {
  interface Window {
    google: any;
    gapi: any;
  }
}

export default function NewMemoryPage() {
  const { user } = useAuth();
  const router = useRouter();
  const googleAuth = useGoogleAuth();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [memoryDate, setMemoryDate] = useState('');
  const [selectedPhotos, setSelectedPhotos] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);

  const handlePhotosPicked = useCallback((photos: any[]) => {
    setSelectedPhotos((prev) => [...prev, ...photos]);
  }, []);

  const handlePickerError = useCallback((msg: string) => {
    setPickerError(msg);
    setTimeout(() => setPickerError(null), 5000);
  }, []);

  const picker = useGooglePhotosPicker({
    accessToken: googleAuth.accessToken || '',
    onPhotosPicked: handlePhotosPicked,
    onError: handlePickerError,
    onDone: () => {},
  });

  const handleGooglePhotosPicker = () => {
    if (!googleAuth.isSignedIn) {
      googleAuth.signIn();
      return;
    }
    picker.startPicker();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const photo = {
          google_photo_id: `local_${Date.now()}_${Math.random()}`,
          base_url: event.target?.result as string,
          filename: file.name,
          mime_type: file.type,
          creation_time: new Date().toISOString(),
          width: null,
          height: null,
        };
        setSelectedPhotos((prev) => [...prev, photo]);
      };
      reader.readAsDataURL(file);
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!title || !memoryDate) {
      alert('Please fill in all required fields');
      return;
    }

    setLoading(true);

    try {
      const memories = await apiClient.createMemory({
        title,
        description,
        memory_date: new Date(memoryDate).toISOString(),
        photos: selectedPhotos,
        google_access_token: googleAuth.accessToken,
      });

      // Navigate to dashboard to see all created memories
      router.push('/dashboard');
    } catch (error) {
      console.error('Failed to create memory:', error);
      alert('Failed to create memory. Please try again.');
    } finally {
      setLoading(false);
    }
  };

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

      <div className="container mx-auto px-4 py-8 max-w-3xl">
        <h1 className="text-2xl font-bold mb-8">Create New Memory</h1>

        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-xl p-6 space-y-6">
          {/* Title */}
          <div>
            <label htmlFor="title" className="block text-sm font-medium text-muted mb-2">
              Memory Title <span className="text-danger">*</span>
            </label>
            <input
              type="text"
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-foreground placeholder:text-muted/40 focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors"
              placeholder="e.g., Summer Vacation 2025"
              required
            />
          </div>

          {/* Date */}
          <div>
            <label htmlFor="date" className="block text-sm font-medium text-muted mb-2">
              <Calendar className="w-3.5 h-3.5 inline mr-1.5" />
              Memory Date <span className="text-danger">*</span>
            </label>
            <input
              type="date"
              id="date"
              value={memoryDate}
              onChange={(e) => setMemoryDate(e.target.value)}
              className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-foreground focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors [color-scheme:dark]"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-muted mb-2">
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-foreground placeholder:text-muted/40 focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors resize-none"
              placeholder="Add some notes about this memory..."
            />
          </div>

          {/* Photos */}
          <div>
            <label className="block text-sm font-medium text-muted mb-3">
              <Camera className="w-3.5 h-3.5 inline mr-1.5" />
              Photos
            </label>
            
            <div className="mb-4 flex gap-2 flex-wrap">
              <button
                type="button"
                onClick={handleGooglePhotosPicker}
                className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-background px-4 py-2 rounded-lg text-sm font-medium"
              >
                <ImageIcon className="w-4 h-4" />
                {googleAuth.isSignedIn ? 'Google Photos' : 'Sign in to Google'}
              </button>

              {googleAuth.isSignedIn && (
                <button
                  type="button"
                  onClick={googleAuth.signOut}
                  className="flex items-center gap-2 text-muted px-3 py-2 rounded-lg hover:bg-surface-hover text-xs"
                >
                  Sign out
                </button>
              )}
              
              <label className="flex items-center gap-2 bg-surface-hover border border-border hover:border-accent/30 text-foreground px-4 py-2 rounded-lg cursor-pointer text-sm font-medium transition-colors">
                <Upload className="w-4 h-4" />
                Upload Files
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>

            {!googleAuth.isLoaded && (
              <p className="text-xs text-muted/50 mb-2">
                Loading Google Photos integration...
              </p>
            )}
            
            {googleAuth.isLoaded && !googleAuth.isSignedIn && (
              <p className="text-xs text-accent/70 mb-2">
                Sign in to access your Google Photos library, or upload files directly.
              </p>
            )}

            {selectedPhotos.length > 0 && (
              <div className="grid grid-cols-3 gap-3">
                {selectedPhotos.map((photo, index) => (
                  <div key={index} className="relative aspect-square bg-surface-hover rounded-lg overflow-hidden group">
                    <img
                      src={getPhotoProxyUrl(photo.base_url, 300, 300)}
                      alt={photo.filename}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => setSelectedPhotos(selectedPhotos.filter((_, i) => i !== index))}
                      className="absolute top-2 right-2 bg-danger hover:bg-danger-hover text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-xs"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Submit */}
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-accent hover:bg-accent-hover text-background px-6 py-3 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-sm transition-all hover:shadow-[0_0_20px_rgba(20,184,166,0.2)]"
            >
              {loading ? 'Creating...' : 'Create Memory'}
            </button>
            <Link
              href="/dashboard"
              className="px-6 py-3 border border-border rounded-lg hover:border-accent/30 hover:bg-surface-hover font-medium text-sm text-center transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>

        <div className="mt-6 bg-accent-subtle border border-accent/20 rounded-xl p-4">
          <h3 className="font-medium text-sm text-accent mb-1.5">Next Steps</h3>
          <p className="text-xs text-muted leading-relaxed">
            After creating your memory, you'll see auto-suggested track matches based on when your photos were taken.
          </p>
        </div>
      </div>

      {/* Google Photos Picker Status Overlay */}
      <PickerStatusOverlay
        state={picker.state}
        pickerUri={picker.pickerUri}
        onCancel={picker.cancel}
      />

      {/* Picker error toast */}
      {pickerError && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-danger text-white px-6 py-3 rounded-lg shadow-lg text-sm">
          {pickerError}
        </div>
      )}
    </div>
  );
}
