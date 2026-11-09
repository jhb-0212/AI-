/* 忘忧居后台：一个不打包的原生 JS 单页。
   没有框架，是因为它只要做一件事——把表单变成接口调用。
   坏处是要手写渲染；好处是打开就能改，不用装 node_modules。 */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

const today = () => new Date().toISOString().slice(0, 10);

async function api(path, opts = {}) {
  const init = { credentials: 'same-origin', ...opts };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = { 'content-type': 'application/json', ...(init.headers || {}) };
    if (typeof init.body !== 'string') init.body = JSON.stringify(init.body);
  }
  const res = await fetch('/api' + path, init);
  if (res.status === 401) {
    showLogin();
    throw new Error('未登录');
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || `请求失败（${res.status}）`);
  return data;
}

let toastTimer = null;
function toast(msg, bad = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast on' + (bad ? ' bad' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = 'toast'), 2600);
}

/* ---------------- Markdown 编辑器 ----------------
   正文三处（文章 / 作品开场白 / 章节）共用这套：左边写、右边实时渲染，
   上面一排按钮插语法，另外能切成「只写」和「只看预览」。
   渲染用本地 vendor/marked.min.js（MIT），不走 CDN，离线也能用。 */

/** 生成一整块带预览的正文输入区。value 已经过 esc()。 */
function mdField(labelText, value, rows = 18, placeholder = '') {
  const tools = [
    ['h2', 'H2', '二级标题'],
    ['h3', 'H3', '三级标题'],
    ['bold', 'B', '加粗'],
    ['italic', 'I', '斜体'],
    ['code', '</>', '行内代码'],
    ['quote', '“', '引用'],
    ['ul', '•', '无序列表'],
    ['ol', '1.', '有序列表'],
    ['link', '链接', '链接'],
    ['image', '图', '图片'],
    ['hr', '—', '分隔线'],
  ];
  return `
    <div class="md-field">
      <div class="md-bar">
        <span class="md-label">${labelText}</span>
        <div class="md-views" role="group" aria-label="编辑视图">
          <button type="button" data-md-view="write">写</button>
          <button type="button" data-md-view="split" aria-pressed="true">分栏</button>
          <button type="button" data-md-view="preview">预览</button>
        </div>
      </div>
      <div class="md-tools" role="toolbar" aria-label="插入 Markdown 语法">
        ${tools
          .map(
            ([act, text, title]) =>
              `<button type="button" data-md-act="${act}" title="${title}" aria-label="${title}">${text}</button>`
          )
          .join('')}
      </div>
      <div class="md-panes" data-md-view="split">
        <textarea id="f-body" class="mono" rows="${rows}" placeholder="${placeholder}">${value}</textarea>
        <div class="md-preview" role="region" aria-label="正文预览"></div>
      </div>
    </div>`;
}

/** 预览里只留安全的节点：脚本、样式、iframe 这类直接扔，on* 属性和 javascript: 也去掉。 */
function mdSanitize(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  tpl.content.querySelectorAll('script, style, iframe, object, embed, link, meta, base').forEach((n) => n.remove());
  tpl.content.querySelectorAll('*').forEach((el) => {
    Array.from(el.attributes).forEach((a) => {
      const name = a.name.toLowerCase();
      const val = a.value.trim().toLowerCase();
      if (name.startsWith('on')) el.removeAttribute(a.name);
      else if ((name === 'href' || name === 'src' || name === 'srcset') && val.startsWith('javascript:'))
        el.removeAttribute(a.name);
    });
  });
  return tpl.innerHTML;
}

/** 在 textarea 当前位置插入一段文本，并给出新的选区。 */
function mdInsert(ta, before, after = '', fallback = '') {
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const sel = ta.value.slice(start, end) || fallback;
  const text = before + sel + after;
  ta.setRangeText(text, start, end, 'end');
  const caret = start + before.length;
  ta.setSelectionRange(caret, caret + sel.length);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  ta.focus();
}

/** 按行加前缀；选中的行都已经带这个前缀时改成去掉（当开关用）。 */
function mdPrefixLines(ta, prefix) {
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const head = ta.value.lastIndexOf('\n', start - 1) + 1;
  let tail = ta.value.indexOf('\n', end);
  if (tail === -1) tail = ta.value.length;
  const block = ta.value.slice(head, tail);
  const lines = block.split('\n');
  const allPrefixed = lines.every((l) => !l.trim() || l.startsWith(prefix));
  const next = lines
    .map((l) => {
      if (!l.trim()) return l;
      if (allPrefixed) return l.slice(prefix.length);
      return prefix + l;
    })
    .join('\n');
  ta.setRangeText(next, head, tail, 'end');
  ta.setSelectionRange(head, head + next.length);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  ta.focus();
}

function mdApply(ta, act) {
  switch (act) {
    case 'h2':
      return mdPrefixLines(ta, '## ');
    case 'h3':
      return mdPrefixLines(ta, '### ');
    case 'bold':
      return mdInsert(ta, '**', '**', '加粗文字');
    case 'italic':
      return mdInsert(ta, '*', '*', '斜体文字');
    case 'code':
      return mdInsert(ta, '`', '`', 'code');
    case 'quote':
      return mdPrefixLines(ta, '> ');
    case 'ul':
      return mdPrefixLines(ta, '- ');
    case 'ol':
      return mdPrefixLines(ta, '1. ');
    case 'link':
      return mdInsert(ta, '[', '](https://example.com)', '链接文字');
    case 'image':
      // 图片上传：弹文件选择框，选好后上传再插入 Markdown
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = 'image/*';
      fileInput.onchange = async () => {
        if (!fileInput.files.length) return;
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        toast('上传中...');
        try {
          const res = await api('/upload-image', { method: 'POST', body: fd });
          mdInsert(ta, '![', `](${res.url})`, '图片说明');
          toast('图片上传成功');
        } catch (e) {
          toast('上传失败：' + (e.message || '未知错误'), true);
        }
      };
      fileInput.click();
      return;
    case 'hr':
      return mdInsert(ta, '\n\n---\n\n');
  }
}

