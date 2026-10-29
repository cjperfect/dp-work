import { readdir, readFile, mkdir, copyFile, writeFile, stat } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import yaml from "js-yaml";

export function releaseVersion(tag, version) {
  if (!/^v\d+\.\d+\.\d+$/.test(tag) || tag !== `v${version}`)
    throw new Error("发布标签必须为 v<桌面 package.json 版本>，当前只支持正式版。");
  return version;
}

/** 汇总各平台产物，合并 Mac 双架构清单，并核验每个下载文件的 SHA-512。 */
export async function mergeRelease(input, output, version) {
  releaseVersion(`v${version}`, version);
  const assets = new Map(),
    manifests = new Map();
  async function walk(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) throw new Error("发布产物不能使用符号链接。");
      if (entry.isDirectory()) {
        await walk(file);
        continue;
      }
      if (!/\.(exe|dmg|zip|AppImage|blockmap|yml)$/.test(entry.name)) continue;
      if (entry.name.endsWith(".yml")) {
        if (!["latest.yml", "latest-mac.yml", "latest-linux.yml"].includes(entry.name))
          throw new Error("不支持的更新频道。");
        const data = yaml.load(await readFile(file, "utf8"));
        if (!data || data.version !== version || !Array.isArray(data.files) || !data.files.length)
          throw new Error("更新清单版本或文件列表无效。");
        const previous = manifests.get(entry.name);
        if (previous) previous.files.push(...data.files);
        else manifests.set(entry.name, data);
      } else {
        if (assets.has(entry.name)) throw new Error(`发布文件重名：${entry.name}`);
        assets.set(entry.name, file);
      }
    }
  }
  await walk(input);
  for (const name of ["latest.yml", "latest-mac.yml", "latest-linux.yml"])
    if (!manifests.has(name)) throw new Error(`缺少更新清单：${name}`);
  for (const data of manifests.values()) {
    const seen = new Set();
    for (const entry of data.files) {
      if (
        typeof entry.url !== "string" ||
        path.basename(entry.url) !== entry.url ||
        /[\\?#:]/.test(entry.url) ||
        seen.has(entry.url)
      )
        throw new Error("更新文件路径无效或重复。");
      seen.add(entry.url);
      const file = assets.get(entry.url);
      if (!file || typeof entry.sha512 !== "string" || !/^[A-Za-z0-9+/]{86}==$/.test(entry.sha512))
        throw new Error("更新文件或 SHA-512 缺失。");
      const info = await stat(file);
      if (entry.size != null && entry.size !== info.size) throw new Error("更新文件大小不匹配。");
      const hash = createHash("sha512");
      for await (const chunk of createReadStream(file)) hash.update(chunk);
      if (hash.digest("base64") !== entry.sha512) throw new Error("更新文件 SHA-512 不匹配。");
    }
    data.path = data.files[0].url;
    data.sha512 = data.files[0].sha512;
  }
  const mac = manifests.get("latest-mac.yml").files;
  if (
    !mac.some((file) => file.url.endsWith("-arm64.zip")) ||
    !mac.some((file) => file.url.endsWith("-x64.zip"))
  )
    throw new Error("缺少 Mac 双架构 ZIP 更新文件。");
  await mkdir(output, { recursive: true });
  for (const [name, file] of assets) await copyFile(file, path.join(output, name));
  for (const [name, data] of manifests)
    await writeFile(path.join(output, name), yaml.dump(data, { lineWidth: -1 }));
  return [...assets.keys(), ...manifests.keys()];
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const [input, output, version] = process.argv.slice(2);
  if (!input || !output || !version)
    throw new Error("用法：merge-release.mjs <产物目录> <汇总目录> <版本>");
  mergeRelease(input, output, version)
    .then((files) => console.info(`已核验并汇总 ${files.length} 个发布文件。`))
    .catch((error) => {
      console.error(error.message);
      process.exitCode = 1;
    });
}
