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

const originals = Object.fromEntries(
  ["window", "localStorage"].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
const created = {
  id: 1,
  owner_id: 12,
  name: "项目资料",
  description: "规范",
  created_at: "2026-10-25T00:00:00Z",
  updated_at: "2026-10-25T00:00:00Z",
};
const stored = (files = []) => ({
  id: "server-1",
  serverId: 1,
  accountId: "user:12",
  name: created.name,
  description: created.description,
  owner: "tester",
  createdAt: created.created_at,
  updatedAt: created.updated_at,
  files,
});
const pageData = (item, page_size = 100, page = 1, total = item.length) => ({
  item,
  total,
  page,
  page_size,
});
beforeEach(() => {
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) =>
        key === "dp-work.auth.token"
          ? "test-token"
          : JSON.stringify([{ id: "demo", name: "旧演示库" }]),
      setItem() {
        throw new Error("No browser cache writes allowed");
      },
    },
  });
  useAuthStore.setState({ user: { id: 12, username: "tester" } });
  resetKnowledgeBases();
});
afterEach(() => {
  mock.restoreAll();
  resetKnowledgeBases();
  useAuthStore.setState({ user: null });
  for (const [key, value] of Object.entries(originals)) {
    if (value) Object.defineProperty(globalThis, key, value);
    else delete globalThis[key];
  }
});

test("creation posts normalized fields with bearer credentials", async () => {
  const transport = mockHttpRequest(async () => Response.json({ code: 0, data: created }));
  const row = await createKnowledgeBaseRequest("user:12", {
    name: " 项目资料 ",
    description: " 规范 ",
  });
  const [url, init] = transport.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases");
  assert.equal(init.method, "POST");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.deepEqual(JSON.parse(init.body), { name: "项目资料", description: "规范" });
  assert.equal(row.serverId, 1);
});
test("successful creation updates memory without requiring browser persistence", async () => {
  useKnowledgeStore.setState({ accountId: "user:12", status: "ready" });
  const transport = mockHttpRequest(async () => Response.json({ code: 0, data: created }));
  const row = await createKnowledgeBase("user:12", { name: "项目资料", description: "规范" });
  assert.equal(transport.mock.callCount(), 1);
  assert.deepEqual(useKnowledgeStore.getState().bases, [row]);
});
test("failed creation never creates a fallback demo record", async () => {
  mockHttpRequest(async () => Response.json({ code: 5000, message: "创建失败" }, { status: 500 }));
  await assert.rejects(
    createKnowledgeBase("user:12", { name: "失败", description: "" }),
    /创建失败/,
  );
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});
test("late responses cannot add a record after switching accounts", async () => {
  mockHttpRequest(async () => {
    useAuthStore.setState({ user: { id: 13, username: "other" } });
    return Response.json({ code: 0, data: created });
  });
  await assert.rejects(
    createKnowledgeBaseRequest("user:12", { name: "项目资料", description: "" }),
    /登录状态已改变/,
  );
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});
test("listing sends search parameters and only returns server records", async () => {
  const transport = mockHttpRequest(async () =>
    Response.json({ code: 0, data: pageData([created], 20) }),
  );
  const page = await listKnowledgeBasesRequest("user:12", " 项目 ");
  const [url, init] = transport.mock.calls[0].arguments;
  assert.equal(new URL(url, "http://test").searchParams.get("q"), "项目");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.deepEqual(
    page.item.map((row) => row.serverId),
    [1],
  );
});
test("refresh keeps same-account in-memory documents without merging local demo bases", async () => {
  const file = { id: "doc", content: "服务端正文" };
  useKnowledgeStore.setState({
    accountId: "user:12",
    bases: [stored([file]), { ...stored(), id: "demo" }],
    status: "ready",
  });
  mockHttpRequest(async () => Response.json({ code: 0, data: pageData([created]) }));
  await loadKnowledgeBases("user:12", true);
  assert.equal(useKnowledgeStore.getState().status, "ready");
  assert.equal(useKnowledgeStore.getState().bases.length, 1);
  assert.deepEqual(useKnowledgeStore.getState().bases[0].files, [file]);
});
test("a failed list shows the error and never reads demo storage", async () => {
  mockHttpRequest(async () => Response.json({ code: 5000, message: "查询失败" }, { status: 500 }));
  await loadKnowledgeBases("user:12");
  assert.equal(useKnowledgeStore.getState().error, "查询失败");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});
test("an empty server catalog stays empty even when old browser demo data exists", async () => {
  mockHttpRequest(async () => Response.json({ code: 0, data: pageData([]) }));
  await loadKnowledgeBases("user:12");
  assert.equal(useKnowledgeStore.getState().status, "ready");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});
test("selectors load later pages rather than truncating the catalog", async () => {
  const first = Array.from({ length: 100 }, (_, i) => ({ ...created, id: i + 1 }));
  const transport = mockHttpRequest(async (url) => {
    const page = Number(new URL(url, "http://test").searchParams.get("page"));
    return Response.json({
      code: 0,
      data: pageData(page === 1 ? first : [{ ...created, id: 101 }], 100, page, 101),
    });
  });
  const rows = await listAllKnowledgeBasesRequest("user:12");
  assert.equal(rows.length, 101);
  assert.equal(transport.mock.callCount(), 2);
});
test("editing uses PUT and preserves same-account memory documents", async () => {
  const file = { id: "doc", content: "保留正文" };
  useKnowledgeStore.setState({ accountId: "user:12", bases: [stored([file])], status: "ready" });
  const transport = mockHttpRequest(async () =>
    Response.json({ code: 0, data: { ...created, name: "新名称", description: "新描述" } }),
  );
  const row = await updateKnowledgeBase("user:12", "server-1", {
    name: " 新名称 ",
    description: " 新描述 ",
  });
  const [url, init] = transport.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1");
  assert.equal(init.method, "PUT");
  assert.deepEqual(JSON.parse(init.body), { name: "新名称", description: "新描述" });
  assert.deepEqual(row.files, [file]);
});
test("successful deletion accepts null and updates memory without browser writes", async () => {
  useKnowledgeStore.setState({ accountId: "user:12", bases: [stored()], status: "ready" });
  const transport = mockHttpRequest(async () => Response.json({ code: 0, data: null }));
  await deleteKnowledgeBase("user:12", "server-1");
  assert.equal(transport.mock.calls[0].arguments[1].method, "DELETE");
  assert.deepEqual(useKnowledgeStore.getState().bases, []);
});
test("failed mutations preserve the existing server-backed record", async () => {
  const row = stored();
  useKnowledgeStore.setState({ accountId: "user:12", bases: [row], status: "ready" });
  mockHttpRequest(async () =>
    Response.json({ code: 1003, message: "知识库不存在" }, { status: 404 }),
  );
  await assert.rejects(
    updateKnowledgeBase("user:12", "server-1", { name: "修改", description: "" }),
    /知识库不存在/,
  );
  await assert.rejects(deleteKnowledgeBase("user:12", "server-1"), /知识库不存在/);
  assert.deepEqual(useKnowledgeStore.getState().bases, [row]);
});