/** 把页面上所有 .md-field 接上逻辑：预览、工具条、视图切换、滚动同步。 */
function mountMarkdown(scope = document) {
  $$('.md-field', scope).forEach((field) => {
    const ta = $('#f-body', field);
    const panes = $('.md-panes', field);
    const preview = $('.md-preview', field);
    if (!ta || !panes || !preview || ta.dataset.mdMounted) return;
    ta.dataset.mdMounted = '1';

    let timer = null;
    const paint = () => {
      const src = ta.value.trim();
      if (!src) {
        preview.innerHTML = '<p class="md-empty">正文还空着。左边写完，这里会按站点的排版显示。</p>';
        return;
      }
      try {
        preview.innerHTML = mdSanitize(marked.parse(src, { gfm: true, breaks: false }));
      } catch (err) {
        preview.innerHTML = `<p class="md-empty">渲染失败：${esc(err.message)}</p>`;
      }
    };
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(paint, 120);
    };

    ta.addEventListener('input', schedule);
    paint();

    // 滚动同步：只按比例，不追求逐行对齐
    let lock = false;
    ta.addEventListener('scroll', () => {
      if (lock || panes.dataset.mdView !== 'split') return;
      lock = true;
      const max = preview.scrollHeight - preview.clientHeight;
      const ratio = ta.scrollTop / Math.max(1, ta.scrollHeight - ta.clientHeight);
      preview.scrollTop = Math.max(0, Math.round(ratio * max));
      lock = false;
    });

    $$('[data-md-act]', field).forEach((btn) =>
      btn.addEventListener('click', () => mdApply(ta, btn.dataset.mdAct))
    );

    $$('[data-md-view]', field).forEach((btn) =>
      btn.addEventListener('click', () => {
        const view = btn.dataset.mdView;
        panes.dataset.mdView = view;
        $$('.md-views button', field).forEach((b) => {
          if (b.dataset.mdView === view) b.setAttribute('aria-pressed', 'true');
          else b.removeAttribute('aria-pressed');
        });
        paint();
      })
    );

    // Ctrl/Cmd+B、I 这几个最常用的顺手键，别拿它们当快捷键冲突区
    ta.addEventListener('keydown', (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === 'b') {
        e.preventDefault();
        mdApply(ta, 'bold');
      } else if (k === 'i') {
        e.preventDefault();
        mdApply(ta, 'italic');
      }
    });
  });
}

/* ---------------- 登录 ---------------- */

function showLogin() {
  $('#app').hidden = true;
  $('#login-view').hidden = false;
}

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await api('/auth/login', {
      method: 'POST',
      body: { username: $('#login-user').value.trim(), password: $('#login-pass').value },
    });
    await boot();
  } catch (err) {
    toast(err.message, true);
  }
});

$('#logout').addEventListener('click', async () => {
  await api('/auth/logout', { method: 'POST' });
  showLogin();
});

/* ---------------- 导航 ---------------- */

const TABS = [
  { id: 'overview', label: '仪表盘' },
  { id: 'posts', label: '文章' },
  { id: 'notes', label: '随记' },
  { id: 'novels', label: '小说' },
  { id: 'albums', label: '相册' },
  { id: 'music', label: '音乐' },
  { id: 'site', label: '站点' },
  { id: 'publish', label: '发布' },
];

let current = 'overview';
let buildTimer = null;

function renderNav(counts = {}) {
  $('#nav').innerHTML = TABS.map(
    (t) => `<button class="nav-item" data-tab="${t.id}" aria-current="${t.id === current}">
      <span>${t.label}</span><span class="n">${counts[t.id] ?? ''}</span>
    </button>`,
  ).join('');
  $$('#nav .nav-item').forEach((btn) =>
    btn.addEventListener('click', () => {
      current = btn.dataset.tab;
      renderNav(counts);
      render();
    }),
  );
}

async function refreshCounts() {
  try {
    const s = await api('/stats');
    renderNav({ posts: s.posts, notes: s.notes, novels: s.novels, albums: s.albums, music: s.tracks });
    setPill(s.build);
    $('#site-link').href = s.urls.site;
  } catch {
    /* 概览页自己会报 */
  }
}

/* ---------------- 构建状态 ---------------- */

function setPill(build) {
  const pill = $('#build-pill');
  const label = { idle: '未构建', running: '构建中', ok: '上次成功', failed: '上次失败' }[build.state];
  pill.className = 'pill ' + { ok: 'ok', failed: 'bad', running: 'run' }[build.state];
  pill.querySelector('span').textContent =
    build.state === 'ok' && build.duration_ms ? `${label} · ${build.duration_ms} ms` : label;
}

function watchBuild() {
  clearInterval(buildTimer);
  const tick = async () => {
    try {
      const b = await api('/publish/status');
      setPill(b);
      if (b.state !== 'running') {
        clearInterval(buildTimer);
        if (current === 'publish' || current === 'overview') render();
      }
    } catch {
      clearInterval(buildTimer);
    }
  };
  buildTimer = setInterval(tick, 900);
  tick();
}

/* ---------------- 视图 ---------------- */

async function render() {
  const view = $('#view');
  $('#view-title').textContent = TABS.find((t) => t.id === current).label;
  view.innerHTML = '<div class="empty">加载中…</div>';
  try {
    const map = {
      overview: viewOverview,
      posts: viewPosts,
      notes: viewNotes,
      novels: viewNovels,
      albums: viewAlbums,
      music: viewMusic,
      site: viewSite,
      publish: viewPublish,
    };
    await map[current](view);
  } catch (err) {
    view.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
  }
}

/* ---------- 仪表盘 ---------- */

const JUMP = { 文章: 'posts', 随记: 'notes', 章节: 'novels', 作品: 'novels' };

