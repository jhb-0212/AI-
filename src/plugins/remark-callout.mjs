// Callout 提示框：把 Obsidian 风格的引用块转成带 data-callout 的容器。
// 支持两种写法：
//   > [!note] 这是标题
//   > 这是内容
// 或
//   > [!note]
//   > 这是内容
// 标题与内容在同一行时，[!type] 后的文字是标题；单独一行 [!type] 时没有标题，
// 后续段落全部作为正文。
import { visit } from 'unist-util-visit';

export default function remarkCallout() {
  return (tree) => {
    visit(tree, 'blockquote', (node) => {
      const firstPara = node.children.find((c) => c.type === 'paragraph');
      if (!firstPara) return;

      // 取第一个段落的完整纯文本（含换行）
      const paraText = firstPara.children
        .map((c) => (c.type === 'text' ? c.value : ''))
        .join('');

      // 匹配 [!type] 或 [!type] 标题（标题与标记同一行）
      const m = /^\[\!([a-zA-Z]+)\](?:[ \t]+([^\n]*))?/.exec(paraText.trimStart());
      if (!m) return;

      const type = m[1].toLowerCase();
      const inlineTitle = (m[2] || '').trim();

      // 去掉 [!type] 标记（含同行的标题文字），得到第一段剩余的文字
      // 剩余部分：标记那一行之后的内容（换行后面的行属于正文）
      const afterMarker = paraText.replace(/^\[\![a-zA-Z]+\](?:[ \t]+[^\n]*)?/, '');
      // afterMarker 可能以换行开头，去掉首部空白/换行
      const restText = afterMarker.replace(/^[ \t]*\r?\n/, '').trim();

      // 组装新子节点
      const newChildren = [];

      // 标题行：有 inlineTitle 用之，否则省略标题（Obsidian 默认无标题就不显示标题栏）
      if (inlineTitle) {
        newChildren.push({
          type: 'paragraph',
          data: { hName: 'div', hProperties: { className: ['callout-title'] } },
          children: [
            {
              type: 'text',
              value: inlineTitle,
            },
          ],
        });
      }

      // 正文：第一段剩余文字（若有）
      if (restText) {
        newChildren.push({
          type: 'paragraph',
          children: [{ type: 'text', value: restText }],
        });
      }

      // 后续节点（第一段之后的段落、列表等）
      for (const c of node.children) {
        if (c === firstPara) continue;
        newChildren.push(c);
      }

      node.children = newChildren;
      node.data = node.data || {};
      node.data.hName = 'blockquote';
      node.data.hProperties = {
        className: ['callout', `callout-${type}`],
        dataCallout: type,
      };
    });
  };
}
