import type { FileType } from "@/interfaces/knowledge";
import { FileSpreadsheet, FileText, Presentation } from "lucide-react";

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
