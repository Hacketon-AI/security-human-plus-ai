import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  async rewrites() {
    const internalApiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://securescope-api:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiBaseUrl}/api/:path*`,
      },
      {
        source: "/ai-proof-of-risk/:path*",
        destination: `${internalApiBaseUrl}/ai-proof-of-risk/:path*`,
      },
      {
        source: "/domain-safe-scan/:path*",
        destination: `${internalApiBaseUrl}/domain-safe-scan/:path*`,
      },
    ];
  },
};

export default nextConfig;