function durText(ms) {
  if (ms === null || ms === undefined) return '—';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/* 30 天趋势：PV 画成面积，UV 叠一条折线。
   viewBox 固定、靠 preserveAspectRatio="none" 拉宽，所以里面不放文字（会被拉扁），
   轴上的字放在外面的 HTML 里。vector-effect 让线宽不被横向拉伸。 */
function svgTrend(series) {
  const W = 960;
  const H = 168;
  const PAD = 6;
  const max = Math.max(1, ...series.map((p) => p.pv), ...series.map((p) => p.uv));
  const x = (i) => (series.length <= 1 ? PAD : (i / (series.length - 1)) * (W - PAD * 2) + PAD);
  const y = (n) => H - PAD - (n / max) * (H - PAD * 2);
  const pts = (key) => series.map((p, i) => `${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`);

  const pvPts = pts('pv');
  const uvPts = pts('uv');
  const areaPath = `M${x(0).toFixed(1)},${H - PAD} L${pvPts.join(' L')} L${x(series.length - 1).toFixed(1)},${H - PAD} Z`;

  return `<svg class="trend" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
      aria-label="近 ${series.length} 天 PV 与 UV 走势">
      <line class="tr-base" x1="0" y1="${H - PAD}" x2="${W}" y2="${H - PAD}" />
      <path class="tr-area" d="${areaPath}" />
      <polyline class="tr-uv" points="${uvPts.join(' ')}" />
    </svg>`;
}

async function viewOverview(el) {
  const s = await api('/stats');
  const v = await api('/visits').catch(() => null);
  setPill(s.build);

  const cards = [
    ['文章', s.posts, 'src/content/posts'],
    ['随记', s.notes, 'src/content/notes'],
    ['小说 / 章节', `${s.novels} / ${s.chapters}`, 'src/content/novels'],
    ['相册 / 照片', `${s.albums} / ${s.photos}`, 'photos.data.json'],
    ['曲目', s.tracks, 'site.data.json'],
    ['草稿', s.drafts, s.drafts ? '还没发布' : '全部已发'],
  ]
    .map(
      ([k, v, sub]) =>
        `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub}</div></div>`,
    )
    .join('');

  const recent = s.recent.length
    ? s.recent
        .map(
          (x) => `<button class="dash-row" data-jump="${JUMP[x.kind] || 'overview'}">
            <span class="badge">${x.kind}</span>
            <span class="t">${esc(x.title)}</span>
            <span class="m">${esc(x.date)}${x.draft ? ' · 草稿' : ''}</span>
          </button>`,
        )
        .join('')
    : '<p class="empty">还没有内容，去「文章」写第一篇。</p>';

  const draftRows = s.draft_items.length
    ? s.draft_items
        .map(
          (x) => `<button class="dash-row" data-jump="${JUMP[x.kind] || 'overview'}">
            <span class="badge draft">${x.kind}</span>
            <span class="t">${esc(x.title)}</span>
            <span class="m">${esc(x.date)}</span>
          </button>`,
        )
        .join('')
    : '<p class="empty">没有草稿。写完直接发就行。</p>';

  const postTotal = s.posts || 1;
  const tagRows = s.tags.length
    ? s.tags
        .map(
          ([name, n]) => `<div class="bar-row">
            <span class="bar-k">${esc(name)}</span>
            <span class="bar"><i style="width:${Math.round((n / postTotal) * 100)}%"></i></span>
            <span class="bar-n">${n}</span>
          </div>`,
        )
        .join('')
    : '<p class="empty">文章还没打标签。</p>';

  const builds = s.builds.length    ? s.builds
        .map(
          (b) => `<tr>
            <td><span class="m">${esc(b.finished_at || '—')}</span></td>
            <td><span class="badge ${b.state === 'ok' ? 'ok' : 'bad'}">${b.state === 'ok' ? '成功' : '失败'}</span></td>
            <td>${b.pages ? b.pages + ' 页' : '—'}</td>
            <td>${durText(b.duration_ms)}</td>
            <td>${b.git ? '已提交' : '—'}</td>
          </tr>`,
        )
        .join('')
    : '<tr><td colspan="5" class="empty">还没有发布记录。</td></tr>';

  /* 访客：PV 面积 + UV 折线。不引图表库，够了——只有一条轴、两条线。 */
  let visitPanel = '';
  if (v) {
    const nums = [
      ['今日 PV', v.today.pv],
      ['今日 UV', v.today.uv],
      ['近 7 日 UV', v.uv7],
      ['近 30 日 UV', v.uv30],
    ]
      .map(([k, n]) => `<div class="vs"><span class="k">${k}</span><span class="v">${n}</span></div>`)
      .join('');

    const list = (items, key) =>
      items.length
        ? items
            .map(
              (x) => `<div class="vl-row"><span class="vl-k">${esc(x[key])}</span><span class="vl-n">${x.pv}</span></div>`,
            )
            .join('')
        : '<p class="empty">还没有数据。</p>';

    visitPanel = `
      <div class="panel">
        <div class="panel-head">
          <span>访客</span>
          <span class="tip">近 ${v.days} 天 · 累计 ${v.pv_total} 次浏览</span>
        </div>
        <div class="visit-stats">${nums}</div>
        ${svgTrend(v.series)}
        <div class="trend-ax">
          <span>${esc(v.series[0].day)}</span>
          <span class="legend"><i class="lg-pv"></i>PV 面积<i class="lg-uv"></i>UV 折线</span>
          <span>${esc(v.series[v.series.length - 1].day)}</span>
        </div>
        <div class="visit-lists">
          <div>
            <div class="vl-head">热门页面</div>
            ${list(v.top_pages, 'path')}
          </div>
          <div>
            <div class="vl-head">来源</div>
            ${list(v.top_refs, 'ref')}
          </div>
          <div>
            <div class="vl-head">设备 / 浏览器</div>
            ${list(v.browsers, 'ua')}
          </div>
        </div>
        <p class="tip" style="margin-top:10px">
          PV 是每一次打开；UV 按「IP + UA + 当天盐」的哈希去重，盐每天换，所以跨天不可关联，
          近 7 日 UV 是这七天各自人数的和。原始 IP 不入库。
        </p>
      </div>`;
  }

  el.innerHTML = `<div class="grid dash-cards" style="margin-bottom:16px">${cards}</div>
    <div class="dash-cols">
      <div class="panel">
        <div class="panel-head"><span>最近更新</span><span class="tip">按日期，点一条去那边改</span></div>
        <div class="dash-list">${recent}</div>
      </div>
      <div class="panel">
        <div class="panel-head"><span>还没发出去的草稿</span><span>${s.drafts} 条</span></div>
        <div class="dash-list">${draftRows}</div>
      </div>
    </div>
    <div class="dash-cols">
      <div class="panel">
        <div class="panel-head"><span>标签分布</span><span class="tip">文章</span></div>
        <div class="dash-list">${tagRows}</div>
      </div>
      <div class="panel">
        <div class="panel-head"><span>发布历史</span><span class="tip">最近 ${s.builds.length} 次</span></div>
        <div class="mini-wrap">
          <table class="mini">
            <thead><tr><th>时间</th><th>结果</th><th>页数</th><th>耗时</th><th>git</th></tr></thead>
            <tbody>${builds}</tbody>
          </table>
        </div>
      </div>
    </div>
    ${visitPanel}
    <div class="panel">
      <div class="panel-head"><span>最近一次构建日志</span><span>${esc(s.build.state)}</span></div>
      <pre class="log">${esc(s.build.log || '还没有构建记录。点右上角「保存并发布」。')}</pre>
    </div>
    <p class="tip" style="margin-top:14px">
      内容存在 SQLite（server/data/nepenthe.db），点发布才写进仓库的 markdown / JSON 并重建静态站。
      站点可以随时单独部署，后台挂了不影响已经发布的页面。
    </p>`;

  $$('[data-jump]', el).forEach((b) =>
    b.addEventListener('click', () => {
      current = b.dataset.jump;
      render();
    }),
  );
}

/* ---------- 文章 ---------- */

async function viewPosts(el) {
  const posts = await api('/posts');
  el.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <span>共 ${posts.length} 篇</span>
        <button class="btn sm primary" id="new-post">新建文章</button>
      </div>
      <table>
        <thead><tr><th>标题</th><th>日期</th><th>标签</th><th>slug</th><th></th></tr></thead>
        <tbody>
          ${
            posts.length
              ? posts
                  .map(
                    (p) => `<tr>
            <td><span class="t">${esc(p.title)}</span><span class="m">${esc(p.summary)}</span></td>
            <td>${p.date}${p.draft ? ' <span class="badge draft">草稿</span>' : ''}</td>
            <td><span class="badge">${esc(p.tag || '—')}</span></td>
            <td><span class="m">${esc(p.slug)}</span></td>
            <td><div class="row-actions">
              <button class="btn sm" data-edit="${p.id}">编辑</button>
              <button class="btn sm danger" data-del="${p.id}">删</button>
            </div></td>
          </tr>`,
                  )
                  .join('')
              : '<tr><td colspan="5" class="empty">还没有文章</td></tr>'
          }
        </tbody>
      </table>
    </div>`;
  $('#new-post').addEventListener('click', () => postEditor(null));
  $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => postEditor(Number(b.dataset.edit))));
  $$('[data-del]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这篇？数据库里就没了，发布后文件也会消失。')) return;
      await api('/posts/' + b.dataset.del, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );
}

async function postEditor(id, draft = null) {
  const post = id ? await api('/posts/' + id) : draft || {
    slug: '', title: '', date: today(), tag: '', read_time: '', summary: '', body: '', draft: false,
  };
  $('#view-title').textContent = id ? '编辑文章' : '新建文章';
  $('#view').innerHTML = `
    <div class="editor">
      <div class="form-col">
        <label class="field"><span>标题</span><input type="text" id="f-title" value="${esc(post.title)}" /></label>
        ${mdField('正文（Markdown）', esc(post.body), 18, '从第二段开始写…')}
        <div class="form-actions">
          <button class="btn primary" id="save">${id ? '保存' : '创建'}</button>
          <button class="btn" id="cancel">取消</button>
          <span class="tip" id="count"></span>
        </div>
      </div>
      <div class="side-col">
        <h3>发布信息</h3>
        <label class="field"><span>slug（网址，英文）</span><input type="text" id="f-slug" value="${esc(post.slug)}" placeholder="opening" /></label>
        <label class="field"><span>日期</span><input type="date" id="f-date" value="${esc(post.date)}" /></label>
        <label class="field"><span>标签</span><input type="text" id="f-tag" value="${esc(post.tag)}" placeholder="开篇 / AIGC" /></label>
        <label class="field"><span>阅读时长</span><input type="text" id="f-read" value="${esc(post.read_time)}" placeholder="3 分钟" /></label>
        <label class="field"><span>摘要</span><textarea id="f-summary" rows="3">${esc(post.summary)}</textarea></label>
        <label class="field" style="display:flex;gap:8px;align-items:center">
          <input type="checkbox" id="f-draft" ${post.draft ? 'checked' : ''} /><span style="margin:0">存为草稿</span>
        </label>
        <p class="tip">slug 会变成 /writing/&lt;slug&gt;/，改了就换网址。</p>
      </div>
    </div>`;

  const bodyEl = $('#f-body');
  mountMarkdown($('#view'));
  const count = () => ($('#count').textContent = `${bodyEl.value.length} 字`);
  bodyEl.addEventListener('input', count);
  count();

  $('#cancel').addEventListener('click', () => {
    current = 'posts';
    render();
  });

  $('#save').addEventListener('click', async () => {
    const payload = {
      slug: $('#f-slug').value.trim(),
      title: $('#f-title').value.trim(),
      date: $('#f-date').value,
      tag: $('#f-tag').value.trim(),
      read_time: $('#f-read').value.trim(),
      summary: $('#f-summary').value.trim(),
      body: bodyEl.value,
      draft: $('#f-draft').checked,
    };
    if (!payload.slug || !payload.title || !payload.date) return toast('slug、标题、日期都必填', true);
    try {
      if (id) await api('/posts/' + id, { method: 'PUT', body: payload });
      else await api('/posts', { method: 'POST', body: payload });
      toast(id ? '已保存（记得发布）' : '已创建（记得发布）');
      current = 'posts';
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- 随记 ---------- */

async function viewNotes(el) {
  const notes = await api('/notes');
  el.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <span>共 ${notes.length} 条</span>
        <button class="btn sm primary" id="new-note">写一条</button>
      </div>
      <table><thead><tr><th>内容</th><th>日期</th><th></th></tr></thead><tbody>
        ${
          notes.length
            ? notes
                .map(
                  (n) => `<tr>
          <td><span class="t">${esc(n.body.split('\n')[0].slice(0, 60) || '（空）')}</span>
            <span class="m">${esc((n.body.split('\n')[1] || '').slice(0, 70))}</span></td>
          <td>${n.date}${n.draft ? ' <span class="badge draft">草稿</span>' : ''}${
                    n.tag ? ' <span class="badge">' + esc(n.tag) + '</span>' : ''
                  }</td>
          <td><div class="row-actions">
            <button class="btn sm" data-edit="${n.id}">编辑</button>
            <button class="btn sm danger" data-del="${n.id}">删</button>
          </div></td></tr>`,
                )
                .join('')
            : '<tr><td colspan="3" class="empty">还没有随记</td></tr>'
        }
      </tbody></table></div>`;
  $('#new-note').addEventListener('click', () => noteEditor(null));
  $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => noteEditor(Number(b.dataset.edit))));
  $$('[data-del]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这条随记？')) return;
      await api('/notes/' + b.dataset.del, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );
}

