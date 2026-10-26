import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
const Y = createRequire(import.meta.url)("yjs");
import { RecordProvider, encodeState, decodeState } from "../lib/record-provider.ts";

// 使用真实 CRDT 合并，网络只替换为可控的 WebSocket。
test("record edits wait for persistence acknowledgement and remote changes merge", async () => {
  const originals = Object.fromEntries(
    ["window", "localStorage", "WebSocket"].map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor() {
      sockets.push(this);
    }
    send(value) {
      this.sent.push(JSON.parse(value));
    }
    close() {}
    message(value) {
      this.onmessage({ data: JSON.stringify(value) });
    }
  }
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { href: "http://localhost:3000/meetings" } },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "fixture" },
  });
  Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: Socket });
  const server = new Y.Doc();
  server.getText("text").insert(0, "原文");
  const initial = {
    meeting_id: "one",
    epoch: "epoch",
    revision: 1,
    saved_revision: 1,
    state: encodeState(Y.encodeStateAsUpdate(server)),
    editable: true,
    owner: true,
    updated_at: new Date().toISOString(),
  };
  const { Awareness, encodeAwarenessUpdate } = createRequire(import.meta.url)(
    "y-protocols/awareness",
  );
  const peerDoc = new Y.Doc();
  const peerAwareness = new Awareness(peerDoc);
  const statuses = [],
    resets = [];
  const provider = new RecordProvider(
    initial,
    undefined,
    (status) => statuses.push(status),
    (doc) => resets.push(doc),
  );
  try {
    const socket = sockets[0];
    socket.onopen();
    assert.equal(socket.sent[0].token, "fixture");
    socket.message({ type: "state", ...initial });
    peerAwareness.setLocalState({ collaborator: { id: 2, username: "产品同事" } });
    const count = socket.sent.filter((value) => value.type === "awareness").length;
    socket.message({
      type: "awareness",
      update: encodeState(encodeAwarenessUpdate(peerAwareness, [peerDoc.clientID])),
    });
    assert.equal(provider.awareness.getStates().has(peerDoc.clientID), true);
    assert.equal(socket.sent.filter((value) => value.type === "awareness").length, count + 1);
    peerAwareness.setLocalState(null);
    socket.message({
      type: "awareness",
      update: encodeState(encodeAwarenessUpdate(peerAwareness, [peerDoc.clientID])),
    });
    assert.equal(provider.awareness.getStates().has(peerDoc.clientID), false);
    provider.doc.getText("text").insert(0, "我的意见");
    const update = socket.sent.find((message) => message.type === "update");
    assert.ok(update);
    assert.equal(statuses.at(-1).pending, true);
    let flushed = false;
    const saving = provider.flush().then(() => {
      flushed = true;
    });
    await Promise.resolve();
    assert.equal(flushed, false);
    server.getText("text").insert(0, "同事的意见");
    Y.applyUpdate(server, decodeState(update.update));
    socket.message({
      type: "ack",
      seq: update.seq,
      ...initial,
      revision: 2,
      state: encodeState(Y.encodeStateAsUpdate(server)),
    });
    await Promise.resolve();
    assert.equal(flushed, false);
    socket.message({
      type: "saved",
      save_seq: socket.sent.find((value) => value.type === "save").save_seq,
      ...initial,
      revision: 2,
      saved_revision: 2,
      state: encodeState(Y.encodeStateAsUpdate(server)),
    });
    await saving;
    assert.equal(statuses.at(-1).pending, false);
    assert.equal(provider.doc.getText("text").toString(), server.getText("text").toString());
    assert.ok(server.getText("text").toString().includes("同事的意见"));
    socket.message({ type: "state", ...initial, epoch: "restored" });
    assert.equal(resets.length, 1);
    provider.doc.getText("text").insert(0, "尚未保存");
    socket.message({ type: "state", ...initial, epoch: "another-restore" });
    assert.equal(resets.length, 1);
    assert.match(statuses.at(-1).error, /复制未同步内容/);
  } finally {
    provider.destroy();
    peerAwareness.destroy();
    peerDoc.destroy();
    server.destroy();
    for (const key of Object.keys(originals)) {
      if (originals[key]) Object.defineProperty(globalThis, key, originals[key]);
      else delete globalThis[key];
    }
  }
});

