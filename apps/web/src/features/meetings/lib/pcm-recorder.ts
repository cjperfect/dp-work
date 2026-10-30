import { PcmEncoder } from "./pcm-encoder";

/** 管理麦克风、AudioWorklet 和音频帧收尾。 */
export class PcmRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private gain: GainNode | null = null;
  private encoder: PcmEncoder | null = null;
  private recording = false;
  private generation = 0;
  private flushDone: (() => void) | null = null;

  constructor(
    private onChunk: (audio: ArrayBuffer) => boolean,
    private onError: (cause: Error) => void,
  ) {}

  async prepare() {
    const generation = ++this.generation;
    if (!navigator.mediaDevices?.getUserMedia || !globalThis.AudioContext)
      throw new Error("当前环境不支持录音，请使用桌面端或 HTTPS / localhost 页面。");
    const context = new AudioContext({ sampleRate: 16000, latencyHint: "interactive" });
    this.context = context;
    try {
      const acquireMic = async () => {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
          video: false,
        });
        if (generation !== this.generation) {
          stream.getTracks().forEach((track) => track.stop());
          throw new Error("录音已取消。");
        }
        this.stream = stream;
      };
      await Promise.all([acquireMic(), context.resume()]);
      if (generation !== this.generation) throw new Error("录音已取消。");
      if (!context.audioWorklet) throw new Error("当前环境不支持实时音频处理。");
      await context.audioWorklet.addModule("/audio/pcm-worklet.js");
      if (generation !== this.generation || !this.stream) throw new Error("录音已取消。");
      this.encoder = new PcmEncoder(context.sampleRate, (chunk) => {
        if (!this.onChunk(chunk)) throw new Error("转写连接已停止，音频未能发送。");
      });
      this.node = new AudioWorkletNode(context, "dp-pcm-capture", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        channelCount: 1,
        channelCountMode: "explicit",
      });
      this.node.port.onmessage = (event) => {
        if (event.data?.type === "flushed") {
          this.flushDone?.();
          return;
        }
        if (!this.recording || !(event.data instanceof Float32Array)) return;
        try {
          this.encoder?.push(event.data);
        } catch (cause) {
          this.onError(cause instanceof Error ? cause : new Error("音频处理失败。"));
        }
      };
      this.node.onprocessorerror = () =>
        this.onError(new Error("实时音频处理异常，请重新开始转写。"));
      this.gain = context.createGain();
      this.gain.gain.value = 0;
      this.node.connect(this.gain).connect(context.destination);
      this.source = context.createMediaStreamSource(this.stream);
      this.stream.getAudioTracks().forEach((track) =>
        track.addEventListener("ended", () => {
          if (this.recording) this.onError(new Error("麦克风已断开，请检查设备后重试。"));
        }),
      );
    } catch (cause) {
      this.close();
      if (
        cause instanceof DOMException &&
        ["NotAllowedError", "PermissionDeniedError"].includes(cause.name)
      )
        throw new Error("麦克风权限被拒绝，请在系统或浏览器设置中允许录音。", { cause });
      if (
        cause instanceof DOMException &&
        ["NotFoundError", "NotReadableError"].includes(cause.name)
      )
        throw new Error("麦克风不可用，请检查设备连接或是否被其他应用占用。", { cause });
      throw cause;
    }
  }

  start() {
    if (!this.source || !this.node) throw new Error("录音尚未准备完成。");
    this.recording = true;
    this.source.connect(this.node);
  }

  async stop() {
    try {
      if (this.recording && this.node) {
        this.source?.disconnect();
        await new Promise<void>((resolve, reject) => {
          const timer = setTimeout(() => {
            this.flushDone = null;
            reject(new Error("等待麦克风音频收尾超时。"));
          }, 1500);
          this.flushDone = () => {
            clearTimeout(timer);
            this.flushDone = null;
            resolve();
          };
          this.node!.port.postMessage({ type: "flush" });
        });
        this.encoder?.flush();
      }
    } finally {
      this.close();
    }
  }

  close() {
    this.generation++;
    this.recording = false;
    this.source?.disconnect();
    this.node?.disconnect();
    this.node?.port.close();
    this.gain?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.flushDone?.();
    this.flushDone = null;
    void this.context?.close().catch(() => {});
    this.context = null;
    this.stream = null;
    this.source = null;
    this.node = null;
    this.gain = null;
    this.encoder = null;
  }
}
