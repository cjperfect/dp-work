import type { AppUpdater } from "electron-updater";
import type { DesktopUpdateState } from "@dp-work/protocols/desktop";

type Backend = Pick<
  AppUpdater,
  | "autoDownload"
  | "autoInstallOnAppQuit"
  | "allowPrerelease"
  | "allowDowngrade"
  | "on"
  | "checkForUpdates"
  | "downloadUpdate"
  | "quitAndInstall"
>;
type Options = {
  packaged: boolean;
  platform: string;
  appImage?: string;
  version: string;
  backend: Backend;
  emit: (state: DesktopUpdateState) => void;
  prepareInstall: () => Promise<void>;
};

export class UpdateBusyError extends Error {}

/** 只使用安装包中固定的发布源，Renderer 不能传入 URL、版本或安装文件。 */
export class UpdateManager {
  private value: DesktopUpdateState;
  private operation: Promise<DesktopUpdateState> | null = null;
  private startup: NodeJS.Timeout | null = null;
  private interval: NodeJS.Timeout | null = null;
  private closed = false;

  constructor(private options: Options) {
    const supported =
      options.packaged &&
      (["darwin", "win32"].includes(options.platform) ||
        (options.platform === "linux" && !!options.appImage));
    this.value = {
      revision: 0,
      status: supported ? "idle" : "disabled",
      currentVersion: options.version,
      ...(!supported
        ? {
            message: options.packaged
              ? "当前安装形式不支持应用内更新，请使用 AppImage 安装包。"
              : "开发模式不检查更新，请在安装版中验证。",
          }
        : {}),
    };
    const updater = options.backend;
    updater.autoDownload = false;
    updater.autoInstallOnAppQuit = false;
    updater.allowPrerelease = false;
    updater.allowDowngrade = false;
    updater.on("update-available", (info) => {
      if (this.value.status === "checking")
        this.set({
          status: "available",
          availableVersion: info.version,
          message: undefined,
          retry: undefined,
        });
    });
    updater.on("update-not-available", () => {
      if (this.value.status === "checking")
        this.set({
          status: "idle",
          availableVersion: undefined,
          message: "当前已是最新版本。",
          retry: undefined,
        });
    });
    updater.on("download-progress", (progress) => {
      if (this.value.status === "downloading")
        this.set({
          percent: Number.isFinite(progress.percent)
            ? Math.min(100, Math.max(0, progress.percent))
            : 0,
        });
    });
    updater.on("update-downloaded", (info) => {
      if (this.value.status === "downloading")
        this.set({
          status: "downloaded",
          availableVersion: info.version,
          percent: 100,
          message: undefined,
          retry: undefined,
        });
    });
    // 退出期间也保留 error listener，避免 EventEmitter 的未处理 error。
    updater.on("error", () => {
      if (!this.closed)
        this.fail(
          this.value.status === "downloading"
            ? "download"
            : this.value.status === "installing"
              ? "install"
              : "check",
        );
    });
  }

  getState(): DesktopUpdateState {
    return { ...this.value };
  }
  private set(change: Partial<DesktopUpdateState>) {
    if (this.closed) return;
    this.value = { ...this.value, ...change, revision: this.value.revision + 1 };
    this.options.emit(this.getState());
  }
  private fail(retry: "check" | "download" | "install", message?: string) {
    this.set({
      status: "error",
      retry,
      message:
        message ??
        (retry === "check"
          ? "检查更新失败，请检查网络或稍后重试。"
          : retry === "download"
            ? "下载或校验更新失败，请重试下载。"
            : "无法安装更新，请稍后重试。"),
    });
  }
  private perform(action: () => Promise<void>) {
    if (this.operation) return this.operation;
    const operation = action().then(() => this.getState());
    this.operation = operation;
    void operation.finally(() => {
      if (this.operation === operation) this.operation = null;
    });
    return operation;
  }
  start() {
    if (this.value.status === "disabled" || this.closed || this.startup) return;
    this.startup = setTimeout(() => {
      void this.check();
    }, 15000);
    this.startup.unref();
    this.interval = setInterval(
      () => {
        void this.check();
      },
      4 * 60 * 60 * 1000,
    );
    this.interval.unref();
  }
  check(): Promise<DesktopUpdateState> {
    if (
      this.closed ||
      this.value.status === "disabled" ||
      ["downloading", "downloaded", "installing"].includes(this.value.status)
    )
      return Promise.resolve(this.getState());
    return this.perform(async () => {
      this.set({ status: "checking", message: undefined, retry: undefined, percent: undefined });
      try {
        await this.options.backend.checkForUpdates();
        if (this.value.status === "checking") this.fail("check");
      } catch {
        this.fail("check");
      }
    });
  }
  download(): Promise<DesktopUpdateState> {
    if (
      this.closed ||
      !this.value.availableVersion ||
      !(
        this.value.status === "available" ||
        (this.value.status === "error" && this.value.retry === "download")
      )
    )
      return Promise.resolve(this.getState());
    return this.perform(async () => {
      this.set({ status: "downloading", percent: 0, message: undefined, retry: undefined });
      try {
        await this.options.backend.downloadUpdate();
        if (this.value.status === "downloading") this.fail("download");
      } catch {
        this.fail("download");
      }
    });
  }
  install(): Promise<DesktopUpdateState> {
    if (
      this.closed ||
      !(
        this.value.status === "downloaded" ||
        (this.value.status === "error" && this.value.retry === "install")
      )
    )
      return Promise.resolve(this.getState());
    return this.perform(async () => {
      this.set({ status: "installing", message: undefined, retry: undefined });
      try {
        await this.options.prepareInstall();
        this.options.backend.quitAndInstall(false, true);
      } catch (cause) {
        this.fail(
          "install",
          cause instanceof UpdateBusyError
            ? "请先结束会议、停止正在执行的任务，并等待本地操作完成后重试。"
            : undefined,
        );
      }
    });
  }
  close() {
    this.closed = true;
    if (this.startup) clearTimeout(this.startup);
    if (this.interval) clearInterval(this.interval);
    this.startup = this.interval = null;
  }
}
