import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readlinkSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

/** 获取按数据类型划分的存储目录。 */
export function persistencePaths(packaged: boolean, home: string, workspace: string) {
  const root = path.join(packaged ? home : workspace, ".dp-work");
  return {
    root,
    data: path.join(root, "data"),
    logs: path.join(root, "logs"),
    cache: path.join(root, "cache"),
    crashes: path.join(root, "logs/crashes"),
  };
}

/** 检查旧存储目录是否仍在使用。 */
function legacyProfileRunning(directory: string): boolean {
  try {
    const lock = readlinkSync(path.join(directory, "SingletonLock"));
    const pid = Number(lock.slice(lock.lastIndexOf("-") + 1));
    if (!Number.isSafeInteger(pid) || pid <= 0 || pid === process.pid) return false;
    try {
      process.kill(pid, 0);
      return true;
    } catch (cause) {
      return (cause as NodeJS.ErrnoException).code !== "ESRCH";
    }
  } catch {
    return false;
  }
}

/** 首次启动时迁移旧版的浏览器存储。 */
export function migrateProfile(destination: string, legacy: string): void {
  mkdirSync(destination, { recursive: true, mode: 0o700 });
  const marker = path.join(destination, ".profile-ready");
  const partitions = path.join(destination, "Partitions");
  if (existsSync(marker) || existsSync(partitions) || destination === legacy) return;
  if (legacyProfileRunning(legacy)) throw new Error("请先退出旧版桌面应用，再重新启动以迁移数据。");
  const source = path.join(legacy, "Partitions");
  if (existsSync(source)) {
    const temporary = mkdtempSync(path.join(destination, ".profile-migration-"));
    try {
      cpSync(source, path.join(temporary, "Partitions"), { recursive: true });
      const state = path.join(legacy, "Local State");
      if (existsSync(state) && !existsSync(path.join(destination, "Local State")))
        cpSync(state, path.join(destination, "Local State"), { errorOnExist: true, force: false });
      renameSync(path.join(temporary, "Partitions"), partitions);
    } finally {
      rmSync(temporary, { recursive: true, force: true });
    }
  }
  writeFileSync(marker, "1\n", { mode: 0o600, flag: "wx" });
}
