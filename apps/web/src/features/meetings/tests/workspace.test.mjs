import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import { emptyWorkspace, elapsed, duration } from "../../../apis/meetings.ts";
import {
  isPending,
  localDraft,
  readDraft,
  saveDraft,
  removeDraft,
  listSavedMeetings,
} from "../lib/workspace-storage.ts";
import { persist, syncNow, loadWorkspace, useMeetingCache } from "../../../stores/meeting/index.ts";
import { updateTranscriptText } from "../lib/recording.ts";
import { meetingApiFixture } from "./api-fixture.mjs";
import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
let owner = 200;
let workspace, api;
beforeEach(() => {
  owner++;
  useAuthStore.setState({ user: { id: owner, username: "tester" } });
  useMeetingCache.setState({ records: {} });
  workspace = emptyWorkspace(crypto.randomUUID(), owner, "评审会议");
  api = meetingApiFixture([workspace]);
});
afterEach(() => {
  useAuthStore.setState({ user: null });
});

test("clock includes active time and excludes paused duration", () => {
  const now = Date.parse("2026-10-24T00:00:00Z");
  assert.equal(
    elapsed(
      { elapsed_ms: 5000, status: "active", resumed_at: new Date(now).toISOString() },
      now + 3000,
    ),
    8000,
  );
  assert.equal(
    elapsed({ elapsed_ms: 8000, status: "paused", resumed_at: null }, now + 60000),
    8000,
  );
  assert.equal(duration(3661000), "01:01:01");
});
test("serial saves use the last acknowledged revision and retain the newest edit", async () => {
  const draft = localDraft(workspace);
  draft.version = 1;
  draft.dirtyMinutes = true;
  draft.minutes = {
    content: "第一稿",
    blocks: [{ type: "paragraph" }],
    status: 1,
    archived_document_id: null,
  };
  const first = saveDraft(draft);
  const second = saveDraft({
    ...draft,
    version: 2,
    minutes: { ...draft.minutes, content: "第二稿" },
  });
  await Promise.all([first, second]);
  const saved = await readDraft(owner, workspace.meeting.id);
  assert.equal(saved.minutes.content, "第二稿");
  assert.deepEqual(saved.minutes.blocks, draft.minutes.blocks);
  assert.equal(saved.meeting.revision, 3);
  assert.equal(isPending(saved), false);
  const puts = api.transport.mock.calls.filter((call) => call.arguments[1].method === "PUT");
  assert.deepEqual(
    puts.map((call) => JSON.parse(call.arguments[1].body).expected_revision),
    [1, 2],
  );
});
test("older snapshots cannot overwrite a newer saved version", async () => {
  const draft = {
    ...localDraft(workspace),
    version: 2,
    meeting: { ...workspace.meeting, title: "新标题" },
  };
  await saveDraft(draft);
  await saveDraft({ ...localDraft(workspace), version: 1 });
  assert.equal((await readDraft(owner, workspace.meeting.id)).meeting.title, "新标题");
});
test("failed writes stay unsaved, focus reads preserve edits, and retry persists them", async () => {
  const draft = {
    ...localDraft(workspace),
    version: 1,
    dirtyControls: true,
    meeting: { ...workspace.meeting, status: "ended" },
  };
  mockHttpRequest(async () => {
    throw new Error("offline");
  });
  await assert.rejects(persist(draft));
  let cached = useMeetingCache.getState().records[`${owner}:${workspace.meeting.id}`];
  assert.equal(cached.localSaved, false);
  assert.equal(cached.meeting.status, "ended");
  assert.equal((await loadWorkspace(owner, workspace.meeting.id)).meeting.status, "ended");
  api = meetingApiFixture([workspace]);
  await syncNow(owner);
  cached = useMeetingCache.getState().records[`${owner}:${workspace.meeting.id}`];
  assert.equal(cached.localSaved, true);
  assert.equal(cached.error, null);
  assert.equal(isPending(cached), false);
  assert.equal(api.records.get(workspace.meeting.id).meeting.status, "ended");
});
test("version conflicts are reported without overwriting another page", async () => {
  api.records.get(workspace.meeting.id).meeting.revision = 5;
  await assert.rejects(persist({ ...localDraft(workspace), version: 1 }), /其他页面/);
  assert.equal(api.records.get(workspace.meeting.id).meeting.revision, 5);
  assert.equal(
    useMeetingCache.getState().records[`${owner}:${workspace.meeting.id}`].localSaved,
    false,
  );
});
test("deletion removes the server record and stale saves cannot recreate it", async () => {
  await removeDraft(owner, workspace.meeting.id);
  assert.equal(await readDraft(owner, workspace.meeting.id), undefined);
  await assert.rejects(saveDraft(localDraft(workspace)), /会议不存在/);
  await assert.rejects(loadWorkspace(owner, workspace.meeting.id), /会议不存在/);
});
test("requests and late responses cannot cross account boundaries", async () => {
  await assert.rejects(readDraft(owner + 1, workspace.meeting.id), /登录状态/);
  let respond, started;
  const waiting = new Promise((resolve) => {
    started = resolve;
  });
  mockHttpRequest(async () => {
    started();
    return new Promise((resolve) => {
      respond = resolve;
    });
  });
  const operation = persist(localDraft(workspace));
  await waiting;
  useAuthStore.setState({ user: { id: owner + 1 } });
  useMeetingCache.setState({ records: {} });
  respond(Response.json({ code: 0, data: workspace }));
  await assert.rejects(operation, /登录状态/);
  assert.deepEqual(useMeetingCache.getState().records, {});
});
test("legacy drafts migrate once and only disappear from IndexedDB after success", async () => {
  const legacy = emptyWorkspace(crypto.randomUUID(), owner, "旧会议");
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("dp-meeting-workspaces", 2);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore("drafts", {
        keyPath: ["accountId", "meeting.id"],
      });
      store.createIndex("account", "accountId");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  await new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", "readwrite");
    tx.objectStore("drafts").put(localDraft(legacy));
    tx.oncomplete = resolve;
    tx.onerror = reject;
  });
  const list = await listSavedMeetings(owner);
  assert.equal(
    list.some((row) => row.id === legacy.meeting.id),
    true,
  );
  assert.equal(api.records.get(legacy.meeting.id).meeting.title, "旧会议");
  const count = await new Promise((resolve) => {
    const request = db
      .transaction("drafts")
      .objectStore("drafts")
      .count([owner, legacy.meeting.id]);
    request.onsuccess = () => resolve(request.result);
  });
  assert.equal(count, 0);
  db.close();
  await removeDraft(owner, legacy.meeting.id);
  assert.equal(
    (await listSavedMeetings(owner)).some((row) => row.id === legacy.meeting.id),
    false,
  );
});