async function noteEditor(id) {
  const note = id ? await api('/notes/' + id) : { slug: today() + '-01', date: today(), tag: '', body: '', draft: false };
  $('#view-title').textContent = id ? '编辑随记' : '写一条随记';
  $('#view').innerHTML = `
    <div class="editor">
      <div class="form-col">
        <label class="field"><span>正文（一句话也算一条）</span>
          <textarea id="f-body" class="mono" rows="10">${esc(note.body)}</textarea></label>
        <div class="form-actions">
          <button class="btn primary" id="save">${id ? '保存' : '创建'}</button>
          <button class="btn" id="cancel">取消</button>
        </div>
      </div>
      <div class="side-col">
        <h3>这条的信息</h3>
        <label class="field"><span>文件名（英文 / 日期）</span><input type="text" id="f-slug" value="${esc(note.slug)}" /></label>
        <label class="field"><span>日期</span><input type="date" id="f-date" value="${esc(note.date)}" /></label>
        <label class="field"><span>标签（可空）</span><input type="text" id="f-tag" value="${esc(note.tag || '')}" /></label>
        <label class="field" style="display:flex;gap:8px;align-items:center">
          <input type="checkbox" id="f-draft" ${note.draft ? 'checked' : ''} /><span style="margin:0">存为草稿</span>
        </label>
      </div>
    </div>`;
  $('#cancel').addEventListener('click', () => {
    current = 'notes';
    render();
  });
  $('#save').addEventListener('click', async () => {
    const payload = {
      slug: $('#f-slug').value.trim(),
      date: $('#f-date').value,
      tag: $('#f-tag').value.trim() || null,
      body: $('#f-body').value,
      draft: $('#f-draft').checked,
    };
    if (!payload.slug || !payload.date) return toast('文件名和日期必填', true);
    try {
      if (id) await api('/notes/' + id, { method: 'PUT', body: payload });
      else await api('/notes', { method: 'POST', body: payload });
      toast('已保存');
      current = 'notes';
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- 小说 ---------- */

let novelOpen = null;

async function viewNovels(el) {
  const novels = await api('/novels');
  const chapters = novelOpen ? await api(`/novels/${novelOpen}/chapters`) : [];
  const active = novels.find((n) => n.slug === novelOpen);
  el.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <span>共 ${novels.length} 部</span>
        <button class="btn sm primary" id="new-novel">新建作品</button>
      </div>
      <table><thead><tr><th>作品</th><th>状态</th><th>更新</th><th></th></tr></thead><tbody>
        ${
          novels.length
            ? novels
                .map(
                  (n) => `<tr>
          <td><span class="t">${esc(n.title)}</span><span class="m">${esc(n.subtitle || '')} · ${esc(
                    n.slug,
                  )}</span></td>
          <td><span class="badge">${esc(n.status)}</span></td>
          <td>${n.updated}</td>
          <td><div class="row-actions">
            <button class="btn sm" data-open="${n.slug}">章节</button>
            <button class="btn sm" data-edit="${n.id}">编辑</button>
            <button class="btn sm danger" data-del="${n.id}">删</button>
          </div></td></tr>`,
                )
                .join('')
            : '<tr><td colspan="4" class="empty">还没有作品</td></tr>'
        }
      </tbody></table>
    </div>
    ${
      active
        ? `<div class="panel" style="margin-top:16px">
            <div class="panel-head">
              <span>《${esc(active.title)}》的章节 · ${chapters.length} 章</span>
              <button class="btn sm primary" id="new-chapter">新增章节</button>
            </div>
            <table><thead><tr><th>#</th><th>章节</th><th>日期</th><th></th></tr></thead><tbody>
              ${
                chapters.length
                  ? chapters
                      .map(
                        (c) => `<tr><td>${c.order}</td>
                <td><span class="t">${esc(c.title)}</span><span class="m">${esc(c.slug)}</span></td>
                <td>${c.date}${c.draft ? ' <span class="badge draft">草稿</span>' : ''}</td>
                <td><div class="row-actions">
                  <button class="btn sm" data-edit-ch="${c.id}">编辑</button>
                  <button class="btn sm danger" data-del-ch="${c.id}">删</button>
                </div></td></tr>`,
                      )
                      .join('')
                  : '<tr><td colspan="4" class="empty">这部还没章节</td></tr>'
              }
            </tbody></table>
          </div>`
        : ''
    }`;

  $('#new-novel').addEventListener('click', () => novelEditor(null));
  $$('[data-open]', el).forEach((b) =>
    b.addEventListener('click', () => {
      novelOpen = novelOpen === b.dataset.open ? null : b.dataset.open;
      render();
    }),
  );
  $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => novelEditor(Number(b.dataset.edit))));
  $$('[data-del]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这部作品和它的全部章节？')) return;
      await api('/novels/' + b.dataset.del, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );
  const nb = $('#new-chapter');
  if (nb) nb.addEventListener('click', () => chapterEditor(novelOpen, null));
  $$('[data-edit-ch]', el).forEach((b) =>
    b.addEventListener('click', () => chapterEditor(novelOpen, Number(b.dataset.editCh))),
  );
  $$('[data-del-ch]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这一章？')) return;
      await api(`/novels/${novelOpen}/chapters/` + b.dataset.delCh, { method: 'DELETE' });
      toast('已删除');
      render();
    }),
  );
}

async function novelEditor(id) {
  const novel = id
    ? await api('/novels/' + id)
    : { slug: '', title: '', subtitle: '', summary: '', status: '连载中', tags: [], updated: today(), body: '', draft: false };
  $('#view-title').textContent = id ? '编辑作品' : '新建作品';
  $('#view').innerHTML = `
    <div class="editor">
      <div class="form-col">
        <label class="field"><span>作品名</span><input type="text" id="f-title" value="${esc(novel.title)}" /></label>
        <label class="field"><span>副标题</span><input type="text" id="f-subtitle" value="${esc(novel.subtitle || '')}" /></label>
        <label class="field"><span>简介</span><textarea id="f-summary" rows="3">${esc(novel.summary)}</textarea></label>
        ${mdField('开场白 / 正文说明（Markdown，可空）', esc(novel.body), 8, '可以留空')}
        <div class="form-actions">
          <button class="btn primary" id="save">${id ? '保存' : '创建'}</button>
          <button class="btn" id="cancel">取消</button>
        </div>
      </div>
      <div class="side-col">
        <h3>作品信息</h3>
        <label class="field"><span>slug（网址）</span><input type="text" id="f-slug" value="${esc(novel.slug)}" placeholder="kuajie-zhufu" /></label>
        <label class="field"><span>状态</span>
          <select id="f-status">${['筹备中', '连载中', '已完结']
            .map((s) => `<option ${s === novel.status ? 'selected' : ''}>${s}</option>`)
            .join('')}</select></label>
        <label class="field"><span>标签（逗号分隔）</span>
          <input type="text" id="f-tags" value="${esc((novel.tags || []).join('，'))}" /></label>
        <label class="field"><span>更新日期</span><input type="date" id="f-updated" value="${esc(novel.updated)}" /></label>
        <label class="field" style="display:flex;gap:8px;align-items:center">
          <input type="checkbox" id="f-draft" ${novel.draft ? 'checked' : ''} /><span style="margin:0">存为草稿</span>
        </label>
      </div>
    </div>`;
  mountMarkdown($('#view'));
  $('#cancel').addEventListener('click', () => {
    current = 'novels';
    render();
  });
  $('#save').addEventListener('click', async () => {
    const payload = {
      slug: $('#f-slug').value.trim(),
      title: $('#f-title').value.trim(),
      subtitle: $('#f-subtitle').value.trim() || null,
      summary: $('#f-summary').value.trim(),
      status: $('#f-status').value,
      tags: $('#f-tags')
        .value.split(/[，,]/)
        .map((s) => s.trim())
        .filter(Boolean),
      updated: $('#f-updated').value,
      body: $('#f-body').value,
      draft: $('#f-draft').checked,
    };
    if (!payload.slug || !payload.title) return toast('slug 和作品名必填', true);
    try {
      if (id) await api('/novels/' + id, { method: 'PUT', body: payload });
      else await api('/novels', { method: 'POST', body: payload });
      toast('已保存');
      current = 'novels';
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function chapterEditor(novelSlug, id) {
  const ch = id
    ? await api(`/novels/${novelSlug}/chapters/${id}`)
    : { slug: 'ch-01', title: '', order: 1, date: today(), body: '', draft: false };
  $('#view-title').textContent = id ? '编辑章节' : '新增章节';
  $('#view').innerHTML = `
    <div class="editor">
      <div class="form-col">
        <label class="field"><span>章节标题</span><input type="text" id="f-title" value="${esc(ch.title)}" /></label>
        ${mdField('正文（Markdown）', esc(ch.body), 20)}
        <div class="form-actions">
          <button class="btn primary" id="save">${id ? '保存' : '创建'}</button>
          <button class="btn" id="cancel">取消</button>
        </div>
      </div>
      <div class="side-col">
        <h3>章节信息</h3>
        <label class="field"><span>文件名</span><input type="text" id="f-slug" value="${esc(ch.slug)}" placeholder="ch-03" /></label>
        <label class="field"><span>序号</span><input type="number" id="f-order" value="${ch.order}" min="1" /></label>
        <label class="field"><span>日期</span><input type="date" id="f-date" value="${esc(ch.date)}" /></label>
        <label class="field" style="display:flex;gap:8px;align-items:center">
          <input type="checkbox" id="f-draft" ${ch.draft ? 'checked' : ''} /><span style="margin:0">存为草稿</span>
        </label>
      </div>
    </div>`;
  mountMarkdown($('#view'));
  $('#cancel').addEventListener('click', () => {
    current = 'novels';
    render();
  });
  $('#save').addEventListener('click', async () => {
    const payload = {
      slug: $('#f-slug').value.trim(),
      title: $('#f-title').value.trim(),
      order: Number($('#f-order').value),
      date: $('#f-date').value,
      body: $('#f-body').value,
      draft: $('#f-draft').checked,
    };
    if (!payload.slug || !payload.title) return toast('文件名和标题必填', true);
    try {
      if (id) await api(`/novels/${novelSlug}/chapters/${id}`, { method: 'PUT', body: payload });
      else await api(`/novels/${novelSlug}/chapters`, { method: 'POST', body: payload });
      toast('已保存');
      current = 'novels';
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- 相册 ---------- */

async function viewAlbums(el) {
  const albums = await api('/albums');
  el.innerHTML = `
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>新建一本相册</span></div>
      <div style="padding:16px">
        <div class="split">
          <label class="field"><span>slug（英文）</span><input type="text" id="a-slug" placeholder="2026-trip" /></label>
          <label class="field"><span>名字</span><input type="text" id="a-title" placeholder="旅行" /></label>
        </div>
        <div class="split">
          <label class="field"><span>色调</span>
            <select id="a-tone">
              <option value="mag">霞（粉）</option><option value="vio">暮（紫）</option>
              <option value="cyan">天（青）</option><option value="amber">夕（金）</option>
            </select></label>
          <label class="field"><span>一句话说明</span><input type="text" id="a-note" /></label>
        </div>
        <button class="btn primary" id="add-album">建这本</button>
      </div>
    </div>
    <div class="album-grid">
      ${
        albums.length
          ? albums
              .map(
                (a) => `<div class="album" data-album="${esc(a.slug)}">
          <div class="album-head"><b>${esc(a.title)}</b><span class="badge">${a.photos.length} 张</span></div>
          <div class="note">${esc(a.note)}</div>
          <div class="thumbs">
            ${a.photos
              .map(
                (p) => `<div class="thumb" title="${esc(p.caption)} · ${p.date}">
                <img src="${esc(p.src)}" alt="" loading="lazy" />
                <button data-del-photo="${p.id}" title="删掉这张">×</button>
              </div>`,
              )
              .join('') || '<span class="tip">还空着</span>'}
          </div>
          <div class="upload-row">
            <input type="file" accept="image/*" data-file="${esc(a.slug)}" />
            <button class="btn sm primary" data-upload="${esc(a.slug)}">上传</button>
            <button class="btn sm danger" data-del-album="${a.id}">删相册</button>
          </div>
        </div>`,
              )
              .join('')
          : '<div class="empty">还没有相册</div>'
      }
    </div>
    <p class="tip" style="margin-top:14px">图片存到 public/gallery/，发布时会跟着构建进 dist。单张上限 12MB。</p>`;

  $('#add-album').addEventListener('click', async () => {
    const payload = {
      slug: $('#a-slug').value.trim(),
      title: $('#a-title').value.trim(),
      tone: $('#a-tone').value,
      note: $('#a-note').value.trim(),
      sort: Date.now(),
    };
    if (!payload.slug || !payload.title) return toast('slug 和名字必填', true);
    try {
      await api('/albums', { method: 'POST', body: payload });
      toast('建好了（记得发布）');
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });

  $$('[data-upload]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      const input = $(`[data-file="${b.dataset.upload}"]`, el);
      if (!input.files.length) return toast('先选一张图', true);
      const fd = new FormData();
      fd.append('file', input.files[0]);
      fd.append('date', today());
      try {
        await api(`/albums/${b.dataset.upload}/photos`, { method: 'POST', body: fd });
        toast('传上去了（记得发布）');
        render();
        refreshCounts();
      } catch (err) {
        toast(err.message, true);
      }
    }),
  );

  $$('[data-del-photo]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这张照片？')) return;
      await api('/photos/' + b.dataset.delPhoto, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );

  $$('[data-del-album]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这本相册和里面所有照片？')) return;
      await api('/albums/' + b.dataset.delAlbum, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );
}

/* ---------- 音乐 ---------- */

async function viewMusic(el) {
  const [tracks, site] = await Promise.all([api('/site/tracks'), api('/site')]);
  el.innerHTML = `
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>曲目 · ${tracks.length} 首</span><button class="btn sm primary" id="new-track">加一首</button></div>
      <table><thead><tr><th>曲名</th><th>歌曲 ID</th><th>时长</th><th>那句理由</th><th></th></tr></thead><tbody>
        ${
          tracks.length
            ? tracks
                .map(
                  (t) => `<tr>
          <td><span class="t">${esc(t.name)}</span><span class="m">${esc(t.artist)}</span></td>
          <td><span class="m">${esc(t.song_id)}</span></td>
          <td>${Math.floor(t.dur / 60)}:${String(t.dur % 60).padStart(2, '0')}</td>
          <td><span class="m">${esc(t.why)}</span></td>
          <td><div class="row-actions">
            <button class="btn sm" data-edit="${t.id}">编辑</button>
            <button class="btn sm danger" data-del="${t.id}">删</button>
          </div></td></tr>`,
                )
                .join('')
            : '<tr><td colspan="5" class="empty">还没有曲目</td></tr>'
        }
      </tbody></table></div>
    <div class="panel">
      <div class="panel-head"><span>接口</span></div>
      <div style="padding:16px">
        <div class="split">
          <label class="field"><span>播放接口（Meting）</span><input type="text" id="m-api" value="${esc(site.musicApi)}" /></label>
          <label class="field"><span>网易云歌单 ID</span><input type="text" id="m-playlist" value="${esc(site.playlistId)}" /></label>
        </div>
        <button class="btn" id="save-music">保存接口设置</button>
        <p class="tip" style="margin-top:10px">公共代理只给 30–45 秒试听。要完整版就自建 NeteaseCloudMusicApi，把地址换到这里，别的代码不用动。</p>
      </div>
    </div>`;

  $('#new-track').addEventListener('click', () => trackEditor(null));
  $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => trackEditor(Number(b.dataset.edit))));
  $$('[data-del]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这首？')) return;
      await api('/site/tracks/' + b.dataset.del, { method: 'DELETE' });
      toast('已删除');
      render();
      refreshCounts();
    }),
  );
  $('#save-music').addEventListener('click', async () => {
    try {
      await api('/site', {
        method: 'PUT',
        body: { ...site, musicApi: $('#m-api').value.trim(), playlistId: $('#m-playlist').value.trim(), tracks: [], doing: [] },
      });
      toast('接口设置已保存');
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function trackEditor(id) {
  const tracks = await api('/site/tracks');
  const t = id ? tracks.find((x) => x.id === id) : { song_id: '', name: '', artist: '', dur: 0, why: '', sort: tracks.length };
  $('#view-title').textContent = id ? '编辑曲目' : '加一首';
  $('#view').innerHTML = `
    <div class="editor">
      <div class="form-col">
        <div class="split">
          <label class="field"><span>曲名</span><input type="text" id="f-name" value="${esc(t.name)}" /></label>
          <label class="field"><span>歌手</span><input type="text" id="f-artist" value="${esc(t.artist)}" /></label>
        </div>
        <div class="split">
          <label class="field"><span>歌曲 ID（QQ 音乐 songmid / 网易云数字 id）</span><input type="text" id="f-id" value="${esc(t.song_id)}" /></label>
          <label class="field"><span>整首时长（秒）</span><input type="number" id="f-dur" value="${t.dur}" /></label>
        </div>
        <label class="field"><span>为什么放这首（一句话）</span><input type="text" id="f-why" value="${esc(t.why)}" /></label>
        <div class="form-actions">
          <button class="btn primary" id="save">${id ? '保存' : '加上'}</button>
          <button class="btn" id="cancel">取消</button>
        </div>
      </div>
      <div class="side-col">
        <h3>说明</h3>
        <p class="tip">时长填整首的秒数。公共接口只给试听时，播放器靠它算出「这段是残的」，会在界面上标「试听」。</p>
      </div>
    </div>`;
  $('#cancel').addEventListener('click', () => {
    current = 'music';
    render();
  });
  $('#save').addEventListener('click', async () => {
    const payload = {
      song_id: $('#f-id').value.trim(),
      name: $('#f-name').value.trim(),
      artist: $('#f-artist').value.trim(),
      dur: Number($('#f-dur').value) || 0,
      why: $('#f-why').value.trim(),
      sort: t.sort ?? 0,
    };
    if (!payload.name || !payload.song_id) return toast('曲名和歌曲 ID 必填', true);
    try {
      if (id) await api('/site/tracks/' + id, { method: 'PUT', body: payload });
      else await api('/site/tracks', { method: 'POST', body: payload });
      toast('已保存（记得发布）');
      current = 'music';
      render();
      refreshCounts();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- 站点 ---------- */

async function viewSite(el) {
  const site = await api('/site');
  const doing = site.doing || [];
  el.innerHTML = `
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>首页文案</span><button class="btn sm primary" id="save-site">保存</button></div>
      <div style="padding:16px">
        <div class="split">
          <label class="field"><span>站名</span><input type="text" id="s-name" value="${esc(site.name)}" /></label>
          <label class="field"><span>英文名</span><input type="text" id="s-en" value="${esc(site.en)}" /></label>
        </div>
        <div class="split">
          <label class="field"><span>右上角日期标</span><input type="text" id="s-mark" value="${esc(site.mark)}" /></label>
          <label class="field"><span>作品集地址（留空则提示待填）</span><input type="text" id="s-portfolio" value="${esc(site.portfolioUrl)}" /></label>
        </div>
        <label class="field"><span>一句话简介（头像旁那句）</span><input type="text" id="s-intro" value="${esc(site.intro)}" /></label>
        <label class="field"><span>首页大段介绍</span><textarea id="s-lead" rows="3">${esc(site.lead)}</textarea></label>
        <label class="field"><span>SEO 描述</span><textarea id="s-desc" rows="2">${esc(site.desc)}</textarea></label>
        <label class="field"><span>简介三段（一行一段）</span><textarea id="s-bio" rows="4">${esc((site.bio || []).join('\n'))}</textarea></label>
      </div>
    </div>

    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>背景图片</span><span class="tip">留空 = 用默认的黄昏天色渐变</span></div>
      <div style="padding:16px">
        <label class="field"><span>背景图地址（或点右边按钮上传本地图片）</span>
          <div style="display:flex;gap:8px">
            <input type="text" id="s-bgimg" value="${esc(site.backgroundImage || '')}" placeholder="/bg.jpg" style="flex:1" />
            <button type="button" class="btn sm primary" id="upload-bgimg">上传图片</button>
          </div>
        </label>
        <label class="field"><span>压暗程度（0–100，数值越大越暗，图片不遮文字）</span><input type="range" id="s-bgdim" min="0" max="100" step="1" value="${Math.round((site.backgroundImageDim ?? 0) * 100)}" style="width:100%" /></label>
        <p class="tip" style="margin:0">背景图会盖在黄昏天色上面、铺满整个窗口并固定不滚动，配一层暗色遮罩保证文字可读。数值建议 60–85。</p>
      </div>
    </div>

    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>联系方式</span><span class="tip">留空 = 首页显示「待接入」</span></div>
      <div style="padding:16px">
        <div class="split">
          <label class="field"><span>GitHub</span><input type="text" id="c-github" value="${esc(site.contact.github || '')}" /></label>
          <label class="field"><span>邮箱</span><input type="text" id="c-email" value="${esc(site.contact.email || '')}" /></label>
        </div>
        <div class="split">
          <label class="field"><span>微信号</span><input type="text" id="c-wechat" value="${esc(site.contact.wechatId || '')}" /></label>
          <label class="field"><span>微信二维码（/wechat-qr.png）</span><input type="text" id="c-qr" value="${esc(site.contact.wechatQr || '')}" /></label>
        </div>
        <label class="field"><span>抖音</span><input type="text" id="c-douyin" value="${esc(site.contact.douyin || '')}" /></label>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><span>现在在做 · ${doing.length} 件</span>
        <button class="btn sm" id="add-doing">加一件</button>
      </div>
      <div style="padding:16px; display:grid; gap:14px">
        ${
          doing.length
            ? doing
                .map(
                  (d, i) => `<div class="card" data-doing="${d.id}">
            <div class="split">
              <label class="field"><span>状态（进行中 / 每天 / 筹备期）</span><input type="text" class="d-state" value="${esc(d.state)}" /></label>
              <label class="field"><span>标题</span><input type="text" class="d-title" value="${esc(d.title)}" /></label>
            </div>
            <label class="field"><span>副标题</span><input type="text" class="d-sub" value="${esc(d.sub)}" /></label>
            <label class="field"><span>首页那句话</span><input type="text" class="d-note" value="${esc(d.note)}" /></label>
            <label class="field"><span>详情页那段</span><textarea class="d-long" rows="2">${esc(d.note_long)}</textarea></label>
            <div class="row-actions" style="justify-content:flex-start">
              <button class="btn sm" data-save-doing="${d.id}">保存这条</button>
              <button class="btn sm danger" data-del-doing="${d.id}">删</button>
            </div>
          </div>`,
                )
                .join('')
            : '<div class="empty">还没有</div>'
        }
      </div>
    </div>`;

  const collectSite = () => ({
    name: $('#s-name').value.trim(),
    en: $('#s-en').value.trim(),
    mark: $('#s-mark').value.trim(),
    intro: $('#s-intro').value.trim(),
    lead: $('#s-lead').value.trim(),
    desc: $('#s-desc').value.trim(),
    playlistId: site.playlistId,
    musicApi: site.musicApi,
    musicServer: site.musicServer,
    portfolioUrl: $('#s-portfolio').value.trim(),
    backgroundImage: $('#s-bgimg').value.trim(),
    backgroundImageDim: Number($('#s-bgdim').value) / 100,
    contact: {
      github: $('#c-github').value.trim(),
      email: $('#c-email').value.trim(),
      wechatId: $('#c-wechat').value.trim(),
      wechatQr: $('#c-qr').value.trim(),
      douyin: $('#c-douyin').value.trim(),
    },
    bio: $('#s-bio').value.split('\n').map((s) => s.trim()).filter(Boolean),
    facts: site.facts,
    tracks: [],
    doing: [],
  });

  $('#save-site').addEventListener('click', async () => {
    try {
      await api('/site', { method: 'PUT', body: collectSite() });
      toast('站点文案已保存（记得发布）');
    } catch (err) {
      toast(err.message, true);
    }
  });

  // 背景图上传
  $('#upload-bgimg').addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async () => {
      if (!input.files.length) return;
      const fd = new FormData();
      fd.append('file', input.files[0]);
      toast('上传中...');
      try {
        const res = await api('/upload-image', { method: 'POST', body: fd });
        $('#s-bgimg').value = res.url;
        toast('背景图上传成功，记得点保存');
      } catch (e) {
        toast('上传失败：' + (e.message || '未知错误'), true);
      }
    };
    input.click();
  });

  $$('[data-save-doing]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      const card = b.closest('[data-doing]');
      const payload = {
        state: $('.d-state', card).value.trim(),
        title: $('.d-title', card).value.trim(),
        sub: $('.d-sub', card).value.trim(),
        note: $('.d-note', card).value.trim(),
        note_long: $('.d-long', card).value.trim(),
        sort: Number(b.dataset.saveDoing),
      };
      if (!payload.title) return toast('标题不能空', true);
      try {
        await api('/site/doing/' + b.dataset.saveDoing, { method: 'PUT', body: payload });
        toast('这条已保存');
      } catch (err) {
        toast(err.message, true);
      }
    }),
  );

  $$('[data-del-doing]', el).forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('删掉这一条？')) return;
      await api('/site/doing/' + b.dataset.delDoing, { method: 'DELETE' });
      toast('已删除');
      render();
    }),
  );

  $('#add-doing').addEventListener('click', async () => {
    try {
      await api('/site/doing', {
        method: 'POST',
        body: { state: '进行中', title: '新的一件事', sub: '', note: '', note_long: '', sort: Date.now() },
      });
      toast('加好了，填完点保存');
      render();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ---------- 发布 ---------- */

async function viewPublish(el) {
  const b = await api('/publish/status');
  const stats = await api('/stats');
  el.innerHTML = `
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-head"><span>发布</span><span>${esc(b.state)}</span></div>
      <div style="padding:16px">
        <p class="tip" style="margin-top:0">
          发布 = 把数据库里的内容写成 <code>src/content/*.md</code> 与 <code>src/data/*.json</code>，
          再跑一次 <code>npm run build</code>（约 1.6 秒，pagefind 会重建索引）。
        </p>
        <div class="split" style="margin:12px 0">
          <label class="field"><span>提交信息（勾了下面对勾才会 git commit）</span>
            <input type="text" id="p-msg" value="chore: 后台发布" /></label>
          <label class="field" style="display:flex;gap:8px;align-items:center;margin-top:26px">
            <input type="checkbox" id="p-git" /><span style="margin:0">顺便 git commit</span></label>
        </div>
        <div class="form-actions">
          <button class="btn primary" id="go">${b.state === 'running' ? '构建中…' : '保存并发布'}</button>
          <a class="btn" href="${esc(stats.urls.site)}" target="_blank" rel="noopener">去站点看看</a>
        </div>
        <p class="tip">库里：${stats.posts} 篇文章 · ${stats.notes} 条随记 · ${stats.novels} 部小说 · ${stats.photos} 张照片 · ${stats.tracks} 首曲目</p>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><span>构建日志</span><span>${b.pages ? b.pages + ' 页' : ''} ${
        b.duration_ms ? b.duration_ms + ' ms' : ''
      }</span></div>
      <pre class="log" id="p-log">${esc(b.log || '还没有记录')}</pre>
    </div>`;

  $('#go').addEventListener('click', async () => {
    try {
      const res = await api('/publish', {
        method: 'POST',
        body: { message: $('#p-msg').value.trim(), git_commit: $('#p-git').checked },
      });
      toast(`写入 ${res.render.written} 个文件，开始构建…`);
      watchBuild();
      render();
    } catch (err) {
      toast(err.message, true);
    }
  });

  if (b.state === 'running') watchBuild();
}

/* ---------------- 入口 ---------------- */

async function boot() {
  try {
    await api('/auth/me');
  } catch {
    showLogin();
    return;
  }
  $('#login-view').hidden = true;
  $('#app').hidden = false;
  await refreshCounts();
  render();
  watchBuild();
}

$('#publish-btn').addEventListener('click', async () => {
  current = 'publish';
  renderNav();
  await render();
  const go = $('#go');
  if (go) go.click();
});

boot();
