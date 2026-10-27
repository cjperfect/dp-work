/** API 协议替身，保留服务端数据以测试刷新、分支和账号隔离。 */
export function conversationFixture() {
  const details = new Map();
  const clone = (value) => structuredClone(value);
  const wrapped = (data) => ({ code: 0, data });
  function combine(detail) {
    const all = new Map((detail.message_branches ?? []).map((entry) => [entry.message.id, entry]));
    detail.messages.forEach((message, index) =>
      all.set(message.id, { parentId: detail.messages[index - 1]?.id ?? null, message }),
    );
    detail.message_branches = [...all.values()];
  }
  return {
    details,
    async handle(request, upstream) {
      const path = request.url;
      if (!path.startsWith("/api/agents/threads")) return upstream(request);
      const body = typeof request.data === "string" ? JSON.parse(request.data) : request.data;
      const method = request.method.toUpperCase();
      if (path === "/api/agents/threads" && method === "GET")
        return wrapped([...details.values()].map((d) => clone(d.thread)));
      if ((path === "/api/agents/threads" && method === "POST") || path.endsWith("/import")) {
        const imported = path.endsWith("/import");
        const thread = imported
          ? body.thread
          : {
              id: body.id,
              agent_id: body.agent_id,
              title: "新会话",
              title_source: "pending",
              draft: "",
              draft_revision: 0,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            };
        if (!details.has(thread.id))
          details.set(
            thread.id,
            imported
              ? clone(body)
              : {
                  thread,
                  knowledge_base_ids: body.knowledge_base_ids,
                  messages: [],
                  message_branches: [],
                },
          );
        return wrapped(clone(details.get(thread.id)));
      }
      const [, id, action] = path.match(/^\/api\/agents\/threads\/([^/]+)(?:\/(.*))?$/);
      const detail = details.get(id);
      if (!detail) throw new Error("会话不存在。");
      if (method === "GET") return wrapped(clone(detail));
      if (method === "DELETE") {
        details.delete(id);
        return wrapped(null);
      }
      if (action === "draft") {
        detail.thread.draft = body.draft;
        detail.knowledge_base_ids = body.knowledge_base_ids;
        detail.thread.draft_revision++;
        return wrapped(clone(detail.thread));
      }
      if (action === "messages") {
        detail.messages = clone(body.messages);
        detail.message_branches = clone(body.message_branches);
        combine(detail);
        detail.thread.draft_revision++;
        return wrapped(clone(detail));
      }
      if (action === "chat") {
        const reader = (await upstream(request)).getReader();
        let buffer = "",
          content = "";
        const decoder = new TextDecoder();
        function save(status) {
          const reply = detail.messages.find((message) => message.id === body.response_id);
          if (reply) {
            reply.content = content;
            reply.status = status;
          }
          combine(detail);
          if (status === "complete") detail.thread.draft = "";
          if (status !== "streaming") detail.thread.draft_revision++;
        }
        return new ReadableStream({
          async pull(controller) {
            const chunk = await reader.read();
            if (chunk.done) {
              controller.close();
              return;
            }
            buffer += decoder.decode(chunk.value, { stream: true });
            while (buffer.includes("\n\n")) {
              const split = buffer.indexOf("\n\n");
              const frame = buffer.slice(0, split);
              buffer = buffer.slice(split + 2);
              const data = frame
                .split("\n")
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trim())
                .join("\n");
              if (data) {
                const event = JSON.parse(data);
                if (event.type === "delta") {
                  content += event.text;
                  save("streaming");
                }
                if (event.type === "done") {
                  content = event.content;
                  save("complete");
                }
                if (event.type === "error") save("failed");
              }
            }
            controller.enqueue(chunk.value);
          },
          async cancel() {
            if (detail.messages.at(-1)?.status === "streaming") save("cancelled");
            await reader.cancel();
          },
        });
      }
      if (!action && method === "PATCH") {
        if (body.title_source !== "generated" || detail.thread.title_source === "pending") {
          detail.thread.title = body.title;
          detail.thread.title_source = body.title_source;
        }
        return wrapped(clone(detail.thread));
      }
      throw new Error(`未实现替身接口 ${method} ${path}`);
    },
  };
}
