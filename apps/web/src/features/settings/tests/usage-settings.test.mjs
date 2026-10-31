import assert from "node:assert/strict";
import { test } from "node:test";
import { usageSettingsInput } from "../lib/usage-settings.ts";
import { getUsageSettings, saveUsageSettings } from "../../../apis/settings.ts";
import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";

const form = {
  enabled: true,
  currency: "CNY",
  token_limit: "1000",
  cost_limit: "1",
  asr_price_per_hour: "",
};
const rows = [{ key: "one", model: "model", input: "1", output: "4", cached_input: "" }];
test("usage form preserves decimal prices, optional cache and ASR, and validates duplicate models", () => {
  const value = usageSettingsInput(form, rows);
  assert.deepEqual(value.model_prices, { model: { input: "1", output: "4" } });
  assert.equal(value.token_limit, 1000);
  assert.equal(value.asr_price_per_hour, undefined);
  assert.equal(
    usageSettingsInput({ ...form, asr_price_per_hour: "0" }, rows).asr_price_per_hour,
    "0",
  );
  assert.throws(
    () => usageSettingsInput(form, [...rows, { ...rows[0], model: " model " }]),
    /重复/,
  );
  assert.throws(() => usageSettingsInput({ ...form, token_limit: "1.5" }, rows), /整数/);
  for (const input of ["NaN", "Infinity", "-1", ""])
    assert.throws(() => usageSettingsInput(form, [{ ...rows[0], input }]), /非负/);
});

test("usage settings API keeps local settings route and explicit save body", async () => {
  const calls = [];
  const data = usageSettingsInput(form, rows);
  mockHttpRequest(async (url, init) => {
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(init.body) : null });
    return new Response(JSON.stringify({ code: 0, data }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  assert.deepEqual(await getUsageSettings(), data);
  assert.deepEqual(await saveUsageSettings(data), data);
  assert.deepEqual(
    calls.map(({ url, method }) => ({ url, method })),
    [
      { url: "/api/settings/usage", method: "GET" },
      { url: "/api/settings/usage", method: "PUT" },
    ],
  );
  assert.deepEqual(calls[1].body, data);
});
