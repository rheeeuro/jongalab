import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // 구 경로 → 신 경로
      { source: "/dashboard", destination: "/market", permanent: true },
      { source: "/stock/:ticker", destination: "/stocks/:ticker", permanent: true },
      { source: "/report/:date", destination: "/reports/:date", permanent: true },
      {
        source: "/report/:date/:ticker",
        destination: "/reports/:date/:ticker",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
