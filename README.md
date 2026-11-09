# 忘忧居 · Nepenthe

个人博客站点。Astro 5 + 手写 CSS + Pagefind 搜索，产物是纯静态 HTML，不依赖任何后端。

## 页面

| 路径 | 内容 |
| --- | --- |
| `/` | 首页：光球、搜索条、个人卡 + 音乐卡、歌词条、内容墙、在做、作品集入口 |
| `/writing/` | 文章归档（按年份分组） |
| `/writing/<文件名>/` | 单篇（带上一篇 / 下一篇） |
| `/notes/` | 随记，一句话一条 |
| `/novels/` | 小说作品列表 |
| `/novels/<作品>/` | 作品详情 + 章节列表 |
| `/novels/<作品>/<章节>/` | 阅读页（上一章 / 下一章） |
| `/gallery/` | 相册：一本一叠拍立得，点开摊成一面照片墙 |
| `/archive/` | 归档：一条蜿蜒的光河，卡片浮在河的两岸 |
| `/music/` | 音乐：上面一张「现在在听」的大卡（盘 + 曲名 + 歌手 + 一句话 + 播放键 / 上下首 + 进度），中间「歌词 / 曲目」两块面板 |
| `/doing/` | 在做 |
| `/search/` | 站内搜索（Pagefind） |
| `/rss.xml`、`/sitemap-index.xml` | 自动生成 |

## 本地跑

```bash
npm install
npm run dev        # http://localhost:4321，改文件自动刷新
npm run build      # dist/，构建后会自动跑 Pagefind 建索引
npm run preview    # 预览 dist（搜索必须在这个模式下测）
```

需要 Node 22 或更高（本机已是 22.23）。

> 搜索依赖构建产物：`npm run dev` 里没有 `/pagefind/`，搜索页会是空输入框。要看搜索效果必须 `npm run build` + `npm run preview`。

## 后台（内容管理）

内容也有一套后台：FastAPI + SQLAlchemy + SQLite，浏览器打开 `/admin/` 就能改文章、随记、小说章节、相册照片、曲目、站点文案和「在做的事」。左边第一项是**仪表盘**：六格计数、最近更新（点一条直接跳到对应页）、还没发的草稿、文章标签分布、发布历史（时间 / 成功与否 / 页数 / 耗时），以及**访客**（今日与 7/30 日 PV·UV、30 天曲线、热门页面、来源、设备构成）。

