import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  createKnowledgeBaseRequest as createKnowledgeBase,
  deleteKnowledgeBaseRequest as deleteKnowledgeBase,
  listAllKnowledgeBasesRequest as listKnowledgeBases,
  updateKnowledgeBaseRequest as updateKnowledgeBase,
} from "../../../apis/knowledge.ts";
import {
  createKnowledgeBase as createInStore,
  loadKnowledgeBases,
  resetKnowledgeBases,
  useKnowledgeStore,
} from "../../../stores/knowledge/index.ts";

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
let token;
const first = {
  id: 11,
  owner_id: 1,
  name: "Project",
  description: "Notes",
  created_at: "2026-10-24T01:00:00Z",
  updated_at: "2026-10-24T01:00:00Z",
};
function signIn(id = 1) {
  token = `token-${id}`;
  useAuthStore.setState({
    user: { id, username: id === 1 ? "Alice" : "Bob", role: "member", status: 0 },
  });
}
function ok(data) {
  return Response.json({
    code: 0,
    message: "ok",
    data: Array.isArray(data) ? { item: data, total: data.length, page: 1, page_size: 100 } : data,
  });
}
function failure(status, message) {
  return Response.json({ code: 1003, message, data: null }, { status });
}
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  const storage = new Map();
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? token : (storage.get(key) ?? null)),
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
  });
  resetKnowledgeBases();
  signIn();
});
afterEach(() => {
  mock.restoreAll();
  resetKnowledgeBases();
  useAuthStore.setState({ user: null });
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("list reads the API with bearer credentials and maps server fields to the UI", async () => {
  const fetch = mockHttpRequest(async () => ok([first]));
  const [base] = await listKnowledgeBases("user:1");
  assert.deepEqual(base, {
    id: "server-11",
    serverId: 11,
    accountId: "user:1",
    name: "Project",
    description: "Notes",
    owner: "Alice",
    files: [],
    documentCount: 0,
    createdAt: first.created_at,
    updatedAt: first.updated_at,
  });
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases?page=1&page_size=100");
  assert.equal(init.headers.Authorization, "Bearer token-1");
  assert.equal(init.method, "GET");
});

test("creation sends trimmed fields and uses only server-generated identity and timestamps", async () => {
  const fetch = mockHttpRequest(async () => ok(first));
  const created = await createKnowledgeBase("user:1", {
    name: " Project ",
    description: " Notes ",
  });
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases");
  assert.equal(init.method, "POST");
  assert.deepEqual(JSON.parse(init.body), { name: "Project", description: "Notes" });
  assert.equal(created.id, "server-11");
  assert.equal(created.createdAt, first.created_at);
});

test("edit uses PUT and displays the committed server response", async () => {
  const fetch = mockHttpRequest(async () =>
    ok({ ...first, name: "Renamed", updated_at: "2026-10-24T02:00:00Z" }),
  );
  const updated = await updateKnowledgeBase("user:1", "server-11", {
    name: "Renamed",
    description: "Notes",
  });
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/knowledge-bases/11");
  assert.equal(fetch.mock.calls[0].arguments[1].method, "PUT");
  assert.equal(updated.name, "Renamed");
  assert.equal(updated.updatedAt, "2026-10-24T02:00:00Z");
});

test("deletion uses DELETE and missing or inaccessible resources preserve the server message", async () => {
  const fetch = mockHttpRequest(async () => ok({ id: 11 }));
  await deleteKnowledgeBase("user:1", "server-11");
  assert.equal(fetch.mock.calls[0].arguments[1].method, "DELETE");
  fetch.mock.mockImplementation(async () => failure(404, "知识库不存在或无权访问"));
  await assert.rejects(deleteKnowledgeBase("user:1", "server-11"), /不存在或无权访问/);
});

test("blank names, missing sessions and stale account requests do not reach the API", async () => {
  const fetch = mockHttpRequest(async () => ok([]));
  await assert.rejects(createKnowledgeBase("user:1", { name: "  ", description: "" }), /请输入/);
  await assert.rejects(listKnowledgeBases("user:2"), /登录/);
  token = null;
  await assert.rejects(listKnowledgeBases("user:1"), /登录/);
  assert.equal(fetch.mock.callCount(), 0);
});

test("failed saves do not insert phantom cards; retry succeeds after recovery", async () => {
  const fetch = mockHttpRequest(async () => ok([]));
  await loadKnowledgeBases("user:1");
  fetch.mock.mockImplementation(async () => failure(500, "数据库暂时不可用"));
  await assert.rejects(
    createInStore("user:1", { name: "Project", description: "" }),
    /数据库暂时不可用/,
  );
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
  fetch.mock.mockImplementation(async () => ok(first));
  await createInStore("user:1", { name: "Project", description: "" });
  assert.equal(useKnowledgeStore.getState().bases[0].id, "server-11");
});

test("network failures, non-JSON responses and expired sessions report recoverable errors", async () => {
  const fetch = mockHttpRequest(async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(listKnowledgeBases("user:1"), /暂时无法连接/);
  fetch.mock.mockImplementation(async () => new Response("Bad gateway", { status: 502 }));
  await assert.rejects(listKnowledgeBases("user:1"), /暂时不可用/);
  fetch.mock.mockImplementation(async () => failure(401, "expired"));
  await assert.rejects(listKnowledgeBases("user:1"), /重新登录/);
});

test("refresh reloads server data and clears cached rows from another account", async () => {
  const fetch = mockHttpRequest(async () => ok([first]));
  await loadKnowledgeBases("user:1");
  fetch.mock.mockImplementation(async () => ok([{ ...first, name: "Changed on another device" }]));
  await loadKnowledgeBases("user:1", true);
  assert.equal(useKnowledgeStore.getState().bases[0].name, "Changed on another device");
  signIn(2);
  fetch.mock.mockImplementation(async () => ok([]));
  await loadKnowledgeBases("user:2");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});

test("a response started by the old account cannot overwrite a newly loaded account", async () => {
  const old = deferred();
  const fetch = mockHttpRequest(() => old.promise);
  const loading = loadKnowledgeBases("user:1");
  signIn(2);
  fetch.mock.mockImplementation(async () =>
    ok([{ ...first, id: 12, owner_id: 2, name: "Bob's base" }]),
  );
  await loadKnowledgeBases("user:2");
  old.resolve(ok([first]));
  await loading;
  assert.equal(useKnowledgeStore.getState().accountId, "user:2");
  assert.equal(useKnowledgeStore.getState().bases[0].owner, "Bob");
  assert.equal(useKnowledgeStore.getState().error, null);
});

test("an older list response cannot erase a newer successful creation", async () => {
  mockHttpRequest(async () => ok([]));
  await loadKnowledgeBases("user:1");
  const old = deferred();
  mockHttpRequest((url, init) =>
    init.method === "POST" ? Promise.resolve(ok(first)) : old.promise,
  );
  const loading = loadKnowledgeBases("user:1", true);
  await createInStore("user:1", { name: "Project", description: "" });
  old.resolve(ok([]));
  await loading;
  assert.equal(useKnowledgeStore.getState().bases[0].id, "server-11");
});
