import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { useAuthStore } from "../../../stores/auth.ts";
import {
  useKnowledgeStore,
  resetKnowledgeBases,
  saveKnowledgeDocument,
  renameKnowledgeDocument,
  deleteKnowledgeDocument,
} from "../../../stores/knowledge/index.ts";
import {
  uploadKnowledgeDocumentRequest,
  downloadKnowledgeDocumentRequest,
  loadKnowledgeDocumentsRequest,
  parseKnowledgeDocumentRequest,
} from "../../../apis/knowledge.ts";
import { listLocalEditorDocuments } from "../lib/legacy-documents.ts";

const originals = Object.fromEntries(
  ["window", "localStorage"].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
let values;
const base = {
  id: "server-1",
  serverId: 1,
  name: "文档库",
  accountId: "user:12",
  owner: "tester",
  files: [],
  createdAt: "2026-10-25",
  updatedAt: "2026-10-25",
};
const doc = {
  id: "editor-doc",
  knowledge_base_id: 1,
  title: "文档",
  content: "正文",
  blocks: [{ id: "p", type: "paragraph" }],
  created_at: "2026-10-25T00:00:00",
  updated_at: "2026-10-25T00:00:01",
};
const input = {
  id: doc.id,
  title: "文档.md",
  content: doc.content,
  blocks: doc.blocks,
  status: "published",
};
function cache(files) {
  values.set("dp-work:mock:v1:knowledge:user:12", JSON.stringify([{ ...base, files }]));
}
function legacy() {
  return {
    id: doc.id,
    name: "旧文档.md",
    source: "editor",
    type: "md",
    content: "旧正文",
    blocks: doc.blocks,
  };
}

beforeEach(() => {
  values = new Map();
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (key === "dp-work.auth.token" ? "test-token" : (values.get(key) ?? null)),
      setItem: (key, value) => values.set(key, value),
    },
  });
  useAuthStore.setState({ user: { id: 12, username: "tester" } });
  useKnowledgeStore.setState({ accountId: "user:12", bases: [base], status: "ready" });
  cache([]);
});
afterEach(() => {
  mock.restoreAll();
  resetKnowledgeBases();
  useAuthStore.setState({ user: null });
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

test("autosave uses API and keeps document content out of localStorage", async () => {
  const request = mockHttpRequest(async () => Response.json({ code: 0, data: doc }));
  const file = await saveKnowledgeDocument("user:12", base.id, input);
  const [url, init] = request.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1/documents/editor-doc");
  assert.equal(init.method, "PUT");
  assert.deepEqual(JSON.parse(init.body), {
    title: "文档",
    content: doc.content,
    blocks: doc.blocks,
  });
  assert.equal(file.id, doc.id);
  assert.deepEqual(useKnowledgeStore.getState().bases[0].files[0].blocks, doc.blocks);
  assert.equal(listLocalEditorDocuments("user:12", base.id).length, 0);
});

test("failed autosave does not report success or fall back to browser storage", async () => {
  mockHttpRequest(async () => Response.json({ code: 5000, message: "写入失败" }, { status: 500 }));
  await assert.rejects(saveKnowledgeDocument("user:12", base.id, input), /写入失败/);
  assert.deepEqual(useKnowledgeStore.getState().bases[0].files, []);
  assert.deepEqual(listLocalEditorDocuments("user:12", base.id), []);
});

test("legacy documents migrate once, retaining blocks and IDs", async () => {
  cache([legacy()]);
  const request = mockHttpRequest(async (_url, init) =>
    Response.json({ code: 0, data: init.method === "PUT" ? doc : [] }),
  );
  const [first, second] = await Promise.all([
    loadKnowledgeDocumentsRequest("user:12", base.id),
    loadKnowledgeDocumentsRequest("user:12", base.id),
  ]);
  assert.equal(request.mock.callCount(), 2);
  assert.deepEqual(first, second);
  assert.equal(first[0].id, doc.id);
  assert.deepEqual(JSON.parse(request.mock.calls[1].arguments[1].body).blocks, doc.blocks);
  assert.deepEqual(listLocalEditorDocuments("user:12", base.id), []);
});

test("migration failure retains the old browser copy for retry", async () => {
  cache([legacy()]);
  mockHttpRequest(async (_url, init) =>
    init.method === "PUT"
      ? Response.json({ code: 5000, message: "迁移失败" }, { status: 500 })
      : Response.json({ code: 0, data: [] }),
  );
  await assert.rejects(loadKnowledgeDocumentsRequest("user:12", base.id), /迁移失败/);
  assert.equal(listLocalEditorDocuments("user:12", base.id).length, 1);
});

test("existing server document wins over a stale browser copy", async () => {
  cache([legacy()]);
  const request = mockHttpRequest(async () => Response.json({ code: 0, data: [doc] }));
  const files = await loadKnowledgeDocumentsRequest("user:12", base.id);
  assert.equal(files[0].content, doc.content);
  assert.equal(request.mock.callCount(), 1);
  assert.deepEqual(listLocalEditorDocuments("user:12", base.id), []);
});

test("document deletion calls the server API before removing the memory record", async () => {
  useKnowledgeStore.setState({
    bases: [{ ...base, files: [{ id: doc.id, source: "editor" }], documentCount: 1 }],
  });
  const request = mockHttpRequest(async () => Response.json({ code: 0, data: null }));
  await deleteKnowledgeDocument("user:12", base.id, doc.id);
  assert.equal(request.mock.calls[0].arguments[0], "/api/knowledge-bases/1/documents/editor-doc");
  assert.equal(request.mock.calls[0].arguments[1].method, "DELETE");
  assert.deepEqual(useKnowledgeStore.getState().bases[0].files, []);
  assert.equal(useKnowledgeStore.getState().bases[0].documentCount, 0);
});

test("failed deletion retains the document for retry", async () => {
  const file = { id: doc.id, source: "editor" };
  useKnowledgeStore.setState({ bases: [{ ...base, files: [file] }] });
  mockHttpRequest(async () => Response.json({ code: 5000, message: "删除失败" }, { status: 500 }));
  await assert.rejects(deleteKnowledgeDocument("user:12", base.id, doc.id), /删除失败/);
  assert.deepEqual(useKnowledgeStore.getState().bases[0].files, [file]);
});

test("upload sends authenticated multipart data and returns a server-backed document", async () => {
  const file = new File(["# 文件上传"], "资料.md", { type: "text/markdown" });
  const request = mockHttpRequest(async () =>
    Response.json({
      code: 0,
      data: {
        ...doc,
        id: "upload-test",
        source: "upload",
        file_type: "md",
        original_name: "资料.md",
        byte_size: file.size,
      },
    }),
  );
  const saved = await uploadKnowledgeDocumentRequest("user:12", base.id, file);
  const [url, init] = request.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1/documents/upload");
  assert.equal(init.method, "POST");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.ok(init.body instanceof FormData);
  assert.equal(init.body.get("file").name, "资料.md");
  assert.equal(saved.name, "资料.md");
  assert.equal(saved.storage, "server");
  assert.equal(saved.source, "upload");
});

test("unsupported uploads fail before the request", async () => {
  const request = mockHttpRequest();
  await assert.rejects(
    uploadKnowledgeDocumentRequest("user:12", base.id, new File(["data"], "program.exe")),
    /Markdown/,
  );
  assert.equal(request.mock.callCount(), 0);
});

test("PDF bytes are fetched with a bearer header rather than a token in the URL", async () => {
  const content = "%PDF-1.4\nfixture";
  const request = mockHttpRequest(
    async () => new Response(content, { headers: { "Content-Type": "application/pdf" } }),
  );
  const blob = await downloadKnowledgeDocumentRequest("user:12", base.id, "upload-pdf");
  assert.equal(await blob.text(), content);
  assert.equal(
    request.mock.calls[0].arguments[0],
    "/api/knowledge-bases/1/documents/upload-pdf/file",
  );
  assert.equal(
    new Headers(request.mock.calls[0].arguments[1].headers).get("Authorization"),
    "Bearer test-token",
  );
});

test("TXT, Markdown and Word uploads retain their source type", async () => {
  const request = mockHttpRequest(async (_url, init) => {
    const file = init.body.get("file");
    const type = file.name.endsWith(".markdown") ? "md" : file.name.split(".").at(-1);
    return Response.json({
      code: 0,
      data: {
        ...doc,
        source: "upload",
        file_type: type,
        original_name: file.name,
      },
    });
  });
  for (const extension of ["txt", "markdown", "doc", "docx"]) {
    const file = new File(["fixture"], `source.${extension}`);
    const result = await uploadKnowledgeDocumentRequest("user:12", base.id, file);
    assert.equal(result.name, file.name);
    assert.equal(result.type, extension === "markdown" ? "md" : extension);
  }
  assert.equal(request.mock.callCount(), 4);
});

test("PDF parsing submits a protected task and maps durable result fields", async () => {
  const request = mockHttpRequest(async () =>
    Response.json({
      code: 0,
      data: {
        ...doc,
        file_type: "pdf",
        parse_status: "parsed",
        parse_content: "| A | B |",
        parsed_at: "2026-10-26T01:00:00Z",
        parse_error: null,
      },
    }),
  );
  const file = await parseKnowledgeDocumentRequest("user:12", base.id, doc.id);
  const [url, init] = request.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1/documents/editor-doc/parse");
  assert.equal(init.method, "POST");
  assert.equal(new Headers(init.headers).get("Authorization"), "Bearer test-token");
  assert.equal(file.parseStatus, "parsed");
  assert.equal(file.parsedContent, "| A | B |");
  assert.equal(file.content, doc.content);
});

test("renaming sends only a title and publishes the committed document to detail subscribers", async () => {
  const events = [];
  window.dispatchEvent = (event) => {
    events.push(event);
    return true;
  };
  const request = mockHttpRequest(async () =>
    Response.json({ code: 0, data: { ...doc, title: "新标题" } }),
  );
  const file = await renameKnowledgeDocument("user:12", base.id, doc.id, "新标题");
  const [url, init] = request.mock.calls[0].arguments;
  assert.equal(url, "/api/knowledge-bases/1/documents/editor-doc/title");
  assert.equal(init.method, "PATCH");
  assert.deepEqual(JSON.parse(init.body), { title: "新标题" });
  assert.equal(file.name, "新标题.md");
  assert.equal(events[0].detail.file.name, "新标题.md");
  assert.equal(events[0].detail.accountId, "user:12");
});

test("source autosave explicitly preserves the server title", async () => {
  const request = mockHttpRequest(async () =>
    Response.json({ code: 0, data: { ...doc, title: "服务端新标题" } }),
  );
  await saveKnowledgeDocument("user:12", base.id, { ...input, preserveTitle: true });
  assert.equal(JSON.parse(request.mock.calls[0].arguments[1].body).preserve_title, true);
});

test("a delayed old autosave response cannot undo a newer title in the cache", async () => {
  let finishOldSave;
  mockHttpRequest(async (url) => {
    if (String(url).endsWith("/title"))
      return Response.json({
        code: 0,
        data: { ...doc, title: "最新标题", updated_at: "2026-10-25T00:00:03" },
      });
    return new Promise((resolve) => {
      finishOldSave = () => resolve(Response.json({ code: 0, data: doc }));
    });
  });
  const oldSave = saveKnowledgeDocument("user:12", base.id, { ...input, preserveTitle: true });
  await new Promise(setImmediate);
  await renameKnowledgeDocument("user:12", base.id, doc.id, "最新标题");
  finishOldSave();
  await oldSave;
  assert.equal(useKnowledgeStore.getState().bases[0].files[0].name, "最新标题.md");
});

test("missing legacy storage never creates seeded knowledge bases", async () => {
  values.clear();
  assert.deepEqual(listLocalEditorDocuments("user:12", base.id), []);
  assert.equal(values.size, 0);
  mockHttpRequest(async () => Response.json({ code: 0, data: [doc] }));
  const files = await loadKnowledgeDocumentsRequest("user:12", base.id);
  assert.equal(files[0].id, doc.id);
  assert.equal(values.size, 0);
});

test("failed legacy cleanup retains the old copy without hiding committed server documents", async () => {
  cache([legacy()]);
  localStorage.setItem = () => {
    throw new Error("Browser storage is read only");
  };
  mockHttpRequest(async (_url, init) =>
    Response.json({ code: 0, data: init.method === "PUT" ? doc : [] }),
  );
  const files = await loadKnowledgeDocumentsRequest("user:12", base.id);
  assert.equal(files[0].id, doc.id);
  assert.equal(listLocalEditorDocuments("user:12", base.id).length, 1);
});
