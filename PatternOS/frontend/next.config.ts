import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost", "195.35.6.159"],
  async rewrites() {
    // Non-technical friendly local setup:
    // The frontend talks to its own origin (`/api/v1/*`) and Next proxies to the backend.
    // Override with PATTERNOS_BACKEND_ORIGIN when needed (e.g. different port).
    const backend = process.env.PATTERNOS_BACKEND_ORIGIN ?? "http://localhost:8000";
    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
