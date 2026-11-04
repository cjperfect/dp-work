import path from "node:path";
import { createRequire } from "node:module";
import { cp, mkdir, readFile, rm } from "node:fs/promises";
import { desktopRoot } from "./runtime.mjs";

/** 将 Runtime 及其运行依赖复制到 asar 外，供 Sidecar 使用 Electron 的 Node 运行时。 */
export async function prepareSandbox(output) {
  const require = createRequire(path.join(desktopRoot, "package.json"));
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });
  async function copyPackage(name, resolver, modules, ancestors = new Map()) {
    let source = path.dirname(resolver.resolve(name));
    for (;;) {
      try {
        const meta = JSON.parse(await readFile(path.join(source, "package.json"), "utf8"));
        if (meta.name === name) break;
      } catch {
        /* 入口可能位于 dist 或 lib 内。 */
      }
      const parent = path.dirname(source);
      if (parent === source) throw new Error(`找不到依赖包：${name}`);
      source = parent;
    }
    if (ancestors.get(name) === source) return;
    const target = path.join(modules, name);
    await mkdir(path.dirname(target), { recursive: true });
    await cp(source, target, {
      recursive: true,
      dereference: true,
      filter: (file) => !path.relative(source, file).split(path.sep).includes("node_modules"),
    });
    const meta = JSON.parse(await readFile(path.join(source, "package.json"), "utf8"));
    const next = new Map(ancestors).set(name, source);
    const dependencyResolver = createRequire(path.join(source, "package.json"));
    for (const dependency of Object.keys(meta.dependencies ?? {})) {
      await copyPackage(dependency, dependencyResolver, path.join(target, "node_modules"), next);
    }
  }
  await copyPackage("@anthropic-ai/sandbox-runtime", require, path.join(output, "node_modules"));
}
