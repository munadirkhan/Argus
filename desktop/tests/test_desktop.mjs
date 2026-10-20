// Drives the real desktop app (Electron) end to end. No model calls: the core
// it starts runs with ARGUS_FAKE=1 in a throwaway workspace.
//
//   cd desktop && npm run build:web && npm test
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
  console.log("A core is already running on 7600 -- stop it first so this test exercises the desktop's own core.");
  process.exit(2);
}

// A real spoken sentence (Windows' built-in voice) to feed in as the microphone.
let wav = null;
if (process.platform === "win32") {
  const { execFileSync } = await import("node:child_process");
  wav = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "argus-mic-")), "say.wav");
  try {
    execFileSync("powershell", ["-NoProfile", "-Command",
      "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; " +
      `$s.SetOutputToWaveFile('${wav}'); $s.Speak('Argus, summarize the attached report.'); $s.Dispose()`]);
  } catch { wav = null; }
}

const ws = fs.mkdtempSync(path.join(os.tmpdir(), "argus-desktop-ws-"));
const app = await electron.launch({
  executablePath: require("electron"),
  args: [APP, "--test"],
  env: { ...process.env, ARGUS_FAKE: "1", ARGUS_WATCH_ROOT: ws, TAVILY_API_KEY: "",
         ...(wav ? { ARGUS_FAKE_MIC: wav } : {}) },
});
const main = (fn, arg) => app.evaluate(fn, arg);

