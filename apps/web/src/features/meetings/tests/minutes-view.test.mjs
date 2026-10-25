import assert from "node:assert/strict";
import { test } from "node:test";
import { emptyWorkspace } from "../../../apis/meetings.ts";
import { meetingCategory, canEditMinutes, generationStatus } from "../lib/minutes-state.ts";
import { minutesOutline } from "../lib/mind-map.ts";
test("generation states determine grouping and editing permissions", () => {
  const meeting = emptyWorkspace("meeting", 1).meeting;
  meeting.status = "ended";
  assert.equal(meetingCategory(meeting), "pending");
  assert.equal(canEditMinutes(meeting), true);
  for (const status of ["generating", "ready", "failed"]) {
    meeting.generation_status = status;
    assert.equal(meetingCategory(meeting), "generating");
    assert.equal(canEditMinutes(meeting), false);
  }
  meeting.status = "archived";
  assert.equal(meetingCategory(meeting), "archived");
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
