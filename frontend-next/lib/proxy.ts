/**
 * Server-side rules for the /api/v1 proxy (app/api/v1/[...path]/route.ts).
 *
 * The browser never sees the API key: it calls this app, which adds the key
 * and forwards only the calls the UI makes. Because every visitor shares that
 * one key, the proxy also decides who may read which estimate (a signed
 * cookie lists the estimates this browser created) and rate-limits analyses
 * per visitor, on top of the API's own per-key limit.
 *
 * Framework-free so it runs under `node --test` (lib/proxy.test.ts).
 */
import { createHmac, hkdfSync, randomBytes, timingSafeEqual } from "node:crypto";

export const OWNED_COOKIE = "cca_estimates";
export const MAX_OWNED = 20;

export type Route =
  | { kind: "upload"; upstream: string }
  | { kind: "analyze"; upstream: string }
  | { kind: "estimate"; upstream: string; id: number }
  | { kind: "report"; upstream: string; id: number }
  | { kind: "mine" };

const ID = /^\d{1,12}$/;

/** Map a method and path under /api/v1 to an allowed call, or null (404). */
export function route(method: string, segments: string[]): Route | null {
  const [head, id, ...rest] = segments;
  if (rest.length) return null;
  if (method === "POST" && id === undefined) {
    if (head === "upload") return { kind: "upload", upstream: "/api/v1/upload" };
    if (head === "analyze") return { kind: "analyze", upstream: "/api/v1/analyze" };
  }
  if (method === "GET") {
    if (head === "mine" && id === undefined) return { kind: "mine" };
    if (id !== undefined && ID.test(id)) {
      if (head === "estimates") return { kind: "estimate", upstream: `/api/v1/estimates/${id}`, id: Number(id) };
      if (head === "report") return { kind: "report", upstream: `/api/v1/report/${id}`, id: Number(id) };
    }
  }
  return null;
}

/** The cookie-signing key: derived from the API key, so there's no extra secret to manage. */
export function signingKey(apiKey: string | undefined): Buffer {
  if (!apiKey) return devKey; // local dev without auth: cookies last until restart
  // HKDF: the API key is already high-entropy random, so this derives a
  // separate key from it rather than stretching a password.
  return Buffer.from(hkdfSync("sha256", apiKey, "car-crash-ai", "web cookie signing", 32));
}
const devKey = randomBytes(32);

function mac(payload: string, key: Buffer): string {
  return createHmac("sha256", key).update(payload).digest("base64url");
}

/** Cookie value listing estimate IDs, newest last, capped at MAX_OWNED. */
export function signIds(ids: number[], key: Buffer): string {
  const payload = ids.slice(-MAX_OWNED).join("-");
  return `${payload}.${mac(payload, key)}`;
}

/** IDs from a cookie value; an unsigned, tampered or malformed cookie gives []. */
export function readIds(value: string | undefined, key: Buffer): number[] {
  if (!value) return [];
  const dot = value.lastIndexOf(".");
  if (dot < 0) return [];
  const payload = value.slice(0, dot);
  const given = Buffer.from(value.slice(dot + 1));
  const expected = Buffer.from(mac(payload, key));
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return [];
  if (payload === "") return [];
  const ids = payload.split("-");
  return ids.every((s) => ID.test(s)) ? ids.map(Number) : [];
}

export function addId(ids: number[], id: number): number[] {
  return [...ids.filter((x) => x !== id), id].slice(-MAX_OWNED);
}

/**
 * The visitor's IP. Cloud Run's front end appends the address it saw to
 * X-Forwarded-For, so the last entry is the one a client can't forge.
 */
export function clientIp(forwardedFor: string | null): string {
  const parts = (forwardedFor ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return parts.at(-1) ?? "unknown";
}

/** Fixed-window counter per visitor, in process memory (per instance). */
export class VisitorLimiter {
  private windows = new Map<string, { start: number; count: number }>();
  private readonly limit: number;
  private readonly windowMs: number;

  constructor(limit: number, windowMs: number) {
    this.limit = limit;
    this.windowMs = windowMs;
  }

  /** Count one request; return 0 if allowed, else seconds until the window resets. */
  take(visitor: string, now: number = Date.now()): number {
    const w = this.windows.get(visitor);
    if (!w || now - w.start >= this.windowMs) {
      this.windows.set(visitor, { start: now, count: 1 });
      if (this.windows.size > 10_000) this.prune(now);
      return 0;
    }
    if (w.count < this.limit) {
      w.count += 1;
      return 0;
    }
    return Math.max(1, Math.ceil((w.start + this.windowMs - now) / 1000));
  }

  private prune(now: number): void {
    for (const [k, w] of this.windows) if (now - w.start >= this.windowMs) this.windows.delete(k);
  }
}

/** An RFC 9457 problem body, the same shape the API returns. */
export function problem(status: number, title: string, detail: string): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, detail }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}
