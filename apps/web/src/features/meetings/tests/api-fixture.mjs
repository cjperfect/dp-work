import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";

/** 模拟持久化 API，用于验证前端队列与响应处理。 */
export function meetingApiFixture(initial = []) {
  const records = new Map(initial.map((row) => [row.meeting.id, structuredClone(row)]));
  const ok = (data) => Response.json({ code: 0, data });
  const transport = mockHttpRequest(async (url, init) => {
    if (url === "/api/meetings/import") {
      const body = JSON.parse(init.body);
      if (!records.has(body.meeting.id)) records.set(body.meeting.id, structuredClone(body));
      return ok(records.get(body.meeting.id));
    }
    if (url === "/api/meetings") return ok([...records.values()].map((row) => row.meeting));
    if (url.endsWith("/minutes/generate")) {
      const id = url.split("/").at(-3);
      const row = records.get(id);
      const body = JSON.parse(init.body);
      if (!row || body.expected_revision !== row.meeting.revision)
        return Response.json({ code: 409, message: "会议内容已变化", data: null }, { status: 409 });
      const task = crypto.randomUUID();
      const source = row.meeting.revision;
      row.meeting = {
        ...row.meeting,
        revision: source + 1,
        generation_status: "generating",
        generation_task_id: task,
        generation_source_revision: source,
        minutes_status: 0,
      };
      return ok({ task_id: task, source_revision: source, meeting: row.meeting });
    }
    const id = decodeURIComponent(url.split("/").at(-1));
    const row = records.get(id);
    if (!row)
      return Response.json({ code: 404, message: "会议不存在", data: null }, { status: 404 });
    if (init.method === "DELETE") {
      records.delete(id);
      return ok(null);
    }
    if (init.method === "PUT") {
      const body = JSON.parse(init.body);
      if (body.expected_revision !== row.meeting.revision)
        return Response.json(
          { code: 409, message: "会议已被其他页面修改", data: null },
          { status: 409 },
        );
      records.set(id, {
        meeting: { ...body.meeting, revision: row.meeting.revision + 1 },
        segments: body.segments,
        minutes: body.minutes,
      });
    }
    return ok(records.get(id));
  });
  return { records, transport };
}
