import assert from "node:assert/strict";
import { test } from "node:test";
import { AsrClient } from "../lib/asr-client.ts";
import { applyAsrTranscript } from "../lib/asr-transcript.ts";

const tick = () => new Promise(setImmediate);
class Socket {
  readyState = 0;
  bufferedAmount = 0;
  sent = [];
  closeCount = 0;
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  send(value) {
    this.sent.push(value);
  }
  message(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  close() {
    this.readyState = 3;
    this.closeCount++;
    this.onclose?.({});
  }
}
function setup(overrides = {}, timeout = 1000) {
  const socket = new Socket();
  const received = [],
    statuses = [],
    errors = [];
  const client = new AsrClient(
    "meeting-1",
    "ws://localhost:8001/ws",
    {
      onTranscript: (message) => received.push(message),
      onStatus: (status) => statuses.push(status),
      onError: (message) => errors.push(message),
      ...overrides,
    },
    () => socket,
    timeout,
  );
  return { client, socket, received, statuses, errors };
}
async function connect(env) {
  const start = env.client.start({ nextSeq: 0, offsetMs: 0 });
  env.socket.open();
  const command = JSON.parse(env.socket.sent[0]);
  env.socket.message({
    type: "asr.ready",
    meetingId: "meeting-1",
    sessionId: "session-1",
    requestId: command.requestId,
  });
  await start;
  return command;
}
function transcript(changes = {}) {
  return {
    type: "asr.transcript",
    meetingId: "meeting-1",
    sessionId: "session-1",
    segment: {
      id: "meeting-1#0",
      seq: 0,
      revision: 1,
      text: "讨论知识库",
      speakerId: "speaker-1",
      startMs: 0,
      endMs: 1000,
      isFinal: false,
      ...changes,
    },
  };
}

test("audio waits for ready and is sent as binary PCM rather than Base64 JSON", async () => {
  const env = setup();
  const start = env.client.start({ nextSeq: 0, offsetMs: 0 });
  assert.equal(env.client.sendAudio(new ArrayBuffer(6400)), false);
  env.socket.open();
  const command = JSON.parse(env.socket.sent[0]);
  assert.deepEqual(command.audio, {
    format: "pcm",
    sampleRate: 16000,
    channels: 1,
    bitsPerSample: 16,
  });
  assert.equal(env.statuses.at(-1), "connecting");
  env.socket.message({
    type: "asr.ready",
    requestId: command.requestId,
    meetingId: "meeting-1",
    sessionId: "session-1",
  });
  await start;
  const pcm = new ArrayBuffer(6400);
  assert.equal(env.client.sendAudio(pcm), true);
  assert.equal(env.socket.sent.at(-1), pcm);
  assert.throws(() => env.client.sendAudio(new ArrayBuffer(3)), /PCM16/);
  env.client.close();
});

test("stop waits for final persistence callbacks and the matching stopped acknowledgement", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let saved = false;
  const env = setup({
    onTranscript: async () => {
      await gate;
      saved = true;
    },
  });
  await connect(env);
  const stopping = env.client.stop();
  const command = JSON.parse(env.socket.sent.at(-1));
  let stopped = false;
  void stopping.then(() => {
    stopped = true;
  });
  assert.equal(env.socket.closeCount, 0);
  env.socket.message(transcript({ isFinal: true, revision: 2 }));
  env.socket.message({
    type: "asr.stopped",
    requestId: command.requestId,
    meetingId: "meeting-1",
    sessionId: "session-1",
    lastFinalSeq: 0,
  });
  await tick();
  assert.equal(stopped, false);
  assert.equal(env.socket.closeCount, 0);
  release();
  await stopping;
  assert.equal(saved, true);
  assert.equal(env.socket.closeCount, 1);
  assert.equal(env.statuses.at(-1), "stopped");
});

test("messages from another meeting or recognition session are ignored", async () => {
  const env = setup();
  await connect(env);
  env.socket.message({ ...transcript(), meetingId: "other" });
  env.socket.message({ ...transcript(), sessionId: "old-session" });
  env.socket.message(transcript());
  await tick();
  assert.equal(env.received.length, 1);
  env.client.close();
});

test("provider errors reject startup and surface the safe server message", async () => {
  const env = setup();
  const pending = env.client.start({ nextSeq: 0, offsetMs: 0 });
  env.socket.open();
  env.socket.message({
    type: "asr.error",
    code: "PROVIDER_NOT_READY",
    message: "识别服务尚未接入",
    retryable: false,
  });
  await assert.rejects(pending, /识别服务尚未接入/);
  assert.equal(env.statuses.at(-1), "error");
  assert.deepEqual(env.errors, ["识别服务尚未接入"]);
});

test("missing ready and unexpected disconnect do not leave the client spinning", async () => {
  const env = setup({}, 10);
  await assert.rejects(env.client.start({ nextSeq: 0, offsetMs: 0 }), /超时/);
  assert.equal(env.statuses.at(-1), "error");
  const next = setup();
  await connect(next);
  next.socket.close();
  await tick();
  assert.equal(next.statuses.at(-1), "error");
  assert.match(next.errors.at(-1), /断开/);
});

test("malformed messages fail without adding invalid transcript data", async () => {
  const env = setup();
  await connect(env);
  env.socket.message(transcript({ seq: -1 }));
  await tick();
  assert.equal(env.statuses.at(-1), "error");
  assert.equal(env.received.length, 0);
});

test("transcript merge deduplicates revisions and never replaces confirmed text with partial text", () => {
  let draft = {
    meeting: { id: "meeting-1" },
    segments: [],
    dirtyEntries: [],
    temporary: { speaker: "", text: "" },
  };
  const partial = transcript();
  draft = applyAsrTranscript(draft, partial);
  assert.equal(draft.segments.length, 0);
  assert.equal(draft.temporary.text, "讨论知识库");
  assert.equal(applyAsrTranscript(draft, partial), draft);
  const final = transcript({ isFinal: true, revision: 2, text: "讨论知识库设计。" });
  draft = applyAsrTranscript(draft, final);
  assert.equal(draft.segments.length, 1);
  assert.equal(draft.temporary.text, "");
  assert.equal(applyAsrTranscript(draft, final), draft);
  assert.equal(applyAsrTranscript(draft, partial), draft);
  assert.equal(draft.dirtyEntries.length, 1);
  assert.equal(draft.segments[0].text, "讨论知识库设计。");
  assert.equal(applyAsrTranscript(draft, { ...final, meetingId: "other" }), draft);
});

test("reconnection sends the API sequence and time offset instead of reading a local database", async () => {
  const env = setup();
  const start = env.client.start({ nextSeq: 12, offsetMs: 6500 });
  env.socket.open();
  const command = JSON.parse(env.socket.sent[0]);
  assert.equal(command.nextSeq, 12);
  assert.equal(command.offsetMs, 6500);
  env.socket.message({
    type: "asr.ready",
    meetingId: "meeting-1",
    sessionId: "resume",
    requestId: command.requestId,
  });
  await start;
  env.client.close();
});

test("API persistence failure surfaces an error instead of reporting a successful stop", async () => {
  const env = setup({
    onTranscript: async () => {
      throw new Error("片段保存失败");
    },
  });
  await connect(env);
  const stopped = env.client.stop();
  env.socket.message(transcript({ isFinal: true }));
  await assert.rejects(stopped, /片段保存失败/);
  assert.equal(env.statuses.at(-1), "error");
  assert.match(env.errors.at(-1), /片段保存失败/);
});
