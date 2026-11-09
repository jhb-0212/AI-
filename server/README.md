# 忘忧居 · 后台（内容管理系统）

一个 FastAPI 写的内容后台：文章、随记、小说与章节、相册与照片、音乐曲目、站点文案、首页「在做的事」，全部在这里改。

关键设计一句话：**数据库是编辑时的唯一数据源，点「发布」才把库内容渲染成仓库里的 markdown / JSON，再触发一次 `npm run build`。**
所以线上站点始终是纯静态文件——后台挂了、数据库坏了，已经发布的页面照常打开。

```
浏览器 ──> /admin/（原生 JS 后台）
              │  CRUD（cookie 鉴权，JSON / multipart）
              ▼
          FastAPI + SQLAlchemy ──> SQLite（可换 PostgreSQL）
              │  点「发布」
              ▼
   render.py 写 src/content/**/*.md + src/data/*.json
              ▼
   builder.py 跑 npm run build（astro build && pagefind --site dist）
              ▼
              dist/  ← 纯静态，随便挪到哪台机器上托管
```

## 跑起来

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

- 后台界面：<http://127.0.0.1:8100/admin/>
- 接口文档（自动生成）：<http://127.0.0.1:8100/docs>
- 健康检查：<http://127.0.0.1:8100/api/health>

首次启动做三件事：建表、建管理员、把仓库里现有的 markdown 灌进库（`seed.py`，只在对应的表为空时才导，不会覆盖你后来在后台改的内容）。

默认账号 `admin` / `nepenthe-admin`。**上线前必须换成自己的**，见下面的环境变量。

> 端口用 8100 是因为本机 8000 被别的项目占着；换端口只改启动参数。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///server/data/nepenthe.db` | 换 PostgreSQL 填 `postgresql+psycopg://user:pass@host/db` |
| `ADMIN_USERNAME` | `admin` | 管理员账号 |
| `ADMIN_PASSWORD` | 无（必填） | 管理员口令，**必须显式设置**，未设置或仍为默认值会拒绝启动 |
| `SECRET_KEY` | 自动生成到 `server/data/.secret` | JWT 签名密钥，多机部署要显式设成同一个 |
| `TOKEN_TTL_MINUTES` | `720` | 登录有效期（12 小时） |
| `BUILD_TIMEOUT` | `300` | 单次构建的秒数上限 |
| `SITE_PREVIEW_URL` | `http://127.0.0.1:4321` | 后台里「去站点看看」的本地预览地址 |
| `PUBLIC_SITE_URL` | 同上 | 上线后的站点域名 |
| `ADMIN_PUBLIC_URL` | `http://127.0.0.1:8100` | 上线后的后台地址 |
| `COOKIE_SECURE` | `0` | 走 HTTPS 时设 `1`，登录 cookie 只走加密连接 |
| `ALLOWED_ORIGINS` | 空 | 前后端分域部署才需要，逗号分隔；同域留空 |
| `TRUST_PROXY` | `0` | 是否信任反向代理的 `X-Forwarded-For`；只有后台确定只被可信 nginx 访问时才设 `1` |
| `NETEASE_COOKIE` | 空 | 网易云音乐登录 Cookie，填了能放完整歌曲，不填只有 30–45 秒试听 |
| `TENCENT_COOKIE` | 空 | QQ 音乐登录 Cookie，填了能放完整歌曲；不填只能放无版权限制歌曲的试听 |
| `BACKUP_DIR` | 空 | 数据库备份的异地目录（挂载云盘/另一块盘），填了每天备份同时写一份过去 |
| `BACKUP_REMOTE_KEEP_DAYS` | `30` | 异地备份保留天数（本地固定 7 天） |

## 目录

