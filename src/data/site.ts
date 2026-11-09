// 全站文案与配置集中在这里。
//
// 真正的数据在 site.data.json —— 后台（server/）保存时写的就是那个文件。
// 手改也行，改完 npm run build 一次就生效；别直接改这个 .ts，发布时它不会被覆盖，
// 但页面读的是 JSON，改了不生效。
import data from './site.data.json';

export const site = data;

export function openPortfolioHint() {
  return '作品集链接还没填。在后台「站点」里填上，或改 src/data/site.data.json 的 portfolioUrl，这个按钮就会直接跳过去。';
}
