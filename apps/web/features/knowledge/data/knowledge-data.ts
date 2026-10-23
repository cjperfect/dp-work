import { FileSpreadsheet, FileText, Presentation } from "lucide-react";

export type FileType = "md" | "pdf" | "docx" | "xlsx" | "pptx";

export type KbFile = {
  id: string;
  name: string;
  type: FileType;
  size: string;
  uploader: string;
  updatedAt: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  owner: string;
  files: KbFile[];
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
        id: "f-001",
        name: "需求评审模板 v3.docx",
        type: "docx",
        size: "86 KB",
        uploader: "产品部",
        updatedAt: "2026-10-22",
      },
      {
        id: "f-002",
        name: "2026Q4 产品路线图.md",
        type: "md",
        size: "24 KB",
        uploader: "产品部",
        updatedAt: "2026-10-21",
      },
      {
        id: "f-003",
        name: "用户画像调研报告.pdf",
        type: "pdf",
        size: "3.2 MB",
        uploader: "产品部",
        updatedAt: "2026-10-15",
      },
      {
        id: "f-004",
        name: "版本发布说明 2.8.0.md",
        type: "md",
        size: "12 KB",
        uploader: "产品部",
        updatedAt: "2026-10-10",
      },
      {
        id: "f-005",
        name: "竞品分析-知识库赛道.xlsx",
        type: "xlsx",
        size: "156 KB",
        uploader: "产品部",
        updatedAt: "2026-09-28",
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
      },
      {
        id: "f-007",
        name: "会议纪要撰写规范.md",
        type: "md",
        size: "9 KB",
        uploader: "产研中心",
        updatedAt: "2026-10-18",
      },
      {
        id: "f-008",
        name: "文档发布审批 SOP.docx",
        type: "docx",
        size: "42 KB",
        uploader: "产研中心",
        updatedAt: "2026-10-05",
      },
      {
        id: "f-009",
        name: "知识库更新流程.md",
        type: "md",
        size: "11 KB",
        uploader: "产研中心",
        updatedAt: "2026-09-26",
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
      },
      {
        id: "f-011",
        name: "2026-10-18 小程序需求对齐纪要.md",
        type: "md",
        size: "13 KB",
        uploader: "管理后台",
        updatedAt: "2026-10-18",
      },
      {
        id: "f-012",
        name: "2026-10-15 产品规划评审纪要.md",
        type: "md",
        size: "21 KB",
        uploader: "管理后台",
        updatedAt: "2026-10-15",
      },
      {
        id: "f-013",
        name: "2026-09-30 周会纪要.md",
        type: "md",
        size: "8 KB",
        uploader: "管理后台",
        updatedAt: "2026-09-30",
      },
    ],
  },
];

export const FILE_TYPE_META: Record<FileType, { label: string; icon: typeof FileText }> = {
  md: { label: "Markdown", icon: FileText },
  pdf: { label: "PDF", icon: FileText },
  docx: { label: "Word", icon: FileText },
  xlsx: { label: "表格", icon: FileSpreadsheet },
  pptx: { label: "演示文稿", icon: Presentation },
};
