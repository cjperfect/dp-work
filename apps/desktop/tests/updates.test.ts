import assert from "node:assert/strict";
import { test } from "node:test";
import { EventEmitter } from "node:events";
import { UpdateManager } from "../src/main/updates/manager";

class FakeUpdater extends EventEmitter {
  autoDownload = true;
  autoInstallOnAppQuit = true;
  allowPrerelease = true;
  allowDowngrade = true;
  checks = 0;
  downloads = 0;
  installs = 0;
  async checkForUpdates() {
    this.checks++;
    this.emit("update-available", { version: "0.2.0" });
    return null;
  }
  async downloadUpdate() {
    this.downloads++;
    this.emit("download-progress", { percent: 50 });
    this.emit("update-downloaded", { version: "0.2.0" });
    return [];
  }
  quitAndInstall() {
    this.installs++;
  }
}
function setup(overrides = {}) {
  const backend = new FakeUpdater(),
    events = [] as { status: string; percent?: number }[];
  const manager = new UpdateManager({
    backend,
    packaged: true,
    platform: "darwin",
    version: "0.1.0",
    emit: (state) => events.push(state),
    prepareInstall: async () => {},
    ...overrides,
  });
  return { backend, manager, events };
}
test("development and unsupported Linux packages never check or download updates", async () => {
  for (const override of [{ packaged: false }, { platform: "linux" }]) {
    const { backend, manager } = setup(override);
    await manager.check();
    await manager.download();
    await manager.install();
    assert.equal(manager.getState().status, "disabled");
    assert.equal(backend.checks + backend.downloads + backend.installs, 0);
  }
});
test("update detection never downloads or installs without an explicit action", async () => {
  const { backend, manager, events } = setup();
  await manager.check();
  assert.equal(manager.getState().status, "available");
  assert.equal(backend.downloads, 0);
  assert.equal(backend.autoDownload, false);
  assert.equal(backend.autoInstallOnAppQuit, false);
  assert.equal(backend.allowPrerelease, false);
  assert.equal(backend.allowDowngrade, false);
  await manager.install();
  assert.equal(backend.installs, 0);
  await manager.download();
  assert.equal(manager.getState().status, "downloaded");
  assert.ok(events.some((state) => state.percent === 50));
  assert.equal(backend.installs, 0);
});
test("install waits for preflight and only launches the verified downloaded package once", async () => {
  let finish!: () => void;
  const cleanup = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const { backend, manager } = setup({ prepareInstall: () => cleanup });
  await manager.check();
  await manager.download();
  const first = manager.install(),
    second = manager.install();
  assert.equal(backend.installs, 0);
  finish();
  await Promise.all([first, second]);
  assert.equal(backend.installs, 1);
});
test("check requests are deduplicated and download errors can retry without exposing upstream text", async () => {
  const { backend, manager } = setup();
  let finish!: () => void;
  backend.checkForUpdates = () =>
    new Promise((resolve) => {
      backend.checks++;
      finish = () => {
        backend.emit("update-available", { version: "0.2.0" });
        resolve(null);
      };
    });
  const one = manager.check(),
    two = manager.check();
  assert.equal(backend.checks, 1);
  finish();
  await Promise.all([one, two]);
  backend.downloadUpdate = async () => {
    backend.emit("error", new Error("private upstream url"));
    throw new Error("private error");
  };
  await manager.download();
  assert.equal(manager.getState().retry, "download");
  assert.doesNotMatch(manager.getState().message!, /private/);
  backend.downloadUpdate = FakeUpdater.prototype.downloadUpdate.bind(backend);
  await manager.download();
  assert.equal(manager.getState().status, "downloaded");
});
test("cleanup failure prevents installation; shutdown ignores late events", async () => {
  const { backend, manager } = setup({
    prepareInstall: async () => {
      throw new Error("busy");
    },
  });
  await manager.check();
  await manager.download();
  await manager.install();
  assert.equal(backend.installs, 0);
  assert.equal(manager.getState().retry, "install");
  manager.close();
  const before = manager.getState();
  backend.emit("error", new Error("late"));
  await manager.check();
  assert.deepEqual(manager.getState(), before);
});

test("active work prevents installation while keeping the downloaded update retryable", async () => {
  const { UpdateBusyError } = await import("../src/main/updates/manager");
  const { backend, manager } = setup({
    prepareInstall: async () => {
      throw new UpdateBusyError();
    },
  });
  await manager.check();
  await manager.download();
  await manager.install();
  assert.equal(backend.installs, 0);
  assert.match(manager.getState().message!, /结束会议/);
  assert.equal(manager.getState().retry, "install");
  assert.equal(manager.getState().availableVersion, "0.2.0");
});
