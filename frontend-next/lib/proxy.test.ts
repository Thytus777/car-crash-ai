// Run with `npm test` (node --test; Node strips the types itself).
import assert from "node:assert/strict";
import { test } from "node:test";

import { addId, clientIp, MAX_OWNED, readIds, route, signIds, signingKey, VisitorLimiter } from "./proxy.ts";

const key = signingKey("test-api-key");

test("only the calls the UI makes are forwarded", () => {
  assert.deepEqual(route("POST", ["upload"]), { kind: "upload", upstream: "/api/v1/upload" });
  assert.deepEqual(route("POST", ["analyze"]), { kind: "analyze", upstream: "/api/v1/analyze" });
  assert.deepEqual(route("GET", ["estimates", "42"]), { kind: "estimate", upstream: "/api/v1/estimates/42", id: 42 });
  assert.deepEqual(route("GET", ["report", "7"]), { kind: "report", upstream: "/api/v1/report/7", id: 7 });
  assert.deepEqual(route("GET", ["mine"]), { kind: "mine" });
});

test("everything else is refused", () => {
  assert.equal(route("GET", ["estimates"]), null, "the list of everyone's estimates");
  assert.equal(route("GET", ["upload"]), null);
  assert.equal(route("DELETE", ["estimates", "1"]), null);
  assert.equal(route("GET", ["estimates", "1", "extra"]), null);
  assert.equal(route("GET", ["estimates", "../admin"]), null);
  assert.equal(route("GET", ["report", "-1"]), null);
  assert.equal(route("POST", ["analyze", "1"]), null);
});

test("a signed cookie round-trips its estimate IDs", () => {
  assert.deepEqual(readIds(signIds([3, 9, 12], key), key), [3, 9, 12]);
  assert.deepEqual(readIds(signIds([], key), key), []);
});

test("a forged or tampered cookie grants nothing", () => {
  const good = signIds([3], key);
  assert.deepEqual(readIds(good.replace(/^3/, "4"), key), [], "changed ID");
  assert.deepEqual(readIds(signIds([3], signingKey("another-key")), key), [], "another key");
  assert.deepEqual(readIds("1-2-3", key), [], "unsigned");
  assert.deepEqual(readIds("1-2-3.", key), [], "empty signature");
  assert.deepEqual(readIds(undefined, key), []);
});

test("the cookie keeps the newest estimates, without duplicates", () => {
  let ids: number[] = [];
  for (let i = 1; i <= MAX_OWNED + 5; i++) ids = addId(ids, i);
  assert.equal(ids.length, MAX_OWNED);
  assert.equal(ids.at(-1), MAX_OWNED + 5);
  assert.deepEqual(addId([1, 2, 3], 2), [1, 3, 2]);
});

test("the visitor IP is the entry Cloud Run appended, not one the client sent", () => {
  assert.equal(clientIp("6.6.6.6, 203.0.113.9"), "203.0.113.9");
  assert.equal(clientIp("203.0.113.9"), "203.0.113.9");
  assert.equal(clientIp(null), "unknown");
});

test("each visitor gets their own analysis allowance per window", () => {
  const limiter = new VisitorLimiter(2, 60_000);
  assert.equal(limiter.take("a", 0), 0);
  assert.equal(limiter.take("a", 1_000), 0);
  assert.equal(limiter.take("a", 2_000), 58, "third in the window waits for the reset");
  assert.equal(limiter.take("b", 2_000), 0, "another visitor is unaffected");
  assert.equal(limiter.take("a", 60_000), 0, "a new window starts fresh");
});
