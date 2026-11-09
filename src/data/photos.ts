// 相册数据。图片放 public/gallery/，这里写文件名即可（前面带 /gallery/）。
// 例：{ "src": "/gallery/2026-11-night.jpg", "caption": "凌晨三点的实验楼", "date": "2026-11-03" }
//
// 数据在 photos.data.json —— 后台保存照片时写的就是那个文件，手改也行。
import data from './photos.data.json';

export type Photo = {
  src: string;
  caption: string;
  date: string;
  span?: 'wide' | 'tall';
};

// 一本相册 = 墙上的一叠拍立得。往 albums 里加一条，相册页就多一叠。
export type Album = {
  id: string; // 用来做锚点和展开面板的 id，用英文
  title: string; // 相纸下面那行的名字
  tone?: 'mag' | 'vio' | 'cyan' | 'amber'; // 空相纸里的那团光、张数徽章的颜色
  note?: string; // 摊开后标题旁边的一句话
  photos: Photo[];
};

export const albums: Album[] = data.albums as Album[];

// 站内所有照片（首页的「照片」计数、内容墙都读这个）
export const photos: Photo[] = albums.flatMap((album) => album.photos);
