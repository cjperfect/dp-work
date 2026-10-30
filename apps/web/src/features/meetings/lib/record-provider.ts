import type { RecordDocument } from "@/interfaces/meeting";
import * as Y from "yjs";
import {
  Awareness,
  applyAwarenessUpdate,
  encodeAwarenessUpdate,
  removeAwarenessStates,
} from "y-protocols/awareness";

import { getAccessToken, useAuthStore } from "@/stores/auth";

export const decodeState = (state: string) =>
  Uint8Array.from(atob(state), (value) => value.charCodeAt(0));
export function encodeState(state: Uint8Array) {
  let value = "";
  for (let i = 0; i < state.length; i += 8192)
    value += String.fromCharCode(...state.subarray(i, i + 8192));
  return btoa(value);
}
export type RecordStatus = {
  document: RecordDocument;
  connected: boolean;
  pending: boolean;
  saving: boolean;
  saveError: string | null;
  error: string | null;
};

/** 同步 CRDT 增量；只有收到持久化确认后，才显示已保存。 */
export class RecordProvider {
  doc = new Y.Doc();
  awareness = new Awareness(this.doc);
  private socket: WebSocket | null = null;
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private seq = 0;
  private pending = new Map<number, Uint8Array>();
  private waiters = new Set<(error?: Error) => void>();
  private idleTimer?: ReturnType<typeof setTimeout>;
  private retryTimer?: ReturnType<typeof setTimeout>;
  private saveTimer?: ReturnType<typeof setTimeout>;
  private interval: ReturnType<typeof setInterval>;
  private saveSeq = 0;
  private retryCount = 0;
  private token = getAccessToken();
  private status: RecordStatus;
  constructor(
    document: RecordDocument,
    private share: string | undefined,
    private changed: (status: RecordStatus) => void,
    private reset: (document: RecordDocument) => void,
  ) {
    this.status = {
      document,
      connected: false,
      pending: false,
      saving: false,
      saveError: null,
      error: null,
    };
    const user = useAuthStore.getState().user;
    if (user)
      this.awareness.setLocalStateField("collaborator", { id: user.id, username: user.username });
    Y.applyUpdate(this.doc, decodeState(document.state), this);
    this.doc.on("update", this.onUpdate);
    this.awareness.on("update", this.onAwareness);
    this.interval = setInterval(() => {
      if (!this.retryTimer) this.persistNow();
    }, 5000);
    window.addEventListener?.("pagehide", this.onPageHide);
    globalThis.document?.addEventListener("visibilitychange", this.onVisibility);
    this.connect();
  }
  private emit() {
    this.changed({ ...this.status, pending: this.needsSave() });
  }
  private onUpdate = (update: Uint8Array, origin: unknown) => {
    if (origin === this || this.stopped) return;
    const seq = ++this.seq;
    this.pending.set(seq, update);
    this.send(seq, update);
    this.scheduleSave();
    this.emit();
  };
  private needsSave() {
    return (
      this.pending.size > 0 ||
      this.status.document.revision >
        (this.status.document.saved_revision ?? this.status.document.revision)
    );
  }
  private scheduleSave() {
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      if (!this.retryTimer) this.persistNow();
    }, 1000);
  }
  private onPageHide = () => this.persistNow();
  private onVisibility = () => {
    if (globalThis.document?.visibilityState === "hidden") this.persistNow();
  };
  private saveFailed(message: string) {
    clearTimeout(this.saveTimer);
    this.status.saving = false;
    this.status.saveError = message;
    for (const done of this.waiters) done(new Error(message));
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(
      () => {
        this.retryTimer = undefined;
        this.persistNow();
      },
      Math.min(2000 * 2 ** Math.min(this.retryCount++, 4), 30000),
    );
    this.emit();
  }
  private persistNow() {
    if (
      this.stopped ||
      !this.status.connected ||
      this.status.saving ||
      this.status.error ||
      !this.needsSave() ||
      this.socket?.readyState !== WebSocket.OPEN
    )
      return;
    clearTimeout(this.idleTimer);
    this.status.saving = true;
    this.status.saveError = null;
    this.socket.send(
      JSON.stringify({ type: "save", save_seq: ++this.saveSeq, epoch: this.status.document.epoch }),
    );
    this.saveTimer = setTimeout(() => this.saveFailed("自动保存超时，请重试。"), 15000);
    this.emit();
  }
  private onAwareness = (
    { added, updated, removed }: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ) => {
    if (origin === this || this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(
      JSON.stringify({
        type: "awareness",
        update: encodeState(
          encodeAwarenessUpdate(this.awareness, [...added, ...updated, ...removed]),
        ),
      }),
    );
  };
  private send(seq: number, update: Uint8Array) {
    if (this.status.connected && this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(
        JSON.stringify({
          type: "update",
          seq,
          epoch: this.status.document.epoch,
          update: encodeState(update),
        }),
      );
  }
  private connect = () => {
    if (this.stopped || getAccessToken() !== this.token) return;
    const url = new URL(
      `/api/meetings/${this.status.document.meeting_id}/record/events`,
      window.location.href,
    );
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    this.socket = socket;
    socket.onopen = () =>
      socket.send(JSON.stringify({ token: this.token, share_token: this.share }));
    socket.onmessage = (event) => {
      if (this.stopped || socket !== this.socket || getAccessToken() !== this.token) return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === "awareness") {
          const before = new Set(this.awareness.getStates().keys());
          applyAwarenessUpdate(this.awareness, decodeState(message.update), this);
          // 新进入的同事立即收到已有成员信息，不必等心跳。
          if (
            [...this.awareness.getStates().keys()].some(
              (id) => id !== this.doc.clientID && !before.has(id),
            )
          )
            this.onAwareness({ added: [this.doc.clientID], updated: [], removed: [] }, null);
          return;
        }
        if (message.type === "save.error") {
          this.saveFailed(message.message || "自动保存失败，请重试。");
          return;
        }
        if (message.type === "error") {
          this.status.error = message.message;
          this.emit();
          return;
        }
        if (!["state", "ack", "saved"].includes(message.type)) return;
        const document = message as RecordDocument;
        if (document.epoch !== this.status.document.epoch) {
          if (this.pending.size) {
            this.status.error = "纪要已恢复历史版本。请复制未同步内容后重新加载。";
            this.status.document.editable = false;
            this.emit();
            return;
          }
          this.reset(document);
          return;
        }
        const previousRevision = this.status.document.revision;
        Y.applyUpdate(this.doc, decodeState(document.state), this);
        if (message.type === "ack") this.pending.delete(message.seq);
        if (document.revision >= this.status.document.revision) this.status.document = document;
        else if ((document.saved_revision ?? 0) > (this.status.document.saved_revision ?? 0))
          this.status.document = {
            ...this.status.document,
            saved_revision: document.saved_revision,
            saved_at: document.saved_at,
          };
        if (message.type === "saved" && message.save_seq === this.saveSeq) {
          clearTimeout(this.saveTimer);
          this.status.saving = false;
          this.status.saveError = null;
          this.retryCount = 0;
        }
        const wasConnected = this.status.connected;
        this.status.connected = true;
        this.status.error = null;
        if (!wasConnected) {
          for (const [seq, update] of this.pending) this.send(seq, update);
          this.onAwareness({ added: [this.doc.clientID], updated: [], removed: [] }, null);
        }
        if (this.needsSave()) {
          if (!wasConnected || document.revision > previousRevision) this.scheduleSave();
          if (this.waiters.size) this.persistNow();
        } else {
          clearTimeout(this.saveTimer);
          clearTimeout(this.retryTimer);
          this.retryTimer = undefined;
          this.status.saving = false;
          this.status.saveError = null;
          this.retryCount = 0;
          for (const done of this.waiters) done();
        }
        this.emit();
      } catch {
        this.status.error = "协作同步失败，请重新加载。";
        this.emit();
      }
    };
    socket.onclose = (event) => {
      this.status.connected = false;
      this.status.saving = false;
      clearTimeout(this.saveTimer);
      removeAwarenessStates(
        this.awareness,
        [...this.awareness.getStates().keys()].filter((id) => id !== this.doc.clientID),
        this,
      );
      if (this.stopped) return;
      if ([4401, 4403].includes(event.code))
        this.status.error = "登录或分享权限已失效，请重新登录或打开链接。";
      else this.timer = setTimeout(this.connect, 2000);
      this.emit();
    };
  };
  async flush() {
    if (this.status.error) throw new Error(this.status.error);
    if (!this.status.connected) throw new Error("协作连接尚未就绪，请稍后重试。");
    if (!this.needsSave()) return;
    clearTimeout(this.idleTimer);
    clearTimeout(this.retryTimer);
    this.retryTimer = undefined;
    await new Promise<void>((resolve, reject) => {
      const done = (error?: Error) => {
        clearTimeout(timer);
        this.waiters.delete(done);
        if (error) reject(error);
        else resolve();
      };
      const timer = setTimeout(() => {
        this.waiters.delete(done);
        reject(new Error("纪要仍未同步，请稍后重试。"));
      }, 15000);
      this.waiters.add(done);
      this.persistNow();
    });
  }
  destroy() {
    if (this.status.connected && this.needsSave() && this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(
        JSON.stringify({
          type: "save",
          save_seq: ++this.saveSeq,
          epoch: this.status.document.epoch,
        }),
      );
    this.stopped = true;
    clearTimeout(this.idleTimer);
    clearTimeout(this.retryTimer);
    clearTimeout(this.saveTimer);
    clearInterval(this.interval);
    window.removeEventListener?.("pagehide", this.onPageHide);
    globalThis.document?.removeEventListener("visibilitychange", this.onVisibility);
    for (const done of this.waiters) done(new Error("编辑器已关闭，正在补保存。"));
    clearTimeout(this.timer);
    this.doc.off("update", this.onUpdate);
    this.awareness.destroy();
    this.socket?.close();
    this.doc.destroy();
  }
}
