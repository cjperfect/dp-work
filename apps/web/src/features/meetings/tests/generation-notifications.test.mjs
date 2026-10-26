import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  trackGenerations,
  finishGenerations,
  forgetGeneration,
  useMeetingGenerationStore,
} from "../../../stores/meeting-generation.ts";
import { emptyWorkspace } from "../../../apis/meetings.ts";
import { subscribeGenerationEvents } from "../lib/generation-events.ts";

const globals = ["window", "localStorage", "WebSocket"];
let originals, sockets, unsubscribes;
function meeting(task = "task-one", status = "generating", owner = 1) {
  return {
    ...emptyWorkspace("meeting-one", owner, "评审会议").meeting,
    generation_task_id: task,
    generation_status: status,
  };
}
class Socket {
  closeCount = 0;
  sent = [];
  constructor() {
    sockets.push(this);
  }
  send(data) {
    this.sent.push(data);
  }
  close() {
    this.closeCount++;
    this.onclose?.({ code: 1000 });
  }
  message(data) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}
beforeEach(() => {
  originals = Object.fromEntries(
    globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
  );
  sockets = [];
  unsubscribes = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { href: "http://localhost:3000/knowledge" } },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "fixture-token" },
  });
  Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: Socket });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
});
afterEach(async () => {
  for (const unsubscribe of unsubscribes) unsubscribe();
  await Promise.resolve();
  useAuthStore.setState({ user: null });
  for (const key of globals) {
    if (originals[key]) Object.defineProperty(globalThis, key, originals[key]);
    else delete globalThis[key];
  }
});
test("only tracked completion notifies once, including reconnect snapshots", () => {
  assert.deepEqual(finishGenerations([meeting("historical", "ready")], true), []);
  trackGenerations([meeting()]);
  assert.equal(finishGenerations([meeting("task-one", "ready")], true).length, 1);
  assert.deepEqual(finishGenerations([meeting("task-one", "ready")]), []);
  trackGenerations([meeting()]);
  assert.deepEqual(useMeetingGenerationStore.getState().pending, {});
});
test("retry task can notify failure independently and account changes clear notifications", () => {
  trackGenerations([meeting()]);
  assert.deepEqual(finishGenerations([meeting("task-one", "ready", 2)]), []);
  assert.equal(finishGenerations([meeting("task-one", "failed")]).length, 1);
  trackGenerations([meeting("task-two")]);
  assert.equal(finishGenerations([meeting("task-two", "ready")]).length, 1);
  trackGenerations([meeting("task-three")]);
  useAuthStore.setState({ user: { id: 2 } });
  assert.deepEqual(useMeetingGenerationStore.getState().pending, {});
});
test("deleting a pending meeting cancels its notification", () => {
  trackGenerations([meeting()]);
  forgetGeneration("meeting-one");
  assert.deepEqual(finishGenerations([meeting("task-one", "ready")]), []);
});
test("page and global notifier share one socket and navigation keeps the global listener", async () => {
  const page = [],
    global = [];
  const pageOff = subscribeGenerationEvents(1, (rows) => page.push(rows));
  const globalOff = subscribeGenerationEvents(1, (rows) => global.push(rows));
  unsubscribes.push(pageOff, globalOff);
  assert.equal(sockets.length, 1);
  sockets[0].onopen();
  assert.deepEqual(JSON.parse(sockets[0].sent[0]), { token: "fixture-token" });
  sockets[0].message({ type: "meetings.snapshot", meetings: [meeting()] });
  pageOff();
  await Promise.resolve();
  assert.equal(sockets[0].closeCount, 0);
  sockets[0].message({ type: "meeting.updated", meeting: meeting("task-one", "ready") });
  assert.equal(page.length, 1);
  assert.equal(global.length, 2);
  globalOff();
  await Promise.resolve();
  assert.equal(sockets[0].closeCount, 1);
});
test("new subscribers receive a completed snapshot instead of missing fast results", async () => {
  unsubscribes.push(subscribeGenerationEvents(1, () => {}));
  sockets[0].message({ type: "meetings.snapshot", meetings: [meeting("task-one", "ready")] });
  const updates = [];
  unsubscribes.push(subscribeGenerationEvents(1, (rows) => updates.push(rows)));
  await Promise.resolve();
  assert.equal(updates[0][0].generation_status, "ready");
  assert.equal(sockets.length, 1);
});