**数据库是编辑时的唯一数据源，点「发布」才把内容渲染回仓库的 markdown / JSON，再跑一次 `npm run build`。** 所以线上站点依旧是纯静态文件，后台挂了网站照常跑；也就是说 `src/content/*.md` 和 `src/data/*.json` 现在由后台接管，手写和后台改两种方式都还能用。

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
# 后台 http://127.0.0.1:8100/admin/ ，接口文档 /docs
```

默认账号 `admin` / `nepenthe-admin`（上线前用 `ADMIN_PASSWORD` 换掉）。首次启动会把现有 markdown 灌进空库，不覆盖后来在后台改的内容。

启动命令、环境变量、接口清单、换 PostgreSQL、nginx 反代和测试都在 [`server/README.md`](server/README.md)。

## 改内容

### 1. `src/data/site.data.json` —— 站点文案总表

站名、英文名、首页自我介绍与导语、右上角日期、曲目、在做的事、底部小事实都在这里。也可以直接进后台「站点」页改——后台会把这块写回这个文件。

```ts
playlistId: '18570165544'  // 网易云歌单 ID，现在只在「曲目」页脚留一个「在网易云打开歌单」的链接
musicApi: 'https://api.injahow.cn/meting/'  // 站内播放器走的接口，换成自建后端就改这一行
portfolioUrl: ''           // 作品集地址，填了导航和首页按钮直接跳过去
```

歌单 ID 就是歌单链接 `music.163.com/playlist?id=` 后面那串数字。音乐页不再是外链面板，而是站内自己包装网易云接口的真播放器（`src/scripts/sound.js`）：能播、能暂停、能上下首、进度条点一下就跳、歌词跟着走。曲目在 `tracks` 里改（`id` 是歌曲 ID，`dur` 是整首秒数）。公共接口没登录态，有些歌只回 30–45 秒试听，这时会亮一颗「试听」标；要完整版就自建 NeteaseCloudMusicApi 再换 `musicApi`——详见下面「音乐页」一节。

首页那张音乐卡是真播放器的一小块：封面盘 + 曲名 + 歌手是链接（点哪儿都去 `/music/`），中间三颗键直接控这一个 `Audio`——暂停 / 上一首 / 下一首，下面一条细进度。两个页面各建一份 `Audio`，共用的是 `sound.js` 那套代码和 `localStorage` 里记住的第几首。

首页是一张「个人卡 + 音乐卡」并排的版式：三段简介和三个数字（文章 / 随记 / 照片，都是从内容里真数出来的）都在个人卡上，右上四个圆形图标就是下面这份 `contact`。

```ts
contact: {
  github: '',    // 用户名（dxy001）或完整主页 https://github.com/xxx
  email: '',     // 收信地址
  wechatId: '',  // 微信号，点击复制
  wechatQr: '',  // 二维码图放 public/ 后填 '/wechat-qr.png'
  douyin: '',    // 抖音号，或主页面链接
},
bio: [
  '学数学出身，后来发现把一件事讲清楚，比算对一个数难。',
  '现在三件事并行：AIGC 漫剧、这个日更的站、一篇还没写完的论文。',
  '这里放过程，成品在作品集。聊 AIGC、剧本，或者只是想说句什么，都行。',
],
```

留空的图标是灰的，点一下会弹出提示告诉你该填哪个字段；填上就变成真入口——GitHub / 抖音新窗口打开，邮箱走 `mailto`，微信点击复制，二维码图可以点开放大。

首页顺序：名字区（光球 + 站名 + 一句话）→ 通栏搜索条 → 个人卡 + 音乐卡 → 歌词条 → 内容墙（最新文章大卡 + 文章 + 随记 + 相册 + 归档）→ 在做 → 作品集入口。内容墙用 CSS `columns` 做瀑布流，卡片数量和高度变了会自己重排。搜索条直接进 `/search/`，在首页按 `/` 也能跳过去；`/search/?q=关键词` 会自动填好输入框并搜一次。

归档页是一条会流动的光河，配色走「倒映黄昏的天空」：一条 SVG 曲线从页面顶上一路摆到底，沿线的颜色从靛蓝（`#3A4E9E`）走到夏蓝、青、暖金（`#FFD37A`）再到霞粉（`#FF9E7A`），末端淡出。河分四层——`.flow-bed` 一条 16px 糊开的粗线当河床（给河一点厚度），`.flow-core` 2px 的细光当河身，`.flow-spark` 是水面上那道亮光：同样一条路径，上面盖一层 `mask`，遮罩里放两块纵向渐变的高光条，各自用 `<animateTransform>` 从顶部平移到底（14s 一轮、两块错开 7s），谁扫过哪段就亮一下；`.flow-glint` 再叠一条 2.5px 的窄带（`#flowRippleMask`，54px 高、22s 一轮、错开 11s），走得更快，读起来是水面一路滑下去的碎光。两块主光带的 `dur` 一样、`begin` 差一半，首尾正好接上，不会出现空档。

这一页的底色也不再是纯近黑：`.arc-page` 自己铺了一层夜空——顶上一点靛蓝、左右各一团很淡的青、地平线那头一层暖起来的霞，外加三组重复的 1px 星点（`background-size` 各不相同，看起来才不排队）。卡片改成偏海军蓝的玻璃（`rgba(15,24,44,.88)`），类型色也跟着调成暖金 / 青 / 霞粉，压在这条河上不打架。

尺寸上有个坑记一下：这个 `viewBox` 是 `0 0 100 H` + `preserveAspectRatio="none"`，横向被拉满、纵向 1:1，所以**凡是纵向的高度（主光带 230px、波光带 54px）可以直接写像素，横向要写成 0–100 的比例**；线宽靠 `vector-effect="non-scaling-stroke"` 保持像素值，不然横向会被拉成一坨。高光条的动画也按这个思路走——只平移纵向，横向不动，所以拉宽拉窄都不会变形。`prefers-reduced-motion: reduce` 时 `.flow-spark` 与 `.flow-glint` 都 `display: none`，河只剩静态的两层。

