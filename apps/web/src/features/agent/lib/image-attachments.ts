import type { ChatImage } from "@/interfaces/agent";
import { SimpleImageAttachmentAdapter, type Attachment } from "@assistant-ui/react";
import { toast } from "sonner";
import { saveChatImage } from "@/apis/chat-images";

class LocalImageAdapter extends SimpleImageAttachmentAdapter {
  accept = "image/png,image/jpeg,image/webp";
  async add({ file }: { file: File }) {
    try {
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 1024 * 1024)
        throw new Error("支持 PNG、JPEG、WebP，每张图片不超过 1 MB。");
      const pending = await super.add({ file });
      const complete = await super.send(pending);
      const data = complete.content.find((part) => part.type === "image");
      if (!data || data.type !== "image") throw new Error("无法读取图片。");
      const ref = await saveChatImage(file.name, file.type, data.image);
      return { ...pending, id: ref.id };
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "添加图片失败。");
      throw cause;
    }
  }
}
export const imageAttachmentAdapter = new LocalImageAdapter();
export function messageImages(attachments: readonly Attachment[] | undefined): ChatImage[] {
  if ((attachments?.length ?? 0) > 3) throw new Error("每条消息最多发送 3 张图片。");
  return (attachments ?? []).map((attachment) => {
    if (attachment.type !== "image" || !/^[a-f0-9]{64}$/.test(attachment.id))
      throw new Error("图片尚未准备好，请重新粘贴。");
    return {
      id: attachment.id,
      name: attachment.name,
      content_type: attachment.contentType ?? "image/png",
    };
  });
}