test("collaborator roster deduplicates accounts and ignores cursor-only states", async () => {
  const { recordCollaborators } = await import("../hooks/use-record-collaborators.ts");
  assert.deepEqual(
    recordCollaborators([
      { collaborator: { id: 2, username: "产品同事" } },
      { collaborator: { id: 1, username: "chenjiang" }, cursor: { anchor: 1 } },
      { collaborator: { id: 2, username: "产品同事" }, cursor: { anchor: 2 } },
      { user: { name: "历史光标" } },
      { collaborator: { id: 3, username: "" } },
    ]),
    [
      { id: 1, username: "chenjiang" },
      { id: 2, username: "产品同事" },
    ],
  );
});

test("autosave waits one second, saves during continuous typing, and retries failures", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const keys = ["window", "localStorage", "WebSocket"];
  const originals = Object.fromEntries(
    keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
  );
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor() {
      sockets.push(this);
    }
    send(value) {
      this.sent.push(JSON.parse(value));
    }
    close() {}
    message(value) {
      this.onmessage({ data: JSON.stringify(value) });
    }
  }
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { href: "http://localhost:3000/meetings" } },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "fixture" },
  });
  Object.defineProperty(globalThis, "WebSocket", { configurable: true, value: Socket });
  const server = new Y.Doc();
  server.getText("text").insert(0, "初始内容");
  let revision = 1,
    savedRevision = 1;
  const snapshot = () => ({
    meeting_id: "one",
    epoch: "epoch",
    revision,
    saved_revision: savedRevision,
    state: encodeState(Y.encodeStateAsUpdate(server)),
    editable: true,
    owner: true,
    updated_at: new Date().toISOString(),
  });
  const statuses = [];
  const provider = new RecordProvider(
    snapshot(),
    undefined,
    (value) => statuses.push(value),
    () => {},
  );
  const socket = sockets[0];
  const saves = () => socket.sent.filter((value) => value.type === "save");
  function type(value) {
    provider.doc.getText("text").insert(0, value);
    const update = socket.sent.filter((value) => value.type === "update").at(-1);
    Y.applyUpdate(server, decodeState(update.update));
    revision++;
    socket.message({ type: "ack", seq: update.seq, ...snapshot() });
  }
  function saved() {
    savedRevision = revision;
    socket.message({ type: "saved", save_seq: saves().at(-1).save_seq, ...snapshot() });
  }
  try {
    socket.onopen();
    socket.message({ type: "state", ...snapshot() });
    type("编辑");
    assert.equal(saves().length, 0);
    t.mock.timers.tick(999);
    assert.equal(saves().length, 0);
    t.mock.timers.tick(1);
    assert.equal(saves().length, 1);
    assert.equal(statuses.at(-1).saving, true);
    saved();
    assert.equal(statuses.at(-1).pending, false);
    // 持续输入不满足停输条件，5 秒兜底仍会保存。
    for (let i = 0; i < 5; i++) {
      type("继续");
      t.mock.timers.tick(800);
    }
    assert.equal(saves().length, 2);
    socket.message({ type: "save.error", message: "保存失败" });
    assert.equal(statuses.at(-1).pending, true);
    assert.equal(statuses.at(-1).saveError, "保存失败");
    t.mock.timers.tick(1999);
    assert.equal(saves().length, 2);
    t.mock.timers.tick(1);
    assert.equal(saves().length, 3);
    saved();
    assert.equal(statuses.at(-1).saveError, null);
    t.mock.timers.tick(5000);
    assert.equal(saves().length, 3);
  } finally {
    provider.destroy();
    server.destroy();
    t.mock.timers.reset();
    for (const key of keys) {
      if (originals[key]) Object.defineProperty(globalThis, key, originals[key]);
      else delete globalThis[key];
    }
  }
});
