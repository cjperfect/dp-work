import { saveComposerDraft as setDraftText } from "../../../stores/agent/agent-message-queue.ts";
import { useAgentMessageQueue } from "../../../stores/agent/agent-message-queue.ts";
import { ensureTestChat as ensureAgentChat } from "./conversation-fixture.mjs";
import { conversationFixture } from "./conversation-fixture.mjs";
import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { streamAgentChat } from "../../../apis/agents.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  cancelMessage,
  sendMessage,
  editMessage,
  regenerateMessage,
} from "../../../stores/agent/agent-send.ts";
import { selectMessageBranch, collectMessageBranches } from "../../../stores/agent/agent-files.ts";
import { generateThreadTitle, renameThread } from "../../../stores/agent/agent-threads.ts";
import { useAgentStore, resetAgents } from "../../../stores/agent/state.ts";

let interceptor;
let handler;
let originalStorage;
let backend;
const input = {
  agent_code: "general",
  thread_id: "one",
  response_id: "one-reply",
  messages: [{ role: "user", content: "你好" }],
};
const event = (value) => `data: ${JSON.stringify(value)}\n\n`;
function response(events) {
  const bytes = new TextEncoder().encode(events);
  return new ReadableStream({
    start(controller) {
      // 每个字节一个分片，覆盖中文 UTF-8 和 SSE 分隔符被拆开的情况。
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
}
beforeEach(() => {
  originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "fixture-token" : null),
      setItem() {},
    },
  });
  useAuthStore.setState({ user: { id: 1, username: "tester" } });
  resetAgents();
  handler = async () =>
    response(
      event({ type: "delta", text: "真实链路的测试回答" }) +
        event({ type: "done", content: "真实链路的测试回答" }),
    );
  backend = conversationFixture();
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => ({
      data:
        request.url === "/api/agents/threads/one/chat"
          ? await handler(request)
          : await backend.handle(request, handler),
      status: 200,
      statusText: "OK",
      config: request,
      headers: {},
    });
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
test("stream decodes fragmented UTF-8 and requires a completion event", async () => {
  const deltas = [];
  assert.equal(
    await streamAgentChat(input, (text) => deltas.push(text), new AbortController().signal),
    "真实链路的测试回答",
  );
  assert.equal(deltas.join(""), "真实链路的测试回答");
  handler = async () => response(event({ type: "delta", text: "partial" }));
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /中断/,
  );
});
test("server errors preserve safe messages and old-account responses are rejected", async () => {
  handler = async () => response(event({ type: "error", message: "模型请求受限，请稍后重试。" }));
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /请求受限/,
  );
  handler = async () => {
    useAuthStore.setState({ user: { id: 2 } });
    return response(event({ type: "done", content: "old account" }));
  };
  await assert.rejects(
    streamAgentChat(input, () => {}, new AbortController().signal),
    /登录状态已改变/,
  );
});
test("chat store forwards real history and keeps streamed replies without mock text", async () => {
  const requests = [];
  handler = async (config) => {
    requests.push(JSON.parse(config.data));
    return response(
      event({ type: "delta", text: "回复" }) + event({ type: "done", content: "回复" }),
    );
  };
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "第一问");
  await sendMessage("general", id, "第二问");
  assert.equal(requests[1].messages.length, 3);
  assert.deepEqual(
    requests[1].messages.map((row) => row.role),
    ["user", "assistant", "user"],
  );
  const messages = useAgentStore.getState().details[id].messages;
  assert.equal(messages.length, 4);
  assert.equal(messages.at(-1).content, "回复");
  assert.equal(messages.at(-1).status, "complete");
  assert.equal(useAgentStore.getState().sending[id], false);
});
test("failed runs can retry without duplicating the user message", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  handler = async () =>
    response(
      event({ type: "delta", text: "partial" }) +
        event({ type: "error", message: "temporary failure" }),
    );
  await assert.rejects(sendMessage("general", id, "重试同一问题"), /temporary failure/);
  assert.equal(useAgentStore.getState().details[id].messages.at(-1).status, "failed");
  handler = async () => response(event({ type: "done", content: "成功回答" }));
  await sendMessage("general", id, "重试同一问题");
  assert.equal(useAgentStore.getState().details[id].messages.length, 2);
  assert.equal(useAgentStore.getState().details[id].messages.at(-1).content, "成功回答");
});

