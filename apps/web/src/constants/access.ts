import type { AccessRole } from "@/interfaces/access";

export const ACCESS_ROLE_LABELS: Record<AccessRole, string> = {
  admin: "管理员",
  manager: "部门负责人",
  member: "成员",
  viewer: "只读成员",
};
export const ACCESS_ROLE_DESCRIPTIONS: Record<AccessRole, string> = {
  admin: "配置平台管理与业务操作权限。",
  manager: "按部门职责独立配置业务与管理权限。",
  member: "按日常工作需要配置可执行的操作。",
  viewer: "默认用于资料查看，也可按需调整权限。",
};
export const PERMISSION_LABELS: Record<string, string> = {
  "knowledge:read": "查看知识库",
  "knowledge:write": "创建与编辑资料",
  "knowledge:delete": "删除知识库与资料",
  "knowledge:search": "知识检索",
  "meeting:read": "查看会议与纪要",
  "meeting:write": "创建与编辑会议",
  "meeting:delete": "删除会议",
  "meeting:generate": "生成会议纪要",
  "meeting:edit": "协同编辑纪要",
  "meeting:share": "分享会议纪要",
  "meeting:restore": "恢复历史版本",
  "meeting:archive": "归档到知识库",
  "device:connect": "连接本机执行设备",
  "access:manage": "管理用户与权限",
};
export const PERMISSION_GROUPS = [
  { prefix: "knowledge:", label: "知识库", description: "资料管理与知识检索" },
  { prefix: "meeting:", label: "会议与协作", description: "会议记录、纪要与归档" },
  { prefix: "device:", label: "执行设备", description: "本机设备执行通道" },
  { prefix: "access:", label: "平台管理", description: "用户与角色授权" },
];
export const roleLabel = (role: string) => ACCESS_ROLE_LABELS[role as AccessRole] ?? role;
