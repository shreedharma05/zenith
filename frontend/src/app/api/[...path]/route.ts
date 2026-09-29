import { NextRequest } from "next/server";

// Manual reverse proxy to the FastAPI backend, replacing next.config.ts
// rewrites(). The framework-level rewrite proxy was silently dropping
// multipart/form-data POST requests (resume upload -> ECONNRESET) under
// Turbopack; a plain route handler forwards the raw body/headers/cookies
// reliably and behaves the same in dev and in production.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Generous ceiling above the 10 MB resume limit (multipart overhead + other
// small JSON bodies) -- rejects oversized requests by their declared
// Content-Length before buffering the body into this process's memory.
const MAX_BODY_BYTES = 15 * 1024 * 1024;

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const target = `${BACKEND_URL}/api/${path.join("/")}${request.nextUrl.search}`;

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (declaredLength > MAX_BODY_BYTES) {
    return new Response("Request body too large.", { status: 413 });
  }

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const init: RequestInit = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
