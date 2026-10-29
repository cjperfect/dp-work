import assert from "node:assert/strict";
import { test } from "node:test";
import { httpClient } from "../../../lib/http.ts";
import { imageAttachmentAdapter, messageImages } from "../lib/image-attachments.ts";
import { useAuthStore } from "../../../stores/auth.ts";
import { imagePreview } from "../../../apis/chat-images.ts";
import { toRuntimeMessage } from "../lib/message-branches.ts";

test("pasted images save locally, expose stable references and reappear in history", async () => {
  const storage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => "fixture" },
  });
  const id = "a".repeat(64),
    seen = [];
  useAuthStore.setState({ user: { id: 71, username: "fixture" } });
  const interceptor = httpClient.interceptors.request.use((config) => {
    config.adapter = async (request) => {
      seen.push(JSON.parse(request.data));
      return {
        data: { code: 0, data: { id, name: "截图.png", content_type: "image/png" } },
        status: 200,
        headers: {},
        config: request,
      };
    };
    return config;
  });
  try {
    const file = new File([Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])], "截图.png", {
      type: "image/png",
    });
    const pending = await imageAttachmentAdapter.add({ file });
    assert.equal(pending.id, id);
    const complete = await imageAttachmentAdapter.send(pending);
    const refs = messageImages([complete]);
    assert.deepEqual(refs, [{ id, name: "截图.png", content_type: "image/png" }]);
    assert.ok(seen[0].data_url.startsWith("data:image/png;base64,"));
    assert.ok(imagePreview(id));
    const runtime = toRuntimeMessage({
      id: "message",
      role: "user",
      content: "图片",
      created_at: new Date().toISOString(),
      context: { images: refs },
      status: "complete",
    });
    assert.equal(runtime.attachments[0].content[0].image, imagePreview(id));
    assert.throws(() => messageImages([complete, complete, complete, complete]), /最多/);
    await assert.rejects(
      imageAttachmentAdapter.add({ file: new File(["test"], "test.txt", { type: "text/plain" }) }),
      /支持/,
    );
  } finally {
    httpClient.interceptors.request.eject(interceptor);
    useAuthStore.setState({ user: null });
    if (storage) Object.defineProperty(globalThis, "localStorage", storage);
    else delete globalThis.localStorage;
  }
});