卡片浮在河的左右两岸，一张轮一边，用一根细引线接到河上的节点上；节点按类型上色——文章 `--mag`、随记 `--cyan`、小说章节 `--vio`，鼠标压上去变实心并发亮。时间戳贴在节点旁边的河面空处，越往下越新。

这条河的路径不是画死的：`archive/index.astro` 里按条目数算出每 152px 一个节点、横向在 50% ± 14% 之间来回，再用三段贝塞尔连成 S 形（`STEP` / `AMP` 两个常量调密度和摆幅），所以加一篇东西河就自己重新长一次。样式在 `extra.css` 的「归档：一条蜿蜒的光河」一段。窄屏（≤860px）不画这条 SVG 河（`display: none`），改用一根 CSS 渐变竖线拉直靠左，卡片一张张竖着摞，日期移到卡片上方——窄屏上就没有那道流水了。

相册页是一面照片墙：一本相册 = 一叠拍立得。三张相纸错开压着（`.stack` 里的 `.polaroid.p1 / .p2 / .p3`，各自一点旋转和位移），最上面那张贴一条半透明胶带（`.tape`），右下角一颗按这本光色走的张数徽章（`.album-count`），相纸下面一行是编号和日期（`.album-meta`）。鼠标移上去整叠轻轻抖一下（`album-card:hover` 上的 `album-quiver`，`prefers-reduced-motion` 时不动）。点开这本就占满整行、那叠收小到 236px，下面 `grid-template-rows: 0fr → 1fr` 摊开——高度是量出来的，不用写死；同时只开一本，其余淡到 50%；按 Esc 也能收起。

摊开的是一面 `.album-wall`：每张照片一张白框相纸（4:3 画面 + 底部一行细字说明），按 `nth-child(4n+n)` 各歪一点角度，顶上贴一条胶带，鼠标压上去会扶正抬起。一本最多四列、窄屏两列。相册里没照片时，同一面墙上是四张空相纸：深色虚线格子里写「待放」——所以现在的站里看到的就是这个空态。样式都在 `extra.css` 的「相册：一叠拍立得」一段。

最后那本「新建相册」是同一种相纸，空壳加一个大加号；照片和相册都在后台「相册」页里加（数据落在 `photos.data.json`）。

页头最右边是个齿轮按钮，点开一张「设置」卡：首页的光球开关、光球亮度滑块、点击涟漪、光标轨迹、降低动效。五项都真生效——光球关掉是整个藏起来（`html.orb-off`），亮度走 `--orb-op` 这个 CSS 变量乘到 `.orb-wrap` 的 opacity 上，涟漪和轨迹是 `Base.astro` 里的指针事件，降低动效给 `<html>` 加 `calm` 把全站动画和过渡压到 0.001ms。设置存在 `localStorage` 的 `nepenthe:set` 里，`Base.astro` head 里另有一段内联脚本先把它应用掉，省得刷新时先看见光球再消失。想加一项：在 `Nav.astro` 的 `.sets` 里加一行 `<button role="switch" data-set="xxx">`（或一个 `data-set` 的 `input[type=range]`），再在 `Base.astro` 的 `DEFAULTS` 里补个默认值，`applyStore()` 会自己认。

### 2. 四类内容，都是「一个文件 = 一条内容」

| 想加什么 | 放哪 | 网址 |
| --- | --- | --- |
| 文章（长文） | `src/content/posts/*.md` | `/writing/<文件名>/` |
| 随记（一句话） | `src/content/notes/*.md` | 归在 `/notes/` 列表里 |
| 小说作品 | `src/content/novels/*.md` | `/novels/<文件名>/` |
| 小说章节 | `src/content/chapters/<作品文件名>/*.md` | `/novels/<作品>/<章节文件名>/` |

**文章** frontmatter：`title / date / tag / readTime / summary / draft`

```markdown
---
title: 忘忧居，开业
date: 2026-11-07
tag: 开篇
readTime: 3 分钟
summary: 一句话摘要，列表页显示这句
---

正文用 Markdown 写。

> 用引用块写金句，会渲染成左边那条渐变竖线的样式。
```

