import { DEMO_MINUTES, emptyWorkspace } from "@/apis/meetings";
import { listDrafts, localDraft, saveDraft } from "./workspace-storage";
import { readMock, writeMock } from "@/lib/mock-storage";
const flights = new Map<number, Promise<void>>();
export function seedMockMeetings(owner: number) {
  const existing = flights.get(owner);
  if (existing) return existing;
  const operation = (async () => {
    const key = `meetings-seeded:${owner}`;
    if (readMock<boolean>(key)) return;
    const records = await listDrafts(owner);
    const demos = [
      { title: "产品需求评审（演示）", state: "idle" as const },
      { title: "项目周会（生成中演示）", state: "generating" as const },
      { title: "客户方案沟通（失败重试演示）", state: "failed" as const },
      { title: "季度规划（已归档演示）", state: "ready" as const },
    ];
    for (const [index, demo] of demos.entries()) {
      const id = `demo-meeting-${owner}-${index}`;
      if (records.some((row) => row.meeting.id === id)) continue;
      const workspace = emptyWorkspace(id, owner, demo.title);
      workspace.meeting.status = index === 3 ? "archived" : "ended";
      workspace.meeting.elapsed_ms = 26 * 60_000;
      workspace.meeting.generation_status = demo.state;
      workspace.meeting.minutes_status = demo.state === "generating" ? 0 : 1;
      if (demo.state === "generating") workspace.meeting.generation_ready_at = Date.now() + 8000;
      if (demo.state === "failed")
        workspace.meeting.generation_error = "模拟生成失败，可点击上方按钮重新生成。";
      workspace.segments = [
        {
          id: `${id}-1`,
          seq: 0,
          speaker: "说话人 1",
          text: "本次优先完善会议流程和纪要分享体验。",
          start_ms: 0,
        },
        {
          id: `${id}-2`,
          seq: 1,
          speaker: "说话人 2",
          text: "由研发团队验证页面跳转、权限和知识库归档。",
          start_ms: 15000,
        },
      ];
      workspace.minutes = { content: DEMO_MINUTES, status: 1, archived_document_id: null };
      await saveDraft(localDraft(workspace));
    }
    writeMock(key, true);
  })();
  flights.set(owner, operation);
  void operation.finally(() => flights.delete(owner)).catch(() => {});
  return operation;
}
