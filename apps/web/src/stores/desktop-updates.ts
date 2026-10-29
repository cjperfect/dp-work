import { create } from "zustand";
import type { DesktopUpdateState } from "@dp-work/protocols/desktop";

export const useDesktopUpdates = create<{
  open: boolean;
  update: DesktopUpdateState | null;
  error: string | null;
}>(() => ({ open: false, update: null, error: null }));
export function openDesktopUpdates() {
  useDesktopUpdates.setState({ open: true, error: null });
}

function receiveUpdate(update: DesktopUpdateState) {
  const previous = useDesktopUpdates.getState().update;
  if (!previous || update.revision >= previous.revision)
    useDesktopUpdates.setState({ update, error: null });
}

/** 先订阅再读取快照，较早发起的快照不能覆盖新事件。 */
export function connectDesktopUpdates() {
  const bridge = typeof window === "undefined" ? undefined : window.desktop;
  if (!bridge?.getUpdateState || !bridge.onUpdateState) return () => {};
  let alive = true,
    revision = 0;
  const dispose = bridge.onUpdateState((update) => {
    revision++;
    if (alive) receiveUpdate(update);
  });
  void bridge
    .getUpdateState()
    .then((update) => {
      if (alive && revision === 0) receiveUpdate(update);
    })
    .catch(() => {
      if (alive && revision === 0)
        useDesktopUpdates.setState({ error: "无法读取更新状态，请稍后重试。" });
    });
  return () => {
    alive = false;
    dispose();
  };
}

export async function runDesktopUpdate(action: "check" | "download" | "install") {
  const bridge = window.desktop;
  const method =
    action === "check"
      ? bridge?.checkForUpdates
      : action === "download"
        ? bridge?.downloadUpdate
        : bridge?.installUpdate;
  if (!method) {
    useDesktopUpdates.setState({ error: "请使用支持自动更新的桌面安装版。" });
    return;
  }
  useDesktopUpdates.setState({ error: null });
  try {
    const update = await method();
    receiveUpdate(update);
  } catch {
    useDesktopUpdates.setState({ error: "更新操作失败，请稍后重试。" });
  }
}
