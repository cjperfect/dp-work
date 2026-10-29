import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { desktopRoot } from "./runtime.mjs";

const directory = await mkdtemp(path.join(tmpdir(), "dp-sidecar-smoke-"));
const listener = createServer();
await new Promise((resolve) => listener.listen(0, "127.0.0.1", resolve));
const port = listener.address().port;
await new Promise((resolve) => listener.close(resolve));
const binary = path.join(
  desktopRoot,
  "build/sidecar",
  process.platform === "win32" ? "dp-work-sidecar.exe" : "dp-work-sidecar",
);
const child = spawn(binary, ["--stdio"], {
  stdio: ["pipe", "pipe", "pipe"],
  env: {
    ...process.env,
    PORT: String(port),
    DP_DATA_DIR: path.join(directory, "data"),
    DP_SIDECAR_ENV_FILE: path.join(directory, "absent.env"),
    MEMORY_AUTO_ENABLED: "0",
    ARK_API_KEY: "",
    VOLC_API_KEY: "",
    EMBEDDING_API_KEY: "",
  },
});
let timer,
  deadline,
  stopping = false;
try {
  await new Promise((resolve, reject) => {
    let buffer = "";
    child.on("error", reject);
    child.on("exit", () => {
      if (!stopping) reject(new Error("Sidecar 冒烟测试期间提前退出。"));
    });
    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      let end;
      while ((end = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end + 1);
        try {
          const response = JSON.parse(line);
          if (
            response.id === "smoke" &&
            response.result?.ok &&
            response.result?.service === "dp-work-sidecar"
          )
            resolve();
        } catch {
          reject(new Error("Sidecar stdout 包含非 JSON-RPC 内容。"));
        }
      }
    });
    child.stderr.resume();
    timer = setInterval(
      () =>
        child.stdin.write(
          JSON.stringify({ jsonrpc: "2.0", id: "smoke", method: "system.health", params: {} }) +
            "\n",
        ),
      500,
    );
    child.stdin.on("error", reject);
    deadline = setTimeout(() => reject(new Error("Sidecar 冒烟测试健康检查超时。")), 90000);
  });
  console.info(`Sidecar 独立程序健康检查通过：${process.platform}/${process.arch}`);
} finally {
  clearInterval(timer);
  clearTimeout(deadline);
  stopping = true;
  child.stdin.end();
  if (child.exitCode === null)
    await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        child.kill("SIGKILL");
        resolve();
      }, 5000);
      child.once("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
    });
  await rm(directory, { recursive: true, force: true });
}
