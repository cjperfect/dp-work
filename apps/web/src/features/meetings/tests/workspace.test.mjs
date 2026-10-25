import "fake-indexeddb/auto";
import { IDBObjectStore } from "fake-indexeddb";
import assert from "node:assert/strict";
import { beforeEach, afterEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import { elapsed, duration } from "../../../apis/meetings.ts";
import { confirmTemporary, control } from "../lib/recording.ts";
import {
  acknowledge,
  isPending,
  listDrafts,
  localDraft,
  prepareFlight,
  readDraft,
  saveDraft,
} from "../lib/workspace-storage.ts";
import { persist, syncNow, useMeetingCache } from "../../../stores/meetings.ts";
let account = 100;
let token;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
function workspace() {
  return {
    meeting: {
      id: crypto.randomUUID(),
      owner_id: account,
      title: "Review",
      status: "paused",
      elapsed_ms: 5000,
      resumed_at: null,
      revision: 0,
    },
    segments: [],
    minutes: { content: "", status: 0, archived_document_id: null },
  };
}
beforeEach(() => {
  account++;
  token = `token-${account}`;
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => token },
  });
  useAuthStore.setState({ user: { id: account, username: "tester" } });
  useMeetingCache.setState({ records: {} });
});
afterEach(() => {
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});
const ok = (data) => Response.json({ code: 0, data });

test("clock counts active time, freezes while paused, and excludes pause duration", () => {
  const time = Date.parse("2026-10-24T00:00:00Z");
  assert.equal(
    elapsed(
      { elapsed_ms: 5000, status: "active", resumed_at: new Date(time).toISOString() },
      time + 3000,
    ),
    8000,
  );
  assert.equal(
    elapsed({ elapsed_ms: 8000, status: "paused", resumed_at: null }, time + 60000),
    8000,
  );
  assert.equal(duration(3661000), "01:01:01");
  const draft = localDraft(workspace());
  assert.equal(control(draft, "active").meeting.elapsed_ms, 5000);
});
test("temporary words are recoverable locally and only confirmed records enter the outbox", async () => {
  const draft = localDraft(workspace());
  draft.temporary = { speaker: " Alice ", text: " Draft words " };
  await saveDraft(draft);
  const recovered = await readDraft(account, draft.meeting.id);
  assert.equal(recovered.temporary.text, " Draft words ");
  assert.equal(isPending(recovered), false);
  const confirmed = confirmTemporary(recovered);
  assert.equal(confirmed.segments[0].text, "Draft words");
  assert.equal(confirmed.segments[0].speaker, "Alice");
  assert.equal(confirmed.segments[0].start_ms, 5000);
  assert.equal(confirmed.segments[0].seq, 0);
  assert.equal(confirmed.temporary.text, "");
  assert.equal(isPending(confirmed), true);
});
test("persistent flights reuse the exact sync ID after reload or lost responses", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "A", text: "One" },
    version: 1,
  });
  await saveDraft(draft);
  const sent = await prepareFlight(account, draft.meeting.id);
  const reloaded = await readDraft(account, draft.meeting.id);
  const resent = await prepareFlight(account, draft.meeting.id);
  assert.equal(sent.flight.payload.sync_id, reloaded.flight.payload.sync_id);
  assert.deepEqual(sent.flight, resent.flight);
  assert.equal(sent.flight.payload.expected_revision, 0);
});
test("edits arriving during a sync survive acknowledgment and use the new server revision", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "A", text: "One" },
    version: 1,
  });
  await saveDraft(draft);
  const sent = await prepareFlight(account, draft.meeting.id);
  const edited = {
    ...sent,
    version: 2,
    dirtyMinutes: true,
    minutes: { ...sent.minutes, content: "New draft" },
    segments: sent.segments.map((row) => ({ ...row, text: "Corrected" })),
  };
  await saveDraft(edited);
  const server = {
    ...workspace(),
    meeting: { ...draft.meeting, revision: 1 },
    segments: draft.segments,
    minutes: draft.minutes,
  };
  const ack = await acknowledge(sent, server);
  assert.equal(ack.segments[0].text, "Corrected");
  assert.equal(ack.minutes.content, "New draft");
  assert.equal(ack.meeting.revision, 1);
  assert.equal(isPending(ack), true);
  const next = await prepareFlight(account, draft.meeting.id);
  assert.equal(next.flight.payload.expected_revision, 1);
  assert.equal(next.flight.payload.segments[0].text, "Corrected");
  const done = await acknowledge(next, {
    ...server,
    meeting: { ...server.meeting, revision: 2 },
    segments: edited.segments,
    minutes: edited.minutes,
  });
  assert.equal(isPending(done), false);
});
test("batches contain at most 200 changed segments and remaining records stay pending", async () => {
  const draft = localDraft(workspace());
  draft.segments = Array.from({ length: 205 }, (_, seq) => ({
    id: crypto.randomUUID(),
    seq,
    speaker: null,
    text: `Entry ${seq}`,
    start_ms: seq,
  }));
  draft.dirtyEntries = draft.segments.map((row) => row.id);
  draft.version = 1;
  await saveDraft(draft);
  const first = await prepareFlight(account, draft.meeting.id);
  assert.equal(first.flight.payload.segments.length, 200);
  const ack = await acknowledge(first, {
    ...draft,
    meeting: { ...draft.meeting, revision: 1 },
    segments: draft.segments.slice(0, 200),
  });
  assert.equal(ack.dirtyEntries.length, 5);
  assert.equal(ack.segments.length, 205);
  const last = await prepareFlight(account, draft.meeting.id);
  assert.equal(last.flight.payload.segments.length, 5);
});
test("older local writes cannot restore an acknowledged batch or erase newer text", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "", text: "One" },
    version: 1,
  });
  await saveDraft(draft);
  const sent = await prepareFlight(account, draft.meeting.id);
  await acknowledge(sent, { ...draft, meeting: { ...draft.meeting, revision: 1 } });
  await saveDraft(draft);
  const stored = await readDraft(account, draft.meeting.id);
  assert.equal(stored.meeting.revision, 1);
  assert.equal(isPending(stored), false);
});
test("failed network sync keeps the persistent outbox and succeeds with the same batch on retry", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "", text: "Recoverable" },
    version: 1,
  });
  await persist(draft);
  const fetch = mock.method(globalThis, "fetch", async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(syncNow(account), /连接失败/);
  const failed = await readDraft(account, draft.meeting.id);
  assert.equal(isPending(failed), true);
  assert.match(failed.error, /连接失败/);
  const syncId = failed.flight.payload.sync_id;
  fetch.mock.mockImplementation(async (url, init) => {
    assert.equal(JSON.parse(init.body).sync_id, syncId);
    return ok({ ...draft, meeting: { ...draft.meeting, revision: 1 } });
  });
  await syncNow(account);
  assert.equal(isPending(await readDraft(account, draft.meeting.id)), false);
});
test("local commit failures are shown as unsaved and never sent to the server", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "", text: "Must not disappear" },
    version: 1,
  });
  mock.method(IDBObjectStore.prototype, "put", () => {
    throw new DOMException("quota", "QuotaExceededError");
  });
  await assert.rejects(persist(draft));
  const cached = Object.values(useMeetingCache.getState().records)[0];
  assert.equal(cached.localSaved, false);
  assert.match(cached.error, /本地保存失败|quota/);
  assert.equal(await readDraft(account, draft.meeting.id), undefined);
});
test("local records are partitioned by account and a late response cannot publish into another login", async () => {
  const draft = localDraft(workspace());
  await saveDraft(draft);
  assert.equal((await listDrafts(account)).length, 1);
  assert.deepEqual(await listDrafts(account + 1), []);
  assert.equal(await readDraft(account + 1, draft.meeting.id), undefined);
});

