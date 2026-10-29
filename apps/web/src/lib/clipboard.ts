import { toast } from "sonner";

/** 在用户点击时复制，桌面端使用原生剪贴板。 */
export async function copyMessageText(text: string): Promise<void> {
  try {
    if (typeof window !== "undefined" && window.desktop?.writeClipboard) {
      await window.desktop.writeClipboard(text);
    } else if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      throw new Error("当前环境不支持剪贴板，请手动复制。");
    }
  } catch (cause) {
    toast.error("复制失败，请检查剪贴板权限或手动复制。");
    throw cause;
  }
}
