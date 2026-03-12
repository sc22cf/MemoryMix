import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Expose backend URL to the browser bundle at build time.
  // Override with the NEXT_PUBLIC_API_URL environment variable (or Docker build arg).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
