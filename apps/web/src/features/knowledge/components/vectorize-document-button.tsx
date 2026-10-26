import { ScanText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function VectorizeDocumentButton({ name }: { name: string }) {
  return (
    <Button onClick={() => toast.info(`「${name}」的向量化服务尚未接入。`)}>
      <ScanText className="size-4" />
      向量化
    </Button>
  );
}
