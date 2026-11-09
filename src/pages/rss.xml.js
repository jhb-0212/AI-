import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { site } from '../data/site';

const base = import.meta.env.BASE_URL || '/';

export async function GET(context) {
  const posts = (await getCollection('posts', ({ data }) => !data.draft)).sort(
    (a, b) => b.data.date.getTime() - a.data.date.getTime()
  );

  return rss({
    title: `${site.name} · ${site.en}`,
    description: site.desc,
    site: context.site,
    items: posts.map((post) => ({
      title: post.data.title,
      pubDate: post.data.date,
      description: post.data.summary,
      link: `${base}writing/${post.id}/`,
      categories: [post.data.tag],
    })),
    customData: '<language>zh-cn</language>',
  });
}
