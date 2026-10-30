import { saveComposerDraft as setDraftText } from "../../../stores/agent/agent-message-queue.ts";
import { useAgentApprovalStore } from "../../../stores/agent/agent-approvals.ts";
import { ensureTestChat as ensureAgentChat } from "./conversation-fixture.mjs";
import assert from "node:assert/strict";
import { beforeEach, afterEach, test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { cancelMessage, resumeApprovedRun, sendMessage } from "../../../stores/agent/agent-send.ts";
import { resetAgents, useAgentStore } from "../../../stores/agent/state.ts";
import {
  enqueueFollowUp,
  guideQueuedMessage,
  initializeMessageQueue,
  useAgentMessageQueue,
  saveComposerDraft,
  continueMessageQueue,
  waitingForApproval,
  removeQueuedMessage,
} from "../../../stores/agent/agent-message-queue.ts";
import { conversationFixture } from "./conversation-fixture.mjs";

let storage, interceptor, values, controls, sent, backend, cancelHandler, guides;
const until = async (condition) => {
  for (let i = 0; i < 500; i++) {
    if (condition()) return;
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
  assert.fail("queue state did not settle");
};
beforeEach(() => {
  storage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  values = new Map();
  controls = [];
  sent = [];
  backend = conversationFixture();
  guides = [];
  cancelHandler = async () => null;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) =>
        key === "dp-work.auth.token" ? "fixture-token" : (values.get(key) ?? null),
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  });
  useAuthStore.setState({ user: { id: 1, username: "queue-test" } });
  resetAgents();
  initializeMessageQueue();
  interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => ({
      data: await backend.handle(request, async (req) => {
        if (req.url.endsWith("/cancel")) return cancelHandler(req);
        if (req.url.endsWith("/steer")) {
          const message = typeof req.data === "string" ? JSON.parse(req.data) : req.data;
          guides.push(message);
          return { id: message.id, status: "queued" };
        }
        if (req.url.endsWith("/decide")) {
          return new ReadableStream({
            start(controller) {
              controls.push(controller);
            },
          });
        }
        if (!req.url.endsWith("/chat")) return [];
        const body = typeof req.data === "string" ? JSON.parse(req.data) : req.data;
        sent.push(body.messages.at(-1).content);
        return new ReadableStream({
          start(controller) {
            controls.push(controller);
            controller.enqueue(
              new TextEncoder().encode(
                `data: ${JSON.stringify({ type: "start", run_id: crypto.randomUUID() })}\n\n`,
              ),
            );
            req.signal.addEventListener("abort", () => controller.error(new Error("cancelled")), {
              once: true,
            });
          },
        });
      }),
      status: 200,
      statusText: "OK",
      config: request,
      headers: {},
    });
    return config;
  });
});
afterEach(() => {
  resetAgents();
  useAuthStore.setState({ user: null });
  httpClient.interceptors.request.eject(interceptor);
  if (storage) Object.defineProperty(globalThis, "localStorage", storage);
  else delete globalThis.localStorage;
});
function complete(index, text = "回答") {
  controls[index].enqueue(
    new TextEncoder().encode(`data: ${JSON.stringify({ type: "done", content: text })}\n\n`),
  );
  controls[index].close();
}
async function start() {
  await ensureAgentChat("general");
  const id = useAgentStore.getState().selected.general;
  const task = sendMessage("general", id, "第一条");
  await until(() => controls.length === 1);
  return { id, task };
}

test("messages drain in order without erasing text typed during generation", async () => {
  const { id, task } = await start();
  enqueueFollowUp(id, "第二条");
  enqueueFollowUp(id, "第三条");
  setDraftText(id, "尚未提交的草稿");
  assert.equal(useAgentMessageQueue.getState().drafts[id], "尚未提交的草稿");
  complete(0);
  await task;
  await until(() => controls.length === 2);
  assert.deepEqual(sent, ["第一条", "第二条"]);
  complete(1);
  await until(() => controls.length === 3);
  complete(2);
  await until(() => !useAgentStore.getState().sending[id]);
  assert.deepEqual(sent, ["第一条", "第二条", "第三条"]);
  assert.equal(useAgentMessageQueue.getState().drafts[id], "尚未提交的草稿");
  assert.equal(backend.details.get(id).thread.draft, "");
});