**写作增强语法**（除标准 Markdown 外，另支持两种）：

- `==重点==` → 行内高亮，淡绿底墨青字，用来标一句里最想让人看到的部分。
- `> [!note]`（或 `[!tip]` / `[!warning]` / `[!danger]` / `[!example]` / `[!info]` / `[!success]` / `[!caution]` / `[!error]` / `[!bug]` / `[!quote]`）→ 提示框。`[!type]` 后同一行可写标题，也可留空只放正文：

```markdown
> [!note]
> 无标题的提示框，正文就是这一行。

> [!warning] 注意
> 带标题的提示框，标题显示在正文上方。
```

不同 `type` 会让提示框左侧的竖条换色（note/绿、tip/浅绿、warning/金、danger/绯、example/紫）。

**随记**：只有 `date` 和可选 `tag`，正文就是那句话。

```markdown
---
date: 2026-11-07
tag: 建站
---

站做完了。剩下的就是写。
```

**小说作品**：`title / subtitle / summary / status（筹备中|连载中|已完结）/ tags / updated`

**章节**：`title / order（排序用，1 开始）/ date`。加一章就是在对应作品目录下新建一个 md，`order` 往下排，上一章/下一章会自动接上。

### 3. `src/data/photos.data.json` —— 相册

一本相册 = 墙上一叠相纸，`albums` 里一条：

```ts
{
  id: 'night',          // 英文，给展开面板当 id 用
  title: '夜里',         // 卡片上的名字
  tone: 'cyan',          // 封面光色：mag / vio / cyan / amber
  note: '凌晨的那几条街。', // 展开后的一句话
  photos: [],            // 照片，先空着也行
}
```

图片放 `public/gallery/`，再把照片写进某本相册的 `photos`：

```ts
photos: [{ src: '/gallery/night.jpg', caption: '凌晨三点的实验楼', date: '2026-11-03' }]
```

加一条相册，墙上就多一叠相纸；相册页最后那叠空相纸的「新建相册」点开就是这段写法。`photos` 导出的是所有相册照片的合集，首页的「照片」计数和内容墙读它。

### 4. `src/styles/global.css` + `extra.css`

`global.css` 顶部 `:root` 是全部设计令牌（底色、四个光谱色、字族）。`extra.css` 是新板块（首页卡片与内容墙、随记 / 小说 / 相册 / 归档 / 音乐 / 搜索 / 折叠菜单）的样式。

**整站的天色**：全站一套「黄昏到入夜」的底色，不是纯黑，也不是霓虹紫。改这一套的地方只有四处：

| 在哪 | 是什么 |
| --- | --- |
| `global.css` `:root` | `--void #050a14` / `--void2 #0a1424` / `--panel #0e1a30` 是夜色的三级；`--ink` / `--dim` / `--faint` 是三档冷白灰字；`--mag #ff6b8b`（珊瑚霞）、`--vio #7c8cf8`（暮紫蓝）、`--cyan #59d8f0`、`--amber #ffc46b`（夕照金）只当「光」用——出现在渐变字、细线、按钮和光斑上，不出现在大面积背景里。想换整站气质就只改这一段。 |
| `global.css` `body` | 固定的天色底：右上暖金、左上高空蓝、中部一层暮紫、最底一道地平线的霞，压一层 `#04070f → #091528` 的竖向渐变。`background-attachment: fixed`，滚动时天不动。 |
| `extra.css` 末尾「天色」块 | `.page:not(.arc-page)::before` 和 `.home-mast::before` 两块**只发光不铺色**的天光（客机窗那种感觉）：左边高空蓝、右边落日与霞、中间一条横云，`mask-image` 往下淡出。它们不带底色，才不会在页头下沿切出一条边。改亮度就调这几层 `radial-gradient` 的 alpha。 |
| `src/components/Orb.astro` | 首页右上那盏天光（canvas 画的四团径向渐变，`mix-blend-mode: screen`），四色和位置在文件顶部的 `COLORS` / `BLOBS`。它外面套的 `#orb` 有一层椭圆 `mask-image`（在 `global.css`），让光化开而不是被容器切一刀。 |

