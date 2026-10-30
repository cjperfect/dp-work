import axios from "axios";

/** 读取图片二进制，不使用业务客户端，避免向外部图片地址附带登录 Token。 */
export async function loadImageBlob(url: string): Promise<Blob> {
  const response = await axios.get<Blob>(url, {
    responseType: "blob",
    withCredentials: false,
    timeout: 20000,
  });
  return response.data;
}
