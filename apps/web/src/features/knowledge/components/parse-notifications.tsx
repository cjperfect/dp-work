import { useEffect } from "react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";
import {
  consumeDocumentParseEvents,
  consumeDocumentVectorEvents,
  consumeDocumentSearchEvents,
} from "@/stores/document-parsing";
import { subscribeDocumentParseEvents } from "../lib/parse-events";

/** 页面切换后仍接收解析结果，自动关闭提示。 */
export function ParseNotifications() {
  const owner = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    if (!owner) return;
    return subscribeDocumentParseEvents(owner, (rows, snapshot) => {
      for (const row of consumeDocumentSearchEvents(rows, snapshot)) {
        toast.success("知识库检索索引已就绪", {
          id: `document-search:${owner}:${row.id}:${row.search_task_id}`,
          description: row.name,
          duration: 6000,
        });
      }
      for (const row of consumeDocumentVectorEvents(rows, snapshot)) {
        const options = {
          id: `document-vector:${owner}:${row.id}:${row.vector_task_id}`,
          description: row.name,
          duration: 6000,
        };
        if (row.vector_status === "indexed") toast.success("文档向量化完成", options);
        else
          toast.error("文档向量化失败", {
            ...options,
            description: `${row.name}：${row.vector_error || "请重试。"}`,
          });
      }
      for (const row of consumeDocumentParseEvents(rows, snapshot)) {
        const options = {
          id: `document-parse:${owner}:${row.id}:${row.task_id}`,
          description: row.name,
          duration: 6000,
        };
        if (row.status === "parsed")
          toast.success("文档解析完成", {
            ...options,
          });
        else
          toast.error("文档解析失败", {
            ...options,
            description: `${row.name}：${row.error || "请重试。"}`,
          });
      }
    });
  }, [owner]);
  return null;
}
