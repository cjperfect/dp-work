import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import { onUnauthorized, request } from "../../../lib/http.ts";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import {
  authenticate,
  restoreAuthSession,
  safeRedirect,
  signOut,
  useAuthStore,
} from "../../../stores/auth.ts";
import { calculateJwkThumbprint, compactDecrypt, exportJWK, generateKeyPair } from "jose";
import { encryptPassword } from "../lib/password-encryption.ts";
import { localAccountId, validateCredentials } from "../lib/auth.ts";

const keyPair = await generateKeyPair("RSA-OAEP-256", { modulusLength: 2048 });
const publicJwk = await exportJWK(keyPair.publicKey);
const encryptionKey = {
  key_id: await calculateJwkThumbprint(publicJwk),
  algorithm: "RSA-OAEP-256",
  encryption: "A256GCM",
  public_key: publicJwk,
  server_time: Math.floor(Date.now() / 1000),
};

function mockAuthFetch(handler) {
  return mockHttpRequest((path, init) =>
    path === "/api/auth/encryption-key"
      ? Promise.resolve(response(encryptionKey))
      : handler(path, init),
  );
}

const TOKEN_KEY = "dp-work.auth.token";
const user = {
  id: 1,
  username: "tester",
  department: "unassigned",
  role: "member",
  status: 0,
};
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
let storage;

beforeEach(() => {
  storage = new Map();
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
  });
  signOut();
});

