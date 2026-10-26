import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  consumeDocumentParseEvents,
  consumeDocumentVectorEvents,
} from "../../../stores/document-parsing.ts";
import { subscribeDocumentParseEvents } from "../lib/parse-events.ts";

const globals = ["window", "localStorage", "WebSocket"];
let originals, sockets, unsubscribes;
function row(status = "parsing", task = "task-one", owner = 1) {
  return {
    id: "doc",
    base_id: 1,
    owner_id: owner,
    name: "file.pdf",
    status,
    task_id: task,
    error: null,
    parsed_at: null,
  };
}
class Socket {
  closed = 0;
  sent = [];
  constructor() {
    sockets.push(this);
  }
  send(data) {
    this.sent.push(data);
  }
  close() {
    this.closed++;
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
  for (const off of unsubscribes) off();
  await Promise.resolve();
  useAuthStore.setState({ user: null });
  for (const key of globals) {
    if (originals[key]) Object.defineProperty(globalThis, key, originals[key]);
    else delete globalThis[key];
  }
});
test("ignore historical tasks, recover disconnected completions, deduplicate and allow retry", () => {
  assert.deepEqual(consumeDocumentParseEvents([row("parsed", "historical")], true), []);
  assert.deepEqual(consumeDocumentParseEvents([row("parsed", "historical")], false), []);
  consumeDocumentParseEvents([row()], true);
  assert.equal(consumeDocumentParseEvents([row("parsed")], true).length, 1);
  assert.deepEqual(consumeDocumentParseEvents([row("parsed")], false), []);
  assert.equal(consumeDocumentParseEvents([row("failed", "retry")], false).length, 1);
  assert.deepEqual(consumeDocumentParseEvents([row("parsed", "other", 2)], false), []);
});
test("fast completion can notify even if the queued event was coalesced", () => {
  assert.equal(consumeDocumentParseEvents([row("parsed")], false).length, 1);
  assert.deepEqual(consumeDocumentParseEvents([row("parsed")], true), []);
});
test("global notification and page share a socket; account changes isolate old events", async () => {
  const global = [],
    page = [];
  unsubscribes.push(subscribeDocumentParseEvents(1, (rows) => global.push(rows)));
  const off = subscribeDocumentParseEvents(1, (rows) => page.push(rows));
  unsubscribes.push(off);
  assert.equal(sockets.length, 1);
  sockets[0].onopen();
  assert.deepEqual(JSON.parse(sockets[0].sent[0]), { token: "fixture-token" });
  sockets[0].message({
    type: "documents.snapshot",
    documents: [row(), row("parsing", "other", 2)],
  });
  assert.equal(global[0].length, 1);
  off();
  await Promise.resolve();
  assert.equal(sockets[0].closed, 0);
  sockets[0].message({ type: "document.updated", document: row("parsed") });
  assert.equal(global.length, 2);
  assert.equal(page.length, 1);
  useAuthStore.setState({ user: { id: 2 } });
  sockets[0].message({ type: "document.updated", document: row("parsed") });
  assert.equal(global.length, 2);
});

test("vector notifications track independent task IDs and do not repeat parse notifications", () => {
  const vectorRow = (status, task = "vector-one", owner = 1) => ({
    ...row("parsed", "parse-one", owner),
    vector_status: status,
    vector_task_id: task,
  });
  consumeDocumentParseEvents([row("parsed", "parse-one")], true);
  assert.deepEqual(consumeDocumentVectorEvents([vectorRow("indexed", "old-vector")], true), []);
  consumeDocumentVectorEvents([vectorRow("queued")], false);
  assert.equal(consumeDocumentVectorEvents([vectorRow("indexed")], true).length, 1);
  assert.deepEqual(consumeDocumentVectorEvents([vectorRow("indexed")], false), []);
  assert.deepEqual(consumeDocumentParseEvents([vectorRow("indexed")], false), []);
  assert.equal(consumeDocumentVectorEvents([vectorRow("failed", "retry-vector")], false).length, 1);
  assert.deepEqual(consumeDocumentVectorEvents([vectorRow("indexed", "foreign", 2)], false), []);
});
