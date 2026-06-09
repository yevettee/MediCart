import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["192.168.123.26", "192.168.123.47"],
  async rewrites() {
    return {
      beforeFiles: [],
      // Next.js 자체 API 라우트(/api/auth/*, /api/display/patient) 우선 처리 후
      // 나머지 /api/* 는 Flask(localhost:5000)로 프록시
      afterFiles: [
        {
          source: "/api/:path*",
          destination: "http://localhost:5000/api/:path*",
        },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
