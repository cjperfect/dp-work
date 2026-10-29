import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  connectDesktopUpdates,
  runDesktopUpdate,
  useDesktopUpdates,
} from "../../../stores/desktop-updates.ts";
const original = Object.getOwnPropertyDescriptor(globalThis, "window");
afterEach(() => {
  if (original) Object.defineProperty(globalThis, "window", original);
  else delete globalThis.window;
  useDesktopUpdates.setState({ open: false, update: null, error: null });
});
const state = (revision, status) => ({
  revision,
  status,
  currentVersion: "0.1.0",
  availableVersion: "0.2.0",
});
test("late startup snapshots and late action responses never overwrite newer download events", async () => {
  let event, finishSnapshot, finishCheck;
  let disposed = false;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      desktop: {
        onUpdateState(listener) {
          event = listener;
          return () => {
            disposed = true;
          };
        },
        getUpdateState: () =>
          new Promise((resolve) => {
            finishSnapshot = resolve;
          }),
        checkForUpdates: () =>
          new Promise((resolve) => {
            finishCheck = resolve;
          }),
      },
    },
  });
  const close = connectDesktopUpdates();
  event(state(2, "available"));
  finishSnapshot(state(0, "idle"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(useDesktopUpdates.getState().update.status, "available");
  const request = runDesktopUpdate("check");
  event(state(4, "downloaded"));
  finishCheck(state(3, "available"));
  await request;
  assert.equal(useDesktopUpdates.getState().update.status, "downloaded");
  close();
  assert.ok(disposed);
});
test("ordinary browsers cannot initiate native update operations", async () => {
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  const dispose = connectDesktopUpdates();
  dispose();
  await runDesktopUpdate("install");
  assert.match(useDesktopUpdates.getState().error, /桌面安装版/);
});
