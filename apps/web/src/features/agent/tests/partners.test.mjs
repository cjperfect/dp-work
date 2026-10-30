import assert from "node:assert/strict";
import { test, beforeEach, afterEach } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  loadAgents,
  addPartner,
  removePartner,
  isAgentAdded,
} from "../../../stores/agent/agent-config.ts";
import { createThread } from "../../../stores/agent/agent-threads.ts";
import { resetAgents, useAgentStore } from "../../../stores/agent/state.ts";
import { agentPath } from "@/constants/agents";
let storage, windowDescriptor, interceptor, values, creates, rows;
beforeEach(() => {
  storage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  values = new Map();
  creates = 0;
  rows = [];
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "fixture" : (values.get(key) ?? null)),
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { desktop: { ensureAgentWorkspace: async () => {} } },
  });
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => {
      if (request.method === "post") creates++;
      return { data: { code: 0, data: rows }, status: 200, headers: {}, config: request };
    };
    return config;
  });
  useAuthStore.setState({ user: { id: 71, username: "first" } });
  resetAgents();
});
afterEach(() => {
  httpClient.interceptors.request.eject(interceptor);
  resetAgents();
  useAuthStore.setState({ user: null });
  if (storage) Object.defineProperty(globalThis, "localStorage", storage);
  else delete globalThis.localStorage;
  if (windowDescriptor) Object.defineProperty(globalThis, "window", windowDescriptor);
  else delete globalThis.window;
});
test("new accounts get only general and partner addition is idempotent without creating history", async () => {
  await loadAgents();
  assert.ok(isAgentAdded("general"));
  assert.equal(isAgentAdded("product"), false);
  assert.equal(isAgentAdded("ui"), false);
  assert.throws(() => createThread("ui"), /伙伴/);
  await addPartner("ui");
  await addPartner("ui");
  assert.deepEqual(useAgentStore.getState().partnerCodes, ["ui"]);
  assert.equal(creates, 0);
  assert.equal(agentPath("ui"), "/ui");
  assert.equal(useAgentStore.getState().agents.find((a) => a.code === "ui").id, 3);
});
test("added partners survive reload and remain isolated between accounts", async () => {
  await addPartner("product");
  await addPartner("ui");
  resetAgents();
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().partnerCodes, ["product", "ui"]);
  useAuthStore.setState({ user: { id: 72, username: "second" } });
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().partnerCodes, []);
  assert.ok(isAgentAdded("general"));
  useAuthStore.setState({ user: { id: 71, username: "first" } });
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().partnerCodes, ["product", "ui"]);
});
test("a failed local preference write does not report a partner as added", async () => {
  await loadAgents();
  localStorage.setItem = () => {
    throw new Error("storage full");
  };
  await assert.rejects(addPartner("ui"), /storage full/);
  assert.equal(isAgentAdded("ui"), false);
});
test("cancelled partners remain cancelled after reload despite existing history and can be added again", async () => {
  await addPartner("ui");
  rows = [{ id: "ui-history", agent_id: 3, title: "已有会话" }];
  const originalAgent = useAgentStore.getState().agents.find((agent) => agent.code === "ui");
  await removePartner("ui");
  await removePartner("ui");
  assert.equal(isAgentAdded("ui"), false);
  resetAgents();
  await loadAgents();
  assert.equal(isAgentAdded("ui"), false);
  assert.deepEqual(useAgentStore.getState().lists.ui, rows);
  assert.deepEqual(
    useAgentStore.getState().agents.find((agent) => agent.code === "ui"),
    originalAgent,
  );
  await addPartner("ui");
  assert.equal(isAgentAdded("ui"), true);
  assert.equal(creates, 0);
  await assert.rejects(removePartner("general"), /不能取消/);
});
test("a failed cancellation write keeps the partner added", async () => {
  await addPartner("product");
  localStorage.setItem = () => {
    throw new Error("storage full");
  };
  await assert.rejects(removePartner("product"), /storage full/);
  assert.equal(isAgentAdded("product"), true);
});

test("adding a partner initializes AGENT.md via Sidecar even before its first chat", async () => {
  const calls = [];
  const capture = httpClient.interceptors.request.use((config) => {
    calls.push({ url: config.url, params: config.params });
    return config;
  });
  try {
    await addPartner("ui");
    assert.ok(
      calls.some((call) => call.url === "/api/agents/config" && call.params.agent_code === "ui"),
    );
    assert.equal(creates, 0);
  } finally {
    httpClient.interceptors.request.eject(capture);
  }
});

test("a failed workspace initialization does not report a partner as added", async () => {
  await loadAgents();
  const failure = httpClient.interceptors.response.use((response) => {
    if (response.config.url === "/api/agents/config") throw new Error("初始化失败");
    return response;
  });
  try {
    await assert.rejects(addPartner("ui"), /初始化失败/);
    assert.equal(isAgentAdded("ui"), false);
    assert.equal(creates, 0);
  } finally {
    httpClient.interceptors.response.eject(failure);
  }
});
