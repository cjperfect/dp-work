import assert from "node:assert/strict";
import { test } from "node:test";
import { isContinuationRequest } from "../lib/continuation.ts";

test("only explicit standalone continuation instructions trigger checkpoint lookup", () => {
  for (const text of [
    "接着执行",
    "请继续运行。",
    "继续",
    "继续处理吧",
    "接着上次的任务",
    "resume",
    "Keep going!",
  ])
    assert.equal(isContinuationRequest(text), true, text);
  for (const text of [
    "你好",
    "继续删除所有文件",
    "接着执行，但换成另一个项目",
    "解释一下接着执行怎么做",
    "",
    "不要继续",
  ])
    assert.equal(isContinuationRequest(text), false, text);
});
