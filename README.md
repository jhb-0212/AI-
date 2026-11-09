# 忘忧居 · Nepenthe

> 闲来无事，坐看云起。

个人博客。Astro 5 + 手写 CSS，中式水墨山水风。产物是纯静态 HTML，后台 FastAPI 管理内容。

## 特色

- **水墨山水风**：宣纸底 + 墨青/青绿配色，首屏水墨山水背景
- **全局变量**：所有颜色走 `:root` CSS 变量，一改全改
- **音乐播放器**：QQ 音乐源，动态加载歌单，不跳转
- **内容管理**：FastAPI + SQLite 后台，浏览器直接编辑文章、随记、相册、站点设置
- **站内搜索**：Pagefind 索引
- **访问统计**：PV/UV 仪表盘、热门页面、来源分析

## 页面

| 路径 | 内容 |
| --- | --- |
| `/` | 首页：水墨首屏、个人卡 + 音乐卡、内容墙 |
| `/writing/` | 文章归档 |
| `/notes/` | 随记，朋友圈样式 |
| `/gallery/` | 相册：banner + 标签栏 + 照片墙 |
| `/music/` | 音乐：完整播放器 + 歌词 + 曲目列表 |
| `/about/` | 关于我：基本信息、技能栈、兴趣爱好 |
| `/doing/` | 在做的事 |
| `/archive/` | 归档 |

## 本地跑

```bash
npm install
npm run dev        # http://localhost:4321/AI-/
npm run build      # dist/，构建后自动跑 Pagefind 建索引
```

需要 Node 22+。

## 后台（内容管理）

FastAPI + SQLAlchemy + SQLite，打开 `/admin/` 管理内容：

```powershell
cd server
python -m uvicorn app.main:app --port 8000
# 后台 http://127.0.0.1:8000/admin/
```

默认账号 `admin` / `nepenthe-admin`。

## 音乐

QQ 音乐源，动态加载歌单（id=9779561294）。代理接口带 cookie，能放完整歌曲。

## 部署

### GitHub Pages

仓库带 `.github/workflows/deploy.yml`，推送后去 Settings → Pages → Source 选 GitHub Actions。

### 自己的服务器

`npm run build` 后把 `dist/` 传上去。