test("stopping generation preserves partial text and clears the running state", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  handler = async () => response(event({ type: "delta", text: "partial" }));
  const unsubscribe = useAgentStore.subscribe((state) => {
    if (state.details[id]?.messages.at(-1)?.content === "partial") cancelMessage(id);
  });
  try {
    await sendMessage("general", id, "停止测试");
    assert.equal(useAgentStore.getState().sending[id], false);
    assert.equal(useAgentStore.getState().details[id].messages.at(-1).status, "cancelled");
    assert.equal(useAgentStore.getState().details[id].messages.at(-1).content, "partial");
    const stoppedId = useAgentStore.getState().details[id].messages.at(-1).id;
    unsubscribe();
    handler = async () => response(event({ type: "done", content: "继续完成剩余工作" }));
    await sendMessage("general", id, "接着运行");
    const messages = useAgentStore.getState().details[id].messages;
    assert.equal(messages.at(-2).content, "接着运行");
    assert.notEqual(messages.at(-1).id, stoppedId);
    assert.equal(messages.find((message) => message.id === stoppedId).status, "cancelled");
    assert.equal(messages.at(-1).status, "complete");
  } finally {
    unsubscribe();
  }
});

test("chat uses the Agent's current knowledge selection and sends numeric server IDs", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  const seen = [];
  handler = async (request) => {
    seen.push(JSON.parse(request.data));
    return response(event({ type: "done", content: "有引用的回答" }));
  };
  useAgentStore.setState((state) => ({
    agents: state.agents.map((agent) =>
      agent.code === "general" ? { ...agent, knowledge_base_ids: ["server-42"] } : agent,
    ),
  }));
  await sendMessage("general", id, "检索关联知识库");
  assert.deepEqual(seen[0].knowledge_base_ids, [42]);
  useAgentStore.setState((state) => ({
    agents: state.agents.map((agent) =>
      agent.code === "general" ? { ...agent, knowledge_base_ids: [] } : agent,
    ),
  }));
  await sendMessage("general", id, "不检索知识库");
  assert.deepEqual(seen[1].knowledge_base_ids, []);
});

test("editing an earlier message regenerates from its preceding context without stale replies", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "第一问");
  await sendMessage("general", id, "第二问");
  await sendMessage("general", id, "第三问");
  const original = useAgentStore.getState().details[id].messages;
  const requests = [];
  handler = async (config) => {
    requests.push(JSON.parse(config.data));
    return response(event({ type: "done", content: "根据修改内容重新回答" }));
  };
  await editMessage("general", id, original[2].id, "修改后的第二问");
  assert.deepEqual(
    requests[0].messages.map((row) => row.content),
    ["第一问", original[1].content, "修改后的第二问"],
  );
  const updated = useAgentStore.getState().details[id].messages;
  assert.equal(updated.length, 4);
  assert.equal(updated[2].content, "修改后的第二问");
  assert.equal(updated[3].content, "根据修改内容重新回答");
  await assert.rejects(editMessage("general", id, updated[1].id, "不能编辑助手"), /用户消息/);
  await assert.rejects(editMessage("product", id, updated[0].id, "错误 Agent"), /不匹配/);
  await assert.rejects(editMessage("general", id, updated[0].id, "  "), /请输入/);
  assert.equal(useAgentStore.getState().details[id].messages.length, 4);
});

test("failed edited messages can retry without restoring the stale continuation", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "原问题");
  const originalId = useAgentStore.getState().details[id].messages[0].id;
  handler = async () => response(event({ type: "error", message: "临时故障" }));
  await assert.rejects(editMessage("general", id, originalId, "修改后的问题"), /临时故障/);
  handler = async () => response(event({ type: "done", content: "重试成功" }));
  await sendMessage("general", id, "修改后的问题");
  const messages = useAgentStore.getState().details[id].messages;
  assert.equal(messages.length, 2);
  assert.equal(messages[0].content, "修改后的问题");
  assert.equal(messages[1].content, "重试成功");
});

