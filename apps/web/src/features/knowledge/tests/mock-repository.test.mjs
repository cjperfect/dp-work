import assert from "node:assert/strict";
import { beforeEach, afterEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  listKnowledgeBases,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase,
  addKnowledgeDocument,
  saveEditorDocument,
} from "../lib/knowledge-repository.ts";
const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
beforeEach(() => {
  const values = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
  });
  useAuthStore.setState({ user: { id: 12, username: "tester" } });
});

test("editor drafts retain formatting and publish as the same document", async () => {
  const base = await createKnowledgeBase("user:12", { name: "在线文档库", description: "" });
  const blocks = [
    {
      id: "paragraph",
      type: "paragraph",
      content: [{ type: "text", text: "正文", styles: { bold: true } }],
    },
  ];
  const draft = await saveEditorDocument("user:12", base.id, {
    id: "editor-test",
    title: "  在线文档  ",
    content: "**正文**",
    blocks,
    status: "draft",
  });
  assert.equal(draft.file.name, "在线文档.md");
  assert.equal(draft.file.status, "draft");
  let reloaded = (await listKnowledgeBases("user:12")).find((row) => row.id === base.id);
  assert.deepEqual(reloaded.files[0].blocks, blocks);
  await saveEditorDocument("user:12", base.id, {
    id: draft.file.id,
    title: "修改后的标题.md",
    content: "**正文**",
    blocks,
    status: "published",
  });
  reloaded = (await listKnowledgeBases("user:12")).find((row) => row.id === base.id);
  assert.equal(reloaded.files.length, 1);
  assert.equal(reloaded.files[0].id, "editor-test");
  assert.equal(reloaded.files[0].status, "published");
  assert.equal(reloaded.files[0].name, "修改后的标题.md");
  assert.equal(
    (await listKnowledgeBases("user:13"))
      .flatMap((row) => row.files)
      .some((file) => file.id === "editor-test"),
    false,
  );
});

test("empty document bodies can be drafted but cannot be saved as completed documents", async () => {
  const base = await createKnowledgeBase("user:12", { name: "草稿库", description: "" });
  const input = { id: "editor-empty", title: "空草稿", content: "", status: "draft" };
  await saveEditorDocument("user:12", base.id, input);
  await assert.rejects(
    saveEditorDocument("user:12", base.id, { ...input, status: "published" }),
    /正文/,
  );
  await assert.rejects(
    saveEditorDocument("user:12", base.id, { ...input, title: " .md " }),
    /标题/,
  );
  await deleteKnowledgeBase("user:12", base.id);
  await assert.rejects(saveEditorDocument("user:12", base.id, input), /知识库不存在/);
});

test("online saves cannot replace uploaded or archived documents", async () => {
  const base = await createKnowledgeBase("user:12", { name: "资料库", description: "" });
  await addKnowledgeDocument("user:12", base.id, {
    id: "source-file",
    name: "源文件.md",
    type: "md",
    content: "原文",
    size: "1 KB",
    uploader: "tester",
    updatedAt: "2026-10-25",
  });
  await assert.rejects(
    saveEditorDocument("user:12", base.id, {
      id: "source-file",
      title: "覆盖",
      content: "修改",
      status: "published",
    }),
    /不支持在线编辑/,
  );
  assert.equal(
    (await listKnowledgeBases("user:12")).find((row) => row.id === base.id).files[0].content,
    "原文",
  );
});
afterEach(() => {
  mock.restoreAll();
  useAuthStore.setState({ user: null });
  if (original) Object.defineProperty(globalThis, "localStorage", original);
  else delete globalThis.localStorage;
});
test("mock knowledge CRUD persists and deleted identities are never reused", async () => {
  const fetch = mock.method(globalThis, "fetch");
  const initial = await listKnowledgeBases("user:12");
  assert.ok(initial.length > 0);
  const created = await createKnowledgeBase("user:12", { name: "测试库", description: "测试" });
  assert.ok(Number.isSafeInteger(Number(created.id)));
  await updateKnowledgeBase("user:12", created.id, { name: "修改后", description: "资料" });
  assert.equal(
    (await listKnowledgeBases("user:12")).find((row) => row.id === created.id).name,
    "修改后",
  );
  await deleteKnowledgeBase("user:12", created.id);
  assert.equal((await listKnowledgeBases("user:12")).length, initial.length);
  const next = await createKnowledgeBase("user:12", { name: "新库", description: "" });
  assert.notEqual(next.id, created.id);
  assert.equal(fetch.mock.callCount(), 0);
});
test("archived documents remain available after reloading knowledge data", async () => {
  const created = await createKnowledgeBase("user:12", { name: "纪要库", description: "" });
  const file = {
    id: "doc-meeting-1",
    name: "周会.md",
    type: "md",
    content: "## 会议结论",
    size: "1 KB",
    uploader: "tester",
    updatedAt: "2026-10-24",
  };
  await addKnowledgeDocument("user:12", created.id, file);
  const saved = (await listKnowledgeBases("user:12")).find((row) => row.id === created.id);
  assert.equal(saved.files[0].content, "## 会议结论");
  assert.equal(
    (await listKnowledgeBases("user:13")).some((row) => row.name === "纪要库"),
    false,
  );
});