```
server/
├─ app/
│  ├─ config.py      路径、数据库地址、凭据、各种开关（全部吃环境变量）
│  ├─ db.py          engine / SessionLocal / Base / get_db
│  ├─ models.py      10 张表
│  ├─ security.py    bcrypt 口令 + JWT（cookie 优先，也认 Bearer）
│  ├─ schemas.py     Pydantic v2 的入参 / 出参
│  ├─ render.py      库 -> 仓库文件（这一层的正确性最要紧）
│  ├─ builder.py     后台线程跑构建、记状态、可选 git commit
│  ├─ seed.py        把现有 markdown 导进空库
│  ├─ main.py        装配：lifespan、路由、静态挂载
│  └─ routers/       auth / content / novels / albums / site / publish
├─ static/           后台界面（index.html + admin.css + admin.js，原生 JS，不打包）
│  └─ vendor/        marked.min.js（MIT，只用来给正文做实时预览，不走 CDN）
├─ tests/            pytest：接口 + 仪表盘数据 22 条
└─ data/             数据库、签名密钥、渲染清单、发布历史（都不进 git）
```

## 数据模型

| 表 | 对应仓库里的 | 备注 |
| --- | --- | --- |
| `AdminUser` | — | bcrypt 哈希，明文不落库 |
| `Post` | `src/content/posts/<slug>.md` | 正文存库 |
| `Note` | `src/content/notes/<slug>.md` | 一句话，`tag` 可空 |
| `Novel` | `src/content/novels/<slug>.md` | 带 `body`（现有作品 frontmatter 后面确实有正文，不存就丢） |
| `Chapter` | `src/content/chapters/<作品>/<slug>.md` | 改作品 slug 时章节的 `novel_slug` 一起改 |
| `Album` / `Photo` | `src/data/photos.data.json` + `public/gallery/` | 照片文件在磁盘，库里存相对路径 |
| `Track` | `src/data/site.data.json` 的 `tracks` | 存网易云歌曲 ID |
| `Doing` | `src/data/site.data.json` 的 `doing` | 首页「在做的事」 |
| `Setting` | `src/data/site.data.json` 其余字段 | `key='site'` 一行存整块 JSON |
| `Visit` | — | 访客埋点，只存加盐哈希，不存 IP |

## 发布做了什么

`POST /api/publish` 返回 202，然后后台线程里两步：

1. **渲染**：`render_all(db)` 把库内容写成文件。frontmatter 字段严格对齐 `src/content.config.ts`；行尾统一 LF；`draft` 只在为真时写（普通稿不写 `draft: false`，diff 干净）；`date` 用 `datetime.date` 让 YAML 输出不带引号。
2. **构建**：`npm run build`（Astro 出 16 个页面 + Pagefind 建索引），正则捞页数和耗时，状态进 `GET /api/publish/status`，后台每 900ms 轮一次。

两个细节值得说：

- **增量删除**：`server/data/generated.json` 记着「上次生成了哪些文件」。这次没生成、上次生成过的会被删掉；**从没被后台管过的手写 md 不会被误删**（有测试守着）。
- **防并发**：`builder.is_running()` 挡住第二次发布，避免两个 `npm run build` 抢同一个 `dist/`。
- **草稿**：`draft=True` 的稿子照样写进仓库（`content.config.ts` 里本来就有 `draft` 字段），但列表、RSS 和单页生成都会跳过它，所以也不会进搜索索引。

「发布」默认不 `git commit`；勾上「发布后提交」才会 `git add -A && git commit`（`nothing to commit` 当成功处理）。

每跑完一次构建，`builder` 会把「什么时候发的、成功没有、几页、多久」追加到 `server/data/build-history.json`（最多留 10 条），仪表盘的「发布历史」读的就是它。这个文件丢了只是历史空白，不影响发布；进程重启后历史还在。

## 访客统计

站点那侧一段小脚本（`src/scripts/visit.js`，构建时内联进每页），页面打开 800ms 后往 `POST /api/hit` 打一条，`text/plain` 的 JSON、走 `sendBeacon`，不挡首屏也不触发跨域预检。同一天同一路径只发一次（`localStorage` 记账），关掉 JS 的访问统计不到。

