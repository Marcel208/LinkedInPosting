// Renders kai-clip.html frame by frame into an MP4 (needs ffmpeg + playwright).
// Usage: node render.mjs [out.mp4] [--stills 1,4,8]
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { writeFileSync } from "node:fs";
import path from "node:path";

const FPS = 30;
const args = process.argv.slice(2);
const stillsIdx = args.indexOf("--stills");
const stills = stillsIdx >= 0 ? args[stillsIdx + 1].split(",").map(Number) : null;
const out = args.find(a => a.endsWith(".mp4")) || "kai-clip.mp4";

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
await page.goto(pathToFileURL(path.resolve("kai-clip.html")).href + "?render");
await page.evaluate(() => window.ready);
const frame = t => page.evaluate(t => { render(t); return document.getElementById("c").toDataURL("image/png").split(",")[1]; }, t);

if (stills) {
  for (const t of stills) writeFileSync(`still-${t}.png`, Buffer.from(await frame(t), "base64"));
} else {
  const duration = await page.evaluate(() => DURATION);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.round(duration * FPS);
  for (let i = 0; i < n; i++) {
    const buf = Buffer.from(await frame(i / FPS), "base64");
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (i % 60 === 0) process.stdout.write(`frame ${i}/${n}\n`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on("close", r));
  console.log("wrote", out);
}
await browser.close();
