import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/connectors/")({
  staticData: { title: "连接器" },
  component: lazyRouteComponent(() => import("@/features/connectors"), "ConnectorsPage"),
});