test("LLM titles are generated once and persisted to the API thread", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "如何设计知识库检索工具？");
  const requests = [];
  let resolve;
  handler = async (request) => {
    requests.push(JSON.parse(request.data));
    return new Promise((done) => {
      resolve = () => done({ code: 0, data: { title: "知识库检索工具设计" } });
    });
  };
  const first = generateThreadTitle(id);
  const second = generateThreadTitle(id);
  assert.equal(first, second);
  await new Promise(setImmediate);
  resolve();
  assert.equal(await first, "知识库检索工具设计");
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].messages, [{ role: "user", content: "如何设计知识库检索工具？" }]);
  assert.equal(useAgentStore.getState().details[id].thread.title_source, "generated");
  assert.equal(await generateThreadTitle(id), "知识库检索工具设计");
  assert.equal(requests.length, 1);
});

test("a late generated title cannot override a manual rename", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "原问题");
  let resolve;
  handler = async () =>
    new Promise((done) => {
      resolve = () => done({ code: 0, data: { title: "模型标题" } });
    });
  const pending = generateThreadTitle(id);
  await new Promise(setImmediate);
  await renameThread("general", id, "手动命名");
  resolve();
  assert.equal(await pending, "手动命名");
  assert.equal(useAgentStore.getState().details[id].thread.title, "手动命名");
  assert.equal(useAgentStore.getState().details[id].thread.title_source, "manual");
});

test("a title response from the previous account cannot update thread metadata", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "标题隔离测试");
  let resolve;
  handler = async () =>
    new Promise((done) => {
      resolve = () => done({ code: 0, data: { title: "旧账号标题" } });
    });
  const pending = generateThreadTitle(id);
  await new Promise(setImmediate);
  useAuthStore.setState({ user: { id: 2, username: "other" } });
  resolve();
  assert.equal(await pending, undefined);
  assert.equal(useAgentStore.getState().details[id].thread.title, "新会话");
});

test("branches keep original continuations and later sends use only the selected path", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "原始问题");
  await sendMessage("general", id, "原分支后续问题");
  const original = useAgentStore.getState().details[id].messages;
  await editMessage("general", id, original[0].id, "修改后的问题");
  const edited = useAgentStore.getState().details[id].messages;
  assert.equal(edited.length, 2);
  const all = collectMessageBranches(edited, useAgentStore.getState().details[id].message_branches);
  assert.equal(all.length, 6);
  selectMessageBranch(
    id,
    original.map((message) => message.id),
    all,
  );
  assert.equal(useAgentStore.getState().details[id].messages[2].content, "原分支后续问题");
  const requests = [];
  handler = async (request) => {
    requests.push(JSON.parse(request.data));
    return response(event({ type: "done", content: "继续原分支" }));
  };
  await sendMessage("general", id, "在原分支继续提问");
  assert.ok(requests[0].messages.some((message) => message.content === "原分支后续问题"));
  assert.ok(!requests[0].messages.some((message) => message.content === "修改后的问题"));
  const current = useAgentStore.getState().details[id];
  selectMessageBranch(
    id,
    edited.map((message) => message.id),
    collectMessageBranches(current.messages, current.message_branches),
  );
  assert.deepEqual(
    useAgentStore.getState().details[id].messages.map((message) => message.content),
    edited.map((message) => message.content),
  );
  assert.throws(() => selectMessageBranch(id, [edited[1].id], all), /分支无效/);
});

