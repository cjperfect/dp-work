import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import type { SidecarJob } from "@dp-work/protocols";
import type { LocalResponseChunk } from "@dp-work/protocols/desktop";
import { LocalGateway } from "../src/main/local/gateway";
import { routeLocal } from "../src/main/local/routes";
import { LocalIdentity } from "../src/main/local/identity";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const owner = 7,
  device = randomUUID();
test("local routes inject owner/device and never route remote business or arbitrary RPC", () => {
  const pricing = routeLocal("/api/settings/usage", "PUT", {}, { enabled: true }, owner, device);
  assert.equal(pricing.method, "usage.settings.save");
  assert.equal(pricing.params.owner_id, owner);
  assert.deepEqual(pricing.params.body, { enabled: true });
  assert.equal(
    routeLocal("/api/settings/usage", "GET", {}, {}, owner, device).method,
    "usage.settings.read",
  );
  const resume = routeLocal(
    "/api/agents/threads/thread1/resume",
    "POST",
    {},
    { run_id: "original", expected_revision: 1 },
    owner,
    device,
  );
  assert.equal(resume.method, "sessions.resume");
  assert.equal(resume.params.owner_id, owner);
  assert.equal(resume.needsRetrieval, true);
  const list = routeLocal("/api/agents/threads", "GET", {}, { owner_id: 99 }, owner, device);
  assert.equal(list.method, "sessions.list");
  assert.equal(list.params.owner_id, owner);
  const image = routeLocal(
    "/api/agents/images",
    "POST",
    {},
    { owner_id: 99, data_url: "fixture" },
    owner,
    device,
  );
  assert.equal(image.method, "sessions.images.save");
  assert.equal(image.params.owner_id, owner);
  const changeId = randomUUID();
  const undo = routeLocal(
    `/api/agents/threads/thread1/files/${changeId}/undo`,
    "POST",
    {},
    { owner_id: 99, path: "/etc/private" },
    owner,
    device,
  );
  assert.equal(undo.method, "sessions.files.undo");
  assert.equal(undo.params.owner_id, owner);
  assert.deepEqual(undo.params.body, { change_id: changeId });
  assert.equal(
    routeLocal("/api/agents/images", "GET", { id: "fixture" }, {}, owner, device).method,
    "sessions.images.read",
  );
  const project = routeLocal("/api/agents/projects", "POST", {}, { owner_id: 99 }, owner, device);
  assert.equal(project.params.owner_id, 7);
  assert.equal(project.params.device_id, device);
  assert.equal(
    routeLocal("/api/settings/model", "PUT", {}, {}, owner, device).method,
    "settings.save",
  );
  assert.equal(
    routeLocal("/api/skills/install", "POST", {}, {}, owner, device).method,
    "skills.install",
  );
  assert.equal(
    routeLocal("/api/connectors/feishu/authorization/login", "POST", {}, {}, owner, device).method,
    "connectors.feishu.start",
  );
  for (const target of [
    "/api/meetings",
    "/api/knowledge-bases",
    "/api/auth/login",
    "/internal/agents/chat",
    "/api/agents/../settings",
  ])
    assert.throws(() => routeLocal(target, "GET", {}, {}, owner, device));
});

test("local JSON and stream calls bypass network and are cancellable", async () => {
  const chunks: LocalResponseChunk[] = [];
  let ended!: () => void;
  const done = new Promise<void>((resolve) => {
    ended = resolve;
  });
  const calls: SidecarJob[] = [];
  const gateway = new LocalGateway(
    async (job, signal) => {
      calls.push(job);
      if (job.method === "sessions.chat")
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                new TextEncoder().encode('data: {"type":"delta","text":"hello"}\n\n'),
              );
              signal.addEventListener("abort", () => controller.error(new Error("cancelled")), {
                once: true,
              });
            },
          }),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      return Response.json({ saved: true });
    },
    async () => ({ owner, deviceId: device }),
    () => {
      throw new Error("local call must not access cloud");
    },
    (chunk) => {
      chunks.push(chunk);
      if (chunk.done || chunk.error) ended();
    },
  );
  const id = randomUUID();
  const head = await gateway.open({
    id,
    token: "fixture",
    path: "/api/settings/model",
    method: "PUT",
    body: { provider: "ark" },
  });
  assert.equal(head.status, 200);
  await done;
  assert.equal(calls[0].method, "settings.save");
  assert.equal(calls[0].params.owner_id, 7);
  assert.ok(chunks.some((chunk) => chunk.done));
  const active = randomUUID();
  await gateway.open({
    id: active,
    token: "fixture",
    path: "/api/agents/threads/thread1/chat",
    method: "POST",
    body: { knowledge_base_ids: [] },
  });
  gateway.cancel(active);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.ok(chunks.some((chunk) => chunk.id === active && chunk.error));
});

test("RAG contacts only knowledge capability endpoint and never uploads chat history", async () => {
  const original = globalThis.fetch;
  const requests: { url: Parameters<typeof fetch>[0]; body: unknown }[] = [];
  globalThis.fetch = async (url, input) => {
    requests.push({ url, body: JSON.parse(String(input?.body)) });
    return Response.json({ code: 0, data: { capability: "scoped-token" } });
  };
  try {
    const calls: SidecarJob[] = [];
    const gateway = new LocalGateway(
      async (job) => {
        calls.push(job);
        return new Response('data: {"type":"done","content":"ok"}\n\n', {
          headers: { "Content-Type": "text/event-stream" },
        });
      },
      async () => ({ owner, deviceId: device }),
      () => "https://cloud.example",
      () => {},
    );
    await gateway.open({
      id: randomUUID(),
      token: "fixture",
      path: "/api/agents/threads/thread1/chat",
      method: "POST",
      body: { messages: [{ content: "PRIVATE CHAT" }], knowledge_base_ids: [1, 2] },
    });
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, "https://cloud.example/api/knowledge-bases/retrieval-capability");
    assert.deepEqual(requests[0].body, { knowledge_base_ids: [1, 2] });
    assert.equal(calls[0].params.retrieval_token, "scoped-token");
  } finally {
    globalThis.fetch = original;
  }
});

