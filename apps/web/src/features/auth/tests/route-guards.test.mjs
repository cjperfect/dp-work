import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { restoreAuthSession, signOut, useAuthStore } from "../../../stores/auth.ts";
import { redirectAuthenticatedUser } from "../lib/auth.ts";

const originals = Object.fromEntries(
  ["window", "localStorage"].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const user = { id: 7, username: "tester" };
let getItem;
beforeEach(() => {
  const values = new Map([
    ["dp-work.auth.token", "token"],
    ["dp-work.auth.user", JSON.stringify(user)],
  ]);
  getItem = mock.fn((key) => values.get(key) ?? null);
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem, removeItem: (key) => values.delete(key) },
  });
  useAuthStore.setState({ user: null });
});
afterEach(() => {
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

test("auth-page redirects use the restored identity without reading storage or fetching", () => {
  const fetch = mockHttpRequest(async () => {
    throw new Error("unexpected request");
  });
  restoreAuthSession();
  const reads = getItem.mock.callCount();
  assert.throws(() => redirectAuthenticatedUser("/knowledge"));
  assert.equal(getItem.mock.callCount(), reads);
  assert.equal(fetch.mock.callCount(), 0);
});

test("logout allows auth pages without restoring stale cache", () => {
  restoreAuthSession();
  signOut();
  const reads = getItem.mock.callCount();
  assert.doesNotThrow(() => redirectAuthenticatedUser("/knowledge"));
  assert.equal(getItem.mock.callCount(), reads);
});