test("message versions and selected branch survive reloading API history", async () => {
  const values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) =>
        key === "dp-work.auth.token" ? "fixture-token" : (values.get(key) ?? null),
      setItem: (key, value) => values.set(key, value),
    },
  });
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "旧版本");
  const original = useAgentStore.getState().details[id].messages;
  await editMessage("general", id, original[0].id, "新版本");
  let current = useAgentStore.getState().details[id];
  selectMessageBranch(
    id,
    original.map((message) => message.id),
    collectMessageBranches(current.messages, current.message_branches),
  );
  await new Promise(setImmediate);
  resetAgents();
  await ensureAgentChat("general");
  current = useAgentStore.getState().details[id];
  assert.equal(current.messages[0].content, "旧版本");
  assert.equal(current.message_branches.length, 4);
  const root = current.message_branches.find((entry) => entry.message.content === "新版本");
  const reply = current.message_branches.find((entry) => entry.parentId === root.message.id);
  selectMessageBranch(id, [root.message.id, reply.message.id], current.message_branches);
  assert.equal(useAgentStore.getState().details[id].messages[0].content, "新版本");
});

test("approval suspends the stream without treating the pause as a failure", async () => {
  handler = async () =>
    response(event({ type: "approval", approval_id: "approval-one", interrupts: [] }));
  const result = await streamAgentChat(
    input,
    () => assert.fail("pause must not generate text"),
    new AbortController().signal,
  );
  assert.equal(result, null);
});

test("SSE forwards persisted tool traces without mixing them into reply text", async () => {
  const change = {
    id: "change1",
    path: "a.txt",
    additions: 1,
    deletions: 0,
    lines: [{ kind: "added", text: "文件" }],
  };
  const trace = {
    id: "c1",
    name: "read_file",
    args: { path: "/a.txt" },
    started_at: 1000,
    status: "running",
  };
  handler = async () =>
    response(
      event({ type: "tool_call", trace }) +
        event({ type: "file_change", change }) +
        event({
          type: "tool_result",
          trace: { ...trace, status: "complete", result: "文件", ended_at: 1200 },
        }) +
        event({ type: "delta", text: "回答" }) +
        event({ type: "done", content: "回答" }),
    );
  const changes = [],
    calls = [],
    text = [];
  const result = await streamAgentChat(
    input,
    (delta) => text.push(delta),
    new AbortController().signal,
    undefined,
    undefined,
    (call) => calls.push(call),
    (file) => changes.push(file),
  );
  assert.equal(result, "回答");
  assert.deepEqual(text, ["回答"]);
  assert.deepEqual(changes, [change]);
  assert.deepEqual(
    calls.map((call) => call.status),
    ["running", "complete"],
  );
});

test("regeneration preserves the user node, old response branch and composer draft", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "第一问");
  await sendMessage("general", id, "第二问");
  const original = useAgentStore.getState().details[id].messages;
  setDraftText(id, "正在输入的内容");
  const requests = [];
  handler = async (config) => {
    requests.push(JSON.parse(config.data));
    return response(event({ type: "done", content: "重新生成的回答" }));
  };
  await regenerateMessage("general", id, original[0].id);
  const detail = useAgentStore.getState().details[id];
  assert.equal(detail.messages.length, 2);
  assert.equal(detail.messages[0].id, original[0].id);
  assert.equal(detail.messages[1].content, "重新生成的回答");
  assert.notEqual(detail.messages[1].id, original[1].id);
  assert.deepEqual(
    requests[0].messages.map((row) => row.content),
    ["第一问"],
  );
  assert.equal(useAgentMessageQueue.getState().drafts[id], "正在输入的内容");
  const branches = collectMessageBranches(detail.messages, detail.message_branches);
  assert.ok(branches.some((entry) => entry.message.id === original[1].id));
  await assert.rejects(regenerateMessage("general", id, "missing"), /原消息不存在/);
});