test("offline local identity accepts only a previously verified token digest", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "dp-local-identity-"));
  try {
    const file = path.join(directory, "identity.json");
    const cache = new LocalIdentity(file);
    const bridge = {
      setSession: async () => ({ deviceId: device }),
      getIdentity: () => ({ owner, deviceId: device }),
      isVerifiedSession: () => false,
    };
    await assert.rejects(cache.resolve("forged", bridge));
    cache.remember("accepted-token", { owner, deviceId: device });
    assert.deepEqual(await cache.resolve("accepted-token", bridge), {
      owner,
      deviceId: device,
    });
    assert.ok(!(await readFile(file, "utf8")).includes("accepted-token"));
    await assert.rejects(cache.resolve("different-token", bridge));
    cache.clear();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("cancelling during identity resolution never starts an Agent", async () => {
  let finish!: (value: { owner: number; deviceId: string }) => void;
  let executions = 0;
  const gateway = new LocalGateway(
    async () => {
      executions++;
      return Response.json({});
    },
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
    () => "",
    () => {},
  );
  const id = randomUUID();
  const opening = gateway.open({ id, token: "fixture", path: "/api/agents/models" });
  gateway.cancel(id);
  finish({ owner, deviceId: device });
  await assert.rejects(opening);
  assert.equal(executions, 0);
});

test("account switch aborts old local streams before executing the new request", async () => {
  let stopped = false;
  const gateway = new LocalGateway(
    async (_job, signal) =>
      new Response(
        new ReadableStream({
          start(controller) {
            signal.addEventListener(
              "abort",
              () => {
                stopped = true;
                controller.error(new Error("account switched"));
              },
              { once: true },
            );
          },
        }),
      ),
    async (token) => ({ owner: token === "old" ? 7 : 8, deviceId: device }),
    () => "",
    () => {},
  );
  await gateway.open({ id: randomUUID(), token: "old", path: "/api/agents/models" });
  await gateway.open({ id: randomUUID(), token: "new", path: "/api/agents/models" });
  assert.ok(stopped);
  gateway.cancelAll();
});

test("memory CRUD is local and Main injects the verified account", () => {
  const id = randomUUID();
  for (const [path, verb, method] of [
    ["/api/memories", "GET", "memory.list"],
    ["/api/memories", "POST", "memory.create"],
    [`/api/memories/${id}`, "PATCH", "memory.update"],
    [`/api/memories/${id}`, "DELETE", "memory.delete"],
    ["/api/memories/preferences", "GET", "memory.preferences"],
    ["/api/memories/preferences", "PUT", "memory.preferences.update"],
  ]) {
    const result = routeLocal(path, verb, { page: 2 }, { owner_id: 99 }, owner, device);
    assert.equal(result.method, method);
    assert.equal(result.params.owner_id, owner);
    if (path.endsWith(id)) assert.equal(result.params.key, id);
    if (path === "/api/memories" && verb === "GET")
      assert.deepEqual(result.params.body, { page: 2 });
  }
  assert.throws(() => routeLocal("/api/memories/anything", "DELETE", {}, {}, owner, device));
});

test("skill uploads and usage summaries stay local and use verified identity", () => {
  const upload = routeLocal(
    "/api/skills/upload",
    "POST",
    {},
    { agent_code: "general", filename: "SKILL.md", content_base64: "fixture" },
    owner,
    device,
  );
  assert.equal(upload.method, "skills.upload");
  const usage = routeLocal("/api/usage", "GET", {}, { owner_id: 99 }, owner, device);
  assert.equal(usage.method, "usage.summary");
  assert.equal(usage.params.owner_id, owner);
});

test("checkpoint resume refreshes only the original run's retrieval scope", async () => {
  const original = globalThis.fetch;
  const requests: unknown[] = [];
  globalThis.fetch = async (_url, input) => {
    requests.push(JSON.parse(String(input?.body)));
    return Response.json({ code: 0, data: { capability: "fresh-scoped-token" } });
  };
  try {
    const calls: SidecarJob[] = [];
    const gateway = new LocalGateway(
      async (job) => {
        calls.push(job);
        if (job.method === "sessions.resume.lookup")
          return Response.json({ thread: { id: "thread1" }, knowledge_base_ids: [1, 2] });
        return new Response('data: {"type":"done","content":"ok"}\n\n', {
          headers: { "Content-Type": "text/event-stream" },
        });
      },
      async () => ({ owner, deviceId: device }),
      () => "https://cloud.example",
      () => {},
    );
    await gateway.open({
      id: randomUUID(),
      token: "fixture",
      path: "/api/agents/threads/thread1/resume",
      method: "POST",
      body: { run_id: "old-run", expected_revision: 1, knowledge_base_ids: [999] },
    });
    assert.deepEqual(requests, [{ knowledge_base_ids: [1, 2] }]);
    assert.deepEqual(
      calls.map((call) => call.method),
      ["sessions.resume.lookup", "sessions.resume"],
    );
    assert.equal(calls[1].params.retrieval_token, "fresh-scoped-token");
    assert.equal(calls[1].params.owner_id, owner);
  } finally {
    globalThis.fetch = original;
  }
});
