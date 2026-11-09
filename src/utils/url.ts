// 站内链接统一走这里：astro.config.mjs 里设了 base（GitHub Pages 项目页需要）时，
// 链接会自动带上前缀，不用手改每一处。
export function link(path: string): string {
  if (/^(https?:)?\/\//.test(path) || path.startsWith('#') || path.startsWith('mailto:')) return path;
  const base = import.meta.env.BASE_URL || '/';
  const prefix = base.endsWith('/') ? base : base + '/';
  return prefix + path.replace(/^\//, '');
}
