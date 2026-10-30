import { saveComposerDraft as setDraftText } from "../../../stores/agent/agent-message-queue.ts";
import { useAgentMessageQueue } from "../../../stores/agent/agent-message-queue.ts";
import { ensureTestChat as ensureAgentChat } from "./conversation-fixture.mjs";
import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { useAgentStore, resetAgents } from "../../../stores/agent/state.ts";
import { removeThread, createThread } from "../../../stores/agent/agent-threads.ts";
import { sendMessage } from "../../../stores/agent/agent-send.ts";
import { addPartner } from "../../../stores/agent/agent-config.ts";
import { changeThreadProject } from "../../../stores/agent/agent-files.ts";
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

test("project conversations keep their directory and stay in global history after reload", async () => {
  await ensureAgentChat("general");
  const project = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const projectThread = await createThread("general", project);
  await addPartner("product");
  const otherThread = await createThread("product");
  assert.equal(backend.details.get(projectThread).thread.project_id, project);
  setDraftText(projectThread, "项目草稿");
  await changeThreadProject(projectThread, null);
  assert.equal(useAgentMessageQueue.getState().drafts[projectThread], "项目草稿");
  assert.equal(backend.details.get(projectThread).thread.draft, "");
  assert.equal(backend.details.get(projectThread).thread.project_id, null);
  await changeThreadProject(projectThread, project);
  await sendMessage("general", projectThread, "项目对话");
  await sendMessage("product", otherThread, "产品对话");
  resetAgents();
  await ensureAgentChat("general");
  const history = Object.values(useAgentStore.getState().lists).flat();
  assert.ok(history.some((row) => row.id === projectThread && row.project_id === project));
  assert.ok(history.some((row) => row.id === otherThread && !row.project_id));
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

test("composer drafts remain local and do not overwrite stored conversation content", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  setDraftText(id, "本机草稿");
  assert.equal(useAgentMessageQueue.getState().drafts[id], "本机草稿");
  assert.equal(backend.details.get(id).thread.draft, "");
  setDraftText(id, "继续编辑的草稿");
  assert.equal(useAgentMessageQueue.getState().drafts[id], "继续编辑的草稿");
  assert.equal(backend.details.get(id).thread.draft, "");
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