afterEach(() => {
  signOut();
  mock.restoreAll();
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

function response(data, status = 200, message = "ok") {
  return Response.json({ code: status === 200 ? 0 : 2001, message, data }, { status });
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("credentials only require nonempty username and password without length restrictions", () => {
  assert.deepEqual(Object.keys(validateCredentials("", "")), ["username", "password"]);
  assert.ok(validateCredentials("   ", "p").username);
  assert.ok(validateCredentials("tester", "").password);
  assert.deepEqual(validateCredentials("a", "p"), {});
  assert.deepEqual(validateCredentials("bad name", "short"), {});
  assert.deepEqual(validateCredentials("u".repeat(64), "p".repeat(256)), {});
});

test("login and registration persist the token and public user cache without passwords", async () => {
  const fetch = mockAuthFetch(async () => response({ token: "valid-token", user }));
  for (const mode of ["login", "register"]) {
    await authenticate(mode, " tester ", "password123");
    const [path, init] = fetch.mock.calls.at(-1).arguments;
    assert.equal(path, `/api/auth/${mode}`);
    const submitted = JSON.parse(init.body);
    assert.deepEqual(Object.keys(submitted).sort(), ["encrypted_password", "username"]);
    assert.equal(submitted.username, "tester");
    assert.equal(init.body.includes("password123"), false);
    const decrypted = await compactDecrypt(submitted.encrypted_password, keyPair.privateKey);
    assert.deepEqual(JSON.parse(new TextDecoder().decode(decrypted.plaintext)), {
      username: "tester",
      password: "password123",
      purpose: mode,
      issued_at: encryptionKey.server_time,
    });
    assert.equal(storage.get(TOKEN_KEY), "valid-token");
    assert.deepEqual(JSON.parse(storage.get("dp-work.auth.user")), user);
    assert.equal(JSON.stringify([...storage]).includes('"password"'), false);
    assert.deepEqual(useAuthStore.getState().user, user);
  }
});

test("incorrect password and duplicate username keep the server's error message", async () => {
  for (const [status, message] of [
    [401, "用户名或密码错误"],
    [409, "用户名已存在"],
  ]) {
    mockAuthFetch(async () => response(null, status, message));
    await assert.rejects(authenticate("login", "tester", "password123"), { message });
    assert.equal(useAuthStore.getState().user, null);
    assert.equal(storage.size, 0);
  }
});

test("network failure and non-JSON responses have recoverable messages", async () => {
  mockHttpRequest(async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(authenticate("login", "tester", "password123"), /暂时无法连接服务/);
  mockHttpRequest(async () => new Response("Bad gateway", { status: 502 }));
  await assert.rejects(authenticate("login", "tester", "password123"), /服务暂时不可用/);
});

test("session restoration uses the login response cache without any requests", async () => {
  storage.set(TOKEN_KEY, "valid-token");
  storage.set("dp-work.auth.user", JSON.stringify(user));
  const fetch = mockHttpRequest(async () => {
    throw new Error("must not request");
  });
  assert.deepEqual(await restoreAuthSession(), user);
  assert.deepEqual(await restoreAuthSession(), user);
  assert.equal(fetch.mock.callCount(), 0);
});

test("missing or invalid user cache does not grant a restored session", async () => {
  storage.set(TOKEN_KEY, "valid-token");
  assert.equal(await restoreAuthSession(), null);
  storage.set("dp-work.auth.user", "invalid-json");
  assert.equal(await restoreAuthSession(), null);
  assert.equal(useAuthStore.getState().user, null);
});

test("a business API 401 clears token and cached identity", async () => {
  storage.set(TOKEN_KEY, "expired-token");
  storage.set("dp-work.auth.user", JSON.stringify(user));
  useAuthStore.setState({ user });
  mockHttpRequest(async () => response(null, 401));
  await assert.rejects(request("/api/knowledge-bases"));
  assert.equal(storage.size, 0);
  assert.equal(useAuthStore.getState().user, null);
});

test("temporary business API failures preserve the login cache", async () => {
  storage.set(TOKEN_KEY, "valid-token");
  storage.set("dp-work.auth.user", JSON.stringify(user));
  mockHttpRequest(async () => response(null, 503));
  await assert.rejects(request("/api/knowledge-bases"));
  assert.equal(storage.get(TOKEN_KEY), "valid-token");
  assert.deepEqual(await restoreAuthSession(), user);
});

test("an old rejected business request cannot log out a newly signed-in account", async () => {
  storage.set(TOKEN_KEY, "old-token");
  const pending = deferred();
  mockHttpRequest(() => pending.promise);
  const oldRequest = request("/api/knowledge-bases");
  const nextUser = { ...user, id: 2, username: "new-user" };
  mockAuthFetch(async () => response({ token: "new-token", user: nextUser }));
  await authenticate("login", "new-user", "password123");
  pending.resolve(response(null, 401));
  await assert.rejects(oldRequest);
  assert.equal(storage.get(TOKEN_KEY), "new-token");
  assert.deepEqual(useAuthStore.getState().user, nextUser);
});

test("logout also invalidates a pending login", async () => {
  const pending = deferred();
  mockHttpRequest(() => pending.promise);
  const login = authenticate("login", "tester", "password123");
  signOut();
  pending.resolve(response({ token: "old-token", user }));
  await assert.rejects(login, /已取消/);
  assert.equal(storage.size, 0);
  assert.equal(useAuthStore.getState().user, null);
});

test("blocked browser storage reports an actionable error without signing in", async () => {
  mockAuthFetch(async () => response({ token: "valid-token", user }));
  mock.method(localStorage, "setItem", () => {
    throw new Error("blocked");
  });
  await assert.rejects(authenticate("login", "tester", "password123"), /允许站点存储/);
  assert.equal(useAuthStore.getState().user, null);
});

test("logout clears identity even when storage access fails", () => {
  useAuthStore.setState({ user });
  mock.method(localStorage, "removeItem", () => {
    throw new Error("blocked");
  });
  signOut();
  assert.equal(useAuthStore.getState().user, null);
});

test("return addresses stay within the workspace and cannot loop through auth pages", () => {
  for (const path of [
    undefined,
    "https://example.com",
    "//example.com",
    "/\\example.com",
    "/sign-in?redirect=/",
    "/sign-up",
  ]) {
    assert.equal(safeRedirect(path), "/");
  }
  assert.equal(safeRedirect("/knowledge?search=sop#docs"), "/knowledge?search=sop#docs");
});

test("long passwords use fresh authenticated encryption without RSA plaintext length limits", async () => {
  const password = "密😀".repeat(300);
  const first = await encryptPassword(encryptionKey, "tester", password, "register");
  const second = await encryptPassword(encryptionKey, "tester", password, "register");
  assert.notEqual(first, second);
  const decrypted = await compactDecrypt(first, keyPair.privateKey);
  assert.equal(JSON.parse(new TextDecoder().decode(decrypted.plaintext)).password, password);
});

test("insecure non-local contexts cannot submit credentials", async () => {
  Object.defineProperty(window, "isSecureContext", { value: false });
  const fetch = mockAuthFetch(async () => {
    throw new Error("login must not be submitted");
  });
  await assert.rejects(authenticate("login", "tester", "password123"), /HTTPS/);
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/auth/encryption-key");
});

test("local data uses only positive numeric user IDs", () => {
  assert.equal(localAccountId({ id: 1 }), "user:1");
  assert.equal(localAccountId({ id: 2 }), "user:2");
  for (const id of ["u-cached", "42", 0, -1, NaN, 1.5, Infinity]) {
    assert.equal(localAccountId({ id }), null);
  }
  assert.equal(localAccountId(null), null);
});

test("a business API 401 without a token still notifies the login redirect handler", async () => {
  const handler = mock.fn();
  const unsubscribe = onUnauthorized(handler);
  try {
    mockHttpRequest(async () => response(null, 401));
    await assert.rejects(request("/api/knowledge-bases"));
    assert.equal(handler.mock.callCount(), 1);
    assert.equal(handler.mock.calls[0].arguments[0], null);
    await assert.rejects(request("/api/auth/login", { auth: false }));
    assert.equal(handler.mock.callCount(), 1);
  } finally {
    unsubscribe();
  }
});