入库前先过滤：

- UA 命中 `bot|spider|crawl|scraper|curl|wget|python-requests|headless|monitor|preview|lighthouse` 的直接丢（无头浏览器也在内）；
- `/admin`、`/api`、`/gallery`、`/pagefind`、`/_astro` 和静态资源不记；
- 来源不在白名单的请求回 403（白名单 = `ALLOWED_ORIGINS` + `PUBLIC_SITE_URL` + `ADMIN_PUBLIC_URL` 的源）；
- 同一 IP 每分钟超过 120 条回 429，避免它被当成写库接口刷。

口径（面试会被问，写清楚）：

- **PV** 是每一次打开，同一个人看两遍算 2。
- **UV** 按 `sha256(IP + UA + 当天盐)` 的前 16 位去重，盐每天换，所以跨天不可关联；「近 7 日 UV」是这七天各自人数的和，不是七天内去重后的人数。
- **原始 IP 不入库、不进日志**，表里只有那个哈希、路径、referrer 主机名和 UA 家族（自己用正则粗分，不引 device-detector）。

站点侧只有一项配置：构建时给

```text
PUBLIC_VISIT_ENDPOINT=https://你的域名/api/hit
```

留空就不采集（本地 `npm run build` / preview 不会往 127.0.0.1 打空请求）。站点和后端不同域时，把站点源加进 `ALLOWED_ORIGINS`，其余不用改。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 口令错与用户不存在都回同一句，不透露账号是否存在 |
| POST | `/api/auth/logout` | 清 cookie |
| GET | `/api/auth/me` | 当前登录者 |
| GET/POST | `/api/posts` | 列表 / 新建（201） |
| PUT/DELETE | `/api/posts/{id}` | 改 / 删（204） |
| GET/POST | `/api/notes`、`/api/notes/{id}` | 同上 |
| GET/POST | `/api/novels`、`/api/novels/{id}` | 作品 |
| GET/POST | `/api/novels/{slug}/chapters` | 章节列表 / 新建 |
| PUT/DELETE | `/api/novels/{slug}/chapters/{id}` | 章节改 / 删 |
| GET/POST | `/api/albums`、`/api/albums/{id}` | 相册 |
| POST | `/api/albums/{slug}/photos` | multipart 上传（jpg/png/webp/gif/avif，≤12MB） |
| PATCH/DELETE | `/api/photos/{id}` | 改说明 / 删（连文件一起删） |
| GET/PUT | `/api/site` | 站点文案整块读写 |
| GET/POST | `/api/site/tracks`、`/api/site/tracks/{id}` | 曲目 |
| GET/POST | `/api/site/doing`、`/api/site/doing/{id}` | 在做的事 |
| POST | `/api/publish` | 渲染 + 构建（202） |
| GET | `/api/publish/status` | 状态、页数、耗时、日志 |
| GET | `/api/publish/preview` | 站点 / 后台链接 |
| GET | `/api/stats` | 各类计数、草稿数、最近更新、草稿清单、标签分布、发布历史、最近一次构建 |
| POST | `/api/hit` | 访客埋点（公开，永远 204；bot / 后台路径 / 非白名单来源直接丢） |
| GET | `/api/visits` | 访客聚合：30 天 PV·UV 序列、今日、7/30 日 UV、热门页、来源、UA 家族 |

内容类接口全部挂 `Depends(current_user)`；slug 规则 `^[a-z0-9][a-z0-9-]{0,118}$`，撞了回 409。

## 测试

```powershell
cd server
.\.venv\Scripts\python.exe -m pytest -q
```

