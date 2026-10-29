import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { request, HttpError } from "../../../lib/http.ts";
import { isLocalBusiness } from "../../../lib/local-transport.ts";
let originalWindow, originalStorage, listeners, calls;
beforeEach(() => {
  originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  listeners = new Set();
  calls = [];
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "fixture-token" },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      desktop: {
        onLocalChunk(listener) {
          listeners.add(listener);
          return () => listeners.delete(listener);
        },
        async cancelLocalRequest(id) {
          calls.push({ cancel: id });
        },
        async localRequest(input) {
          calls.push(input);
          const data = new TextEncoder().encode(JSON.stringify({ saved: true }));
          for (const listener of [...listeners]) listener({ id: input.id, data });
          for (const listener of [...listeners]) listener({ id: input.id, done: true });
          return { status: 200, contentType: "application/json" };
        },
      },
    },
  });
});
afterEach(() => {
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});
test("local domains use desktop IPC while remote business stays classified separately", async () => {
  for (const path of [
    "/api/agents/threads",
    "/api/settings",
    "/api/skills",
    "/api/memories",
    "/api/memories/preferences",
    "/api/connectors/feishu",
  ])
    assert.ok(isLocalBusiness(path));
  for (const path of ["/api/auth/login", "/api/meetings", "/api/knowledge-bases"])
    assert.equal(isLocalBusiness(path), false);
  assert.deepEqual(
    await request("/api/settings/model", { method: "PUT", data: { model: "local-model" } }),
    { saved: true },
  );
  assert.equal(calls[0].path, "/api/settings/model");
  assert.equal(calls[0].token, "fixture-token");
  assert.deepEqual(calls[0].body, { model: "local-model" });
  assert.equal(listeners.size, 0);
});
test("local business preserves conflict messages and never falls back to remote API", async () => {
  window.desktop.localRequest = async (input) => {
    const data = new TextEncoder().encode(JSON.stringify({ detail: { message: "会话版本冲突" } }));
    for (const listener of [...listeners]) listener({ id: input.id, data });
    for (const listener of [...listeners]) listener({ id: input.id, done: true });
    return { status: 409, contentType: "application/json" };
  };
  await assert.rejects(
    request("/api/agents/threads/one"),
    (error) =>
      error instanceof HttpError && error.status === 409 && error.message === "会话版本冲突",
  );
  delete window.desktop;
  await assert.rejects(request("/api/agents/threads"), /请在桌面端/);
  await assert.rejects(request("/api/agents/projects"), /浏览器无法连接本机服务/);
});
test("local streaming preserves chunks emitted before IPC response head resolves", async () => {
  window.desktop.localRequest = async (input) => {
    for (const listener of [...listeners])
      listener({
        id: input.id,
        data: new TextEncoder().encode('data: {"type":"done","content":"local"}\n\n'),
      });
    for (const listener of [...listeners]) listener({ id: input.id, done: true });
    return { status: 200, contentType: "text/event-stream" };
  };
  const stream = await request("/api/agents/threads/one/chat", {
    method: "POST",
    responseType: "stream",
    adapter: "fetch",
    data: {},
  });
  assert.match(await new Response(stream).text(), /local/);
  assert.equal(listeners.size, 0);
});