test("a stale server load cannot erase a newer locally committed draft", async () => {
  const { replaceFromServer } = await import("../lib/workspace-storage.ts");
  const server = workspace();
  const draft = localDraft(server);
  draft.version = 1;
  draft.dirtyMinutes = true;
  draft.minutes = { ...draft.minutes, content: "New unsynced words" };
  await saveDraft(draft);
  const loaded = await replaceFromServer(server);
  assert.equal(loaded.minutes.content, "New unsynced words");
  assert.equal(isPending(loaded), true);
});
test("a late response after switching accounts does not populate the new account cache", async () => {
  const draft = confirmTemporary({
    ...localDraft(workspace()),
    temporary: { speaker: "", text: "Private" },
    version: 1,
  });
  await persist(draft);
  let respond;
  let started;
  const waiting = new Promise((resolve) => {
    started = resolve;
  });
  mock.method(globalThis, "fetch", () => {
    started();
    return new Promise((resolve) => {
      respond = resolve;
    });
  });
  const operation = syncNow(account);
  await waiting;
  useAuthStore.setState({ user: { id: account + 1, username: "other" } });
  token = "other-token";
  useMeetingCache.setState({ records: {} });
  respond(ok({ ...draft, meeting: { ...draft.meeting, revision: 1 } }));
  await assert.rejects(operation, /账号已切换/);
  assert.deepEqual(useMeetingCache.getState().records, {});
  assert.equal(isPending(await readDraft(account, draft.meeting.id)), true);
});
