import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync, writeFileSync, renameSync, unlinkSync } from "node:fs";
import type { DeviceBridge } from "../device/bridge";
type Identity = { owner: number; deviceId: string };

/** 只缓存云端已经验证的登录凭证摘要，离线重启不能伪造另一个用户 ID。 */
export class LocalIdentity {
  constructor(private file: string) {}
  private digest(token: string) {
    return createHash("sha256").update(token).digest("hex");
  }
  remember(token: string, identity: Identity): void {
    const temporary = this.file + "." + randomUUID() + ".tmp";
    try {
      writeFileSync(temporary, JSON.stringify({ digest: this.digest(token), ...identity }), {
        mode: 0o600,
        flag: "wx",
      });
      renameSync(temporary, this.file);
    } finally {
      if (existsSync(temporary)) unlinkSync(temporary);
    }
  }
  async resolve(
    token: string,
    bridge: Pick<DeviceBridge, "setSession" | "getIdentity" | "isVerifiedSession">,
  ): Promise<Identity> {
    if (existsSync(this.file)) {
      const saved = JSON.parse(readFileSync(this.file, "utf8"));
      if (
        saved.digest === this.digest(token) &&
        Number.isSafeInteger(saved.owner) &&
        saved.owner > 0 &&
        typeof saved.deviceId === "string"
      ) {
        void bridge.setSession(token, false);
        return { owner: saved.owner, deviceId: saved.deviceId };
      }
    }
    await bridge.setSession(token);
    const identity = bridge.getIdentity();
    if (!identity || !bridge.isVerifiedSession(token))
      throw new Error("请先联网登录，验证当前账号后即可使用本地功能。");
    this.remember(token, identity);
    return identity;
  }
  clear(): void {
    if (existsSync(this.file)) unlinkSync(this.file);
  }
}
