import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  loadConnectors,
  applyFeishuStatus,
  useConnectorStore,
} from "../../../stores/connectors.ts";

const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
const disconnected = {
  installed: true,
  configured: false,
  connected: false,
  verified: false,
  account: null,
  flow: null,
};
beforeEach(() => {
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "test-token", setItem: () => {} },
  });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
});
afterEach(async () => {
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  await loadConnectors(null);
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("connector status comes from API instead of a simulated connected account", async () => {
  const request = mockHttpRequest(async () => Response.json({ code: 0, data: disconnected }));
  await Promise.all([loadConnectors(1), loadConnectors(1)]);
  assert.equal(request.mock.callCount(), 1);
  assert.equal(useConnectorStore.getState().connectors[0].status, "disconnected");
  assert.equal(useConnectorStore.getState().connectors[0].account, undefined);
  assert.equal(useConnectorStore.getState().feishu.installed, true);
});

test("late responses cannot expose another platform account's connection", async () => {
  mockHttpRequest(async () => {
    useAuthStore.setState({ user: { id: 2, username: "other" } });
    return Response.json({
      code: 0,
      data: { ...disconnected, connected: true, account: "private-user" },
    });
  });
  await loadConnectors(1);
  assert.notEqual(useConnectorStore.getState().feishu?.account, "private-user");
  applyFeishuStatus(1, { ...disconnected, account: "private-user" });
  assert.notEqual(useConnectorStore.getState().feishu?.account, "private-user");
});

test("an unavailable API does not invent an authorized connection", async () => {
  await loadConnectors(null);
  mockHttpRequest(async () =>
    Response.json({ code: 5000, message: "连接器服务不可用", data: null }, { status: 500 }),
  );
  await loadConnectors(1);
  assert.equal(useConnectorStore.getState().connectors[0].status, "disconnected");
  assert.match(useConnectorStore.getState().error, /服务不可用/);
});

test("display-only consumers reuse cached status while explicit refresh still requests API", async () => {
  const request = mockHttpRequest(async () => Response.json({ code: 0, data: disconnected }));
  await loadConnectors(1);
  await loadConnectors(1, false);
  await loadConnectors(1, false);
  assert.equal(request.mock.callCount(), 1);
  await loadConnectors(1);
  assert.equal(request.mock.callCount(), 2);
});
