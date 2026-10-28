import { randomUUID } from "node:crypto";
import {
  lstat,
  mkdir,
  readFile,
  realpath,
  rename,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import type { LocalProject } from "@dp-work/protocols/desktop";
let writing: Promise<void> = Promise.resolve();

/** 只登记原生文件夹选择器返回的目录，不接受 Renderer 提交的任意路径。 */
export function registerProject(
  data: string,
  directory: string,
  owner: number,
  deviceId: string,
): Promise<LocalProject> {
  const operation = writing.then(async () => {
    const resolved = await realpath(directory);
    if (!(await stat(resolved)).isDirectory() || !Number.isSafeInteger(owner) || owner <= 0)
      throw new Error("项目目录或账号无效。");
    await mkdir(data, { recursive: true, mode: 0o700 });
    const file = path.join(data, "projects.json");
    let records: { projects: Record<string, LocalProject & { owner_id: number }> } = {
      projects: {},
    };
    try {
      const info = await lstat(file);
      if (info.isSymbolicLink() || info.size > 4 * 1024 * 1024)
        throw new Error("本地项目记录无效。");
      records = JSON.parse(await readFile(file, "utf8"));
      if (
        !records ||
        !records.projects ||
        Array.isArray(records.projects) ||
        typeof records.projects !== "object"
      )
        throw new Error("本地项目记录无效。");
    } catch (cause) {
      if ((cause as NodeJS.ErrnoException).code !== "ENOENT") throw cause;
    }
    const existing = Object.values(records.projects).find(
      (item) => item.owner_id === owner && item.path === resolved && item.device_id === deviceId,
    );
    if (existing) return existing;
    const project = {
      id: randomUUID(),
      name: path.basename(resolved) || resolved,
      path: resolved,
      owner_id: owner,
      device_id: deviceId,
    };
    records.projects[project.id] = project;
    const temporary = `${file}.${randomUUID()}.tmp`;
    try {
      await writeFile(temporary, JSON.stringify(records), {
        encoding: "utf8",
        mode: 0o600,
        flag: "wx",
      });
      await rename(temporary, file);
    } finally {
      await unlink(temporary).catch(() => {});
    }
    return project;
  });
  writing = operation.then(
    () => {},
    () => {},
  );
  return operation;
}
