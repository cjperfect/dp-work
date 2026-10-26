import { Loader2, ScanText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentParsing } from "../hooks/use-document-parsing";
import type { KbFile } from "../constants/knowledge-data";

export function ParseDocumentButton({
  baseId,
  file,
  disabled = false,
}: {
  baseId: string;
  file: KbFile;
  disabled?: boolean;
}) {
  const parsing = useDocumentParsing(baseId);
  const busy =
    parsing.submitting || file.parseStatus === "queued" || file.parseStatus === "parsing";
  return (
    <Button
      disabled={disabled || busy || file.parseStatus === "parsed"}
      onClick={() => void parsing.start(file)}
      title={disabled ? "请等待文档自动保存完成" : "解析文档正文，保留内容结构"}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : <ScanText className="size-4" />}
      {busy
        ? "解析中"
        : file.parseStatus === "failed"
          ? "重试解析"
          : file.parseStatus === "parsed"
            ? "已解析"
            : "解析文档"}
    </Button>
  );
}