try {
  console.log("=== startup ===");
  check("desktop starts the core itself", await until(async () => (await health())?.ready, 40000, 500));
  const h = await health();
  check("core watches the configured workspace", h && path.resolve(h.root) === path.resolve(ws), h?.root);

  await until(() => app.windows().length >= 2, 15000);
  const pages = app.windows();
  const orbPage = pages.find((p) => p.url().includes("#orb"));
  const hubPage = pages.find((p) => !p.url().includes("#orb"));
  check("two windows: hub + orb", Boolean(orbPage && hubPage), pages.map((p) => p.url()).join(" | "));

  await hubPage.waitForSelector(".composer", { timeout: 20000 });
  check("hub uses desktop chrome", await hubPage.evaluate(() => document.documentElement.classList.contains("desktop")));
  check("header leaves room for window controls",
    await hubPage.evaluate(() => getComputedStyle(document.querySelector(".header")).paddingRight) === "146px");
  check("hub goes live against the core", await until(() => hubPage.evaluate(() =>
    window.__argusStore.getState().conn === "live"), 15000));
  check("orb hidden while the hub is in front", !(await main(() => global.__argus.orb().isVisible())));
  await hubPage.screenshot({ path: path.join(OUT, "hub.png") });

  console.log("\n=== attach a file from anywhere ===");
  const doc = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "argus-doc-")), "quarterly report.txt");
  fs.writeFileSync(doc, "Revenue up 12%. Churn flat. Hiring paused in Q3.\n");
  await hubPage.setInputFiles('.composer input[type="file"]', doc);
  check("chip uploads and turns ready", await until(() =>
    hubPage.locator(".att-chip.ready").count().then((n) => n === 1), 8000));
  const stored = path.join(ws, ".argus", "attachments", "quarterly report.txt");
  check("file copied into the workspace's attachment folder", fs.existsSync(stored), stored);

  console.log("\n=== talk to it (fake mic plays a spoken WAV) ===");
  if (wav) {
    await hubPage.locator(".composer-btn.mic").click();
    check("mic starts recording", await until(() => hubPage.locator(".composer.listening").count().then((n) => n > 0), 6000));
    await sleep(4200);
    await hubPage.locator(".composer-btn.mic").click();
    const heard = await until(() => hubPage.inputValue("#argus-composer").then((v) => /summari[sz]e/i.test(v)), 30000, 250);
    const text = await hubPage.inputValue("#argus-composer");
    check("speech transcribed locally into the composer", heard, JSON.stringify(text));
    console.log("    heard:", JSON.stringify(text));
  } else {
    console.log("  [SKIP] no Windows speech engine to make a test recording");
  }

  console.log("\n=== send it: text + attachment reach the agent ===");
  if (!(await hubPage.inputValue("#argus-composer"))) await hubPage.fill("#argus-composer", "Summarize the attached report.");
  await hubPage.locator(".invoke").click();
  check("chat shows the attachment on the message", await until(() =>
    hubPage.locator(".msg-user .sent-att", { hasText: "quarterly report.txt" }).count().then((n) => n > 0), 8000));
  check("composer clears after sending", (await hubPage.locator(".att-chip").count()) === 0);
  // Wait for Argus's answer itself: `busy` can still read false in the moment
  // before the run starts, and a reply that lands after we leave the hub is
  // (rightly) shown beside the orb.
  await until(() => hubPage.evaluate(() => {
    const s = window.__argusStore.getState();
    const last = s.entries[s.entries.length - 1];
    return !s.busy && last?.kind === "message" && last.role === "assistant";
  }), 60000, 300);
  // The orb has its own connection; let the reply reach it too, or it is news
  // to the orb when the hub goes away a moment later.
  await until(() => orbPage.evaluate(() => {
    const e = window.__argusStore.getState().entries;
    return e.length > 0 && e[e.length - 1].kind === "message" && e[e.length - 1].role === "assistant";
  }), 15000, 200);
  await sleep(300);
  await hubPage.screenshot({ path: path.join(OUT, "hub-sent.png") });

  console.log("\n=== leave the hub: the orb appears ===");
  await main(() => global.__argus.hub().minimize());
  check("orb shows when the hub is minimized", await until(() => main(() => global.__argus.orb().isVisible()), 4000));
  const st = await main(() => ({
    top: global.__argus.orb().isAlwaysOnTop(),
    b: global.__argus.orb().getBounds(),
    taskbar: global.__argus.orb().isMenuBarVisible?.(),
  }));
  check("orb is always on top", st.top);
  check("orb is a small 168px square", st.b.width === 168 && st.b.height === 168, JSON.stringify(st.b));
  await orbPage.waitForSelector(".orb-box canvas", { timeout: 15000 });
  check("orb window is transparent", await orbPage.evaluate(() =>
    getComputedStyle(document.body).backgroundColor === "rgba(0, 0, 0, 0)"));
  check("orb is live too", await until(() => orbPage.evaluate(() => window.__argusStore.getState().conn === "live"), 15000));
  const coreLog = path.join(await main(({ app }) => app.getPath("userData")), "core.log");
  check("Argus spoke its reply (orb asked the core for speech; muted in tests)",
    await until(() => fs.readFileSync(coreLog, "utf8").includes('"POST /speak HTTP/1.1" 200'), 15000, 300));
  await sleep(1200);
  await orbPage.screenshot({ path: path.join(OUT, "orb.png"), omitBackground: true });

  console.log("\n=== Argus speaks while you're elsewhere ===");
  await orbPage.evaluate(() => window.__argusStore.getState().ingest({
    type: "watcher.observation", id: "obs_test", confidence: 0.92,
    observation: "Your dev server crashed at watchlist.js:24.",
    suggestion: "Want me to trace it and patch watchlist.js?", dismissible: true,
  }));
  check("orb expands to show the card", await until(() =>
    main(() => global.__argus.orb().getBounds().width === 168 + 340), 4000),
    JSON.stringify(await main(() => global.__argus.orb().getBounds())));
  const card = await orbPage.locator(".orb-card").innerText();
  check("card carries the offer", card.includes("patch watchlist.js"), card);
  const side = await main(() => global.__argus.state().orbSide);
  check("card opens toward the screen centre (orb sits bottom-right → left)", side === "left", side);
  await sleep(600);
  await orbPage.screenshot({ path: path.join(OUT, "orb-speaks.png"), omitBackground: true });

  console.log("\n=== click OPEN: back to the hub ===");
  await orbPage.locator(".oc-actions button", { hasText: "OPEN" }).click();
  check("hub restored", await until(() => main(() => {
    const w = global.__argus.hub(); return w.isVisible() && !w.isMinimized();
  }), 4000));
  check("orb steps aside", await until(() => main(() => !global.__argus.orb().isVisible()), 4000));

  console.log("\n=== closing the hub doesn't kill Argus ===");
  await main(() => global.__argus.hub().close());
  await sleep(500);
  const after = await main(() => ({ destroyed: global.__argus.hub().isDestroyed(), visible: global.__argus.hub().isVisible() }));
  check("hub hides instead of quitting", !after.destroyed && !after.visible, JSON.stringify(after));
  check("orb takes over", await until(() => main(() => global.__argus.orb().isVisible()), 4000));
  check("core still running", (await health())?.ready === true);
  check("desktop owns this core", (await main(() => global.__argus.state())).ownsCore);
} finally {
  await app.close();
}

console.log("\n=== quit ===");
check("quitting stops the core it started", await until(async () => !(await health()), 8000, 300));

console.log("\n" + (ok ? "ALL CHECKS PASSED" : "SOME CHECKS FAILED"));
process.exit(ok ? 0 : 1);
