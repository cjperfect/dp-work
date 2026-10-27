import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { loadSkills, useSkillsStore } from "../../../stores/skills.ts";

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
const adapter = httpClient.defaults.adapter;
let token;
beforeEach(() => {
  token = "fixture-token";
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: (key) => (key === "dp-work.auth.token" ? token : null), setItem() {} },
  });
  useAuthStore.setState({ user: { id: 1, username: "fixture" } });
  useSkillsStore.setState({ entries: {} });
});
afterEach(() => {
  httpClient.defaults.adapter = adapter;
  useAuthStore.setState({ user: null });
  for (const [key, original] of [
    ["window", originalWindow],
    ["localStorage", originalStorage],
  ]) {
    if (original) Object.defineProperty(globalThis, key, original);
    else delete globalThis[key];
  }
});
function response(config, items) {
  return { data: { code: 0, data: { items } }, status: 200, statusText: "OK", headers: {}, config };
}
test("installed skill reads deduplicate and Agent results stay separate", async () => {
  let calls = 0;
  httpClient.defaults.adapter = async (config) => {
    calls++;
    return response(config, [{ id: config.params.agent_code, name: config.params.agent_code }]);
  };
  await Promise.all([loadSkills("general"), loadSkills("general")]);
  assert.equal(calls, 1);
  await loadSkills("product");
  assert.equal(useSkillsStore.getState().entries.general.items[0].id, "general");
  assert.equal(useSkillsStore.getState().entries.product.items[0].id, "product");
});
test("logout discards an in-flight local device skill response", async () => {
  let finish;
  httpClient.defaults.adapter = (config) =>
    new Promise((resolve) => {
      finish = () => resolve(response(config, [{ id: "private" }]));
    });
  const loading = loadSkills("general");
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
  token = null;
  useAuthStore.setState({ user: null });
  finish();
  await loading;
  assert.deepEqual(useSkillsStore.getState().entries, {});
});

test("cached skills expire and failed refresh preserves content but reports failure", async () => {
  const now = Date.now;
  let clock = 100000,
    calls = 0;
  Date.now = () => clock;
  httpClient.defaults.adapter = async (config) => {
    calls++;
    return response(config, [{ id: "installed" }]);
  };
  try {
    assert.equal(await loadSkills("general"), true);
    await loadSkills("general");
    assert.equal(calls, 1);
    clock += 31000;
    await loadSkills("general");
    assert.equal(calls, 2);
    httpClient.defaults.adapter = async () => {
      throw new Error("fixture refresh failure");
    };
    assert.equal(await loadSkills("general", true), false);
    const entry = useSkillsStore.getState().entries.general;
    assert.equal(entry.items[0].id, "installed");
    assert.equal(entry.loaded, false);
    assert.equal(typeof entry.error, "string");
    assert.ok(entry.error.length > 0);
  } finally {
    Date.now = now;
  }
});

test("device reconnection discards stale responses and fetches a fresh list", async () => {
  const { invalidateSkills } = await import("../../../stores/skills.ts");
  let finish;
  httpClient.defaults.adapter = (config) =>
    new Promise((resolve) => {
      finish = () => resolve(response(config, [{ id: "stale" }]));
    });
  const previous = loadSkills("general");
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
  const revision = useSkillsStore.getState().revision;
  invalidateSkills();
  assert.equal(useSkillsStore.getState().revision, revision + 1);
  httpClient.defaults.adapter = async (config) => response(config, [{ id: "fresh" }]);
  assert.equal(await loadSkills("general"), true);
  finish();
  assert.equal(await previous, false);
  assert.equal(useSkillsStore.getState().entries.general.items[0].id, "fresh");
});

test("forced refresh waits for older reads and fetches again", async () => {
  let finish,
    calls = 0;
  httpClient.defaults.adapter = (config) => {
    calls++;
    if (calls === 1)
      return new Promise((resolve) => {
        finish = () => resolve(response(config, [{ id: "before-install" }]));
      });
    return Promise.resolve(response(config, [{ id: "after-install" }]));
  };
  const previous = loadSkills("general");
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
  const refreshed = loadSkills("general", true);
  finish();
  await previous;
  assert.equal(await refreshed, true);
  assert.equal(calls, 2);
  assert.equal(useSkillsStore.getState().entries.general.items[0].id, "after-install");
});
