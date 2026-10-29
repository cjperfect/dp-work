import assert from "node:assert/strict";
import { test } from "node:test";
import { uniqueRunUsage, usageLines, formatCost } from "../lib/usage.ts";

const usage = (run, tokens) => ({
  run_id: run,
  input_tokens: tokens - 20,
  output_tokens: 20,
  total_tokens: tokens,
  cached_input_tokens: 10,
  reasoning_tokens: 5,
  reported_calls: 1,
  unreported_calls: 0,
  in_flight_calls: 0,
  complete: true,
  estimated_cost: null,
  currency: "CNY",
  token_limit: null,
  cost_limit: null,
  calls: [
    {
      id: run + "-call",
      model: "fixture",
      status: "reported",
      input_tokens: tokens - 20,
      output_tokens: 20,
      cached_input_tokens: 10,
      reasoning_tokens: 5,
      total_tokens: tokens,
      currency: "CNY",
    },
  ],
});

test("Steering and approval continuation usage count only once on the selected branch", () => {
  const result = uniqueRunUsage([
    usage("one", 120),
    undefined,
    usage("one", 240),
    usage("two", 120),
  ]);
  assert.equal(result.length, 2);
  assert.equal(
    result.reduce((sum, run) => sum + run.total_tokens, 0),
    360,
  );
});

test("cost meter totals exclude cache/reasoning subsets and don't claim missing pricing is free", () => {
  const line = usageLines(usage("one", 120))[0];
  assert.equal(line.inputTokens, 100);
  assert.equal(line.outputTokens, 20);
  assert.equal(line.share, 1);
  assert.equal(line.cost, "费用未知");
  const missing = usage("two", 120);
  missing.calls[0].status = "unreported";
  assert.deepEqual(usageLines(missing), []);
  assert.equal(formatCost(null, "CNY"), null);
  assert.equal(formatCost("NaN", "CNY"), null);
  assert.equal(formatCost("-1", "CNY"), null);
  assert.match(formatCost("0", "CNY"), /CNY 0\.0000/);
});
