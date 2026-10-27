import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { DeviceBridge } from "../../src/main/device/bridge";
import { SidecarRpc } from "../../src/main/sidecar/rpc";
const config = JSON.parse(await readFile(process.argv[2], "utf8"));
const child = spawn(process.execPath, [fileURLToPath(new URL("./sidecar.mjs", import.meta.url))], {
  env: { ...process.env, PORT: "0", CLOSED_FILE: config.closed },
  stdio: ["pipe", "pipe", "inherit"],
});
const rpc = new SidecarRpc(child);
const bridge = new DeviceBridge(config.api, config.installation, (job, signal) =>
  rpc.request(job, signal),
);
const result = await bridge.setSession(config.token);
await writeFile(config.ready, JSON.stringify(result));
process.on("SIGTERM", () => {
  bridge.stop();
  rpc.close();
  child.kill();
  child.once("exit", () => process.exit(0));
});
