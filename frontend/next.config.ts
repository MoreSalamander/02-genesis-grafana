import type { NextConfig } from "next";

// /api/* and /sim/* are proxied at runtime by route handlers reading
// GENESIS_API_URL and SIMULATOR_URL — no build-time backend coupling.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
