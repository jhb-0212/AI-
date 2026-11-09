// 功能自检：搜索能出结果、窄屏菜单能展开、导航不带错的前缀。
import { chromium } from 'playwright-core';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = process.env.BASE || 'http://127.0.0.1:4321';

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
let failed = false;

// 1) 搜索（Component UI：搜索框是 pagefind-searchbox 里的 .pf-searchbox-input）
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(BASE + '/search/', { waitUntil: 'networkidle' });
const hasInput = await page
  .waitForSelector('.pf-searchbox-input', { timeout: 8000 })
  .then(() => true)
  .catch(() => false);
if (!hasInput) {
  console.log('search: UI 没加载出来（dev 模式下 /pagefind 不存在，需要在 build + preview 下测）');
  failed = true;
} else {
  for (const q of ['文案', '唢呐', '删掉形容词']) {
    await page.fill('.pf-searchbox-input', '');
    await page.fill('.pf-searchbox-input', q);
    await page.waitForTimeout(1200);
    const titles = await page.$$eval('.pf-result-title', (els) =>
      els.map((e) => e.textContent.trim()).slice(0, 3)
    );
    console.log(`search "${q}" -> ${titles.length} 条 ${JSON.stringify(titles)}`);
    if (!titles.length) failed = true;
  }
  await page.screenshot({ path: '.shots/search-results.png' });
}
await page.close();

// 2) 窄屏菜单
const m = await browser.newPage({ viewport: { width: 375, height: 812 } });
await m.goto(BASE + '/', { waitUntil: 'networkidle' });
const collapsed = await m.evaluate(() => {
  const menu = document.getElementById('site-menu');
  return getComputedStyle(menu).display === 'none';
});
await m.click('.nav-toggle');
await m.waitForTimeout(300);
const opened = await m.evaluate(() => document.getElementById('site-menu').classList.contains('open'));
const overflow = await m.evaluate(
  () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
);
console.log(`nav: 默认收起=${collapsed} 点开=${opened} 展开后溢出=${overflow}`);
await m.screenshot({ path: '.shots/nav-open-mobile.png' });
if (!collapsed || !opened || overflow) failed = true;
await m.close();

// 3) 首页：搜索条 / 个人卡统计 / 四个联系入口 / 内容墙 / 歌词条
const home = await browser.newPage({ viewport: { width: 375, height: 812 } });
await home.goto(BASE + '/', { waitUntil: 'networkidle' });

const stats = await home.$$eval('.pf-num', (els) =>
  els.map((e) => e.textContent.replace(/\s+/g, ' ').trim())
);
const iconCount = await home.$$eval('.pf-icon-btn', (els) => els.length);
const wallCards = await home.$$eval('.wall .wc', (els) => els.length);
const lyricHref = await home.$eval('.lyric', (el) => el.getAttribute('href'));
const searchBand = await home.$eval('.search-band', (el) => el.getAttribute('href'));
console.log(
  `home: 统计=${JSON.stringify(stats)} 联系图标=${iconCount} 内容卡=${wallCards} 歌词条=${lyricHref} 搜索条=${searchBand}`
);
if (stats.length !== 3 || iconCount !== 4 || wallCards < 5 || !lyricHref || !searchBand) failed = true;

await home.screenshot({ path: '.shots/profile-mobile.png' });

const todoBtn = await home.$('.pf-icon-btn.is-todo');
if (todoBtn) {
  await todoBtn.click();
  await home.waitForTimeout(400);
  const t = await home.$eval('#toast', (el) => el.textContent);
  console.log(`contact: 未填项点击提示=${JSON.stringify(t)}`);
  if (!t) failed = true;
}

// 按 / 直接进搜索页
await home.keyboard.press('/');
const jumped = await home
  .waitForURL(/\/search/, { timeout: 5000 })
  .then(() => true)
  .catch(() => false);
console.log(`slash: 按 / 进搜索=${jumped}`);
if (!jumped) failed = true;
await home.close();

// 4) 404：不存在的路径要有自定义页，三个入口都在
const nf = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const res = await nf.goto(BASE + '/no-such-page-xyz/', { waitUntil: 'networkidle' });
const nfCode = await nf.$eval('.nf-code', (e) => e.textContent.trim()).catch(() => '');
const nfH1 = await nf.$eval('.nf h1', (e) => e.textContent.trim()).catch(() => '');
const nfLinks = await nf.$$eval('.nf-act a', (els) => els.map((a) => a.getAttribute('href')));
console.log(`404: status=${res.status()} code=${JSON.stringify(nfCode)} h1=${JSON.stringify(nfH1)} links=${JSON.stringify(nfLinks)}`);
if (res.status() !== 404 || nfCode !== '404' || nfLinks.length !== 3) failed = true;

// 404 页里也能按 / 跳搜索
await nf.keyboard.press('/');
const nfJump = await nf
  .waitForURL(/\/search/, { timeout: 5000 })
  .then(() => true)
  .catch(() => false);
console.log(`404 slash: 按 / 进搜索=${nfJump}`);
if (!nfJump) failed = true;
await nf.screenshot({ path: '.shots/site-404.png' });
await nf.close();

await browser.close();
process.exit(failed ? 1 : 0);
