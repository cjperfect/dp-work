import assert from "node:assert/strict";
import { test } from "node:test";
import { toRuntimeMessage } from "../lib/message-branches.ts";
const message = (status, calls) => ({
  id: "reply",
  role: "assistant",
  content: "回答",
  status,
  created_at: new Date().toISOString(),
  context: { tool_calls: calls },
});
const call = {
  id: "call-1",
  name: "read_file",
  args: { path: "/a.txt" },
  started_at: 1000,
  status: "running",
};
test("live tool calls render via assistant-ui and completed calls keep result and duration", () => {
  const live = toRuntimeMessage(message("streaming", [call]));
  assert.equal(live.content[0].type, "tool-call");
  assert.equal(live.content[0].result, undefined);
  const saved = toRuntimeMessage(
    message("complete", [{ ...call, status: "complete", result: "文件内容", ended_at: 1500 }]),
  );
  assert.equal(saved.content[0].result, "文件内容");
  assert.deepEqual(saved.content[0].timing, { startedAt: 1000, completedAt: 1500 });
  assert.equal(saved.content[1].text, "回答");
});
test("failed and interrupted calls remain visible without becoming successful results", () => {
  assert.equal(
    toRuntimeMessage(message("complete", [{ ...call, status: "failed", result: "命令失败" }]))
      .content[0].isError,
    true,
  );
  const stopped = toRuntimeMessage(message("cancelled", [call]));
  assert.equal(stopped.content[0].isError, true);
  assert.match(stopped.content[0].result, /中断/);
  assert.equal(toRuntimeMessage(message("waiting_approval", [call])).content[0].result, undefined);
});

test("reasoning and tool details follow execution order without entering the answer text", () => {
  const row = message("streaming", [
    { ...call, status: "complete", result: "资料", ended_at: 1200 },
  ]);
  row.context.reasoning = [
    { id: "r1", text: "先检查资料", started_at: 900, completed_at: 1000 },
    { id: "r2", text: "根据资料整理", started_at: 1300 },
  ];
  row.context.execution_order = ["reasoning:r1", "tool:call-1", "reasoning:r2"];
  const runtime = toRuntimeMessage(row);
  assert.deepEqual(
    runtime.content.map((part) => part.type),
    ["reasoning", "tool-call", "reasoning", "text"],
  );
  assert.equal(runtime.content[0].status.type, "complete");
  assert.equal(runtime.content[2].status.type, "running");
  assert.equal(runtime.content[3].text, "回答");
});
