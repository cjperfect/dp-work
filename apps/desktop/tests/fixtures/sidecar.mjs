import readline from "node:readline";
import http from "node:http";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";

let launch = 1;
if (process.env.LAUNCHES) {
  launch = existsSync(process.env.LAUNCHES)
    ? Number(readFileSync(process.env.LAUNCHES, "utf8")) + 1
    : 1;
  writeFileSync(process.env.LAUNCHES, String(launch));
}
const grandchild = process.env.PIDS
  ? spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" })
  : null;
if (process.env.PIDS)
  writeFileSync(process.env.PIDS, JSON.stringify([process.pid, grandchild.pid]));

const server = http.createServer((_request, response) => {
  if (process.env.UNHEALTHY && existsSync(process.env.UNHEALTHY)) {
    response.writeHead(503);
    response.end();
    return;
  }
  response.setHeader("Content-Type", "application/json");
  response.end(
    JSON.stringify({
      ok: true,
      service: "dp-work-sidecar",
      instance_id: process.env.DP_SIDECAR_INSTANCE_ID ?? null,
    }),
  );
});
if (process.env.NO_LISTEN) setInterval(() => {}, 1000);
else server.listen(Number(process.env.PORT), "127.0.0.1");
if (process.env.IGNORE_TERM) process.on("SIGTERM", () => {});
else process.on("SIGTERM", () => server.close(() => process.exit(0)));
if (process.env.CRASH_ALWAYS || (process.env.CRASH_FIRST && launch === 1))
  setTimeout(() => process.exit(12), 350);

const pending = new Set();
const send = (value) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...value }) + "\n");
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const { id, method, params } = JSON.parse(line);
  if (method === "$/cancelRequest") {
    if (pending.delete(params.id) && process.env.CLOSED_FILE)
      writeFileSync(process.env.CLOSED_FILE, "closed");
    send({ id: params.id, error: { code: -32800, message: "cancelled" } });
    return;
  }
  if (method === "system.health") {
    send({
      id,
      result: {
        ok: server.listening && !(process.env.UNHEALTHY && existsSync(process.env.UNHEALTHY)),
        service: "dp-work-sidecar",
        instance_id: process.env.DP_SIDECAR_INSTANCE_ID,
      },
    });
    return;
  }
  const data =
    method === "knowledge.parse"
      ? Buffer.from(params.content_base64, "base64")
      : Buffer.from(JSON.stringify(params));
  send({
    method: "stream.head",
    params: {
      id,
      status: 200,
      content_type: method === "agents.chat" ? "text/event-stream" : "application/json",
    },
  });
  let seq = 0;
  const chunk = (value) =>
    send({
      method: "stream.chunk",
      params: { id, seq: seq++, data: Buffer.from(value).toString("base64") },
    });
  if (method === "agents.models")
    chunk(
      JSON.stringify({
        configured: true,
        models: [{ id: "fixture-model", name: "fixture-model" }],
      }),
    );
  else if (method === "knowledge.parse")
    chunk(JSON.stringify({ status: "parsed", content: data.toString(), metadata: [] }));
  else if (method === "agents.chat") {
    const body = JSON.parse(data.toString());
    chunk(
      "data: " +
        JSON.stringify({ type: "start", run_id: body.run_id, model: "fixture-model" }) +
        "\n\n",
    );
    if (body.messages.at(-1).content === "stall") {
      pending.add(id);
      chunk("data: " + JSON.stringify({ type: "delta", text: "部分内容" }) + "\n\n");
      return;
    }
    chunk(
      "data: " +
        JSON.stringify({ type: "done", content: "本地执行测试完成", model: "fixture-model" }) +
        "\n\n",
    );
  }
  send({ id, result: { complete: true } });
});