test("concurrent meeting list loads share one request and the next visit refreshes", async () => {
  const [first, second] = await Promise.all([listSavedMeetings(owner), listSavedMeetings(owner)]);
  assert.deepEqual(first, second);
  assert.equal(
    api.transport.mock.calls.filter((call) => call.arguments[0] === "/api/meetings").length,
    1,
  );
  await listSavedMeetings(owner);
  assert.equal(
    api.transport.mock.calls.filter((call) => call.arguments[0] === "/api/meetings").length,
    2,
  );
});

test("a failed shared meeting list request does not block subsequent retries", async () => {
  const request = mockHttpRequest(async () => {
    throw new Error("offline");
  });
  const result = await Promise.allSettled([listSavedMeetings(owner), listSavedMeetings(owner)]);
  assert.equal(request.mock.callCount(), 1);
  assert.ok(result.every((row) => row.status === "rejected"));
  meetingApiFixture([workspace]);
  assert.equal((await listSavedMeetings(owner))[0].id, workspace.meeting.id);
});

test("editing original text persists its revision without changing speaker, time, or minutes", async () => {
  workspace.segments = [
    {
      id: "asr-original",
      seq: 3,
      revision: 2,
      speaker: "说话人 1",
      text: "识别错误",
      start_ms: 1234,
      end_ms: 4567,
    },
  ];
  workspace.minutes = { content: "独立的纪要草稿", status: 1, archived_document_id: null };
  meetingApiFixture([workspace]);
  const draft = localDraft(workspace);
  const edited = updateTranscriptText(draft, "asr-original", "修正后的正文");
  assert.equal(edited.segments[0].revision, 3);
  assert.deepEqual(edited.dirtyEntries, ["asr-original"]);
  assert.equal(updateTranscriptText(edited, "asr-original", "修正后的正文"), edited);
  await saveDraft({ ...edited, version: 1 });
  const restored = await readDraft(owner, workspace.meeting.id);
  assert.deepEqual(restored.segments[0], {
    ...workspace.segments[0],
    revision: 3,
    text: "修正后的正文",
  });
  assert.deepEqual(restored.minutes, workspace.minutes);
});
