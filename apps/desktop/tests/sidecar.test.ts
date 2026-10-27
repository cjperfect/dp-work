import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import os from "node:os";
import { setTimeout as delay } from "node:timers/promises";
import { SidecarManager } from "../src/main/sidecar/manager";
import { sidecarOptions, type SidecarOptions } from "../src/main/sidecar/config";

const fixture = path.resolve("tests/fixtures/sidecar.mjs");

async function port(): Promise<number> {
  const server = http.createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address !== "string");
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return address.port;
}

async function until(check: () => boolean | Promise<boolean>, timeout = 6000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await check()) return;
    await delay(30);
  }
  assert.fail("等待子进程状态超时");
}

function alive(pid: number) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function context(t: TestContext, env: NodeJS.ProcessEnv = {}) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "dp-sidecar-"));
  const options: SidecarOptions = {
    command: process.execPath,
    args: [fixture],
    cwd: process.cwd(),
    port: await port(),
    logFile: path.join(directory, "sidecar.log"),
    env: { ...process.env, ...env },
    healthInterval: 50,
    healthTimeout: 100,
    healthFailures: 2,
    startupTimeout: 2500,
    shutdownTimeout: 200,
    restartDelay: 20,
  };
  const errors: Error[] = [];
  const manager = new SidecarManager(options, (error) => errors.push(error));
  t.after(async () => {
    await manager.stop();
    await rm(directory, { recursive: true, force: true });
  });
  return { manager, options, directory, errors };
}

test("Sidecar config supports development, production runtime and remote-only mode", () => {
  const config = sidecarOptions(false, "/workspace", "/resources", "/logs", {});
  assert(config);
  assert.equal(config.port, 8001);
  assert.equal(config.cwd, "/workspace/services/sidecar");
  assert.deepEqual(config.args, ["desktop_entry.py", "--stdio"]);
  assert.equal(
    sidecarOptions(true, "/workspace", "/resources", "/logs", {})?.command,
    "/resources/sidecar/" +
      (process.platform === "win32" ? "dp-work-sidecar.exe" : "dp-work-sidecar"),
  );
  assert.equal(
    sidecarOptions(false, "/workspace", "/resources", "/logs", { DESKTOP_SIDECAR_ENABLED: "0" }),
    null,
  );
  const bundled = sidecarOptions(true, "/workspace", "/resources", "/logs", {
    DESKTOP_SIDECAR_ENABLED: "1",
    DESKTOP_SIDECAR_EXECUTABLE: "/runtime/sidecar",
  });
  assert.equal(bundled?.command, "/runtime/sidecar");
  assert.deepEqual(bundled?.args, ["--stdio"]);
  assert.throws(() => sidecarOptions(false, "/w", "/r", "/l", { DESKTOP_SIDECAR_PORT: "80" }));
  assert.throws(() => sidecarOptions(false, "/w", "/r", "/l", { DESKTOP_SIDECAR_ENABLED: "yes" }));
});

test("owned Sidecar waits for health and shutdown cleans its process group", async (t) => {
  const ctx = await context(t);
  ctx.options.env!.PIDS = path.join(ctx.directory, "pids.json");
  await ctx.manager.start();
  assert.equal(ctx.manager.state.mode, "managed");
  const pids = JSON.parse(await readFile(ctx.options.env!.PIDS, "utf8")) as number[];
  assert(pids.every(alive));
  await ctx.manager.stop();
  await until(() => pids.every((pid) => !alive(pid)));
  assert.equal(ctx.manager.state.mode, "stopped");
});

test("external HTTP Sidecar cannot be reused through process pipes", async (t) => {
  const ctx = await context(t);
  const server = http.createServer((_req, res) =>
    res.end(JSON.stringify({ ok: true, service: "dp-work-sidecar" })),
  );
  await new Promise<void>((resolve) => server.listen(ctx.options.port, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve) => server.close(() => resolve())));
  await assert.rejects(ctx.manager.start(), /端口/);
  assert.equal(ctx.manager.state.pid, null);
  await ctx.manager.stop();
  assert.equal((await fetch(`http://127.0.0.1:${ctx.options.port}/health`)).status, 200);
});

