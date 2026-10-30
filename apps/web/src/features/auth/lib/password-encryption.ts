import type { AuthMode, PasswordEncryptionKey } from "@/interfaces/auth";
import { CompactEncrypt, importJWK } from "jose";

export async function encryptPassword(
  key: PasswordEncryptionKey,
  username: string,
  password: string,
  purpose: AuthMode,
): Promise<string> {
  if (
    !globalThis.crypto?.subtle ||
    (typeof window !== "undefined" && window.isSecureContext === false)
  )
    throw new Error("请使用 HTTPS 地址登录；本机开发可以使用 localhost。");
  if (
    key.algorithm !== "RSA-OAEP-256" ||
    key.encryption !== "A256GCM" ||
    key.public_key.kty !== "RSA"
  )
    throw new Error("暂时无法安全提交登录信息，请稍后重试。");
  const deadline = (ms: number) =>
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("密码加密超时，请刷新页面后重试。")), ms),
    );
  let publicKey: CryptoKey;
  try {
    publicKey = (await Promise.race([
      importJWK(key.public_key, "RSA-OAEP-256"),
      deadline(6000),
    ])) as CryptoKey;
  } catch (cause) {
    if (cause instanceof Error && cause.message.includes("超时")) throw cause;
    throw new Error("浏览器加密模块不可用，请关闭浏览器插件后重试，或改用 Chrome 访问。", {
      cause,
    });
  }
  const payload = new TextEncoder().encode(
    JSON.stringify({ username, password, purpose, issued_at: key.server_time }),
  );
  try {
    return await Promise.race([
      new CompactEncrypt(payload)
        .setProtectedHeader({ alg: "RSA-OAEP-256", enc: "A256GCM", kid: key.key_id })
        .encrypt(publicKey),
      deadline(6000),
    ]);
  } catch (cause) {
    if (cause instanceof Error && cause.message.includes("超时")) throw cause;
    throw new Error("浏览器加密模块不可用，请关闭浏览器插件后重试，或改用 Chrome 访问。", {
      cause,
    });
  }
}
