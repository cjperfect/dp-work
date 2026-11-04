import assert from "node:assert/strict";
import { beforeEach, afterEach, test, mock } from "node:test";
import { mockHttpRequest } from "../../../lib/testing/mock-http.mjs";
import { signOut, useAuthStore } from "../../../stores/auth.ts";
import {
  resetAccess,
  refreshAccess,
  requireManagementAccess,
  useAccessStore,
} from "../../../stores/access.ts";
import {
  getManagedUsers,
  getRolePolicies,
  updateUserRole,
  updateRolePermissions,
} from "../../../apis/access.ts";

const originals = Object.fromEntries(
  ["window", "localStorage"].map((k) => [k, Object.getOwnPropertyDescriptor(globalThis, k)]),
);
let values;
const response = (data, status = 200, message = "ok") =>
  new Response(JSON.stringify({ code: status === 200 ? 0 : 3003, message, data }), { status });
beforeEach(() => {
  values = new Map([["dp-work.auth.token", "session-one"]]);
  Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  });
  useAuthStore.setState({ user: { id: 7, username: "admin", role: "admin" } });
  resetAccess();
});
afterEach(() => {
  resetAccess();
  useAuthStore.setState({ user: null });
  mock.restoreAll();
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

test("cached admin role does not grant management when server returns member permissions", async () => {
  mockHttpRequest(async () => response({ role: "member", permissions: ["knowledge:read"] }));
  await assert.rejects(requireManagementAccess(), (error) => error.status === 403);
  assert.deepEqual(useAccessStore.getState().data.permissions, ["knowledge:read"]);
});

test("deduplicates concurrent permission checks but revalidates later route entries", async () => {
  const transport = mockHttpRequest(async () =>
    response({ role: "admin", permissions: ["access:manage"] }),
  );
  await Promise.all([refreshAccess(), requireManagementAccess()]);
  assert.equal(transport.mock.callCount(), 1);
  await requireManagementAccess();
  assert.equal(transport.mock.callCount(), 2);
});

test("logout discards a late admin response", async () => {
  let resolve;
  const transport = mockHttpRequest(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const pending = refreshAccess();
  while (!transport.mock.callCount()) await new Promise((done) => setImmediate(done));
  signOut();
  resolve(response({ role: "admin", permissions: ["access:manage"] }));
  await assert.rejects(pending, (error) => error.status === 401);
  assert.equal(useAccessStore.getState().data, null);
});

test("account switch cannot reuse former admin permissions", async () => {
  mockHttpRequest(async () => response({ role: "admin", permissions: ["access:manage"] }));
  await refreshAccess();
  values.set("dp-work.auth.token", "session-two");
  useAuthStore.setState({ user: { id: 8, username: "member", role: "member" } });
  assert.equal(useAccessStore.getState().data, null);
  mockHttpRequest(async () => response({ role: "member", permissions: [] }));
  await assert.rejects(requireManagementAccess(), (error) => error.status === 403);
});

test("failed revalidation clears previous permissions and permits a subsequent retry", async () => {
  mockHttpRequest(async () => response({ role: "admin", permissions: ["access:manage"] }));
  await refreshAccess();
  mockHttpRequest(async () => response(null, 503, "temporarily unavailable"));
  await assert.rejects(refreshAccess(), /temporarily unavailable/);
  assert.equal(useAccessStore.getState().data, null);
  assert.equal(useAccessStore.getState().loading, false);
  mockHttpRequest(async () => response({ role: "admin", permissions: ["access:manage"] }));
  await requireManagementAccess();
});

test("management APIs use real HTTP endpoints and preserve business rejection", async () => {
  const transport = mockHttpRequest(async (path) => {
    if (path === "/api/access/users") return response([]);
    if (path === "/api/access/roles") return response({ roles: [], permissions: [] });
    return response(null, 409, "不能移除最后一个有效管理员。");
  });
  await Promise.all([getManagedUsers(), getRolePolicies()]);
  await assert.rejects(updateUserRole(7, "member"), (error) => error.status === 409);
  const call = transport.mock.calls[2].arguments;
  assert.equal(call[0], "/api/access/users/7/role");
  assert.equal(call[1].method, "PUT");
  assert.deepEqual(JSON.parse(call[1].body), { role: "member" });
  mockHttpRequest(async (path, options) => {
    assert.equal(path, "/api/access/roles/viewer/permissions");
    assert.deepEqual(JSON.parse(options.body), { permissions: ["meeting:read"] });
    return response({ role: "viewer", permissions: ["meeting:read"] });
  });
  await updateRolePermissions("viewer", ["meeting:read"]);
});

// 路由权限按实际编辑入口匹配，不能把名为 new/edit 的普通资源误判成编辑页。
test("page permissions separate viewing, editing and shared minutes", async () => {
  const { pagePermissions } = await import("../lib/page-permissions.ts");
  assert.deepEqual(pagePermissions("/knowledge/server-1/new"), [
    "knowledge:read",
    "knowledge:write",
  ]);
  assert.deepEqual(pagePermissions("/knowledge/server-1/edit/doc"), [
    "knowledge:read",
    "knowledge:write",
  ]);
  assert.deepEqual(pagePermissions("/knowledge/server-1/files/new"), ["knowledge:read"]);
  assert.deepEqual(pagePermissions("/knowledge/edit/files/doc"), ["knowledge:read"]);
  assert.deepEqual(pagePermissions("/meetings/active"), ["meeting:read"]);
  assert.deepEqual(pagePermissions("/shared/meeting-records/token"), ["meeting:read"]);
  assert.deepEqual(pagePermissions("/skills"), []);
});

test("imperative actions use current permission and require every requested capability", async () => {
  const { hasPermission, requirePermissions } = await import("../../../stores/access.ts");
  assert.equal(hasPermission("meeting:edit"), false);
  mockHttpRequest(async () =>
    response({ role: "member", permissions: ["meeting:read", "meeting:archive"] }),
  );
  await refreshAccess();
  assert.equal(hasPermission("meeting:read"), true);
  assert.equal(hasPermission("meeting:archive", "knowledge:write"), false);
  await assert.rejects(requirePermissions("knowledge:write"), (error) => error.status === 403);
  signOut();
  assert.equal(hasPermission("meeting:read"), false);
});
