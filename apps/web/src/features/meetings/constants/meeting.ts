/**
 * 会议模块常量（features/meetings/constants/meeting.ts）
 */

/** 会议会话持久化键（sessionStorage）——创建/恢复/清除三处共用 */
export const SESSION_KEY = "dp-meeting-session-v1";

/** 本机 Sidecar WebSocket 地址。 */
export const SIDECAR_WS = import.meta.env.VITE_SIDECAR_WS ?? "ws://localhost:8001/ws";

/** 历史会议（mock 数据）：待接入后端 meetings 接口 */
export type HistoryMeeting = {
  id: string;
  title: string;
  date: string;
  summary: string;
  /** 会议转写内容（BlockNote blocks），「查看」时载入纪要编辑页 */
  transcript?: Record<string, unknown>[];
};

export const HISTORY_MEETINGS: HistoryMeeting[] = [
  {
    id: "m-002",
    title: "RAG 知识库架构讨论",
    date: "2026-10-21",
    summary: "已生成纪要 · 8 项待办",
  },
  {
    id: "m-003",
    title: "倍轻松小程序需求对齐",
    date: "2026-10-18",
    summary: "已生成纪要 · 3 项待办",
  },
];

/** 「会议纪要 AI 生成中」区块的兜底测试数据（无动态数据时展示） */
export const GENERATING_DEMO_MEETING = {
  id: "m-demo",
  title: "Q4 产品规划评审（测试数据）",
  startedAt: "刚刚",
};

/** 「未生成」区块：已结束但未点击生成纪要的会议（mock 数据，待接入后端） */
export const UNGENERATED_MEETINGS: HistoryMeeting[] = [
  {
    id: "m-004",
    title: "周会进度同步",
    date: "2026-10-23",
    summary: "已结束 · 未生成纪要",
    transcript: [
      {
        id: "mg-01",
        type: "heading",
        props: { level: 1 },
        content: [{ type: "text", text: "周会进度同步", styles: {} }],
      },
      {
        id: "mg-02",
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "王明：本周 RAG 知识库完成 pgvector 语义检索联调，Recall@5 提升到 0.70",
            styles: {},
          },
        ],
      },
      {
        id: "mg-03",
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "李静：会议纪要生成链路已通，占位接口返回正常，下一步接真实 LLM 摘要",
            styles: {},
          },
        ],
      },
    ],
  },
  {
    id: "m-005",
    title: "客户需求沟通",
    date: "2026-10-22",
    summary: "已结束 · 未生成纪要",
    transcript: [
      {
        id: "mg-11",
        type: "heading",
        props: { level: 1 },
        content: [{ type: "text", text: "客户需求沟通", styles: {} }],
      },
      {
        id: "mg-12",
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "客户：希望补充移动端访问能力，会议纪要支持导出 PDF",
            styles: {},
          },
        ],
      },
      {
        id: "mg-13",
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "内部：下周二前给出方案，优先级 P1",
            styles: {},
          },
        ],
      },
    ],
  },
];
