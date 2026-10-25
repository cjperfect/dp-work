import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { PcmEncoder } from "../lib/pcm-encoder.ts";
import { PcmRecorder } from "../lib/pcm-recorder.ts";

function encode(rate, samples, split = samples.length) {
  const chunks = [];
  const encoder = new PcmEncoder(rate, (chunk) => chunks.push(chunk));
  for (let index = 0; index < samples.length; index += split)
    encoder.push(samples.subarray(index, index + split));
  encoder.flush();
  return Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)));
}

test("PCM encoder outputs 16kHz samples and retains state across 44.1kHz input boundaries", () => {
  const samples = Float32Array.from({ length: 44100 }, (_, i) =>
    Math.sin((2 * Math.PI * 440 * i) / 44100),
  );
  const whole = encode(44100, samples);
  const split = encode(44100, samples, 137);
  assert.equal(whole.length, 32000);
  assert.deepEqual(split, whole);
  assert.equal(encode(48000, new Float32Array(48000)).length, 32000);
});

test("PCM encoder clips samples, uses little endian and flushes a short tail exactly once", () => {
  const samples = new Float32Array([-2, -1, 0, 1, 2]);
  const pcm = encode(16000, samples);
  assert.deepEqual(
    Array.from({ length: 5 }, (_, i) => pcm.readInt16LE(i * 2)),
    [-32768, -32768, 0, 32767, 32767],
  );
  const chunks = [];
  const encoder = new PcmEncoder(16000, (chunk) => chunks.push(chunk));
  encoder.push(new Float32Array(3210));
  encoder.flush();
  encoder.flush();
  assert.deepEqual(
    chunks.map((chunk) => chunk.byteLength),
    [6400, 20],
  );
});

const globals = ["navigator", "AudioContext", "AudioWorkletNode"];
let originals;
let track, stream, contexts, nodes, getUserMedia;
class AudioNode {
  connections = [];
  disconnects = 0;
  connect(other) {
    this.connections.push(other);
    return other;
  }
  disconnect() {
    this.disconnects++;
  }
}
beforeEach(() => {
  originals = new Map(
    globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
  );
  contexts = [];
  nodes = [];
  track = {
    stops: 0,
    stop() {
      this.stops++;
    },
    addEventListener() {},
  };
  stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  getUserMedia = async () => stream;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia: (...args) => getUserMedia(...args) } },
  });
  Object.defineProperty(globalThis, "AudioContext", {
    configurable: true,
    value: class {
      sampleRate = 48000;
      closed = 0;
      destination = {};
      audioWorklet = {
        addModule: async (url) => {
          assert.equal(url, "/audio/pcm-worklet.js");
        },
      };
      source = new AudioNode();
      constructor() {
        contexts.push(this);
      }
      async resume() {}
      async close() {
        this.closed++;
      }
      createGain() {
        return Object.assign(new AudioNode(), { gain: { value: 1 } });
      }
      createMediaStreamSource() {
        return this.source;
      }
    },
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: class extends AudioNode {
      port = {
        onmessage: null,
        postMessage: () =>
          queueMicrotask(() => {
            // 模拟消息通道里排在 flush 回执之前的最后一帧。
            this.port.onmessage({ data: new Float32Array(96) });
            this.port.onmessage({ data: { type: "flushed" } });
          }),
        close() {},
      };
      constructor() {
        super();
        nodes.push(this);
      }
    },
  });
});
afterEach(() => {
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

test("recorder prepares without sending, then drains queued audio before releasing microphone", async () => {
  const sent = [],
    errors = [];
  const recorder = new PcmRecorder(
    (audio) => {
      sent.push(audio);
      return true;
    },
    (error) => errors.push(error),
  );
  await recorder.prepare();
  nodes.at(-1).port.onmessage({ data: new Float32Array(9600) });
  assert.equal(sent.length, 0);
  assert.equal(contexts.at(-1).source.connections.length, 0);
  recorder.start();
  nodes.at(-1).port.onmessage({ data: new Float32Array(9600) });
  assert.equal(sent[0].byteLength, 6400);
  await recorder.stop();
  assert.deepEqual(
    sent.map((chunk) => chunk.byteLength),
    [6400, 64],
  );
  assert.equal(track.stops, 1);
  assert.equal(contexts.at(-1).closed, 1);
  assert.equal(errors.length, 0);
});

test("permission rejection releases the audio context and shows an actionable error", async () => {
  getUserMedia = async () => {
    throw new DOMException("denied", "NotAllowedError");
  };
  const recorder = new PcmRecorder(
    () => true,
    () => {},
  );
  await assert.rejects(recorder.prepare(), /麦克风权限被拒绝/);
  assert.equal(contexts.at(-1).closed, 1);
});

test("cancelling while permission is pending also releases a stream granted later", async () => {
  let grant;
  getUserMedia = () =>
    new Promise((resolve) => {
      grant = resolve;
    });
  const recorder = new PcmRecorder(
    () => true,
    () => {},
  );
  const pending = recorder.prepare();
  recorder.close();
  grant(stream);
  await assert.rejects(pending, /录音已取消/);
  assert.equal(track.stops, 1);
  assert.equal(contexts.at(-1).closed, 1);
});
