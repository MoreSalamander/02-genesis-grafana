// Runtime proxy to the Operational Intelligence backend (GENESIS_API_URL read
// at request time — identical behavior in `next dev` and the Cloud Run container).
import { NextRequest } from "next/server";

const BASE = () => process.env.GENESIS_API_URL ?? "http://127.0.0.1:8010";

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const search = new URL(req.url).search;
  const target = `${BASE()}/api/${path.join("/")}${search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }
  const res = await fetch(target, init);
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await ctx.params).path);
}
