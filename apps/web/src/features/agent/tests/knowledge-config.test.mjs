import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { resetAgents, useAgentStore } from "../../../stores/agent/state.ts";
import { loadAgents, saveAgent } from "../../../stores/agent/agent-config.ts";
import { conversationFixture } from "./conversation-fixture.mjs";

let interceptor, storageDescriptor, values, failWrite, failImport;
const key = "dp-work:mock:v1:agent-config:55";
beforeEach(() => {
  storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  });
  const fixture = conversationFixture();
  failWrite = failImport = false;
  interceptor = httpClient.interceptors.request.use((request) => {
    request.adapter = async (config) => {
      const failed =
        config.url === "/api/agents/knowledge" &&
        ((failWrite && config.method === "put") || (failImport && config.method === "post"));
      return {
        status: failed ? 500 : 200,
        statusText: "",
        headers: {},
        config,
        data: failed
          ? { message: "本地保存失败" }
          : await fixture.handle(config, () => ({ code: 0, data: [] })),
      };
    };
    return request;
  });
  resetAgents();
  useAuthStore.setState({ user: { id: 55, username: "fixture" } });
});
afterEach(() => {
  httpClient.interceptors.request.eject(interceptor);
  resetAgents();
  useAuthStore.setState({ user: null });
  if (storageDescriptor) Object.defineProperty(globalThis, "localStorage", storageDescriptor);
  else delete globalThis.localStorage;
});

test("migrates legacy IDs, removes browser copy and restores SQLite selection after reload", async () => {
  values.set(
    key,
    JSON.stringify({
      agents: [{ code: "general", knowledge_base_ids: ["server-13", 1, "server-13"] }],
    }),
  );
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().agents[0].knowledge_base_ids, [
    "server-13",
    "server-1",
  ]);
  assert.equal(JSON.parse(values.get(key)).agents[0].knowledge_base_ids, undefined);
  resetAgents();
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().agents[0].knowledge_base_ids, [
    "server-13",
    "server-1",
  ]);
  const agent = useAgentStore.getState().agents[0];
  await saveAgent("general", { ...agent, knowledge_base_ids: [] });
  values.set(
    key,
    JSON.stringify({ agents: [{ code: "general", knowledge_base_ids: ["server-13"] }] }),
  );
  resetAgents();
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().agents[0].knowledge_base_ids, []);
});

test("migration failure preserves legacy selection for retry", async () => {
  const original = JSON.stringify({
    agents: [{ code: "general", knowledge_base_ids: ["server-13"] }],
  });
  values.set(key, original);
  failImport = true;
  await assert.rejects(loadAgents(), /本地保存失败/);
  assert.equal(values.get(key), original);
});

test("failed save keeps existing selection in UI and database", async () => {
  await loadAgents();
  const agent = useAgentStore.getState().agents[0];
  await saveAgent("general", { ...agent, knowledge_base_ids: ["server-13"] });
  failWrite = true;
  await assert.rejects(saveAgent("general", { ...agent, knowledge_base_ids: [] }), /本地保存失败/);
  assert.deepEqual(useAgentStore.getState().agents[0].knowledge_base_ids, ["server-13"]);
  failWrite = false;
  resetAgents();
  await loadAgents();
  assert.deepEqual(useAgentStore.getState().agents[0].knowledge_base_ids, ["server-13"]);
});
