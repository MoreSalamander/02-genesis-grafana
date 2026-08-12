// Runtime proxy to the render-farm simulator (demo controls).
import { NextRequest } from "next/server";

const BASE = () => process.env.SIMULATOR_URL ?? "http://127.0.0.1:9105";

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const res = await fetch(`${BASE()}/${path.join("/")}`, { method: "POST", cache: "no-store" });
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
