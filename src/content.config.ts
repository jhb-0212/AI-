import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// 文章：src/content/posts/ 下的一篇 .md，文件名即网址。
const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    tag: z.string(),
    readTime: z.string(),
    summary: z.string(),
    draft: z.boolean().default(false),
  }),
});

// 随记：一句话或一小段，正文就是 markdown body。
const notes = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/notes' }),
  schema: z.object({
    date: z.coerce.date(),
    tag: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

// 小说作品：一个文件 = 一部作品，文件名即作品网址 /novels/<文件名>/。
const novels = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/novels' }),
  schema: z.object({
    title: z.string(),
    subtitle: z.string().optional(),
    summary: z.string(),
    status: z.enum(['筹备中', '连载中', '已完结']).default('连载中'),
    tags: z.array(z.string()).default([]),
    updated: z.coerce.date(),
    draft: z.boolean().default(false),
  }),
});

// 章节：src/content/chapters/<作品文件名>/<章节文件>.md
const chapters = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/chapters' }),
  schema: z.object({
    title: z.string(),
    order: z.number(),
    date: z.coerce.date(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { posts, notes, novels, chapters };