test("an unrelated service on the port is not accepted or killed", async (t) => {
  const ctx = await context(t);
  const server = http.createServer((_req, res) => res.end(JSON.stringify({ ok: true })));
  await new Promise<void>((resolve) => server.listen(ctx.options.port, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve) => server.close(() => resolve())));
  await assert.rejects(ctx.manager.start(), /端口/);
  assert.equal(ctx.manager.state.pid, null);
  assert(server.listening);
});

test("crashed process restarts with a new pid and becomes healthy", async (t) => {
  const ctx = await context(t, { CRASH_FIRST: "1" });
  ctx.options.env!.LAUNCHES = path.join(ctx.directory, "launches");
  await ctx.manager.start();
  const first = ctx.manager.state.pid!;
  await until(
    async () =>
      ctx.manager.state.pid !== null &&
      ctx.manager.state.pid !== first &&
      (await fetch(`http://127.0.0.1:${ctx.options.port}/health`).catch(() => null))?.status ===
        200,
  );
  assert(!alive(first));
  assert.equal(ctx.errors.length, 0);
});

test("persistent failed health restarts an owned process", async (t) => {
  const ctx = await context(t);
  ctx.options.env!.UNHEALTHY = path.join(ctx.directory, "unhealthy");
  await ctx.manager.start();
  const first = ctx.manager.state.pid!;
  await writeFile(ctx.options.env!.UNHEALTHY, "fail");
  await until(() => ctx.manager.state.restarts > 0);
  await rm(ctx.options.env!.UNHEALTHY);
  await until(
    async () =>
      ctx.manager.state.pid !== null &&
      ctx.manager.state.pid !== first &&
      (await fetch(`http://127.0.0.1:${ctx.options.port}/health`).catch(() => null))?.status ===
        200,
  );
  assert(!alive(first));
});

test("repeated crashes stop at the configured retry budget", async (t) => {
  const ctx = await context(t, { CRASH_ALWAYS: "1" });
  ctx.options.maxRestarts = 1;
  await ctx.manager.start();
  await until(() => ctx.errors.length > 0);
  assert.match(ctx.errors[0].message, /连续重启失败/);
  assert.equal(ctx.manager.state.mode, "stopped");
});

test("shutdown escalates when owned process ignores SIGTERM", async (t) => {
  const ctx = await context(t, { IGNORE_TERM: "1" });
  await ctx.manager.start();
  const pid = ctx.manager.state.pid!;
  await ctx.manager.stop();
  await until(() => !alive(pid));
});

test("quitting during startup cancels waiting and never restarts", async (t) => {
  const ctx = await context(t, { NO_LISTEN: "1" });
  const starting = ctx.manager.start().catch(() => {});
  await until(() => ctx.manager.state.pid !== null);
  const pid = ctx.manager.state.pid!;
  await ctx.manager.stop();
  await starting;
  await until(() => !alive(pid));
  await delay(100);
  assert.equal(ctx.manager.state.mode, "stopped");
  assert.equal(ctx.manager.state.pid, null);
});

test("JSON-RPC streams independent calls and cancellation releases the task", async (t) => {
  const ctx = await context(t);
  ctx.options.env!.CLOSED_FILE = path.join(ctx.directory, "cancelled");
  await ctx.manager.start();
  const abort = new AbortController();
  const job = (text: string) => ({
    method: "agents.chat" as const,
    params: { messages: [{ content: text }] },
  });
  const stalled = await ctx.manager.request(job("stall"), abort.signal);
  const reader = stalled.body!.getReader();
  assert(!(await reader.read()).done);
  const completed = await ctx.manager.request(job("hello"), AbortSignal.timeout(1000));
  assert.match(await completed.text(), /本地执行测试完成/);
  abort.abort();
  await assert.rejects(async () => {
    while (!(await reader.read()).done) {
      /* drain */
    }
  });
  await until(
    async () =>
      (await readFile(ctx.options.env!.CLOSED_FILE!, "utf8").catch(() => "")) === "closed",
  );
  const again = await ctx.manager.request(job("again"), AbortSignal.timeout(1000));
  assert.match(await again.text(), /本地执行测试完成/);
});

test("process exit rejects in-flight RPC streams without replay", async (t) => {
  const ctx = await context(t);
  await ctx.manager.start();
  const response = await ctx.manager.request(
    {
      method: "agents.chat",
      params: { messages: [{ content: "stall" }] },
    },
    AbortSignal.timeout(3000),
  );
  process.kill(ctx.manager.state.pid!, "SIGKILL");
  await assert.rejects(response.text(), /中断|断开/);
});