test("guidance stays in the same stream and is removed only after it takes effect", async () => {
  const { id, task } = await start();
  enqueueFollowUp(id, "继续等候");
  const guidance = enqueueFollowUp(id, "按钮改成黑色");
  await guideQueuedMessage(id, guidance);
  assert.equal(controls.length, 1);
  assert.equal(guides.length, 1);
  assert.equal(
    useAgentMessageQueue.getState().items[id].find((row) => row.id === guidance).mode,
    "steering",
  );
  const detail = backend.details.get(id);
  const previous = detail.messages.at(-1);
  const context = { ...previous.context, steering_status: "applied", steering_run_id: "same-run" };
  const event = {
    type: "steering",
    id: guidance,
    response_id: guidance + "-reply",
    previous_response_id: previous.id,
    previous_content: "已读取资料",
    previous_removed: false,
    thread: { ...detail.thread, draft_revision: detail.thread.draft_revision + 1 },
    message: {
      id: guidance,
      role: "user",
      content: "按钮改成黑色",
      status: "complete",
      context,
      created_at: new Date().toISOString(),
    },
    response: {
      id: guidance + "-reply",
      role: "assistant",
      content: "",
      status: "streaming",
      context: previous.context,
      created_at: new Date().toISOString(),
    },
  };
  controls[0].enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
  await until(() => !useAgentMessageQueue.getState().items[id].some((row) => row.id === guidance));
  assert.equal(useAgentStore.getState().details[id].messages.at(-2).content, "按钮改成黑色");
  complete(0, "已按补充要求完成");
  await task;
  await until(() => controls.length === 2);
  assert.deepEqual(sent, ["第一条", "继续等候"]);
  complete(1);
  await until(() => !useAgentStore.getState().sending[id]);
  const saved = backend.details.get(id).messages;
  assert.equal(saved.filter((row) => row.id === guidance).length, 1);
  assert.equal(saved.find((row) => row.id === guidance + "-reply").content, "已按补充要求完成");
});

test("stop still waits for API cancellation and leaves follow-up messages paused", async () => {
  const { id, task } = await start();
  enqueueFollowUp(id, "稍后继续发送");
  let release;
  cancelHandler = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  cancelMessage(id);
  await until(() => !!release);
  assert.equal(controls.length, 1);
  assert.equal(useAgentStore.getState().sending[id], true);
  release(null);
  await task;
  assert.equal(useAgentMessageQueue.getState().paused[id], true);
  continueMessageQueue(id);
  await until(() => controls.length === 2);
  complete(1);
  await until(() => !useAgentStore.getState().sending[id]);
});

test("a restored queue stays paused and is isolated from another account", async () => {
  const { id, task } = await start();
  enqueueFollowUp(id, "等待刷新恢复");
  saveComposerDraft(id, "正在输入");
  useAuthStore.setState({ user: { id: 2 } });
  assert.deepEqual(useAgentMessageQueue.getState().items, {});
  useAuthStore.setState({ user: { id: 1 } });
  assert.equal(useAgentMessageQueue.getState().items[id][0].text, "等待刷新恢复");
  assert.equal(useAgentMessageQueue.getState().drafts[id], "正在输入");
  assert.equal(useAgentMessageQueue.getState().paused[id], true);
  complete(0);
  await task;
  assert.equal(sent.length, 1);
});

test("failure pauses the queue and keeps unsent messages for retry", async () => {
  const { id, task } = await start();
  enqueueFollowUp(id, "排队消息");
  complete(0);
  await task;
  await until(() => controls.length === 2);
  controls[1].enqueue(
    new TextEncoder().encode('data: {"type":"error","message":"模型暂不可用"}\n\n'),
  );
  controls[1].close();
  await until(() => useAgentMessageQueue.getState().paused[id]);
  assert.equal(useAgentMessageQueue.getState().items[id][0].text, "排队消息");
  continueMessageQueue(id);
  await until(() => controls.length === 3);
  complete(2);
  await until(() => !useAgentStore.getState().sending[id]);
});

for (const decision of ["approve", "reject"]) {
  test(`guidance unlocks when ${decision} is acknowledged, before the resumed reply finishes`, async () => {
    const { id, task } = await start();
    complete(0);
    await task;
    const detail = backend.details.get(id);
    detail.messages.at(-1).status = "waiting_approval";
    useAgentStore.setState((state) => ({
      details: { ...state.details, [id]: structuredClone(detail) },
    }));
    const approval = {
      id: crypto.randomUUID(),
      run_id: crypto.randomUUID(),
      conversation_id: id,
      response_id: detail.messages.at(-1).id,
      status: "pending",
      actionable: true,
      interrupts: [],
      created_at: new Date().toISOString(),
      decided_at: null,
    };
    useAgentApprovalStore.setState({
      entries: { [id]: { items: [approval], loading: false, error: null } },
    });
    const resumed = resumeApprovedRun(approval, decision);
    await until(() => controls.length === 2);
    assert.equal(
      waitingForApproval(id),
      true,
      "must stay locked until the server confirms resuming",
    );
    controls[1].enqueue(
      new TextEncoder().encode(
        `data: ${JSON.stringify({ type: "start", run_id: approval.run_id })}\n\n`,
      ),
    );
    await until(() => !waitingForApproval(id));
    assert.equal(useAgentStore.getState().sending[id], true);
    assert.equal(
      useAgentApprovalStore.getState().entries[id].items[0].status,
      decision === "approve" ? "approved" : "rejected",
    );
    const guideId = enqueueFollowUp(id, "恢复后可以引导");
    await guideQueuedMessage(id, guideId);
    assert.equal(guides.length, 1);
    removeQueuedMessage(id, guideId);
    detail.messages.at(-1).status = "complete";
    complete(1);
    await resumed;
  });
}
