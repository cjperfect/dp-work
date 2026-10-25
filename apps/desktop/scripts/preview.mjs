import process from "node:process";
import { spawn } from "node:child_process";
import electron from "electron";
import { desktopRoot, loadDesktopEnv, completed } from "./runtime.mjs";

loadDesktopEnv();
const env = { ...process.env, DESKTOP_BUNDLED_WEB: "1" };
delete env.ELECTRON_RUN_AS_NODE;
const desktop = spawn(electron, ["."], { cwd: desktopRoot, stdio: "inherit", env });
process.once("SIGINT", () => desktop.kill());
process.once("SIGTERM", () => desktop.kill());
await completed(desktop);
