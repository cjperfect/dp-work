import { useAuthStore } from "@/stores/auth";
import { hasPermission, useAccessStore } from "@/stores/access";

/** 订阅已核验的服务端权限；初始化和核验失败期间均不授予操作权限。 */
export function usePermission(...permissions: string[]) {
  const owner = useAuthStore((state) => state.user?.id);
  return useAccessStore(
    (state) =>
      state.ownerId === owner &&
      !!state.data &&
      permissions.every((permission) => state.data!.permissions.includes(permission)),
  );
}

export { hasPermission };
