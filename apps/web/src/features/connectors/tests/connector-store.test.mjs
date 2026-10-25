import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import { loadConnectors, updateConnectors, useConnectorStore } from "../../../stores/connectors.ts";

const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
beforeEach(() => {
  const data = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => data.get(key) ?? null,
      setItem: (key, value) => data.set(key, value),
    },
  });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
  loadConnectors(1);
});
afterEach(() => {
  useAuthStore.setState({ user: null });
  loadConnectors(null);
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("connection changes update the shared state and survive loading again", () => {
  assert.equal(useConnectorStore.getState().connectors[0].status, "connected");
  updateConnectors(1, (rows) => rows.map((row) => ({ ...row, status: "disconnected" })));
  assert.equal(
    useConnectorStore.getState().connectors.filter((row) => row.status === "connected").length,
    0,
  );
  loadConnectors(1);
  assert.equal(useConnectorStore.getState().connectors[0].status, "disconnected");
});

test("connector settings remain isolated between accounts", () => {
  updateConnectors(1, (rows) => rows.map((row) => ({ ...row, status: "disconnected" })));
  useAuthStore.setState({ user: { id: 2, username: "other" } });
  loadConnectors(2);
  assert.equal(useConnectorStore.getState().connectors[0].status, "connected");
  assert.throws(() => updateConnectors(1, () => []), /登录状态已改变/);
  loadConnectors(1);
  assert.equal(useConnectorStore.getState().owner, 2);
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
  loadConnectors(1);
  assert.equal(useConnectorStore.getState().connectors[0].status, "disconnected");
});