归档页是这套天色里唯一「整页都是天」的：`.arc-page` 自己的夜空 + 三层霞光 + 星点，河是一条 SVG 光带，配色在 `extra.css` 的 `.flow-line` 段。

页头右边那颗**齿轮**是设置入口（`.set-btn`，图标是内联 SVG 的 path，不是图标字体），点开是 `aside#sets`。

### 5. `src/pages/music/index.astro` —— 音乐页

真能播的一个播放器，不是外链面板。数据还是 `src/data/site.data.json` 的 `tracks`：

```ts
tracks: [
  { id: 64638, name: '陀飞轮', artist: '陈奕迅', dur: 278, why: '讲时间怎么把人推着走' },
  //  id  = 网易云歌曲 ID（song?id= 后面那串数字）
  //  dur = 整首的秒数，用来判断接口给的是不是残段
]
```

从上往下：

1. `.stage` 大卡：左边 `.disc` 盘（conic 四色圆环 + 挖空盘面，播放时转），右边「正在听 · 02 / 05」、曲名、歌手、那句理由，下面一行进度（当前时间 / 可点的 `.stage-bar` / 总时长 / 接口只给试听时亮一颗琥珀「试听」标）、三个键（上一首 / 中间大播放键 / 下一首），最右「网易云 ↗」直链到这首。
2. `.mtabs`：两个 tab，**歌词** 和 **曲目**。
3. `.mpanel[data-panel="lyr"]`：`.lyr` 固定 300px 高、上下用 mask 淡出，顶部一行制作人（作词 / 作曲 / 编曲 / 制作人……），下面一句一行，播到哪句哪句提亮到 17px 并自动滚到中间。歌词是真抓来的 LRC——`<api>?server=netease&type=lrc&id=`，`sound.js` 里解析（正则抽 `mm:ss.ms`，制作人行单独挑出来）。`.mpanel[data-panel="list"]`：五条曲目（编号 / 曲名 / 歌手 / 那句理由），点一条上面的大卡就换开播，当前条 `.is-on`；页脚写改法，加一条「在网易云打开歌单」。
4. 播放引擎在 `src/scripts/sound.js`，首页那张卡和这一页共用同一份：`createDeck(tracks, api)` 返回 `{ init, toggle, next, prev, pick, seek, bump, fmt, on }`，事件 `track / state / time / lyrics / line`。它建一个 `new Audio()`（`preload='none'`、音量 0.6），用 `localStorage` 的 `nepenthe:sound` 记住上次听到第几首；`ended` 自己跳下一首；`timeupdate` 里算进度和当前歌词行，只在变化时发事件。

**接口和版权**：音频走公开的 Meting 代理（`site.data.json` 的 `musicApi`，默认 `https://api.injahow.cn/meting/`），参数 `?server=netease&type=url&id=<歌曲ID>`，带 CORS，静态站直接 fetch 就能播，不用后端。但它没有登录态，**版权受限的歌只给 30–45 秒试听**——这时候大卡和首页卡上会亮那颗「试听」标（`dur + 8 < track.dur` 就判定成残段），别以为是进度条坏了。想听完整版就自己起一个 [NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi)（Vercel / 自己的服务器都行，带上你自己的 cookie），然后把 `musicApi` 换成那个地址，别的代码不用动。公共代理这条路不是长久之计，歌单变现或接口下线都可能，真要长期挂着建议换自建。

样式：`.stage` / `.mtabs` / `.lyr` 在 `extra.css` 的「音乐：上面一张大卡，下面两块面板」段；`.tracks` / `.track` 是 `global.css` 里的通用行式排版，页内把每条做成 `<button>`，额外补了 `border: 0; background: none; font: inherit` 和选中态 `.track.is-on`。

## 部署

### 方案 A：Vercel / Netlify / Cloudflare Pages（最省事）

1. 推到 GitHub。
2. 平台 Import 仓库，框架选 **Astro**：构建命令 `npm run build`，输出目录 `dist`，Node 22。
3. 绑自己的域名。

`npm run build` 已经包含 `pagefind --site dist`，搜索索引会跟着一起生成，不用额外配置。

