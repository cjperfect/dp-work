import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  createKnowledgeBaseRequest,
  listKnowledgeBasesRequest,
  listAllKnowledgeBasesRequest,
} from "../../../apis/knowledge.ts";
import {
  createKnowledgeBase,
  loadKnowledgeBases,
  updateKnowledgeBase,
  deleteKnowledgeBase,
  resetKnowledgeBases,
  useKnowledgeStore,
} from "../../../stores/knowledge.ts";
import { listKnowledgeBases } from "../lib/knowledge-repository.ts";

const originals = Object.fromEntries(
  ["window", "sessionStorage", "localStorage"].map((key) => [
    key,
    Object.getOwnPropertyDescriptor(globalThis, key),
  ]),
);
let token;
const created = {
  id: 1,
  owner_id: 12,
  name: "项目资料",
  description: "规范",
  created_at: "2026-10-25T00:00:00Z",
  updated_at: "2026-10-25T00:00:00Z",
};
beforeEach(() => {
  token = "test-token";
  const values = new Map();
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: { getItem: () => token },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? token : (values.get(key) ?? null)),
      setItem: (key, value) => values.set(key, value),
    },
  });
  useAuthStore.setState({ user: { id: 12, username: "tester" } });
  resetKnowledgeBases();
});
afterEach(() => {
  mock.restoreAll();
  resetKnowledgeBases();
  useAuthStore.setState({ user: null });
  for (const key of Object.keys(originals)) {
    if (originals[key]) Object.defineProperty(globalThis, key, originals[key]);
    else delete globalThis[key];
  }
});

test("creation posts only normalized fields with bearer credentials", async () => {
  const fetch = mockHttpRequest(async () =>
    Response.json({ code: 0, data: created }, { status: 200 }),
  );
  const record = await createKnowledgeBaseRequest("user:12", {
    name: " 项目资料 ",
    description: " 规范 ",
  });
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases");
  assert.equal(init.method, "POST");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.deepEqual(JSON.parse(init.body), { name: "项目资料", description: "规范" });
  assert.equal(record.serverId, 1);
  assert.equal(record.owner, "tester");
});

test("the new dialog's store uses the API and preserves local demo entries on ID collisions", async () => {
  const original = await listKnowledgeBases("user:12");
  useKnowledgeStore.setState({ accountId: "user:12", bases: original, status: "ready" });
  const fetch = mockHttpRequest(async () =>
    Response.json({ code: 0, data: created }, { status: 200 }),
  );
  const record = await createKnowledgeBase("user:12", { name: "项目资料", description: "规范" });
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(
    useKnowledgeStore.getState().bases.find((base) => base.id === record.id).serverId,
    1,
  );
  const reloaded = await listKnowledgeBases("user:12");
  assert.equal(reloaded.length, original.length + 1);
  assert.equal(reloaded.find((row) => row.id === record.id).name, "项目资料");
});

test("failed requests do not create a fallback mock knowledge base", async () => {
  const original = await listKnowledgeBases("user:12");
  mockHttpRequest(async () =>
    Response.json({ code: 5000, message: "服务器内部错误" }, { status: 500 }),
  );
  await assert.rejects(
    createKnowledgeBase("user:12", { name: "失败的资料库", description: "" }),
    /服务器内部错误/,
  );
  assert.deepEqual(await listKnowledgeBases("user:12"), original);
});

test("late responses cannot add a record after switching accounts", async () => {
  mockHttpRequest(async () => {
    useAuthStore.setState({ user: { id: 13, username: "other" } });
    return Response.json({ code: 0, data: created }, { status: 200 });
  });
  await assert.rejects(
    createKnowledgeBaseRequest("user:12", { name: "项目资料", description: "" }),
    /登录状态已改变/,
  );
});

test("listing sends the search query and authenticates the request", async () => {
  const fetch = mockHttpRequest(async () =>
    Response.json({ code: 0, data: pageData([created], 20) }),
  );
  const records = await listKnowledgeBasesRequest("user:12", " 项目 ");
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(new URL(url, "http://test").searchParams.get("q"), "项目");
  assert.equal(init.method, "GET");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.deepEqual(
    records.item.map((record) => record.serverId),
    [1],
  );
});

