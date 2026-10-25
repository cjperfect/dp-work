import { afterEach, mock } from "node:test";
import { httpClient } from "../http.ts";

const originalAdapter = httpClient.defaults.adapter;
afterEach(() => {
  httpClient.defaults.adapter = originalAdapter;
});

/** 使用 Axios 适配器模拟请求，保留请求参数断言。 */
export function mockHttpRequest(
  handler = async () => {
    throw new Error("unexpected request");
  },
) {
  const transport = mock.fn(handler);
  httpClient.defaults.adapter = async (config) => {
    const response = await transport(config.url, {
      method: config.method.toUpperCase(),
      headers: config.headers.toJSON(),
      body: config.data,
      signal: config.signal,
    });
    return {
      data: config.responseType === "blob" ? await response.blob() : await response.text(),
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers),
      config,
    };
  };
  return transport;
}
