import path from "node:path";
import { existsSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { desktopRoot, workspaceRoot } from "./runtime.mjs";
const root = path.join(workspaceRoot, "services/sidecar");
const python =
  process.env.SIDECAR_BUILD_PYTHON ??
  path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
if (!existsSync(python)) throw new Error("请先安装 Sidecar Python 虚拟环境及 PyInstaller。");
const output = path.join(desktopRoot, "build/sidecar");
const temporary = path.join(workspaceRoot, ".dp-work/temp/sidecar-build");
await mkdir(temporary, { recursive: true });
await rm(output, { recursive: true, force: true });
const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--name",
  "dp-work-sidecar",
  "--distpath",
  path.dirname(output),
  "--workpath",
  path.join(temporary, "work"),
  "--specpath",
  temporary,
  "--paths",
  root,
  "--collect-submodules",
  "src",
  "--collect-submodules",
  "langchain.agents",
  "--collect-all",
  "deepagents",
  "--collect-submodules",
  "langgraph",
  "--collect-submodules",
  "langgraph.checkpoint.sqlite",
  "--collect-submodules",
  "langchain_openai",
  "--hidden-import",
  "langchain_community.document_loaders.pdf",
  "--hidden-import",
  "langchain_community.document_loaders.text",
  "--collect-all",
  "pymupdf",
  "--collect-all",
  "pymupdf4llm",
  "--collect-all",
  "docx",
  "--recursive-copy-metadata",
  "langchain",
  "--copy-metadata",
  "langchain-community",
  "--collect-all",
  "templates",
  "--add-data",
  `${path.join(root, "src/meetings/prompts")}${path.delimiter}src/meetings/prompts`,
  "--add-data",
  `${path.join(workspaceRoot, "packages/protocols/protocol.json")}${path.delimiter}protocols`,
  "--exclude-module",
  "torch",
  "--exclude-module",
  "tensorflow",
  "--exclude-module",
  "sentence_transformers",
  path.join(root, "desktop_entry.py"),
];
await new Promise((resolve, reject) => {
  const child = spawn(python, args, { cwd: root, stdio: "inherit" });
  child.once("error", reject);
  child.once("exit", (code) =>
    code === 0 ? resolve() : reject(new Error(`Sidecar 打包失败：${code}`)),
  );
});
const { rename } = await import("node:fs/promises");
await rename(path.join(desktopRoot, "build/dp-work-sidecar"), output);
await writeFile(
  path.join(output, "runtime.json"),
  JSON.stringify({ platform: process.platform, arch: process.arch }, null, 2),
);
console.info("Sidecar 独立运行环境已生成：apps/desktop/build/sidecar（未复制 .env）。");
