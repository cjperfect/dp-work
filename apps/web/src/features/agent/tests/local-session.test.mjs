import { saveComposerDraft as setDraftText } from "../../../stores/agent/agent-message-queue.ts";
import { useAgentMessageQueue } from "../../../stores/agent/agent-message-queue.ts";
import { ensureTestChat as ensureAgentChat } from "./conversation-fixture.mjs";
import { conversationFixture } from "./conversation-fixture.mjs";
import assert from "node:assert/strict";
import { httpClient } from "../../../lib/http.ts";
import { afterEach, beforeEach, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  createThread,
  getThreadAgentCode,
  selectThreadById,
  loadThreads,
  selectThread,
  ensureAgentChat as initializeAgent,
} from "../../../stores/agent/agent-threads.ts";
import { resetAgents, useAgentStore } from "../../../stores/agent/state.ts";
import { sendMessage } from "../../../stores/agent/agent-send.ts";

let streamInterceptor, created;
beforeEach(() => {
  const backend = conversationFixture();
  created = 0;
  streamInterceptor = httpClient.interceptors.request.use((config) => {
    if (config.url === "/api/agents/threads" && config.method === "post") created++;
    config.adapter = async (request) => ({
      data: await backend.handle(
        request,
        async () =>
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                new TextEncoder().encode('data: {"type":"done","content":"测试回答"}\n\n'),
              );
              controller.close();
            },
          }),
      ),
      status: 200,
      statusText: "OK",
      config: request,
      headers: {},
    });
    return config;
  });
  useAuthStore.setState({ user: { id: 123, username: "tester" } });
  resetAgents();
});

test("opening Agents creates no conversation and the first complete reply makes history visible", async () => {
  await initializeAgent("general");
  await initializeAgent("product");
  assert.equal(created, 0);
  assert.equal(useAgentStore.getState().selected.general, undefined);
  assert.equal(useAgentStore.getState().selected.product, undefined);
  const id = await createThread("general");
  assert.equal(created, 1);
  assert.equal(useAgentStore.getState().details[id].thread.has_history, false);
  await sendMessage("general", id, "第一条消息");
  assert.equal(useAgentStore.getState().details[id].thread.has_history, true);
});

test("Agent replies and conversation selection survive reinitializing the page", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
  });
  try {
    await ensureAgentChat("general");
    const id = useAgentStore.getState().selected.general;
    await sendMessage("general", id, "保存这段对话");
    assert.equal(useAgentStore.getState().details[id].messages.length, 2);
    resetAgents();
    await ensureAgentChat("general");
    const restored = useAgentStore.getState();
    assert.equal(restored.selected.general, id);
    assert.equal(restored.details[id].messages[0].content, "保存这段对话");
    assert.equal(restored.details[id].messages[1].role, "assistant");
  } finally {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else delete globalThis.localStorage;
  }
});
afterEach(() => {
  httpClient.interceptors.request.eject(streamInterceptor);
  resetAgents();
  useAuthStore.setState({ user: null });
});

test("repeated page mounts retain the active conversation without store updates", async () => {
  await ensureAgentChat("general");
  const initial = useAgentStore.getState();
  const id = initial.selected.general;
  assert.ok(id);
  assert.equal(initial.details[id].thread.agent_id, initial.agents[0].id);
  let updates = 0;
  const unsubscribe = useAgentStore.subscribe(() => updates++);
  try {
    for (let i = 0; i < 10; i++) await ensureAgentChat("general");
    assert.equal(useAgentStore.getState().selected.general, id);
    assert.equal((await loadThreads("general")).length, 1);
    assert.equal(updates, 0);
  } finally {
    unsubscribe();
  }
});

test("switching conversations and Agents preserves drafts and isolates their lists", async () => {
  await ensureAgentChat("general");
  const first = useAgentStore.getState().selected.general;
  setDraftText(first, "保留这段草稿");
  const second = await createThread("general");
  assert.notEqual(first, second);
  await selectThread("general", first);
  await ensureAgentChat("product");
  await ensureAgentChat("general");
  const state = useAgentStore.getState();
  assert.equal(state.selected.general, first);
  assert.equal(useAgentMessageQueue.getState().drafts[first], "保留这段草稿");
  assert.equal(state.lists.general.length, 2);
  assert.equal(state.lists.product.length, 1);
  await assert.rejects(selectThread("product", first), /会话不存在/);
});

test("a history item selects its own Agent without a previously selected conversation", async () => {
  await ensureAgentChat("general");
  const generalId = useAgentStore.getState().selected.general;
  await ensureAgentChat("product");
  const productId = useAgentStore.getState().selected.product;
  setDraftText(generalId, "通用会话草稿");
  useAgentStore.setState({ selected: {} });
  assert.equal(getThreadAgentCode(productId), "product");
  assert.equal(await selectThreadById(productId), "product");
  assert.equal(useAgentStore.getState().selected.product, productId);
  assert.equal(await selectThreadById(generalId), "general");
  assert.equal(useAgentStore.getState().selected.general, generalId);
  assert.equal(useAgentMessageQueue.getState().drafts[generalId], "通用会话草稿");
  await assert.rejects(selectThreadById("missing"), /会话不存在/);
  useAuthStore.setState({ user: { id: 999, username: "another" } });
  assert.equal(getThreadAgentCode(generalId), undefined);
  await assert.rejects(selectThreadById(generalId), /会话不存在/);
});

test("logged-out page initialization does not create a session or report a retry error", async () => {
  useAuthStore.setState({ user: null });
  await ensureAgentChat("general");
  await ensureAgentChat("general", true);
  assert.equal(useAgentStore.getState().owner, null);
  assert.deepEqual(useAgentStore.getState().selected, {});
});

test("sign-out during initialization discards the old task and a new login can reload", async () => {
  const previous = ensureAgentChat("general");
  useAuthStore.setState({ user: null });
  resetAgents();
  await previous;
  assert.deepEqual(useAgentStore.getState().selected, {});
  useAuthStore.setState({ user: { id: 456, username: "new-user" } });
  await ensureAgentChat("general", true);
  const current = useAgentStore.getState();
  assert.equal(current.owner, 456);
  assert.ok(current.selected.general);
});
