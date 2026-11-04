/** 页面读取与编辑权限分开，查看页不要求写权限。 */
export function pagePermissions(path: string): string[] {
  if (/^\/knowledge(?:\/|$)/.test(path)) {
    return /^\/knowledge\/[^/]+\/(?:new\/?$|edit\/[^/]+\/?$)/.test(path)
      ? ["knowledge:read", "knowledge:write"]
      : ["knowledge:read"];
  }
  if (/^\/meetings(?:\/|$)/.test(path) || /^\/shared\/meeting-records\//.test(path))
    return ["meeting:read"];
  return [];
}
