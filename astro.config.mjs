import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import remarkCallout from './src/plugins/remark-callout.mjs';
import rehypeHighlight from './src/plugins/rehype-highlight.mjs';

// GitHub Pages 项目页：仓库名是 AI-，站点挂在 https://jhb-0212.github.io/AI-/
// 所以 site 要写全，base 要带 /AI- 前缀（站内链接、搜索索引路径都会自动跟着走）。
export default defineConfig({
  site: 'https://jhb-0212.github.io',
  base: '/AI-',
  integrations: [sitemap()],
  markdown: {
    remarkPlugins: [remarkCallout],
    rehypePlugins: [rehypeHighlight],
  },
  build: {
    format: 'directory',
  },
});
