import { withAui } from "@assistant-ui/next";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const apiBase = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
    return [{ source: "/api/v1/:path*", destination: `${apiBase}/api/v1/:path*` }];
  },
};

export default withAui(nextConfig);
