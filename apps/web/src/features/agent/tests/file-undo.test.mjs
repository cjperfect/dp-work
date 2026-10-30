import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { resetAgents, useAgentStore } from "../../../stores/agent/state.ts";
import { undoFileChange } from "../../../stores/agent/agent-files.ts";

let interceptor, handler, originalStorage;
const change = {
  id: "00000000-0000-0000-0000-000000000001",
  path: "/project/a",
  undoable: true,
  additions: 1,
  deletions: 0,
  lines: [],
};
beforeEach(() => {
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "fixture" : null),
      setItem() {},
    },
  });
  resetAgents();
  useAuthStore.setState({ user: { id: 7, username: "fixture" } });
  const message = {
    id: "reply",
    role: "assistant",
    content: "done",
    context: { file_changes: [change] },
  };
  useAgentStore.setState({
    owner: 7,
    agents: [{ id: 1, code: "general" }],
    details: {
      thread1: {
        thread: { id: "thread1", agent_id: 1, draft_revision: 2, draft: "草稿" },
        messages: [message],
        message_branches: [{ parentId: null, message }],
        knowledge_base_ids: [],
      },
    },
    drafts: { thread1: { text: "仍在输入", version: 0, savedVersion: 0 } },
  });
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => {
      const data = await handler(request);
      return {
        data: data?.code === 409 ? data : { code: 0, data },
        status: data?.code === 409 ? 409 : 200,
        statusText: "OK",
        headers: {},
        config: request,
      };
    };
    return config;
  });
});
afterEach(() => {
  httpClient.interceptors.request.eject(interceptor);
  resetAgents();
  useAuthStore.setState({ user: null });
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete globalThis.localStorage;
});

test("undo updates both visible messages and branches, keeps draft, and takes server revision", async () => {
  handler = async (request) => {
    assert.equal(request.method, "post");
    assert.equal(request.url, `/api/agents/threads/thread1/files/${change.id}/undo`);
    return {
      change: { ...change, undone: true },
      thread: { id: "thread1", agent_id: 1, draft_revision: 3 },
    };
  };
  await undoFileChange("thread1", change.id);
  const state = useAgentStore.getState();
  assert.equal(state.details.thread1.messages[0].context.file_changes[0].undone, true);
  assert.equal(
    state.details.thread1.message_branches[0].message.context.file_changes[0].undone,
    true,
  );
  assert.equal(state.details.thread1.thread.draft_revision, 3);
  assert.equal(state.drafts.thread1.text, "仍在输入");
});

test("undo conflict never marks a change as undone", async () => {
  handler = async () => ({ code: 409, message: "文件已有后续修改", data: null });
  await assert.rejects(undoFileChange("thread1", change.id), /后续修改/);
  assert.equal(
    useAgentStore.getState().details.thread1.messages[0].context.file_changes[0].undone,
    undefined,
  );
});
