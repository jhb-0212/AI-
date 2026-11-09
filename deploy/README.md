# 上线加固：CDN + 限流 + 正确拿到访客 IP

这个目录放的是**给服务器用的**文件，跟本地开发无关：

| 文件 | 放到哪 | 干什么 |
| --- | --- | --- |
| `nginx-nepenthe.conf` | `/etc/nginx/conf.d/nepenthe.conf` | 站点静态 + `/admin` `/api` 反代 + 三档限流 |
| `nepenthe-cms.service` | `/etc/systemd/system/nepenthe-cms.service` | 后台常驻，崩了自动拉起 |

> 本机是 Windows，没有 nginx 也没装 Docker，**这两个文件没有跑过 `nginx -t`**。它们是我按官方指令语义写的，第一次上线请务必先 `sudo nginx -t` 再 reload——这一条不能省。

## 一、为什么不希望源站直接扛流量

静态站最大的优势是“谁来都只是一次文件读”。但流量一多，两个地方会先痛：

1. **静态文件**：每次访问都从这台机器的磁盘读、走它的带宽。
2. **埋点接口**：每个页面访问都 `INSERT` 一行，还可能被爬虫当靶子刷。

解决办法不是加机器，是**把静态文件挡到 CDN 边缘**，源站只在缓存没命中时回源；接口则用 nginx 的 `limit_req` 挡住脚本。这两件事做完，个人的小站基本不会再被流量打穿。

## 二、Cloudflare（或任意 CDN）怎么配

1. 域名 NS 指到 Cloudflare，开橙色云（代理模式）。
2. SSL 模式选 **Full (strict)**——源站也要有真证书（`certbot` 签就行），别用 Flexible（那会在 CF 和源站之间走明文）。
3. 缓存规则：
   - `/admin/*`、`/api/*`：**Bypass cache**（后台和写接口绝不能缓存）。
   - `/_astro/*`、`/gallery/*`、`*.woff2`、图片：**Cache everything / 长 TTL**（文件名带 hash 或图片不会变）。
   - 其余 HTML 页面：标准缓存即可（CF 默认对 HTML 不缓存，够用）。
4. 源站只允许 CF 回源（可选但推荐）：安全组里只放 CF 的 IP 段，或 nginx 里 `allow` CF 段 + `deny all`。

### 最容易被忽略的一条：真实 IP

挂了 CDN 之后，到源站的请求 `$remote_addr` 全是 CF 节点的 IP。后果有两个，都很致命：

- **访客统计的 UV 会塌成 1**（所有访问看起来来自同一个 IP，哈希相同）；
- **限流会误伤所有人**（2r/s 是按“一个 IP”算的，所有人共享这一个额度）。

所以 `nginx-nepenthe.conf` 顶部留了 `set_real_ip_from` + `real_ip_header CF-Connecting-IP` 那段，取消注释并填 CF 的官方 IP 段（列表会更新，去 <https://www.cloudflare.com/ips/> 取最新）。配好之后：

```bash
# 在源站上看日志，确认拿到的是访客真实 IP 而不是 172.x / CF 段
sudo tail -f /var/log/nginx/access.log
```

后端那边不用改：`/api/hit` 已经优先读 `X-Forwarded-For`（nginx 会填好）。

## 三、三档限流的参数怎么来的

| 分区 | 速率 | 突发 | 给谁 | 为什么是这个数 |
| --- | --- | --- | --- | --- |
| `hit` | 2r/s | 10 | `/api/hit` | 正常访客一页一条；2r/s 已经够一个急性子来回点，脚本会被挡 |
| `api` | 20r/s | 40 | `/api/*`、`/admin/*` | 后台一次操作会连发几个请求，留出余量 |
| `conn` | 20 并发 | — | 全站 | 挡“一次开几百个连接”的低成本攻击 |

`limit_req` 触发时返回 **503**，不是 429——如果你想让埋点接口在被限流时也安静地回 204，把 `location = /api/hit` 里的 `limit_req` 去掉、只留应用层那份限流（`server/app/routers/visits.py` 的 120 次/分钟）。两种都成立，区别是“挡在门口”还是“进了门再挡”。

## 四、上线步骤（从零到能访问）

```bash
# 1. 代码和依赖
sudo mkdir -p /srv/nepenthe && sudo chown $USER /srv/nepenthe
git clone <你的仓库> /srv/nepenthe
cd /srv/nepenthe && npm ci && npm run build          # 需要 node，产物在 dist/
python3 -m venv server/.venv && server/.venv/bin/pip install -r server/requirements.txt

# 2. 后台配置（口令、域名、cookie、埋点开关都在这里）
sudo tee /etc/nepenthe.env > /dev/null <<'EOF'
ADMIN_PASSWORD=换成强口令
PUBLIC_SITE_URL=https://blog.example.com
ADMIN_PUBLIC_URL=https://blog.example.com/admin/
COOKIE_SECURE=1
# 站点和后端同域时不用设 ALLOWED_ORIGINS
EOF
sudo chmod 600 /etc/nepenthe.env

# 3. 常驻 + 反代
sudo cp deploy/nepenthe-cms.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now nepenthe-cms
sudo cp deploy/nginx-nepenthe.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx

# 4. 证书
sudo certbot --nginx -d blog.example.com

# 5. 埋点开关：站点构建时给这个变量（同域就写 /api/hit）
PUBLIC_VISIT_ENDPOINT=/api/hit npm run build
```

改完内容后点后台「发布」即可——它在这台机器上跑 `npm run build`，产物直接落到 `/srv/nepenthe/dist`，nginx 立刻就是新的。

## 五、验证（别只看“页面能打开”）

```bash
# 404 是 404，不是 200 壳页
curl -o /dev/null -s -w '%{http_code}\n' https://blog.example.com/no-such-page/

# 埋点只收 POST
curl -o /dev/null -s -w '%{http_code}\n' https://blog.example.com/api/hit          # 405/403
curl -X POST -d '{"path":"/x/"}' -H 'content-type: text/plain' \
     -A 'Mozilla/5.0 Chrome/140' https://blog.example.com/api/hit                  # 204

# 后台没登录是 401
curl -o /dev/null -s -w '%{http_code}\n' https://blog.example.com/api/visits

# 限流真的生效（连打 40 次，应该出现 503）
for i in $(seq 40); do curl -o /dev/null -s -w '%{http_code} ' -X POST -d '{"path":"/"}' \
  -H 'content-type: text/plain' -A 'Mozilla/5.0 Chrome/140' https://blog.example.com/api/hit; done; echo

# 压一下静态页，看源站扛不扛（hey 需要先装：apt install hey）
hey -n 500 -c 20 https://blog.example.com/
```

最后一件事：**CDN 起来之后，访问日志里的 IP 应该还是访客的真实 IP**。如果日志里全是 `172.68.x.x`（CF 段），说明第二节的 `set_real_ip_from` 没生效，先别上线，否则 UV 数据是错的。
