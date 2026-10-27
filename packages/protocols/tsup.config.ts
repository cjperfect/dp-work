import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/desktop.ts", "src/asr.ts", "src/rpc.ts"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
});
