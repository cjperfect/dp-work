import { Toaster as SonnerToaster, type ToasterProps } from "sonner";

import { usePreferences } from "@/stores/preferences";

export function Toaster(props: ToasterProps) {
  const theme = usePreferences((state) => state.theme);
  return (
    <SonnerToaster
      theme={theme}
      position="top-right"
      richColors
      offset={typeof window !== "undefined" && window.desktop?.windowChrome ? 48 : undefined}
      {...props}
      closeButton={false}
    />
  );
}