test("reasoning SSE is delivered separately and never concatenated into the answer", async () => {
  handler = async () =>
    response(
      event({ type: "reasoning", id: "r1", text: "先查看资料", started_at: 1000 }) +
        event({ type: "reasoning_end", id: "r1", started_at: 1000, completed_at: 1200 }) +
        event({ type: "delta", text: "最终回答" }) +
        event({ type: "done", content: "最终回答" }),
    );
  const thoughts = [],
    answers = [];
  const result = await streamAgentChat(
    input,
    (text) => answers.push(text),
    new AbortController().signal,
    undefined,
    undefined,
    undefined,
    undefined,
    (event) => thoughts.push(event),
  );
  assert.equal(result, "最终回答");
  assert.deepEqual(answers, ["最终回答"]);
  assert.deepEqual(
    thoughts.map((event) => event.type),
    ["reasoning", "reasoning_end"],
  );
  assert.equal(thoughts[0].text, "先查看资料");
});

test("reported usage SSE stays separate from assistant reply text", async () => {
  const usage = { run_id: "usage-one", input_tokens: 100, output_tokens: 20, total_tokens: 120 };
  handler = async () =>
    response(
      event({ type: "usage", usage }) +
        event({ type: "delta", text: "回答" }) +
        event({ type: "done", content: "回答" }),
    );
  const values = [];
  const text = await streamAgentChat(
    input,
    () => {},
    new AbortController().signal,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    (value) => values.push(value),
  );
  assert.equal(text, "回答");
  assert.deepEqual(values, [usage]);
});

test("ordinary chat requires a response record and never falls back to a direct endpoint", async () => {
  let called = false;
  handler = async (config) => {
    called = true;
    assert.equal(config.url, "/api/agents/threads/one/chat");
    return response(event({ type: "done", content: "回复" }));
  };
  await assert.rejects(
    streamAgentChat({ ...input, response_id: undefined }, () => {}, new AbortController().signal),
    /回复记录缺失/,
  );
  assert.equal(called, false);
  assert.equal(await streamAgentChat(input, () => {}, new AbortController().signal), "回复");
});

test("approval continuation keeps its own endpoint without requiring a response record", async () => {
  handler = async (config) => {
    assert.equal(config.url, "/api/agents/approvals/approval-one/decide");
    assert.deepEqual(JSON.parse(config.data), { decision: "approve" });
    return response(event({ type: "done", content: "继续执行" }));
  };
  assert.equal(
    await streamAgentChat(
      {
        ...input,
        response_id: undefined,
        approval_request: { id: "approval-one", decision: "approve" },
      },
      () => {},
      new AbortController().signal,
    ),
    "继续执行",
  );
});

test("compaction progress is delivered separately and updates only its reply", async () => {
  const { applyCompaction } = await import("../../../stores/agent/agent-files.ts");
  useAgentStore.setState({
    details: {
      one: {
        messages: [
          { id: "one-reply", context: {}, status: "streaming" },
          { id: "old-reply", context: {}, status: "complete" },
        ],
      },
      other: { messages: [{ id: "other-reply", context: {}, status: "streaming" }] },
    },
  });
  handler = async () =>
    response(
      event({ type: "compaction", id: "compact-one", status: "running" }) +
        event({ type: "compaction", id: "compact-one", status: "complete" }) +
        event({ type: "delta", text: "正式回答" }) +
        event({ type: "done", content: "正式回答" }),
    );
  const progress = [],
    text = [];
  const result = await streamAgentChat(
    input,
    (delta) => text.push(delta),
    new AbortController().signal,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    (value) => {
      progress.push(value.status);
      applyCompaction("one", "one-reply", value);
      assert.equal(
        useAgentStore.getState().details.one.messages[0].context.compaction.status,
        value.status,
      );
    },
  );
  assert.deepEqual(progress, ["running", "complete"]);
  assert.deepEqual(text, ["正式回答"]);
  assert.equal(result, "正式回答");
  assert.equal(useAgentStore.getState().details.one.messages[1].context.compaction, undefined);
  assert.equal(useAgentStore.getState().details.other.messages[0].context.compaction, undefined);
});

