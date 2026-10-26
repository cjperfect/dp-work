import { Toaster as SonnerToaster, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  return <SonnerToaster position="top-right" richColors {...props} closeButton={false} />;
}