国内访问：`*.vercel.app` 默认域名常连不上，主要读者在国内就配自己的域名。

### 方案 B：GitHub Pages

仓库带 `.github/workflows/deploy.yml`，推送后去 Settings → Pages → Source 选 **GitHub Actions**。

| 地址 | astro.config.mjs |
| --- | --- |
| 用户页 `https://用户名.github.io/` | `site: 'https://用户名.github.io'`，不要 base |
| 项目页 `https://用户名.github.io/仓库名/` | `site: '.../仓库名/'`，并加 `base: '/仓库名'` |

站内链接统一走 `src/utils/url.ts` 的 `link()`，自动带 `base` 前缀。**搜索页的 Pagefind 路径也走 `base`**，不用手改。

### 方案 C：自己的服务器 / 国内云

`npm run build` 后把整个 `dist/` 传上去。注意配好 404 页面（`dist/404.html`）。国内服务器需要域名备案。

**要访客统计就多设一个变量**：构建前给 `PUBLIC_VISIT_ENDPOINT=https://你的域名/api/hit`（或直接 `/api/hit`，同域时），后台那侧的 `/api/hit` 就会收到埋点，仪表盘上出 PV/UV 曲线、热门页面和来源。不设就不采集。站点和后端不同域时，把站点源写进后台的 `ALLOWED_ORIGINS`。口径和过滤规则见 [`server/README.md`](server/README.md#访客统计)。

流量上来之后要做的两件事都在 [`deploy/`](deploy/)：静态文件前面挂 CDN、给 `/api` 与 `/api/hit` 加 nginx 限流。配置和步骤可直接抄，包括「挂了 CDN 必须配真实 IP，否则 UV 会塌成 1」这种容易翻车的点。

## 自检脚本

```bash
npm run build
npm run preview            # 另开一个终端
node tools/shot.mjs        # 12 个页面 × 桌面/375，查横向溢出 + 截图到 .shots/
node tools/check-ui.mjs    # 搜三组词验证搜索、窄屏菜单、首页统计/联系图标/内容墙、按 / 跳搜索
```

两个脚本都只读页面，不改数据；有问题会返回非 0。

## 目录

```
src/
├─ data/
│  ├─ site.data.json     站点文案总表（后台会重写）
│  ├─ site.ts            薄壳，只 re-export 上面的 JSON
│  ├─ photos.data.json   相册数据（后台会重写）
│  └─ photos.ts          薄壳 + Photo / Album 类型
├─ content/
│  ├─ posts/             文章
│  ├─ notes/             随记
│  ├─ novels/            小说作品
│  └─ chapters/<作品>/   小说章节
├─ content.config.ts     四类内容的字段定义
├─ layouts/Base.astro    页头、页脚、字体、提示条、菜单折叠、入场、设置落地
├─ components/           Nav（含设置面板） / Orb 光球 / PostRow
├─ scripts/sound.js      播放器（首页卡和音乐页共用）
├─ pages/                各页面 + rss.xml
├─ styles/               global.css（令牌与主样式）、extra.css（新板块）
└─ utils/url.ts          带 base 前缀的站内链接
public/                  favicon、相册图片（后台传的进 public/gallery/）
server/                  后台：FastAPI + SQLAlchemy（见 server/README.md）
tools/                   本地渲染自检
.github/workflows/       GitHub Pages 部署
```

## 已知未做

- 相册还没有照片（后台「相册」页可以传）；小说两章是示例正文（`src/content/chapters/kuajie-zhufu/`），换成你自己的
- 首页四个联系方式还是空的，等你填 `contact`（后台「站点」页）
- 音乐页的音频走公共 Meting 代理，版权受限的歌只给 30–45 秒试听（界面会亮「试听」标）。要听完整版得自建 NeteaseCloudMusicApi + 自己的 cookie，再把 `musicApi` 换过去
- 后台正文有分栏实时预览和工具条，但预览的渲染器和建站时的不完全等价（脚注之类可能差一点）；上传的图不压缩、不生成缩略图
- 评论系统（要接 Giscus / Waline 得先有仓库和账号）
- 社交分享图（`og:image`）还没配