test("the list store uses server records and retains local documents on refresh", async () => {
  const { cacheCreatedKnowledgeBase } = await import("../lib/knowledge-repository.ts");
  const record = {
    ...(await listKnowledgeBases("user:12"))[0],
    id: "server-1",
    serverId: 1,
    files: [{ id: "draft-1", name: "草稿.md", type: "md", source: "editor", content: "正文" }],
  };
  cacheCreatedKnowledgeBase("user:12", record);
  mockHttpRequest(async () => Response.json({ code: 0, data: pageData([created]) }));
  await loadKnowledgeBases("user:12");
  const state = useKnowledgeStore.getState();
  assert.equal(state.status, "ready");
  assert.equal(state.bases.length, 1);
  assert.equal(state.bases[0].name, created.name);
  assert.equal(state.bases[0].files[0].content, "正文");
});

test("a failed list request shows an error without falling back to demo records", async () => {
  mockHttpRequest(async () => Response.json({ code: 5000, message: "查询失败" }, { status: 500 }));
  await loadKnowledgeBases("user:12");
  assert.equal(useKnowledgeStore.getState().status, "error");
  assert.equal(useKnowledgeStore.getState().error, "查询失败");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});

function pageData(items, pageSize = 100, page = 1, total = items.length) {
  return { item: items, total, page, page_size: pageSize };
}

test("knowledge selectors load later pages instead of truncating the catalog", async () => {
  const first = Array.from({ length: 100 }, (_, index) => ({ ...created, id: index + 1 }));
  const fetch = mockHttpRequest(async (url) => {
    const page = Number(new URL(url, "http://test").searchParams.get("page"));
    return Response.json({
      code: 0,
      data: pageData(page === 1 ? first : [{ ...created, id: 101 }], 100, page, 101),
    });
  });
  const records = await listAllKnowledgeBasesRequest("user:12");
  assert.equal(records.length, 101);
  assert.equal(records[100].serverId, 101);
  assert.equal(fetch.mock.callCount(), 2);
});

test("editing persists through PUT and preserves local document content", async () => {
  const { cacheCreatedKnowledgeBase } = await import("../lib/knowledge-repository.ts");
  cacheCreatedKnowledgeBase("user:12", {
    ...(await listKnowledgeBases("user:12"))[0],
    id: "server-1",
    serverId: 1,
    files: [{ id: "draft", content: "保留正文" }],
  });
  const fetch = mockHttpRequest(async () =>
    Response.json({ code: 0, data: { ...created, name: "新名称", description: "新描述" } }),
  );
  const updated = await updateKnowledgeBase("user:12", "server-1", {
    name: " 新名称 ",
    description: " 新描述 ",
  });
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1");
  assert.equal(init.method, "PUT");
  assert.deepEqual(JSON.parse(init.body), { name: "新名称", description: "新描述" });
  assert.equal(updated.files[0].content, "保留正文");
  assert.equal(
    (await listKnowledgeBases("user:12")).find((row) => row.id === "server-1").name,
    "新名称",
  );
});

test("deleting accepts the successful null response and removes the local record", async () => {
  const { cacheCreatedKnowledgeBase } = await import("../lib/knowledge-repository.ts");
  const record = { ...(await listKnowledgeBases("user:12"))[0], id: "server-1", serverId: 1 };
  cacheCreatedKnowledgeBase("user:12", record);
  useKnowledgeStore.setState({ accountId: "user:12", bases: [record], status: "ready" });
  const fetch = mockHttpRequest(async () => Response.json({ code: 0, data: null }));
  await deleteKnowledgeBase("user:12", "server-1");
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/knowledge-bases/1");
  assert.equal(fetch.mock.calls[0].arguments[1].method, "DELETE");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
  assert.equal(
    (await listKnowledgeBases("user:12")).some((row) => row.id === "server-1"),
    false,
  );
});

test("failed mutations keep existing local data and surface the server error", async () => {
  const { cacheCreatedKnowledgeBase } = await import("../lib/knowledge-repository.ts");
  cacheCreatedKnowledgeBase("user:12", {
    ...(await listKnowledgeBases("user:12"))[0],
    id: "server-1",
    serverId: 1,
  });
  const original = await listKnowledgeBases("user:12");
  mockHttpRequest(async () =>
    Response.json({ code: 1003, message: "知识库不存在" }, { status: 404 }),
  );
  await assert.rejects(
    updateKnowledgeBase("user:12", "server-1", { name: "修改", description: "" }),
    /知识库不存在/,
  );
  await assert.rejects(deleteKnowledgeBase("user:12", "server-1"), /知识库不存在/);
  assert.deepEqual(await listKnowledgeBases("user:12"), original);
});