29 条：健康检查、未登录 401、错口令、登录后 me、灌数据校验、文章 CRUD + slug 冲突 409、slug 非法 400、作品 + 章节（含改 slug 同步章节）、相册 + 曲目、非图片文件被拒、渲染层四类（frontmatter 往返、`tag` 可空、冗余删除但手写稿保留、`site.data.json` 形状、字段与 `content.config.ts` 对齐）、仪表盘数据五条（stats 字段、排序、草稿过滤、构建历史滚动与落盘）、访客七条（入库、PV/UV 口径、query 与静态资源过滤、bot 与后台路径丢弃、来源与浏览器聚合、聚合接口要登录、30 天序列补齐）。

测试用临时数据库和临时目录，**不会碰真仓库**。

## 换 PostgreSQL

SQLAlchemy 同一套 ORM，只改环境变量：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://nepenthe:pass@127.0.0.1:5432/nepenthe"
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]"
```

首次启动会自动建表；从 SQLite 迁数据就 `seed_if_empty` 从 markdown 重建一遍，然后补后台里改过的内容。

## 上线

后台和站点可以在一台机器上，也可以分开。同一个域、nginx 反代最省事。完整配置在 [`deploy/nginx-nepenthe.conf`](../deploy/nginx-nepenthe.conf)：静态出站 + `/admin`、`/api`、`/gallery` 反代 + 三档限流（埋点 2r/s、接口 20r/s、单 IP 20 并发）+ 404 保持真 404。上手步骤、CDN 设置和验证命令在 [`deploy/README.md`](../deploy/README.md)，常驻服务用 [`deploy/nepenthe-cms.service`](../deploy/nepenthe-cms.service)。

两条最容易翻车的：

- **挂了 CDN 不配真实 IP**：`$remote_addr` 会全是 CDN 节点的地址，访客 UV 直接塌成 1，`limit_req` 也会把所有人当成同一个 IP 误伤。要 `set_real_ip_from <CDN 段>` + `real_ip_header CF-Connecting-IP`。
- **404 写成 200**：`try_files $uri $uri/ /404.html` 会返回 200 的 404 页；用 `try_files $uri $uri/ =404` 配 `error_page 404 /404.html`。

SQLite 下 uvicorn 只开 `--workers 1`（多进程会抢写锁），换 PostgreSQL 之后再开多 worker。

配套的环境变量：

```powershell
$env:ADMIN_PASSWORD = "换成强口令"
$env:PUBLIC_SITE_URL = "https://blog.example.com"
$env:ADMIN_PUBLIC_URL = "https://blog.example.com/admin/"
$env:COOKIE_SECURE = "1"
```

上线前还得把 `astro.config.mjs` 里的 `site` 换成真域名（`sitemap` / `rss` 里的绝对地址靠它）。

> 发布动作要在**仓库所在的机器**上跑（`npm run build` 需要 node_modules），所以后台一般和站点同机；纯静态产物可以再同步到 CDN / 对象存储。

## 安全上的取舍

- 口令 bcrypt 哈希，比较前按 72 字节截断（bcrypt 的硬限制，不截会静默报错）。
- 登录发 HttpOnly + SameSite=Lax 的 cookie；HTTPS 下开 `Secure`。同时认 `Authorization: Bearer`，方便以后接前端框架或写脚本。
- 上传只收图片后缀 + 12MB 上限，文件名用 `uuid4` 重命名，不保留原文件名（避免路径穿越和重名覆盖）。
- 默认不开 CORS；同域部署就够了，跨域才设 `ALLOWED_ORIGINS`。
- 后台不提供注册、改密码接口——账号走环境变量，只可能有一个管理员。

## 已知限制

- 预览用本地 vendored 的 marked（MIT，`server/static/vendor/marked.min.js`），渲染结果和 Astro 建站时的渲染器不完全等价：脚注、标题编号这类细节可能差一点。
- 上传不压缩、不生成缩略图（原图直进 `public/gallery/`）。
- 只有单管理员、没有多用户与角色。
- 构建是同步占满一次 `npm run build`，构建中再点发布会被告知等一等；没有任务队列。
- `site.data.json` 由后台整块重写，所以它现在的排版是机器生成的（首次发布会看到一次格式化 diff，之后就稳定了）。
