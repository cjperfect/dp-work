import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import "fake-indexeddb/auto";
import { useAuthStore } from "../../../stores/auth.ts";
import { emptyWorkspace, generateMinutes, createMinutesShare } from "../../../apis/meetings.ts";
import {
  cacheCreated,
  cacheServerWorkspace,
  loadWorkspace,
  syncNow,
} from "../../../stores/meetings.ts";
import { readDraft } from "../lib/workspace-storage.ts";
import { readLocalShare, saveSharedMinutes } from "../lib/mock-sharing.ts";
import { meetingCategory } from "../lib/minutes-state.ts";
import { meetingApiFixture } from "./api-fixture.mjs";
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
let workspace;
beforeEach(async () => {
  const storage = new Map();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { origin: "http://localhost:3000" } },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
  });
  useAuthStore.setState({ user: { id: 123, username: "tester" } });
  workspace = emptyWorkspace(crypto.randomUUID(), 123, "产品评审");
  workspace.meeting.status = "ended";
  workspace.segments = [
    { id: "asr-1", seq: 0, speaker: "说话人 1", text: "下周交付", start_ms: 1000 },
  ];
  meetingApiFixture([workspace]);
  await cacheCreated(workspace);
});
afterEach(() => {
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});
test("generation submits the saved revision to the real API instead of returning placeholder text", async () => {
  const api = meetingApiFixture([workspace]);
  const result = await generateMinutes(workspace);
  assert.equal(result.meeting.generation_status, "generating");
  assert.ok(result.task_id);
  const call = api.transport.mock.calls[0].arguments;
  assert.equal(call[0], `/api/meetings/${workspace.meeting.id}/minutes/generate`);
  assert.deepEqual(JSON.parse(call[1].body), { expected_revision: workspace.meeting.revision });
});
test("active and paused meetings cannot generate minutes", async () => {
  for (const status of ["active", "paused"]) {
    workspace.meeting.status = status;
    await assert.rejects(generateMinutes(workspace), /请先结束会议/);
  }
});
test("submission stays in pending with a generating status until a real result is available", async () => {
  const result = await generateMinutes(workspace);
  const generating = cacheServerWorkspace({ ...workspace, meeting: result.meeting });
  assert.equal(meetingCategory(generating.meeting), "pending");
  assert.equal(
    (await readDraft(123, workspace.meeting.id)).meeting.generation_status,
    "generating",
  );
  const future = Date.now() + 24 * 60 * 60 * 1000;
  mock.method(Date, "now", () => future);
  await syncNow(123);
  const ready = await loadWorkspace(123, workspace.meeting.id);
  assert.equal(ready.meeting.generation_status, "generating");
  assert.equal(ready.minutes, null);
});
test("read links open saved minutes and reject edits", async () => {
  const url = await createMinutesShare(workspace, "read");
  assert.equal(await createMinutesShare(workspace, "read"), url);
  const token = new URL(url).pathname.split("/").at(-1);
  const { share, draft } = await readLocalShare(token);
  assert.equal(share.permission, "read");
  assert.equal(draft.meeting.id, workspace.meeting.id);
  await assert.rejects(saveSharedMinutes(token, "不允许"), /仅可阅读/);
});
test("edit links update the original meeting", async () => {
  const url = await createMinutesShare(workspace, "edit");
  const token = new URL(url).pathname.split("/").at(-1);
  await saveSharedMinutes(token, "## 修改后的纪要");
  assert.equal((await loadWorkspace(123, workspace.meeting.id)).minutes.content, "## 修改后的纪要");
});

test("rich text blocks and formatting survive shared saves and reloads", async () => {
  const url = await createMinutesShare(workspace, "edit");
  const token = new URL(url).pathname.split("/").at(-1);
  const blocks = [
    {
      id: "rich-paragraph",
      type: "paragraph",
      content: [{ type: "text", text: "保留加粗格式", styles: { bold: true } }],
    },
  ];
  await saveSharedMinutes(token, "**保留加粗格式**", blocks);
  const restored = await loadWorkspace(123, workspace.meeting.id);
  assert.deepEqual(restored.minutes.blocks, blocks);
  assert.equal(restored.minutes.content, "**保留加粗格式**");
});
test("shared edits are blocked once the meeting is archived", async () => {
  const url = await createMinutesShare(workspace, "edit");
  const token = new URL(url).pathname.split("/").at(-1);
  workspace.meeting.status = "archived";
  meetingApiFixture([workspace]);
  await cacheCreated(workspace);
  await assert.rejects(saveSharedMinutes(token, "不允许"), /仅可阅读/);
});
