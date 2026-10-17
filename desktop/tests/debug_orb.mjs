// Diagnostic: what is the orb window showing, and why, right after the hub sends a message?
import { _electron as electron } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ws = fs.mkdtempSync(path.join(os.tmpdir(), "argus-dbg-"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const app = await electron.launch({ executablePath: require("electron"), args: [APP, "--test"],
  env: { ...process.env, ARGUS_FAKE: "1", ARGUS_WATCH_ROOT: ws, TAVILY_API_KEY: "" } });
try {
  for (let i = 0; i < 100 && app.windows().length < 2; i++) await sleep(200);
  const orb = app.windows().find((p) => p.url().includes("#orb"));
  const hub = app.windows().find((p) => !p.url().includes("#orb"));
  await hub.waitForSelector(".composer", { timeout: 30000 });
  for (let i = 0; i < 100; i++) { if (await hub.evaluate(() => window.__argusStore.getState().conn === "live")) break; await sleep(200); }
  const snap = async (label) => console.log(label, JSON.stringify(await orb.evaluate(() => {
    const s = window.__argusStore.getState();
    const cv = document.querySelector(".orb-box canvas");
    const r = cv?.getBoundingClientRect();
    return {
      vis: document.visibilityState, hidden: document.hidden,
      card: document.querySelector(".orb-card")?.className ?? null,
      busy: s.busy, prophecy: s.prophecy, conn: s.conn,
      canvas: cv ? { w: r.width, h: r.height, disp: getComputedStyle(cv).display, vis: getComputedStyle(cv).visibility } : null,
      box: (() => { const b = document.querySelector(".orb-box")?.getBoundingClientRect(); return b ? { w: b.width, h: b.height } : null; })(),
    };
  })));
  await snap("orb at start:");
  await hub.fill("#argus-composer", "hello");
  await hub.locator(".invoke").click();
  await sleep(400);
  await snap("orb while hub works:");
  for (let i = 0; i < 150; i++) { if (!(await hub.evaluate(() => window.__argusStore.getState().busy))) break; await sleep(200); }
  await snap("orb after the reply:");
  await app.evaluate(() => global.__argus.hub().minimize());
  await sleep(800);
  await snap("orb once shown:");
  console.log("bounds:", JSON.stringify(await app.evaluate(() => global.__argus.orb().getBounds())));
} finally {
  await app.close();
}
