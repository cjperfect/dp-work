import { useLayoutEffect, type CSSProperties } from "react";
import { Download, LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { openDesktopUpdates, runDesktopUpdate, useDesktopUpdates } from "@/stores/desktop-updates";

/** 原生窗口按钮继续由 Electron 提供，仅更新按钮位于非拖拽区域。 */
export function DesktopTitlebar() {
  const chrome = typeof window === "undefined" ? undefined : window.desktop?.windowChrome;
  const update = useDesktopUpdates((state) => state.update);
  useLayoutEffect(() => {
    if (!chrome) return;
    const root = document.documentElement;
    root.dataset.desktopTitlebar = chrome.platform;
    root.style.setProperty("--desktop-titlebar-height", `${chrome.titleBarHeight}px`);
    return () => {
      delete root.dataset.desktopTitlebar;
      root.style.removeProperty("--desktop-titlebar-height");
    };
  }, [chrome]);
  if (!chrome) return null;
  const status = update?.status;
  const visible =
    status &&
    ["available", "downloading", "downloaded", "installing", "error"].includes(status) &&
    update?.availableVersion;
  const downloading = status === "downloading";
  const ready = status === "downloaded" || (status === "error" && update?.retry === "install");
  return (
    <header
      data-slot="desktop-titlebar"
      className="fixed inset-x-0 top-0 z-50 flex items-center justify-center border-b bg-[#f3f3f3] text-[#171717] select-none"
      style={{ height: chrome.titleBarHeight, WebkitAppRegion: "drag" } as CSSProperties}
    >
      <span className="pointer-events-none text-xs font-medium">企业 Agent 平台</span>
      {visible && (
        <Button
          size="sm"
          variant="ghost"
          disabled={downloading || status === "installing"}
          className="absolute h-6 gap-1.5 rounded-md px-2 text-xs text-[#171717] hover:bg-black/5"
          style={
            {
              right: chrome.platform === "darwin" ? 16 : 152,
              WebkitAppRegion: "no-drag",
            } as CSSProperties
          }
          onClick={() => {
            if (ready || status === "error") openDesktopUpdates();
            else void runDesktopUpdate("download");
          }}
        >
          {downloading || status === "installing" ? (
            <LoaderCircle className="size-3 animate-spin" />
          ) : ready ? (
            <RefreshCw className="size-3" />
          ) : (
            <Download className="size-3" />
          )}
          {downloading
            ? `下载中 ${Math.round(update?.percent ?? 0)}%`
            : status === "installing"
              ? "正在更新"
              : ready
                ? "重启更新"
                : status === "error"
                  ? "重试更新"
                  : "下载更新"}
        </Button>
      )}
    </header>
  );
}
