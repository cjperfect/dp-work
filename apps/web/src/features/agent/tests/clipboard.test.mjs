import assert from "node:assert/strict";
import { test } from "node:test";
import { copyMessageText } from "../../../lib/clipboard.ts";

test("copy uses native desktop clipboard, browser fallback, and propagates failure", async () => {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const writes = [];
  try {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { desktop: { writeClipboard: async (text) => writes.push(["native", text]) } },
    });
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: { clipboard: { writeText: async (text) => writes.push(["browser", text]) } },
    });
    await copyMessageText("原始回复");
    delete window.desktop;
    await copyMessageText("浏览器回复");
    assert.deepEqual(writes, [
      ["native", "原始回复"],
      ["browser", "浏览器回复"],
    ]);
    navigator.clipboard.writeText = async () => {
      throw new Error("denied");
    };
    await assert.rejects(copyMessageText("不能复制"), /denied/);
  } finally {
    if (windowDescriptor) Object.defineProperty(globalThis, "window", windowDescriptor);
    else delete globalThis.window;
    if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    else delete globalThis.navigator;
  }
});
