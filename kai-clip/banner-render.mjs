// Renders the signature banners: static PNGs (2x) and looping animated GIFs (3 s).
//   node banner-render.mjs
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";

const OUT = "signatur", FPS = 15, LOOP = 3;
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(path.resolve("banner.html")).href + "?render");
await page.evaluate(() => window.ready);
const draw = t => page.evaluate(t => drawBanner(t), t);

for (const [name, b64] of Object.entries(await draw(.4))) writeFileSync(`${OUT}/kai-signatur-${name}.png`, Buffer.from(b64, "base64"));

mkdirSync(`${OUT}/.frames`, { recursive: true });
for (let i = 0; i < FPS * LOOP; i++) {
  for (const [name, b64] of Object.entries(await draw(i / FPS)))
    writeFileSync(`${OUT}/.frames/${name}-${String(i).padStart(3, "0")}.png`, Buffer.from(b64, "base64"));
}
for (const name of ["light", "dark", "red"]) {
  // GIF at 1.5x (900 px wide): sharp on most screens, still a reasonable file size
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", `${OUT}/.frames/${name}-%03d.png`,
    "-vf", "scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
    "-loop", "0", `${OUT}/kai-signatur-${name}.gif`]);
}
// light banner in exact display sizes: Outlook/Gmail show a pasted image at its pixel size
for (const w of [600, 450]) {
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", `${OUT}/kai-signatur-light.png`, "-vf", `scale=${w}:-1:flags=lanczos`, `${OUT}/kai-signatur-light-${w}.png`]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", `${OUT}/.frames/light-%03d.png`,
    "-vf", `scale=${w}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle`,
    "-loop", "0", `${OUT}/kai-signatur-light-${w}.gif`]);
}
rmSync(`${OUT}/.frames`, { recursive: true });
await browser.close();
console.log("done");
