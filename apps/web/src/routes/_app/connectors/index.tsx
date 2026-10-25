import { ConnectorsPage } from "@/features/connectors";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/connectors/")({
  staticData: { title: "连接器" },
  component: ConnectorsPage,
});
