// Renders a clip page frame by frame into an MP4 (needs ffmpeg + playwright).
//   node render.mjs                                  -> kai-clip.html  -> kai-clip.mp4 (30 fps)
//   node render.mjs --page kai-promo.html --fps 60 --blur 6 --audio
//   node render.mjs --page kai-promo.html --stills 1,2.5,8
//   node render.mjs --page kai-galaxy.html --audio-only     (new soundtrack, keep the picture)
// --blur N   motion blur: N sub-frames per frame (page must expose renderFrame)
// --audio    synthesise the soundtrack from the page's SFX cue list (synth.py) and mux it
import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { writeFileSync, rmSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : def; };
const pageFile = opt("--page", "kai-clip.html");
const FPS = Number(opt("--fps", 30)), BLUR = Number(opt("--blur", 1));
const stills = opt("--stills", null)?.split(",").map(Number);
const out = opt("--out", pageFile.replace(/\.html$/, ".mp4"));
const withAudio = args.includes("--audio");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
await page.goto(pathToFileURL(path.resolve(pageFile)).href + "?render");
await page.evaluate(() => window.ready);
const frame = t => page.evaluate(([t, fps, blur]) => window.renderFrame
  ? renderFrame(t, fps, blur)
  : (render(t), document.getElementById("c").toDataURL("image/png").split(",")[1]), [t, FPS, BLUR]);

if (args.includes("--audio-only")) {
  // re-synthesise the soundtrack and swap it into an existing render
  const duration = await page.evaluate(() => DURATION);
  const style = await page.evaluate(() => window.MUSIC || "promo");
  writeFileSync("sfx.json", JSON.stringify({ duration, style, cues: await page.evaluate(() => window.SFX || []) }));
  execFileSync("python3", ["synth.py", "sfx.json", "soundtrack.wav"], { stdio: "inherit" });
  const tmp = out.replace(/\.mp4$/, ".remux.mp4");
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", out, "-i", "soundtrack.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", tmp], { stdio: "inherit" });
  execFileSync("mv", [tmp, out]); rmSync("sfx.json");
  console.log("remuxed", out);
} else if (stills) {
  const base = path.basename(pageFile, ".html");
  for (const t of stills) writeFileSync(`still-${base}-${t}.png`, Buffer.from(await frame(t), "base64"));
} else {
  const duration = await page.evaluate(() => DURATION);
  const video = withAudio ? out.replace(/\.mp4$/, ".video.mp4") : out;
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", video], { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.round(duration * FPS);
  for (let i = 0; i < n; i++) {
    const buf = Buffer.from(await frame(i / FPS), "base64");
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (i % (FPS * 2) === 0) console.log(`frame ${i}/${n}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on("close", r));
  if (withAudio) {
    const sfx = await page.evaluate(() => window.SFX || []);
    const style = await page.evaluate(() => window.MUSIC || "promo");
    writeFileSync("sfx.json", JSON.stringify({ duration, style, cues: sfx }));
    execFileSync("python3", ["synth.py", "sfx.json", "soundtrack.wav"], { stdio: "inherit" });
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", video, "-i", "soundtrack.wav", "-c:v", "copy",
      "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], { stdio: "inherit" });
    rmSync(video); rmSync("sfx.json");
  }
  console.log("wrote", out);
}
await browser.close();
