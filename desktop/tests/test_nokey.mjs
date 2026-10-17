// First run on someone else's machine: no Nebius key anywhere. The desktop
// must not start a core that would only exit; the hub plays a simulated
// session with ADD KEY / GO LIVE instead of a dead "offline" screen.
//
// Never touches the real .env: the app is pointed at a throwaway file.
//
//   cd desktop && npm run build:web && node tests/test_nokey.mjs
import { _electron as electron } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(here, "..");
const OUT = path.resolve(APP, "..", "web", "evidence", "desktop");
fs.mkdirSync(OUT, { recursive: true });

let ok = true;
const check = (label, cond, detail = "") => {
  console.log(`  [${cond ? "PASS" : "FAIL"}] ${label}${!cond && detail ? " -- " + detail : ""}`);
  ok &&= Boolean(cond);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 8000, step = 100) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if (await fn()) return true; } catch { /* keep polling */ }
    await sleep(step);
  }
  return false;
}
async function health() {
  try { return await (await fetch("http://127.0.0.1:7600/health")).json(); } catch { return null; }
}

if (await health()) {
  console.log("A core is already running on 7600 -- stop it first (with one running, the desktop would just use it).");
  process.exit(2);
}

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "argus-nokey-"));
const envFile = path.join(dir, ".env");
fs.writeFileSync(envFile, "# Nebius Token Factory\nNEBIUS_API_KEY=\nTAVILY_API_KEY=\n");

const env = { ...process.env, ARGUS_ENV_FILE: envFile, ARGUS_WATCH_ROOT: dir };
delete env.ARGUS_FAKE;
delete env.NEBIUS_API_KEY;
const app = await electron.launch({ executablePath: require("electron"), args: [APP, "--test"], env });
const main = (fn, arg) => app.evaluate(fn, arg);

try {
  console.log("=== no key: no core, a simulated session instead ===");
  await until(() => app.windows().length >= 2, 15000);
  const pages = app.windows();
  const hub = pages.find((p) => !p.url().includes("#orb"));
  const orb = pages.find((p) => p.url().includes("#orb"));
  await hub.waitForSelector(".composer", { timeout: 20000 });

  const st = await main(() => global.__argus.state());
  check("desktop knows the key is missing", st.needsKey === true);
  check("no core was started", !st.ownsCore);
  await sleep(1500);
  check("nothing listening on 7600", !(await health()));

  check("hub plays the simulated session", await until(() => hub.evaluate(() =>
    window.__argusStore.getState().source === "replay"), 8000));
  const note = await hub.waitForSelector(".mode-note", { timeout: 8000 }).catch(() => null);
  check("note says add your key", Boolean(note) && /Add your Nebius key/.test(await note.innerText()));
  check("ADD KEY and GO LIVE buttons", (await hub.$$(".mode-note .mn-btn")).length === 2);
  check("LIVE toggle is disabled", await hub.evaluate(() =>
    [...document.querySelectorAll(".seg button")].find((b) => b.textContent === "LIVE")?.disabled === true));
  check("composer explains instead of erroring", await hub.evaluate(() =>
    document.querySelector("#argus-composer")?.getAttribute("placeholder")?.includes("Nebius key")));

  await sleep(2500); // let the replay draw something for the screenshot
  await hub.screenshot({ path: path.join(OUT, "hub-nokey.png") });

  console.log("=== GO LIVE while the key is still blank ===");
  await hub.click(".mode-note .mn-btn.go");
  check("explains the key is still missing", await until(() => hub.evaluate(() =>
    /No key found yet/.test(document.querySelector(".mode-note")?.textContent ?? "")), 8000));
  check("still no core", !(await health()));

  console.log("=== the key check itself (never reads the value out) ===");
  const cases = [
    ["NEBIUS_API_KEY=", false],
    ["NEBIUS_API_KEY=   ", false],
    ["NEBIUS_API_KEY=\"\"", false],
    ["# NEBIUS_API_KEY=abc", false],
    ["NEBIUS_API_KEY= # paste here", false],
    ["NEBIUS_API_KEY=abc123", true],
    ["NEBIUS_API_KEY = \"abc123\"", true],
    ["FOO=1\r\nNEBIUS_API_KEY=abc123\r\n", true],
  ];
  for (const [text, want] of cases) {
    fs.writeFileSync(envFile, text);
    check(`${JSON.stringify(text)} -> ${want ? "key" : "no key"}`, (await main(() => global.__argus.hasKey())) === want);
  }
  fs.writeFileSync(envFile, "NEBIUS_API_KEY=\n");

  console.log("=== the orb, meanwhile ===");
  check("orb stays dim, not retrying a core", await orb.evaluate(() =>
    window.__argusStore.getState().conn !== "live"));
  check("orb tooltip points at the key", await orb.evaluate(() =>
    document.querySelector(".orb-box")?.getAttribute("title")?.includes("Nebius key")));
} catch (e) {
  check("no exceptions", false, e.stack || String(e));
} finally {
  await app.close().catch(() => {});
}

console.log(ok ? "\nALL CHECKS PASSED" : "\nSOME CHECKS FAILED");
process.exit(ok ? 0 : 1);
