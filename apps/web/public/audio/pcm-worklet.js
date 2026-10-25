class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.recording = true;
    this.port.onmessage = (event) => {
      if (event.data?.type === "flush") {
        this.recording = false;
        this.port.postMessage({ type: "flushed" });
      }
    };
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (this.recording && channel?.length) {
      const samples = channel.slice();
      this.port.postMessage(samples, [samples.buffer]);
    }
    return true;
  }
}
registerProcessor("dp-pcm-capture", PcmCaptureProcessor);
