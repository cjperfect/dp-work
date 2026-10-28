import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { loadApprovals, useAgentApprovalStore } from "../../../stores/agent-approvals.ts";

let originalStorage, originalWindow, interceptor;
let handler;
beforeEach(() => {
  originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "fixture-token" : null),
      setItem() {},
    },
  });
  useAuthStore.setState({ user: { id: 1, username: "fixture" } });
  useAgentApprovalStore.setState({ entries: {} });
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => ({
      data: { code: 0, data: await handler(request) },
      status: 200,
      statusText: "OK",
      headers: {},
      config: request,
    });
    return config;
  });
});
afterEach(() => {
  httpClient.interceptors.request.eject(interceptor);
  useAuthStore.setState({ user: null });
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("approvals deduplicate reads and isolate conversations", async () => {
  let calls = 0;
  handler = async (config) => {
    calls++;
    return [{ id: config.params.conversation_id }];
  };
  await Promise.all([loadApprovals("one"), loadApprovals("one")]);
  assert.equal(calls, 1, JSON.stringify(useAgentApprovalStore.getState().entries));
  await loadApprovals("two");
  assert.equal(useAgentApprovalStore.getState().entries.one.items[0].id, "one");
  assert.equal(useAgentApprovalStore.getState().entries.two.items[0].id, "two");
});

test("late approval responses cannot enter the next account", async () => {
  let finish;
  handler = async () =>
    new Promise((resolve) => {
      finish = () => resolve([{ id: "private" }]);
    });
  const loading = loadApprovals("one");
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
  useAuthStore.setState({ user: { id: 2 } });
  finish();
  await loading;
  assert.deepEqual(useAgentApprovalStore.getState().entries, {});
});
