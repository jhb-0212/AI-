// 行内高亮：把正文里的 ==文字== 转成 <mark>。
// 放在 rehype 阶段处理最稳——直接扫文本节点，不跟 markdown 解析器抢语法。
import { visit } from 'unist-util-visit';

export default function rehypeHighlight() {
  return (tree) => {
    visit(tree, 'text', (node, index, parent) => {
      if (!node.value || node.value.indexOf('==') === -1) return;
      const parts = node.value.split('==');
      // 没有成对标记（不足 3 段），原样返回
      if (parts.length < 3) return;

      const rebuilt = [];
      parts.forEach((text, i) => {
        if (i % 2 === 1) {
          // 奇数段是 ==...== 之间的高亮内容
          rebuilt.push({
            type: 'element',
            tagName: 'mark',
            properties: {},
            children: text ? [{ type: 'text', value: text }] : [],
          });
        } else if (text) {
          rebuilt.push({ type: 'text', value: text });
        }
      });

      parent.children.splice(index, 1, ...rebuilt);
      // 返回下一个要访问的位置，跳过刚插入的节点
      return index + rebuilt.length;
    });
  };
}
