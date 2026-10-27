import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  ensureAgentChat,
  useAgentStore,
  resetAgents,
  setDraftText,
  flushDraft,
  removeThread,
  sendMessage,
} from "../../../stores/agent.ts";
import { conversationFixture } from "./conversation-fixture.mjs";

let interceptor, originalStorage, backend, values, fail, calls;
beforeEach(() => {
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) =>
        key === "dp-work.auth.token" ? "fixture-token" : (values.get(key) ?? null),
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  });
  backend = conversationFixture();
  calls = [];
  fail = () => false;
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => {
      calls.push(request);
      if (fail(request)) throw new Error("暂时无法连接服务");
      const data = await backend.handle(
        request,
        async () =>
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                new TextEncoder().encode('data: {"type":"done","content":"数据库里的回答"}\n\n'),
              );
              controller.close();
            },
          }),
      );
      return { data, status: 200, statusText: "OK", config: request, headers: {} };
    };
    return config;
  });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
  resetAgents();
});
afterEach(() => {
  resetAgents();
  httpClient.interceptors.request.eject(interceptor);
  useAuthStore.setState({ user: null });
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("messages use API persistence and never get written to localStorage", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "这段消息只存数据库");
  assert.equal(backend.details.get(id).messages[0].content, "这段消息只存数据库");
  assert.ok(![...values.values()].some((value) => value.includes("这段消息只存数据库")));
  resetAgents();
  await ensureAgentChat("general");
  assert.equal(useAgentStore.getState().details[id].messages[1].content, "数据库里的回答");
  fail = (request) => request.method === "delete";
  await assert.rejects(removeThread("general", id));
  assert.ok(useAgentStore.getState().details[id]);
  fail = () => false;
  await removeThread("general", id);
  assert.ok(!backend.details.has(id));
  assert.ok(!useAgentStore.getState().details[id]);
});

test("failed draft saves remain unsaved and can retry", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  setDraftText(id, "未保存草稿");
  fail = (request) => request.url.endsWith("/draft");
  await assert.rejects(flushDraft("general", id));
  assert.equal(useAgentStore.getState().drafts[id].savedVersion, 0);
  assert.equal(backend.details.get(id).thread.draft, "");
  fail = () => false;
  await flushDraft("general", id);
  assert.equal(backend.details.get(id).thread.draft, "未保存草稿");
});

test("legacy migration keeps the source on failure and removes it only after success", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "旧设备消息");
  const legacy = structuredClone(useAgentStore.getState());
  const key = "dp-work:mock:v1:agents:1";
  values.set(key, JSON.stringify(legacy));
  backend.details.clear();
  resetAgents();
  fail = (request) => request.url.endsWith("/import");
  await assert.rejects(ensureAgentChat("general"));
  assert.ok(values.has(key));
  assert.equal(backend.details.size, 0);
  assert.equal(Object.keys(useAgentStore.getState().details).length, 0);
  fail = () => false;
  await ensureAgentChat("general", true);
  assert.ok(!values.has(key));
  assert.equal(useAgentStore.getState().details[id].messages[0].content, "旧设备消息");
  assert.equal(calls.filter((request) => request.url.endsWith("/import")).length, 2);
});
