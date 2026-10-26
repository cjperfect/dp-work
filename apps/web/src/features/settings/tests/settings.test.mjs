import assert from "node:assert/strict";
import { test } from "node:test";
import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import { saveService, testService } from "../../../apis/settings.ts";
import { createAsrSession } from "../../../apis/sidecar.ts";

const reply = (data) =>
  new Response(JSON.stringify({ code: 0, data }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

test("connection tests do not save settings and ASR startup uses opaque tickets", async () => {
  const calls = [];
  mockHttpRequest(async (url, init) => {
    calls.push({ url, method: init.method, data: init.body ? JSON.parse(init.body) : null });
    if (url.includes("/session/")) return reply({ ticket: "one-time-fixture" });
    return reply({ ok: true, saved: true });
  });
  const form = {
    enabled: true,
    provider: "ark",
    model: "model",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
  };
  await testService("model", form);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/settings/model/test");
  assert.ok(!("api_key" in calls[0].data));
  await saveService("model", form);
  assert.equal(calls[1].method, "PUT");
  const result = await createAsrSession("meeting-1");
  assert.deepEqual(result, { ticket: "one-time-fixture" });
  assert.equal(calls[2].url, "/api/settings/asr/session/meeting-1");
});
