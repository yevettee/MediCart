import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 실시간 관제·로봇 제어·디버그를 '관리자 콘솔'(/console) 한 페이지로 통합.
  // 기존 경로는 콘솔로 리다이렉트(북마크·링크 보존).
  async redirects() {
    return [
      { source: "/map", destination: "/console", permanent: false },
      { source: "/control", destination: "/console", permanent: false },
      { source: "/debug", destination: "/console", permanent: false },
    ];
  },
};

export default nextConfig;
