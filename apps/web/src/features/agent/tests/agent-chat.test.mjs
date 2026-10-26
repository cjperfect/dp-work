import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { streamAgentChat } from "../../../apis/agents.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { ensureAgentChat, sendMessage, useAgentStore, resetAgents } from "../../../stores/agent.ts";

let interceptor;
let handler;
let originalStorage;
const input = {
  agent_code: "general",
  thread_id: "one",
  messages: [{ role: "user", content: "你好" }],
};
const event = (value) => `data: ${JSON.stringify(value)}\n\n`;
function response(events) {
  const bytes = new TextEncoder().encode(events);
  return new ReadableStream({
    start(controller) {
      // 每个字节一个分片，覆盖中文 UTF-8 和 SSE 分隔符被拆开的情况。
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
}
beforeEach(() => {
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "fixture-token" : null),
      setItem() {},
    },
  });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
  resetAgents();
  handler = async () =>
    response(
      event({ type: "delta", text: "真实链路的测试回答" }) +
        event({ type: "done", content: "真实链路的测试回答" }),
    );
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => ({
      data: await handler(request),
      status: 200,
      statusText: "OK",
      config: request,
      headers: {},
    });
    return config;
  });
});
afterEach(() => {
  httpClient.interceptors.request.eject(interceptor);
  resetAgents();
  useAuthStore.setState({ user: null });
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});
test("stream decodes fragmented UTF-8 and requires a completion event", async () => {
  const deltas = [];
  assert.equal(
    await streamAgentChat(input, (text) => deltas.push(text), new AbortController().signal),
    "真实链路的测试回答",
  );
  assert.equal(deltas.join(""), "真实链路的测试回答");
  handler = async () => response(event({ type: "delta", text: "partial" }));
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /中断/,
  );
});
test("server errors preserve safe messages and old-account responses are rejected", async () => {
  handler = async () => response(event({ type: "error", message: "模型请求受限，请稍后重试。" }));
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /请求受限/,
  );
  handler = async () => {
    useAuthStore.setState({ user: { id: 2 } });
    return response(event({ type: "done", content: "old account" }));
  };
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /登录状态已改变/,
  );
});
test("chat store forwards real history and keeps streamed replies without mock text", async () => {
  const requests = [];
  handler = async (config) => {
    requests.push(JSON.parse(config.data));
    return response(
      event({ type: "delta", text: "回复" }) + event({ type: "done", content: "回复" }),
    );
  };
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "第一问");
  await sendMessage("general", id, "第二问");
  assert.equal(requests[1].messages.length, 3);
  assert.deepEqual(
    requests[1].messages.map((row) => row.role),
    ["user", "assistant", "user"],
  );
  const messages = useAgentStore.getState().details[id].messages;
  assert.equal(messages.length, 4);
  assert.equal(messages.at(-1).content, "回复");
  assert.equal(messages.at(-1).status, "complete");
  assert.equal(useAgentStore.getState().drafts[id].sending, false);
});
test("failed runs can retry without duplicating the user message", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  handler = async () =>
    response(
      event({ type: "delta", text: "partial" }) +
        event({ type: "error", message: "temporary failure" }),
    );
  await assert.rejects(sendMessage("general", id, "重试同一问题"), /temporary failure/);
  assert.equal(useAgentStore.getState().details[id].messages.at(-1).status, "failed");
  handler = async () => response(event({ type: "done", content: "成功回答" }));
  await sendMessage("general", id, "重试同一问题");
  assert.equal(useAgentStore.getState().details[id].messages.length, 2);
  assert.equal(useAgentStore.getState().details[id].messages.at(-1).content, "成功回答");
});
