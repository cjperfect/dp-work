import assert from "node:assert/strict";
import { test, afterEach } from "node:test";
import { http, httpClient } from "../../../lib/http.ts";
const adapter = httpClient.defaults.adapter;
afterEach(() => {
  httpClient.defaults.adapter = adapter;
});

test("HTTP helpers preserve verbs, bodies, query parameters, headers and unwrapped responses", async () => {
  const calls = [];
  httpClient.defaults.adapter = async (config) => {
    calls.push(config);
    return {
      data: { code: 0, data: { saved: true } },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    };
  };
  const controller = new AbortController();
  const options = {
    auth: false,
    timeout: 25000,
    signal: controller.signal,
    headers: { "X-Test": "fixture" },
  };
  assert.deepEqual(await http.get("/api/example", { ...options, params: { page: 2 } }), {
    saved: true,
  });
  await http.post("/api/example", { title: "创建" }, options);
  await http.put("/api/example", { title: "更新" }, options);
  await http.patch("/api/example", { title: "改名" }, options);
  await http.delete("/api/example", options);
  assert.deepEqual(
    calls.map((call) => call.method),
    ["get", "post", "put", "patch", "delete"],
  );
  assert.deepEqual(calls[0].params, { page: 2 });
  assert.deepEqual(
    calls.slice(1, 4).map((call) => JSON.parse(call.data).title),
    ["创建", "更新", "改名"],
  );
  assert.ok(
    calls.every(
      (call) =>
        call.timeout === 25000 &&
        call.signal === controller.signal &&
        call.headers.get("X-Test") === "fixture" &&
        call.requiresAuth === false,
    ),
  );
});

test("POST accepts FormData and GET preserves binary/stream response types", async () => {
  const form = new FormData();
  form.append("file", new Blob(["content"]), "test.md");
  const blob = new Blob(["download"]);
  const stream = new ReadableStream({
    start(controller) {
      controller.close();
    },
  });
  httpClient.defaults.adapter = async (config) => {
    if (config.method === "post") assert.equal(config.data, form);
    return {
      data:
        config.responseType === "blob"
          ? blob
          : config.responseType === "stream"
            ? stream
            : { code: 0, data: null },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    };
  };
  await http.post("/api/upload", form, { auth: false });
  assert.equal(await http.get("/api/download", { auth: false, responseType: "blob" }), blob);
  assert.equal(await http.get("/api/events", { auth: false, responseType: "stream" }), stream);
  await assert.rejects(http.get("https://external.example"), /\/api\//);
});
