/**
 * Same-origin proxy to the Car Crash AI API: the browser calls /api/v1/...,
 * and this server adds the API key, which never reaches the browser.
 * The rules (allowed calls, estimate ownership, per-visitor limits) live in
 * lib/proxy.ts. Server env: API_URL, and API_KEYS (or API_KEY) when the API
 * requires a key; the first comma-separated key is used.
 */
import { type NextRequest } from "next/server";

import {
  OWNED_COOKIE,
  VisitorLimiter,
  addId,
  clientIp,
  problem,
  readIds,
  route,
  signIds,
  signingKey,
} from "@/lib/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const API_KEY = (process.env.API_KEYS ?? process.env.API_KEY ?? "").split(",")[0]?.trim() || undefined;
const KEY = signingKey(API_KEY);

// Per visitor and per instance, on top of the API's own per-key limit.
const analyses = new VisitorLimiter(5, 10 * 60_000);
const uploads = new VisitorLimiter(20, 10 * 60_000);

const PASS_HEADERS = ["content-type", "content-disposition", "retry-after", "x-request-id"];

function upstreamHeaders(req: NextRequest): Headers {
  const h = new Headers();
  const type = req.headers.get("content-type");
  if (type) h.set("Content-Type", type);
  if (API_KEY) h.set("X-API-Key", API_KEY);
  return h;
}

function relay(res: Response, body: BodyInit | null): Response {
  const headers = new Headers();
  for (const name of PASS_HEADERS) {
    const value = res.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(body, { status: res.status, headers });
}

function withOwned(response: Response, ids: number[]): Response {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  response.headers.append(
    "Set-Cookie",
    `${OWNED_COOKIE}=${signIds(ids, KEY)}; Path=/api/v1; Max-Age=${30 * 86_400}; HttpOnly; SameSite=Lax${secure}`,
  );
  return response;
}

async function upstream(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, { ...init, cache: "no-store", signal: AbortSignal.timeout(170_000) });
}

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const r = route(req.method, (await ctx.params).path);
  if (!r) return problem(404, "Not found", "This app doesn't offer that request.");
  const owned = readIds(req.cookies.get(OWNED_COOKIE)?.value, KEY);
  const visitor = clientIp(req.headers.get("x-forwarded-for"));

  try {
    if (r.kind === "mine") {
      // Summaries of the estimates this browser created, newest first.
      const found = await Promise.all(
        [...owned].reverse().map(async (id) => {
          const res = await upstream(`/api/v1/estimates/${id}`, { headers: upstreamHeaders(req) });
          return res.ok ? res.json() : null;
        }),
      );
      return Response.json(found.filter(Boolean));
    }

    if (r.kind === "estimate" || r.kind === "report") {
      // IDs are sequential, so only show this browser's own estimates.
      if (!owned.includes(r.id)) return problem(404, "Not found", `Estimate ${r.id} not found.`);
      const res = await upstream(r.upstream, { headers: upstreamHeaders(req) });
      return relay(res, res.body);
    }

    const limiter = r.kind === "analyze" ? analyses : uploads;
    const wait = limiter.take(visitor);
    if (wait) {
      const res = problem(
        429,
        "Too many requests",
        r.kind === "analyze"
          ? `This demo allows 5 analyses per visitor every 10 minutes. Try again in ${Math.ceil(wait / 60)} min.`
          : `Too many uploads. Try again in ${Math.ceil(wait / 60)} min.`,
      );
      res.headers.set("Retry-After", String(wait));
      return res;
    }

    const res = await upstream(r.upstream, {
      method: "POST",
      headers: upstreamHeaders(req),
      body: req.body,
      // Stream the upload through instead of buffering it.
      duplex: "half",
    } as RequestInit);
    if (r.kind === "upload" || !res.ok) return relay(res, res.body);

    const text = await res.text();
    const id = (JSON.parse(text) as { estimate_id?: number | null }).estimate_id;
    const response = relay(res, text);
    return typeof id === "number" ? withOwned(response, addId(owned, id)) : response;
  } catch (err) {
    console.error(JSON.stringify({ severity: "ERROR", message: "API request failed", error: String(err) }));
    return problem(502, "API unavailable", "The analysis service didn't respond. Try again in a minute.");
  }
}

export { handle as GET, handle as POST };
