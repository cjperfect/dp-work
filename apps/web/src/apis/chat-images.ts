import type { ChatImage, ThreadDetail } from "@/interfaces/agent";
import { http } from "@/lib/http";
import { useAuthStore } from "@/stores/auth";

import { toast } from "sonner";
const previews = new Map<string, string>();
/** 生成账号与图片对应的缓存键。 */
const key = (id: string) => `${useAuthStore.getState().user?.id}:${id}`;
/** 获取本机图片的预览地址。 */
export const imagePreview = (id: string) => previews.get(key(id));
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) previews.clear();
});
/** 保存聊天图片并返回附件引用。 */
export async function saveChatImage(name: string, content_type: string, data_url: string) {
  const owner = useAuthStore.getState().user?.id;
  const image = await http.post<ChatImage>("/api/agents/images", { name, content_type, data_url });
  if (owner !== useAuthStore.getState().user?.id) throw new Error("登录状态已改变。");
  previews.set(key(image.id), data_url);
  return image;
}
/** 为历史消息中的图片补齐预览地址。 */
export async function hydrateChatImages(detail: ThreadDetail) {
  const owner = useAuthStore.getState().user?.id;
  const refs = new Map(
    [...detail.messages, ...(detail.message_branches ?? []).map((entry) => entry.message)]
      .flatMap((row) => row.context.images ?? [])
      .map((image) => [image.id, image]),
  );
  let missing = false;
  for (const image of refs.values()) {
    if (imagePreview(image.id)) continue;
    let url: string;
    try {
      url = await http.get<string>("/api/agents/images", {
        params: { id: image.id, content_type: image.content_type },
      });
    } catch {
      missing = true;
      continue;
    }
    if (owner !== useAuthStore.getState().user?.id) throw new Error("登录状态已改变。");
    previews.set(key(image.id), url);
  }
  if (owner !== useAuthStore.getState().user?.id) throw new Error("登录状态已改变。");
  if (missing) toast.warning("部分会话图片暂时无法读取，文字记录仍可查看。");
  return detail;
}
