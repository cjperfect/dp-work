/** 将连续音频重采样为 16kHz PCM16 小端，每包 200ms。 */
export class PcmEncoder {
  private buffer = new ArrayBuffer(6400);
  private view = new DataView(this.buffer);
  private count = 0;
  private ratio: number;
  private remaining: number;
  private sum = 0;

  constructor(
    sampleRate: number,
    private onChunk: (audio: ArrayBuffer) => void,
  ) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000) throw new Error("录音采样率不受支持。");
    this.ratio = sampleRate / 16000;
    this.remaining = this.ratio;
  }

  push(samples: Float32Array) {
    for (const sample of samples) {
      let available = 1;
      while (available > 1e-9) {
        const weight = Math.min(available, this.remaining);
        this.sum += (Number.isFinite(sample) ? sample : 0) * weight;
        this.remaining -= weight;
        available -= weight;
        if (this.remaining < 1e-9) {
          const value = Math.max(-1, Math.min(1, this.sum / this.ratio));
          this.view.setInt16(this.count * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
          this.count++;
          this.sum = 0;
          this.remaining = this.ratio;
          if (this.count === 3200) {
            const chunk = this.buffer;
            this.buffer = new ArrayBuffer(6400);
            this.view = new DataView(this.buffer);
            this.count = 0;
            this.onChunk(chunk);
          }
        }
      }
    }
  }

  flush() {
    if (!this.count) return;
    const chunk = this.buffer.slice(0, this.count * 2);
    this.count = 0;
    this.buffer = new ArrayBuffer(6400);
    this.view = new DataView(this.buffer);
    this.onChunk(chunk);
  }
}
