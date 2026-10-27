import type { SidecarToClient, WsAsrTranscript } from "@dp-work/protocols/asr";

export type AsrStatus = "idle" | "connecting" | "live" | "stopping" | "stopped" | "error";

type Pending = {
  requestId: string;
  resolve: () => void;
  reject: (cause: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};
type Callbacks = {
  onTranscript: (message: WsAsrTranscript) => unknown | Promise<unknown>;
  onStatus: (status: AsrStatus) => void;
  onError: (message: string) => void;
};

/** 校验 Sidecar 消息，避免无效结果进入会议记录。 */
function parseMessage(raw: string): SidecarToClient {
  const message = JSON.parse(raw);
  if (!message || typeof message !== "object") throw new Error("转写消息格式无效。");
  const text = (value: unknown) => typeof value === "string" && value.length > 0;
  const integer = (value: unknown, min = 0) =>
    Number.isSafeInteger(value) && (value as number) >= min;
  if (
    message.type === "asr.error" &&
    text(message.code) &&
    text(message.message) &&
    typeof message.retryable === "boolean"
  )
    return message;
  if (!text(message.meetingId)) throw new Error("转写消息缺少会议标识。");
  if (!text(message.sessionId)) throw new Error("转写消息缺少会话标识。");
  if (message.type === "asr.ready" && text(message.requestId)) return message;
  if (
    message.type === "asr.stopped" &&
    text(message.requestId) &&
    integer(message.lastFinalSeq, -1)
  )
    return message;
  const segment = message.segment;
  if (
    message.type === "asr.transcript" &&
    segment &&
    text(segment.id) &&
    integer(segment.seq) &&
    integer(segment.revision, 1) &&
    typeof segment.text === "string" &&
    (segment.speakerId === null || text(segment.speakerId)) &&
    integer(segment.startMs) &&
    integer(segment.endMs) &&
    segment.endMs >= segment.startMs &&
    typeof segment.isFinal === "boolean"
  )
    return message;
  throw new Error("转写消息格式无效。");
}

/** 管理单场会议的 WebSocket 生命周期。 */
export class AsrClient {
  private socket: WebSocket | null = null;
  private status: AsrStatus = "idle";
  private sessionId: string | null = null;
  private pendingStart: Pending | null = null;
  private pendingStop: Pending | null = null;
  private messages: Promise<void> = Promise.resolve();

  constructor(
    private meetingId: string,
    private url: string,
    private callbacks: Callbacks,
    private socketFactory = (url: string) => new WebSocket(url),
    private timeoutMs = 10_000,
  ) {}

  private setStatus(status: AsrStatus) {
    this.status = status;
    this.callbacks.onStatus(status);
  }

  private wait(kind: "pendingStart" | "pendingStop", requestId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => this.fail(new Error("等待转写服务响应超时，请重试。")),
        this.timeoutMs,
      );
      this[kind] = { requestId, resolve, reject, timer };
    });
  }

  private settle(kind: "pendingStart" | "pendingStop", cause?: Error) {
    const pending = this[kind];
    if (!pending) return;
    this[kind] = null;
    clearTimeout(pending.timer);
    if (cause) pending.reject(cause);
    else pending.resolve();
  }

  private fail(cause: Error) {
    this.settle("pendingStart", cause);
    this.settle("pendingStop", cause);
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.setStatus("error");
    this.callbacks.onError(cause.message);
  }

  start(position: { nextSeq: number; offsetMs: number; ticket?: string }): Promise<void> {
    if (!this.meetingId) return Promise.reject(new Error("缺少会议标识。"));
    if (this.socket) return Promise.reject(new Error("转写连接已存在。"));
    this.sessionId = null;
    this.messages = Promise.resolve();
    this.setStatus("connecting");
    const requestId = crypto.randomUUID();
    const ready = this.wait("pendingStart", requestId);
    try {
      const socket = this.socketFactory(this.url);
      this.socket = socket;
      socket.onopen = () => {
        if (this.socket !== socket) return;
        socket.send(
          JSON.stringify({
            type: "asr.start",
            requestId,
            meetingId: this.meetingId,
            ...position,
            audio: { format: "pcm", sampleRate: 16000, channels: 1, bitsPerSample: 16 },
          }),
        );
      };
      socket.onmessage = (event) => {
        this.messages = this.messages
          .then(async () => {
            if (this.socket !== socket) return;
            if (typeof event.data !== "string") throw new Error("转写服务返回了非 JSON 消息。");
            await this.receive(parseMessage(event.data));
          })
          .catch((cause) => {
            if (this.socket === socket)
              this.fail(cause instanceof Error ? cause : new Error("转写消息处理失败。"));
          });
      };
      socket.onerror = () => {
        if (this.socket === socket)
          this.fail(new Error("无法连接转写服务，请确认 Sidecar 已启动。"));
      };
      socket.onclose = () => {
        void this.messages.then(() => {
          if (this.socket !== socket) return;
          this.socket = null;
          if (this.status !== "stopped") this.fail(new Error("转写连接已断开，请重新开始转写。"));
        });
      };
    } catch (cause) {
      this.fail(cause instanceof Error ? cause : new Error("无法建立转写连接。"));
    }
    return ready;
  }

  private async receive(message: SidecarToClient) {
    if (message.meetingId && message.meetingId !== this.meetingId) return;
    if (message.type === "asr.error") throw new Error(message.message);
    if (message.type === "asr.ready") {
      if (message.requestId !== this.pendingStart?.requestId) return;
      this.sessionId = message.sessionId;
      this.setStatus("live");
      this.settle("pendingStart");
    } else if (message.sessionId === this.sessionId) {
      if (message.type === "asr.transcript") await this.callbacks.onTranscript(message);
      else if (message.requestId === this.pendingStop?.requestId) {
        this.setStatus("stopped");
        this.settle("pendingStop");
        this.socket?.close();
        this.socket = null;
      }
    }
  }

  /** 只在 ready 后发送 PCM16 二进制音频。 */
  sendAudio(audio: ArrayBuffer): boolean {
    const socket = this.socket;
    if (this.status !== "live" || !socket || socket.readyState !== 1) return false;
    if (!audio.byteLength || audio.byteLength % 2 || audio.byteLength > 64000)
      throw new Error("PCM16 音频帧大小无效。");
    if (socket.bufferedAmount > 256_000) {
      this.fail(new Error("转写连接发送积压，请重新开始转写。"));
      return false;
    }
    socket.send(audio);
    return true;
  }

  /** 等待确认片段处理完毕及 stopped 回执，再关闭连接。 */
  stop(): Promise<void> {
    if (this.status === "idle" || this.status === "stopped") return Promise.resolve();
    if (this.status === "connecting") {
      this.close();
      return Promise.resolve();
    }
    if (this.status !== "live" || !this.socket)
      return Promise.reject(new Error("转写连接不可用，请检查错误提示。"));
    this.setStatus("stopping");
    const requestId = crypto.randomUUID();
    const stopped = this.wait("pendingStop", requestId);
    try {
      this.socket.send(JSON.stringify({ type: "asr.stop", requestId, meetingId: this.meetingId }));
    } catch (cause) {
      this.fail(cause instanceof Error ? cause : new Error("停止转写失败。"));
    }
    return stopped;
  }

  /** 页面卸载时释放连接并取消等待。 */
  close() {
    this.settle("pendingStart", new Error("转写连接已关闭。"));
    this.settle("pendingStop", new Error("转写连接已关闭。"));
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.setStatus("stopped");
  }
}
