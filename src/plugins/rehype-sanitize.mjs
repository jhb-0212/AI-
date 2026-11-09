// rehype 阶段的安全过滤：删掉 Markdown 里可能混进来的危险 HTML，
// 防止后台写的内容在前台造成存储型 XSS。
//
// Astro 的 markdown 管线顺序是：
//   remarkRehype(allowDangerousHtml:true) → 用户 rehypePlugins → rehypeRaw → stringify
// 也就是说 raw HTML 在「用户插件」之后才被 rehypeRaw 解析成 element。
// 所以这里要同时拦两层：
//   1. raw 节点：此刻还是原始 HTML 字符串，直接整段转义（危险内容全废）；
//   2. element 节点：过滤属性（on*、javascript:、data: 等）。
//
// 白名单外的标签 / 危险属性一律剔除，只保留安全标签和安全属性。
import { visit } from 'unist-util-visit';

// 允许保留的标签。mark 是 ==高亮== 用的，blockquote.callout 是 [!type] 用的。
const ALLOWED_TAGS = new Set([
  'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'del', 'div', 'em', 'h1', 'h2',
  'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'mark', 'ol', 'p', 'pre',
  'q', 's', 'span', 'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'th',
  'thead', 'tr', 'u', 'ul',
]);

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// href / src 只允许安全协议，其余（javascript:、data:、vbscript: 等）整条删掉。
function sanitizeUrl(value) {
  const v = String(value).trim();
  // 去掉控制字符与空白，防「java\nscript:」这类绕过
  const cleaned = v.replace(/[\u0000-\u0020]/g, '');
  const lower = cleaned.toLowerCase();
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('data:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('file:')
  ) {
    return '';
  }
  return v;
}

export default function rehypeSanitize() {
  return (tree) => {
    // 第一层：raw HTML（rehypeRaw 之前还是字符串）。整段转义，让危险 HTML 变成可见文本。
    visit(tree, 'raw', (node, index, parent) => {
      if (parent && typeof index === 'number') {
        // 转成普通文本节点，内容按 HTML 转义后原样显示
        parent.children.splice(index, 1, { type: 'text', value: node.value });
      }
    });

    // 第二层：element 节点，过滤危险标签和属性。
    visit(tree, 'element', (node, index, parent) => {
      const tag = String(node.tagName || '').toLowerCase();

      if (!ALLOWED_TAGS.has(tag)) {
        if (parent && typeof index === 'number') {
          parent.children.splice(index, 1);
          return index;
        }
        return;
      }

      const props = node.properties || {};
      for (const key of Object.keys(props)) {
        const k = key.toLowerCase();
        if (k.startsWith('on')) {
          delete props[key];
          continue;
        }
        if (k === 'href' || k === 'src' || k === 'srcset') {
          const clean = sanitizeUrl(props[key]);
          if (!clean) delete props[key];
          else props[key] = clean;
        }
      }
    });
  };
}
