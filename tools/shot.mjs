// 本地自检：用系统里已装的 Edge 渲染各页面，检查横向溢出并截图。
// 用法：npm run build && npm run preview，另开终端 node tools/shot.mjs
import { chromium } from 'playwright-core';
import { mkdirSync } from 'node:fs';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = process.env.BASE || 'http://127.0.0.1:4321';
const OUT = '.shots';

const targets = [
  { name: 'home', path: '/' },
  { name: 'writing', path: '/writing/' },
  { name: 'post', path: '/writing/opening/' },
  { name: 'notes', path: '/notes/' },
  { name: 'novels', path: '/novels/' },
  { name: 'novel', path: '/novels/kuajie-zhufu/' },
  { name: 'chapter', path: '/novels/kuajie-zhufu/ch-01/' },
  { name: 'gallery', path: '/gallery/' },
  { name: 'archive', path: '/archive/' },
  { name: 'music', path: '/music/' },
  { name: 'doing', path: '/doing/' },
  { name: 'search', path: '/search/' },
];

const viewports = [
  { label: 'desktop', width: 1440, height: 2400 },
  { label: 'mobile', width: 375, height: 900 },
];

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
let failed = false;

for (const vp of viewports) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
  for (const t of targets) {
    await page.goto(BASE + t.path, { waitUntil: 'networkidle' });
    const info = await page.evaluate(() => {
      const de = document.documentElement;
      // 被祖先 overflow 裁掉的元素（比如故意探出画布的光球）不算溢出。
      const clipped = (el) => {
        let p = el.parentElement;
        while (p) {
          const s = getComputedStyle(p);
          if (s.overflowX !== 'visible' || s.overflowY !== 'visible') return true;
          p = p.parentElement;
        }
        return false;
      };
      const over = [];
      document.querySelectorAll('body *').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && (r.right > de.clientWidth + 1 || r.left < -1) && !clipped(el)) {
          over.push(`${el.tagName.toLowerCase()}.${el.className || ''} right=${Math.round(r.right)}`);
        }
      });
      return { scrollWidth: de.scrollWidth, clientWidth: de.clientWidth, overflow: over.slice(0, 5) };
    });
    const bad = info.scrollWidth > info.clientWidth + 1 || info.overflow.length > 0;
    if (bad) failed = true;
    console.log(
      `${vp.label.padEnd(8)}${t.path.padEnd(30)}scrollW=${info.scrollWidth} clientW=${info.clientWidth} ${
        bad ? 'OVERFLOW ' + JSON.stringify(info.overflow) : 'ok'
      }`
    );
    await page.screenshot({ path: `${OUT}/${t.name}-${vp.label}.png`, fullPage: false });
  }
  await page.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
