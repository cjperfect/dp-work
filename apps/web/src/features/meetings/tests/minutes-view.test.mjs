import assert from "node:assert/strict";
import { test } from "node:test";
import { emptyWorkspace } from "../../../apis/meetings.ts";
import {
  meetingCategory,
  canEditMinutes,
  generationStatus,
  showOriginalMeeting,
} from "../lib/minutes-state.ts";
import { minutesContent, originalMeetingContent } from "../lib/minutes-content.ts";
import { minutesOutline } from "../lib/mind-map.ts";
test("generation states determine grouping and editing permissions", () => {
  const meeting = emptyWorkspace("meeting", 1).meeting;
  meeting.status = "ended";
  assert.equal(meetingCategory(meeting), "pending");
  assert.equal(canEditMinutes(meeting), true);
  for (const status of ["generating", "ready", "failed"]) {
    meeting.generation_status = status;
    assert.equal(meetingCategory(meeting), "pending");
    assert.equal(showOriginalMeeting(meeting), status !== "ready");
    assert.equal(canEditMinutes(meeting), status === "ready");
  }
  meeting.status = "archived";
  assert.equal(meetingCategory(meeting), "archived");
  assert.equal(showOriginalMeeting(meeting), false);
  assert.equal(canEditMinutes(meeting), false);
});
test("legacy processing states remain read only", () => {
  const meeting = emptyWorkspace("meeting", 1).meeting;
  meeting.minutes_status = 0;
  assert.equal(generationStatus(meeting), "generating");
  assert.equal(canEditMinutes(meeting), false);
});
test("mind maps preserve heading hierarchy and do not invent content", () => {
  const outline = minutesOutline(
    "评审",
    "# 评审\n## 会议结论\n- 下周交付\n### 风险\n- 依赖评审\n## 行动项\n- [ ] 陈江整理需求",
  );
  assert.deepEqual(
    outline.map((point) => point.label),
    ["评审", "会议结论", "下周交付", "风险", "依赖评审", "行动项", "陈江整理需求"],
  );
  assert.equal(outline[2].parent, outline[1].id);
  assert.equal(outline[3].parent, outline[1].id);
  assert.equal(outline[4].parent, outline[3].id);
  assert.equal(outline[5].parent, "root");
  for (const point of outline) assert.ok(Number.isFinite(point.y));
});
test("mind maps ignore fenced code and cap very large documents", () => {
  assert.equal(minutesOutline("标题", "```ts\n# not a heading\n```\n").length, 1);
  assert.equal(minutesOutline("标题", "- 条目\n".repeat(200)).length, 120);
});

test("minutes show confirmed meeting text before a draft exists and preserve deliberately empty drafts", () => {
  const workspace = emptyWorkspace("meeting", 1);
  workspace.segments = [
    { id: "one", seq: 0, speaker: "说话人 1", text: "确认的会议文字", start_ms: 0 },
    { id: "two", seq: 1, speaker: null, text: "下一句话", start_ms: 1000 },
  ];
  assert.equal(minutesContent(workspace), "说话人 1：确认的会议文字\n\n下一句话");
  workspace.minutes = { content: "已编辑纪要", status: 1, archived_document_id: null };
  assert.equal(minutesContent(workspace), "已编辑纪要");
  workspace.minutes.content = "";
  assert.equal(minutesContent(workspace), "");
});

test("pending meeting original content stays independent of an edited minutes draft", () => {
  const workspace = emptyWorkspace("original", 1);
  workspace.meeting.status = "ended";
  workspace.segments = [
    { id: "one", seq: 0, speaker: "说话人1", text: "原始识别结果", start_ms: 0 },
  ];
  workspace.minutes = { content: "已修改的纪要", status: 1, archived_document_id: null };
  assert.equal(meetingCategory(workspace.meeting), "pending");
  assert.equal(originalMeetingContent(workspace), "说话人1：原始识别结果");
  assert.equal(minutesContent(workspace), "已修改的纪要");
});
