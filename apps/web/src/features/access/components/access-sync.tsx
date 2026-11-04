import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { refreshAccess } from "@/stores/access";

/** 登录、窗口激活和定时核验权限，菜单不依赖本地缓存的角色名称。 */
export function AccessSync() {
  const userId = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    if (!userId) return;
    const refresh = () => {
      void refreshAccess().catch(() => {});
    };
    const visible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 60_000);
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [userId]);
  return null;
}
