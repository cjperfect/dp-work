import { useRef, useState } from "react";
import { useConnectors, applyFeishuStatus } from "@/stores/connectors";
import { useAuthStore } from "@/stores/auth";
import {
  startFeishuAuthorization,
  cancelFeishuAuthorization,
  verifyFeishuAuthorization,
  disconnectFeishu,
} from "@/apis/connectors";

/** 编排授权操作和账号隔离，页面只负责状态展示。 */
export function useConnectorPage() {
  const { connectors, feishu, loading, error, reload } = useConnectors({
    watchAuthorization: true,
  });
  const owner = useAuthStore((state) => state.user?.id ?? null);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ owner: number; text: string; failed: boolean } | null>(
    null,
  );
  const lock = useRef(false);
  const flow = feishu?.flow;
  const waiting = flow?.state === "starting" || flow?.state === "waiting";

  async function act(action: "configure" | "login" | "verify" | "disconnect" | "cancel") {
    if (owner === null || lock.current || !feishu) return;
    lock.current = true;
    setBusy(action);
    setNotice(null);
    try {
      if (action === "configure" || action === "login") {
        const nextFlow = await startFeishuAuthorization(action);
        applyFeishuStatus(owner, { ...feishu, flow: nextFlow });
      } else if (action === "verify") {
        const checked = await verifyFeishuAuthorization();
        applyFeishuStatus(owner, checked);
        setNotice({
          owner,
          failed: !checked.connected,
          text: checked.connected
            ? "验证成功，飞书用户身份有效。"
            : "尚未获得有效的用户授权，请完成或重新授权。",
        });
      } else {
        if (action === "disconnect") await disconnectFeishu();
        else await cancelFeishuAuthorization();
        setDisconnectOpen(false);
        await reload();
      }
    } catch (cause) {
      if (useAuthStore.getState().user?.id === owner)
        setNotice({
          owner,
          failed: true,
          text: cause instanceof Error ? cause.message : "操作失败，请重试。",
        });
    } finally {
      lock.current = false;
      setBusy(null);
    }
  }

  return {
    connectors,
    feishu,
    loading,
    error,
    reload,
    owner,
    disconnectOpen,
    setDisconnectOpen,
    busy,
    notice,
    flow,
    waiting,
    act,
  };
}
