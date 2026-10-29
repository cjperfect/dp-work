import { createFileRoute } from "@tanstack/react-router";
import { PartnersPage } from "@/features/partners";
export const Route = createFileRoute("/_app/partners/")({
  staticData: { title: "伙伴" },
  component: PartnersPage,
});
