/** Renderer 的现有业务地址仅在 Main 转换为语义 RPC，不发送云端。 */
export type LocalCall = {
  method: string;
  params: Record<string, unknown>;
  needsRetrieval?: boolean;
};
export function routeLocal(
  path: string,
  verb: string,
  query: Record<string, unknown>,
  body: Record<string, unknown>,
  owner: number,
  deviceId: string,
): LocalCall {
  if (!path.startsWith("/api/") || path.includes("?") || path.includes("..") || path.includes("\\"))
    throw new Error("无效的本地业务路径。");
  const session = (action: string, thread_id?: string, data = body): LocalCall => ({
    method: `sessions.${action}`,
    params: { owner_id: owner, ...(thread_id ? { thread_id } : {}), body: data },
    needsRetrieval: action === "chat" || action === "approval.decide",
  });
  if (path === "/api/memories/preferences" && ["GET", "PUT"].includes(verb))
    return {
      method: verb === "GET" ? "memory.preferences" : "memory.preferences.update",
      params: { owner_id: owner, body: verb === "GET" ? {} : body },
    };
  const memory = path.match(/^\/api\/memories(?:\/([a-fA-F0-9-]{36}))?$/);
  if (memory) {
    const action = memory[1]
      ? ({ PATCH: "update", DELETE: "delete" } as Record<string, string>)[verb]
      : ({ GET: "list", POST: "create" } as Record<string, string>)[verb];
    if (action)
      return {
        method: `memory.${action}`,
        params: {
          owner_id: owner,
          ...(memory[1] ? { key: memory[1] } : {}),
          body: verb === "GET" ? query : body,
        },
      };
  }
  if (path === "/api/agents/threads") {
    if (verb === "GET") return session("list", undefined, query);
    if (verb === "POST") return session("create");
  }
  if (path === "/api/agents/threads/import" && verb === "POST") return session("import");
  if (path === "/api/agents/images" && verb === "POST") return session("images.save");
  if (path === "/api/agents/images" && verb === "GET")
    return session("images.read", undefined, query);
  const fileUndo = path.match(
    /^\/api\/agents\/threads\/([a-zA-Z0-9_-]{1,128})\/files\/([a-f0-9-]{36})\/undo$/,
  );
  if (fileUndo && verb === "POST")
    return session("files.undo", fileUndo[1], { change_id: fileUndo[2] });
  const thread = path.match(
    /^\/api\/agents\/threads\/([a-zA-Z0-9_-]{1,128})(?:\/(draft|messages|project|chat|steer))?$/,
  );
  if (thread) {
    const action =
      thread[2] ||
      ({ GET: "get", PATCH: "rename", DELETE: "delete" } as Record<string, string>)[verb];
    const allowed = {
      draft: "PATCH",
      messages: "PUT",
      project: "PATCH",
      chat: "POST",
      steer: "POST",
    } as Record<string, string>;
    if (action && (!thread[2] || allowed[action] === verb)) return session(action, thread[1]);
  }
  if (path === "/api/agents/runs" && verb === "GET") return session("runs.list", undefined, query);
  const run = path.match(/^\/api\/agents\/runs\/([a-fA-F0-9-]{36})(\/cancel)?$/);
  if (run && verb === (run[2] ? "POST" : "GET"))
    return session(run[2] ? "runs.cancel" : "runs.get", undefined, { run_id: run[1] });
  if (path === "/api/agents/approvals" && verb === "GET")
    return session("approvals", String(query.conversation_id));
  const approval = path.match(/^\/api\/agents\/approvals\/([a-fA-F0-9-]{36})\/decide$/);
  if (approval && verb === "POST")
    return session("approval.decide", undefined, {
      approval_id: approval[1],
      decision: body.decision,
    });
  const project = path.match(/^\/api\/agents\/projects(?:\/([a-fA-F0-9-]{36}))?$/);
  if (project) {
    const action = project[1]
      ? ({ GET: "get", PATCH: "rename", DELETE: "delete" } as Record<string, string>)[verb]
      : ({ GET: "list", POST: "create" } as Record<string, string>)[verb];
    if (action)
      return {
        method: `projects.${action}`,
        params: {
          owner_id: owner,
          device_id: deviceId,
          body: { ...body, ...(project[1] ? { id: project[1] } : {}) },
        },
      };
  }
  if (path === "/api/agents/models" && verb === "GET")
    return { method: "agents.models", params: { owner_id: owner } };
  if (path === "/api/agents/title" && verb === "POST")
    return { method: "agents.title", params: { ...body, owner_id: owner } };
  if (path === "/api/agents/config" && ["GET", "PUT"].includes(verb))
    return {
      method: verb === "GET" ? "agents.config" : "agents.config.update",
      params: verb === "GET" ? { agent_code: query.agent_code } : body,
    };
  const settings = path.match(/^\/api\/settings(?:\/(model|asr)(?:\/(test|configured))?)?$/);
  if (settings) {
    const action =
      !settings[1] && verb === "GET"
        ? "read"
        : settings[2] === "configured" && verb === "GET"
          ? "configured"
          : settings[2] === "test" && verb === "POST"
            ? "test-local"
            : !settings[2] && verb === "PUT"
              ? "save"
              : null;
    if (action)
      return {
        method: `settings.${action}`,
        params: { owner_id: owner, kind: settings[1] || "model", body },
      };
  }
  if (path === "/api/skills" && verb === "GET")
    return { method: "skills.list", params: { agent_code: query.agent_code } };
  if (path === "/api/skills/search" && verb === "GET")
    return { method: "skills.search", params: { query: query.q || "" } };
  if (path === "/api/usage" && verb === "GET")
    return { method: "usage.summary", params: { owner_id: owner } };
  const skill = path.match(/^\/api\/skills\/(install|uninstall|descriptions|upload)$/);
  if (skill && verb === "POST") return { method: `skills.${skill[1]}`, params: body };
  const feishu = path.match(
    /^\/api\/connectors\/feishu(?:\/(verify|disconnect|authorization)(?:\/(configure|login))?)?$/,
  );
  if (feishu) {
    const action =
      !feishu[1] && verb === "GET"
        ? "status"
        : feishu[1] === "authorization" && verb === "POST" && feishu[2]
          ? "start"
          : feishu[1] === "authorization" && verb === "DELETE"
            ? "cancel"
            : verb === "POST" && ["verify", "disconnect"].includes(feishu[1] || "")
              ? feishu[1]
              : null;
    if (action)
      return {
        method: `connectors.feishu.${action}`,
        params: { owner_id: owner, ...(feishu[2] ? { action: feishu[2] } : {}) },
      };
  }
  throw new Error("不支持的本地业务操作。");
}
