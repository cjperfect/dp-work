/** 全局视图与 Agent 相关类型定义 */

export type AgentId = "general" | "product";

export type ViewKey = "chat" | "meetings" | "skills" | "knowledge" | "agent";

export type AppStore = {
  view: ViewKey;
  agentId: AgentId;
  /** 已开启的知识库 id 列表，开启后作为 Agent 回答上下文（UI 骨架，待接入） */
  enabledKbs: string[];
  /** 当前选中模型 id（UI 骨架，接入时传给后端模型服务） */
  currentModel: string;
  /** 当前进行中会议标题（开始会议弹窗写入，会议页展示，UI 骨架） */
  meetingTitle: string | null;
  /** 当前会议状态：live = 转写中，generating = 已结束、AI 纪要生成中 */
  meetingStatus: "live" | "generating";
  /** 会话归属映射：threadId → AgentId，新会话自动绑定当前选中 Agent（轻量隔离方案） */
  threadAgent: Record<string, AgentId>;
  setView: (view: ViewKey) => void;
  setAgentId: (id: AgentId) => void;
  toggleKb: (id: string) => void;
  setModel: (id: string) => void;
  /** 写入当前进行中会议标题 */
  setMeetingTitle: (title: string) => void;
  /** 更新当前会议状态（结束会议 → generating；新会议 → live） */
  setMeetingStatus: (status: "live" | "generating") => void;
  /** 将线程绑定到 Agent，已绑定则不覆盖 */
  bindThreadAgent: (threadId: string, agentId: AgentId) => void;
};
