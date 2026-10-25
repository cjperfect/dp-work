import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { restoreAuthSession } from "@/stores/auth";
import { AppRouter } from "@/router";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

restoreAuthSession();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider>
      <AppRouter />
    </TooltipProvider>
  </StrictMode>,
);