test("checkpoint resume replaces partial output and keeps original messages and run", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "保存文件后继续说明");
  const detail = useAgentStore.getState().details[id];
  const replyId = detail.messages.at(-1).id;
  const remote = backend.details.get(id).messages.at(-1);
  remote.status = "cancelled";
  remote.context.recovery = { run_id: "original-run" };
  const seen = [];
  handler = async (request) => {
    seen.push({ url: request.url, body: JSON.parse(request.data) });
    return response(
      event({ type: "start", run_id: "original-run" }) +
        event({ type: "restore", content: "文件已保存。" }) +
        event({ type: "delta", text: "继续完成。" }) +
        event({ type: "done", content: "文件已保存。继续完成。" }),
    );
  };
  const contents = [];
  const unsubscribe = useAgentStore.subscribe((state) =>
    contents.push(state.details[id]?.messages.at(-1)?.content),
  );
  try {
    await sendMessage("general", id, "接着执行");
  } finally {
    unsubscribe();
  }
  assert.equal(seen[0].url, `/api/agents/threads/${id}/resume`);
  assert.equal(seen[0].body.run_id, "original-run");
  const saved = useAgentStore.getState().details[id];
  assert.equal(saved.messages.length, 2);
  assert.equal(saved.messages.at(-1).id, replyId);
  assert.equal(saved.messages.at(-1).content, "文件已保存。继续完成。");
  assert.ok(contents.includes("文件已保存。"));
  assert.ok(contents.includes("文件已保存。继续完成。"));
  assert.equal(useAgentStore.getState().sending[id], false);
});

test("continue checks authoritative unfinished task before resuming without creating new messages", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "执行原任务");
  const remote = backend.details.get(id);
  const reply = remote.messages.at(-1);
  reply.status = "cancelled";
  reply.context.recovery = { run_id: "unfinished-run" };
  const seen = [];
  handler = async (request) => {
    seen.push({ url: request.url, body: JSON.parse(request.data) });
    return response(
      event({ type: "start", run_id: "unfinished-run" }) +
        event({ type: "restore", content: "" }) +
        event({ type: "done", content: "原任务继续完成" }),
    );
  };
  // 页面仍然缓存 complete；必须先查询本机服务才能发现未完成任务。
  assert.equal(useAgentStore.getState().details[id].messages.at(-1).status, "complete");
  await sendMessage("general", id, "接着执行");
  assert.equal(seen.length, 1);
  assert.equal(seen[0].url, `/api/agents/threads/${id}/resume`);
  assert.equal(seen[0].body.run_id, "unfinished-run");
  assert.equal(seen[0].body.instruction, "接着执行");
  assert.equal(useAgentStore.getState().details[id].messages.length, 2);
  assert.equal(useAgentStore.getState().sending[id], false);
});

test("continue with no unfinished task uses normal chat and ignores stale local recovery", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "已经完成的任务");
  useAgentStore.setState((state) => ({
    details: {
      ...state.details,
      [id]: {
        ...state.details[id],
        messages: state.details[id].messages.map((row) =>
          row.role === "assistant"
            ? {
                ...row,
                status: "cancelled",
                context: { ...row.context, recovery: { run_id: "stale" } },
              }
            : row,
        ),
      },
    },
  }));
  const requests = [];
  handler = async (request) => {
    requests.push(request.url);
    return response(event({ type: "done", content: "普通新一轮" }));
  };
  await sendMessage("general", id, "接着执行");
  assert.deepEqual(requests, [`/api/agents/threads/${id}/chat`]);
  assert.equal(useAgentStore.getState().details[id].messages.length, 4);
});

test("unsafe resume failure never falls back to a new task", async () => {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  await sendMessage("general", id, "执行任务");
  const reply = backend.details.get(id).messages.at(-1);
  reply.status = "cancelled";
  reply.context.recovery = { run_id: "uncertain-run" };
  const requests = [];
  handler = async (request) => {
    requests.push(request.url);
    return response(event({ type: "error", message: "工具结果未确认，已阻止重复执行" }));
  };
  await assert.rejects(sendMessage("general", id, "继续运行"), /工具结果未确认/);
  assert.deepEqual(requests, [`/api/agents/threads/${id}/resume`]);
  assert.equal(useAgentStore.getState().details[id].messages.length, 2);
  assert.equal(useAgentStore.getState().sending[id], false);
});
