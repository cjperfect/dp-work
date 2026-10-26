import { FileSpreadsheet, FileText, Presentation } from "lucide-react";
import type { PartialBlock } from "@blocknote/core";

export type FileType = "txt" | "md" | "pdf" | "doc" | "docx" | "xlsx" | "pptx";

export type KbFile = {
  id: string;
  name: string;
  type: FileType;
  size: string;
  uploader: string;
  updatedAt: string;
  /** 文档正文（仅 md 提供示例内容；其他格式暂不支持在线预览） */
  content?: string;
  blocks?: PartialBlock[];
  source?: "editor" | "upload";
  storage?: "server";
  status?: "draft" | "published";
  /** 源文件地址（pdf 等二进制文件提供，用于在线预览；上传文件为 data URL） */
  pdfUrl?: string;
  parseStatus?: "unparsed" | "queued" | "parsing" | "parsed" | "failed";
  parsedContent?: string;
  parseError?: string;
  parsedAt?: string;
  parsedBlocks?: PartialBlock[];
  vectorizedAt?: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  owner: string;
  files: KbFile[];
  documentCount?: number;
};

// 静态示例数据：仅用于搭建页面结构，后续接入真实知识库接口
export const KNOWLEDGE_BASES: KnowledgeBase[] = [
  {
    id: "kb-001",
    name: "产品文档库",
    description: "产品需求、PRD 与版本说明",
    owner: "产品部",
    files: [
      {
        id: "f-002",
        name: "2026Q4 产品路线图.md",
        type: "md",
        size: "24 KB",
        uploader: "产品部",
        updatedAt: "2026-10-21",
        content: `# 2026Q4 产品路线图

> 目标：围绕「企业 Agent 平台」完成 Agent 编排、知识库与会议纪要三大核心链路闭环。

## 一、季度目标

- **10 月**：Agent 编排框架上线，支持按部门专业范畴 + SOP + 技能路由输出
- **11 月**：知识库（RAG）全面接入对话，支持会议纪要一键沉淀入库
- **12 月**：开放 API 与模板市场，接入 3 个外部场景

## 二、关键里程碑

| 时间 | 里程碑 | 负责 |
| --- | --- | --- |
| 10.15 | Agent 路由 v1 联调完成 | 平台组 |
| 11.10 | RAG 召回率 ≥ 0.70（Recall@5） | 检索组 |
| 12.05 | 会议纪要 → 知识库发布链路打通 | 会议组 |

## 三、风险与依赖

- pgvector 语义检索性能待压测（>10 万条向量）
- 部门 SOP 结构化进度依赖运营侧提供口径

## 四、验收口径

- 三大模块均以「端到端演示 + 指标达标」为验收标准，不单独验收子功能。
`,
      },
      {
        id: "f-003",
        name: "用户画像调研报告.pdf",
        type: "pdf",
        size: "3.2 MB",
        uploader: "产品部",
        updatedAt: "2026-10-15",
        pdfUrl: "/pdf/sample-user-report.pdf",
      },
      {
        id: "f-004",
        name: "版本发布说明 2.8.0.md",
        type: "md",
        size: "12 KB",
        uploader: "产品部",
        updatedAt: "2026-10-10",
        content: `# 版本发布说明 2.8.0

**发布日期**：2026-10-10

## 新功能

- 新增「开始会议」实时转写入口，支持 ASR 分句流式展示
- 会议结束后自动进入「会议纪要 AI 生成中」状态
- Agent 聊天支持 @ 选择知识库作为回答上下文

## 优化

- 会话区域高度自适应，消息多时区域内滚动
- 转写富文本支持标题、颜色、背景色、列表等格式

## 修复

- 修复侧边栏路由切换后会话归属错乱的问题
- 修复转写长文本下横向滚动条问题

## 兼容性

- 桌面端 Chrome / Edge 最新版；移动端 WebView 建议升级至最新内核
`,
      },
    ],
  },
  {
    id: "kb-002",
    name: "部门 SOP 库",
    description: "各部门业务规范与标准作业流程",
    owner: "产研中心",
    files: [
      {
        id: "f-006",
        name: "需求评审流程 SOP.md",
        type: "md",
        size: "18 KB",
        uploader: "产研中心",
        updatedAt: "2026-10-20",
        content: `# 需求评审流程 SOP

**适用范围**：产研中心全部需求评审；**生效日期**：2026-10-01

## 一、评审前置条件

- PRD 已按模板填写完整（背景 / 目标 / 范围 / 验收标准）
- 已关联原型或交互稿；涉及数据的需附口径说明

## 二、流程节点

1. **需求提交**：产品经理在知识库新建 PRD 并 @ 评审组
2. **预审**：技术负责人 2 个工作日内完成可行性预审
3. **评审会**：默认周三 14:00，评审组全员参加
4. **结论输出**：通过 / 有条件通过 / 驳回，24h 内写入评审记录

## 三、评审检查项

- 验收标准是否可量化、可测试
- 是否有明确的数据口径与埋点定义
- 依赖模块是否已排期对齐

## 四、例外处理

- 紧急修复类需求可走「绿色通道」，需产品负责人书面授权。
`,
      },
      {
        id: "f-007",
        name: "会议纪要撰写规范.md",
        type: "md",
        size: "9 KB",
        uploader: "产研中心",
        updatedAt: "2026-10-18",
        content: `# 会议纪要撰写规范

## 结构模板

- **会议主题**：一句话说明会议目的
- **时间 / 参会人**：含角色与部门
- **结论**：本次会议确定的决策（编号 D1、D2…）
- **行动项**：负责人 + 截止时间（编号 A1、A2…）
- **待办跟进**：遗留问题与下次会议安排

## 撰写要求

- 结论先行，每条行动项必须可追踪（负责人 + 时间）
- 使用转写富文本的标题、列表格式组织，便于沉淀入库
- 会议纪要 AI 生成后需人工复核再发布

## 命名规范

\`YYYY-MM-DD 会议主题纪要.md\`，归档至「会议纪要库」对应目录。
`,
      },
      {
        id: "f-009",
        name: "知识库更新流程.md",
        type: "md",
        size: "11 KB",
        uploader: "产研中心",
        updatedAt: "2026-09-26",
        content: `# 知识库更新流程

## 一、更新场景

- 文档新建 / 修订：内容稳定后 1 个工作日内入库
- 会议纪要：生成并复核后一键发布入库
- 过期内容：标注「已废弃」，不物理删除（保留审计）

## 二、更新步骤

1. 文档上传至对应知识库分类目录
2. 系统解析文本并生成向量（pgvector）
3. 语义检索质量校验（Ragas 评测，Recall@5 ≥ 0.70）
4. 通过后标记「可检索」，全量索引更新

## 三、职责

- 上传人：保证内容口径正确、脱敏完整
- 知识库管理员：审核分类与权限
- 平台组：维护向量索引与重排（BGE-Reranker-v2-m3）

## 四、注意

- 敏感信息必须先脱敏；部门级文档默认仅本部门可检索。
`,
      },
    ],
  },
  {
    id: "kb-003",
    name: "会议纪要库",
    description: "历史会议纪要沉淀，支持对话中检索引用",
    owner: "管理后台",
    files: [
      {
        id: "f-010",
        name: "2026-10-21 RAG架构讨论纪要.md",
        type: "md",
        size: "15 KB",
        uploader: "管理后台",
        updatedAt: "2026-10-21",
        content: `# 2026-10-21 RAG 架构讨论纪要

**时间**：2026-10-21 14:00-15:30 | **参会**：产研中心（后端、检索、平台组）

## 结论

- **D1**：向量库采用 pgvector，与 PostgreSQL 统一部署，暂不引入独立向量服务
- **D2**：检索链路 = 召回（pgvector）+ 重排（BGE-Reranker-v2-m3）+ LLM 回答
- **D3**：评测用 Ragas，主指标 Recall@5，基线 0.57，目标 ≥ 0.70

## 行动项

- A1（李静 / 10.28）：完成 20 类产品文档的切分与向量化
- A2（王明 / 11.05）：接入重排并跑通评测闭环
- A3（陈工 / 11.15）：10 万条向量的性能压测报告

## 待跟进

- 部门级权限过滤对召回率的影响，下周专项验证。
`,
      },
      {
        id: "f-011",
        name: "2026-10-18 小程序需求对齐纪要.md",
        type: "md",
        size: "13 KB",
        uploader: "管理后台",
        updatedAt: "2026-10-18",
        content: `# 2026-10-18 小程序需求对齐纪要

**时间**：2026-10-18 10:00-11:30 | **参会**：产品部、前端、测试

## 结论

- **D1**：v2.0 范围锁定蓝牙 BLE 设备连接 + 健康报告解读两模块
- **D2**：报告解读结果需可分享（生成海报图）
- **D3**：兼容 iOS/Android WebView，统一降级策略

## 行动项

- A1（前端组 / 10.25）：BLE 连接协议联调
- A2（测试 / 11.01）：输出兼容性用例集（含弱网）
- A3（产品 / 11.08）：报告解读文案终稿

## 待跟进

- 分享海报的模板评审，下周一例会确认。
`,
      },
      {
        id: "f-012",
        name: "2026-10-15 产品规划评审纪要.md",
        type: "md",
        size: "21 KB",
        uploader: "管理后台",
        updatedAt: "2026-10-15",
        content: `# 2026-10-15 产品规划评审纪要

**时间**：2026-10-15 14:00-16:00 | **参会**：产品部、技术负责人、部门负责人

## 结论

- **D1**：企业 Agent 平台定位「部门协作 + 知识管理 + 会议沉淀」一体化
- **D2**：Q4 优先完成知识库与会议纪要闭环，模板市场顺延至 2027Q1
- **D3**：Agent 输出结果需依据部门专业范畴 + SOP + 技能，可追溯引用来源

## 行动项

- A1（产品 / 10.22）：输出 Q4 里程碑拆解文档
- A2（平台组 / 11.05）：Agent 路由 + 部门隔离联调
- A3（运营 / 11.30）：首批部门 SOP 结构化交付

## 风险

- 部门 SOP 质量参差，需统一模板与审核流程。
`,
      },
      {
        id: "f-013",
        name: "2026-09-30 周会纪要.md",
        type: "md",
        size: "8 KB",
        uploader: "管理后台",
        updatedAt: "2026-09-30",
        content: `# 2026-09-30 周会纪要

**时间**：2026-09-30 10:00-11:00

## 本周进展

- 知识库原型完成，开始会议入口已上线（转写展示）
- ASR 实时转写侧边流程设计评审通过

## 下周计划

- 搭建 api 服务骨架：认证、统一响应、部门权限隔离
- 启动 pgvector 部署与 20 类文档向量化

## 行动项

- A1（后端 / 10.09）：api 认证与统一响应落地
- A2（检索 / 10.12）：文档解析与切分脚本

## 备注

- 国庆期间线上值班表已同步，紧急问题走绿色通道。
`,
      },
    ],
  },
];

export const FILE_TYPE_META: Record<
  FileType,
  { label: string; icon: typeof FileText; badge: string }
> = {
  txt: { label: "TXT", icon: FileText, badge: "bg-slate-500/10 text-slate-600" },
  doc: { label: "Word", icon: FileText, badge: "bg-sky-500/10 text-sky-600" },
  md: { label: "Markdown", icon: FileText, badge: "bg-blue-500/10 text-blue-600" },
  pdf: { label: "PDF", icon: FileText, badge: "bg-red-500/10 text-red-600" },
  docx: { label: "Word", icon: FileText, badge: "bg-sky-500/10 text-sky-600" },
  xlsx: { label: "表格", icon: FileSpreadsheet, badge: "bg-emerald-500/10 text-emerald-600" },
  pptx: { label: "演示文稿", icon: Presentation, badge: "bg-orange-500/10 text-orange-600" },
};
