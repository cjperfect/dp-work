import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import { knowledgeMention, removeMention } from "../lib/mention.ts";
import {
  createThread,
  flushDraft,
  loadAgents,
  loadThreads,
  renameThread,
  resetAgents,
  saveAgent,
  selectThread,
  sendMessage,
  setDraftKnowledge,
  setDraftText,
  useAgentStore,
} from "../../../stores/agent.ts";
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
let owner = 1000;
let token;
const tid = "11111111-1111-4111-8111-111111111111";
const productTid = "22222222-2222-4222-8222-222222222222";
function agents() {
  return [
    {
      id: 1,
      owner_id: owner,
      code: "general",
      name: "General",
      department: "All",
      description: "",
      knowledge_base_ids: [],
      skill_ids: ["s-001"],
      revision: 0,
      active_thread_id: tid,
    },
    {
      id: 2,
      owner_id: owner,
      code: "product",
      name: "Product",
      department: "Product",
      description: "",
      knowledge_base_ids: [],
      skill_ids: [],
      revision: 0,
      active_thread_id: productTid,
    },
  ];
}
function detail(id = tid, agent = 1) {
  return {
    thread: {
      id,
      agent_id: agent,
      title: "New",
      draft: "",
      draft_revision: 0,
      created_at: "2026-10-24T00:00:00Z",
      updated_at: "2026-10-24T00:00:00Z",
    },
    knowledge_base_ids: [],
    messages: [],
  };
}
function setup() {
  useAgentStore.setState({
    owner,
    agents: agents(),
    skills: [],
    loading: false,
    error: null,
    selected: { general: tid, product: productTid },
    lists: { general: [detail().thread], product: [detail(productTid, 2).thread] },
    details: { [tid]: detail(), [productTid]: detail(productTid, 2) },
    drafts: Object.fromEntries(
      [tid, productTid].map((id) => [
        id,
        {
          text: "",
          ids: [],
          version: 0,
          savedVersion: 0,
          saving: false,
          sending: false,
          error: null,
          pending: null,
        },
      ]),
    ),
  });
}
function ok(data) {
  return Response.json({ code: 0, data });
}
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  owner++;
  token = `token-${owner}`;
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => token },
  });
  useAuthStore.setState({ user: { id: owner, username: "tester" } });
  resetAgents();
  setup();
});
afterEach(() => {
  resetAgents();
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else delete globalThis.window;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("mentions support Unicode queries and caret editing without treating emails as knowledge mentions", () => {
  assert.deepEqual(knowledgeMention("@", 1), { start: 0, end: 1, query: "" });
  assert.deepEqual(knowledgeMention("看看 @产品", 6), { start: 3, end: 6, query: "产品" });
  assert.equal(knowledgeMention("a@company.com", 13), null);
  assert.equal(knowledgeMention("hello", 5), null);
  const text = "参考 @产品 补充";
  const mention = knowledgeMention(text, 6);
  assert.equal(removeMention(text, mention), "参考  补充");
});
test("Agent writes use the selected code and revision and cannot modify the other Agent", async () => {
  const updated = { ...agents()[0], name: "Research", knowledge_base_ids: [4], revision: 1 };
  const fetch = mock.method(globalThis, "fetch", async () => ok(updated));
  await saveAgent("general", updated);
  const [url, init] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/agents/general");
  assert.equal(init.headers.Authorization, `Bearer ${token}`);
  assert.equal(JSON.parse(init.body).expected_revision, 0);
  assert.equal(useAgentStore.getState().agents[1].name, "Product");
});
test("failed Agent saves keep the committed configuration and release the busy state", async () => {
  mock.method(globalThis, "fetch", async () =>
    Response.json({ code: 3003, message: "other page changed", data: null }, { status: 409 }),
  );
  await assert.rejects(saveAgent("general", { ...agents()[0], name: "Unsaved" }), /other page/);
  assert.equal(useAgentStore.getState().agents[0].name, "General");
  assert.equal(useAgentStore.getState().configBusy, false);
});
test("new conversation creation is deduplicated while pending and is scoped to its Agent", async () => {
  useAgentStore.setState({ selected: { general: null } });
  const response = deferred();
  const fetch = mock.method(globalThis, "fetch", () => response.promise);
  const first = createThread("general");
  const second = createThread("general");
  assert.equal(first, second);
  response.resolve(ok(detail()));
  await first;
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/agents/general/threads");
  assert.equal(useAgentStore.getState().selected.general, tid);
  assert.equal(useAgentStore.getState().lists.product[0].id, productTid);
});
test("draft edits during saving survive the earlier response and use the next server revision", async () => {
  setDraftText(tid, "First");
  const response = deferred();
  let call = 0;
  const fetch = mock.method(globalThis, "fetch", async (url, init) => {
    call++;
    const body = JSON.parse(init.body);
    if (call === 1) return response.promise;
    assert.equal(body.text, "Newer");
    assert.equal(body.expected_revision, 1);
    return ok({
      thread: { ...detail().thread, draft: body.text, draft_revision: 2 },
      knowledge_base_ids: body.knowledge_base_ids,
    });
  });
  const saving = flushDraft("general", tid);
  setDraftText(tid, "Newer");
  response.resolve(
    ok({
      thread: { ...detail().thread, draft: "First", draft_revision: 1 },
      knowledge_base_ids: [],
    }),
  );
  await saving;
  const draft = useAgentStore.getState().drafts[tid];
  assert.equal(draft.text, "Newer");
  assert.equal(draft.version, draft.savedVersion);
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(useAgentStore.getState().drafts[productTid].text, "");
});
test("knowledge selection is unique and is saved with the draft without changing another conversation", async () => {
  setDraftKnowledge(tid, [4, 4, 5]);
  const fetch = mock.method(globalThis, "fetch", async (url, init) => {
    const body = JSON.parse(init.body);
    return ok({
      thread: { ...detail().thread, draft_revision: 1 },
      knowledge_base_ids: body.knowledge_base_ids,
    });
  });
  await flushDraft("general", tid);
  assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body).knowledge_base_ids, [4, 5]);
  assert.deepEqual(useAgentStore.getState().drafts[productTid].ids, []);
});
test("failed message sends retain text and reuse the message ID on retry", async () => {
  useAgentStore.setState((state) => ({
    drafts: { ...state.drafts, [tid]: { ...state.drafts[tid], text: "Hello" } },
  }));
  const fetch = mock.method(globalThis, "fetch", async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(sendMessage("general", tid, "Hello"), /暂时无法连接/);
  const pendingId = useAgentStore.getState().drafts[tid].pending.id;
  assert.equal(useAgentStore.getState().drafts[tid].text, "Hello");
  assert.equal(useAgentStore.getState().drafts[tid].sending, false);
  fetch.mock.mockImplementation(async (url, init) => {
    assert.equal(JSON.parse(init.body).id, pendingId);
    assert.equal(url, `/api/agents/general/threads/${tid}/messages`);
    return ok({
      ...detail(),
      thread: { ...detail().thread, draft_revision: 1 },
      messages: [
        { id: pendingId, role: "user", content: "Hello", context: { knowledge_bases: [] } },
      ],
    });
  });
  await sendMessage("general", tid, "Hello");
  assert.equal(useAgentStore.getState().details[tid].messages.length, 1);
  assert.equal(useAgentStore.getState().drafts[tid].text, "");
});
test("sending gates rapid duplicates before the draft has finished saving", async () => {
  const response = deferred();
  mock.method(globalThis, "fetch", () => response.promise);
  const sending = sendMessage("general", tid, "");
  await assert.rejects(sendMessage("general", tid, ""), /正在保存/);
  response.resolve(ok(detail()));
  await sending;
});
test("older list responses cannot replace a newer successful rename", async () => {
  const response = deferred();
  mock.method(globalThis, "fetch", (url, init) =>
    init.method === "PATCH"
      ? Promise.resolve(
          ok({ ...detail().thread, title: "Renamed", updated_at: "2026-10-24T01:00:00Z" }),
        )
      : response.promise,
  );
  const loading = loadThreads("general");
  await renameThread("general", tid, "Renamed");
  response.resolve(ok([detail().thread]));
  await loading;
  assert.equal(useAgentStore.getState().lists.general[0].title, "Renamed");
});
test("late responses after an account change cannot replace the next account configuration", async () => {
  const response = deferred();
  mock.method(globalThis, "fetch", () => response.promise);
  const saving = saveAgent("general", agents()[0]);
  useAuthStore.setState({ user: { id: owner + 1, username: "other" } });
  token = "next-token";
  resetAgents();
  useAgentStore.setState({ owner: owner + 1 });
  response.resolve(ok(agents()[0]));
  await assert.rejects(saving, /账号已切换/);
  assert.deepEqual(useAgentStore.getState().agents, []);
});

test("Agent bootstrap requests are shared and restore the server's per-Agent current conversation", async () => {
  resetAgents();
  const response = deferred();
  const fetch = mock.method(globalThis, "fetch", () => response.promise);
  const first = loadAgents();
  const second = loadAgents();
  assert.equal(first, second);
  response.resolve(ok({ agents: agents(), skills: [] }));
  await first;
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(useAgentStore.getState().selected.general, tid);
  assert.equal(useAgentStore.getState().selected.product, productTid);
});
test("selecting a product conversation leaves the general Agent draft and selection intact", async () => {
  setDraftText(tid, "General draft");
  const next = "33333333-3333-4333-8333-333333333333";
  const fetch = mock.method(globalThis, "fetch", async () => ok(detail(next, 2)));
  await selectThread("product", next);
  assert.equal(fetch.mock.calls[0].arguments[0], `/api/agents/product/threads/${next}/activate`);
  assert.equal(useAgentStore.getState().selected.general, tid);
  assert.equal(useAgentStore.getState().drafts[tid].text, "General draft");
  assert.equal(useAgentStore.getState().selected.product, next);
});
