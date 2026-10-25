import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const env = { ...process.env };
const venv = env.VIRTUAL_ENV ?? join(process.cwd(), ".venv");

if (process.platform === "win32") {
  const configPath = join(venv, "pyvenv.cfg");
  const home = existsSync(configPath)
    ? readFileSync(configPath, "utf8").match(/^home\s*=\s*(.+)$/m)?.[1]?.trim()
    : undefined;

  if (home) {
    // PyO3 loads python312.dll before Rust main() runs, so Windows needs it on PATH.
    env.VIRTUAL_ENV = venv;
    const pathKey = Object.keys(env).find((key) => key.toUpperCase() === "PATH") ?? "Path";
    env[pathKey] = `${home};${env[pathKey] ?? ""}`;
  }
}

const result = spawnSync("pnpm", ["exec", "tauri", ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
  shell: process.platform === "win32",
});

process.exitCode = result.status ?? 1;
