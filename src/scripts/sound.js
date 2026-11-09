// 站内的播放器：一套 audio 状态，两个页面共用。
// 音频走公开的 Meting 接口（它把网易云的 /song/url 包了一层，带 CORS）：
//   <api>?server=netease&type=url&id=<歌曲ID>
// 换自建的后端（NeteaseCloudMusicApi）时，只改 site.ts 里的 musicApi。
const DEFAULT_API = 'https://api.injahow.cn/meting/';

const KEY = 'nepenthe:sound';
const fmt = (sec) => {
  if (!Number.isFinite(sec) || sec <= 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};

const CREDIT = /^(作词|作曲|编曲|制作人|监制|出品|录音|混音|母带|吉他|贝斯|键盘|鼓|和声|弦乐|原唱|翻唱|统筹|企划|词|曲)\s*[:：]/;
const LRC = /^\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\](.*)$/;

function parseLrc(text) {
  const credits = [];
  const lines = [];
  for (const raw of text.split('\n')) {
    const hit = LRC.exec(raw.trim());
    if (!hit) continue;
    const [, m, s, ms, body] = hit;
    const t =
      Number(m) * 60 + Number(s) + (ms ? Number(`0.${'0'.repeat(3 - ms.length)}${ms}`) : 0);
    const body2 = body.trim();
    if (!body2) continue;
    if (CREDIT.test(body2)) {
      if (!credits.includes(body2)) credits.push(body2);
      continue;
    }
    if (lines.some((l) => l.t === t && l.text === body2)) continue;
    lines.push({ t, text: body2 });
  }
  lines.sort((a, b) => a.t - b.t);
  return { credits, lines };
}

export function createDeck(tracks, api = DEFAULT_API, server = 'netease') {
  const endpoint = (type, id) =>
    `${api}${api.includes('?') ? '&' : '?'}server=${server}&type=${type}&id=${id}`;
  const audio = new Audio();
  audio.preload = 'none';
  audio.volume = 0.6;

  let index = 0;
  try {
    const saved = Number(localStorage.getItem(KEY));
    if (Number.isInteger(saved) && saved >= 0 && saved < tracks.length) index = saved;
  } catch {}

  let lyricsState = 'idle'; // idle | loading | ready | none
  let lyrics = { credits: [], lines: [] };
  let current = -1; // 歌词当前行
  const subs = new Map();

  const emit = (type, data) => {
    const set = subs.get(type);
    if (set) set.forEach((fn) => fn(data));
  };
  const on = (type, fn) => {
    if (!subs.has(type)) subs.set(type, new Set());
    subs.get(type).add(fn);
    return () => subs.get(type).delete(fn);
  };

  const track = () => tracks[index];
  const persist = () => {
    try {
      localStorage.setItem(KEY, String(index));
    } catch {}
  };

  // ---- 歌词 ----
  const loadLyrics = () => {
    const id = track().id;
    lyricsState = 'loading';
    lyrics = { credits: [], lines: [] };
    current = -1;
    emit('lyrics', { state: lyricsState, credits: [], lines: [] });
    fetch(endpoint('lrc', id))
      .then((r) => (r.ok ? r.text() : ''))
      .then((text) => {
        if (track().id !== id) return; // 切歌了，丢弃旧结果
        const parsed = text ? parseLrc(text) : { credits: [], lines: [] };
        lyrics = parsed;
        lyricsState = parsed.lines.length ? 'ready' : 'none';
        emit('lyrics', { state: lyricsState, ...parsed });
      })
      .catch(() => {
        if (track().id !== id) return;
        lyricsState = 'none';
        emit('lyrics', { state: lyricsState, credits: [], lines: [] });
      });
  };

  // ---- 切歌 ----
  const load = (next, autoplay) => {
    index = ((next % tracks.length) + tracks.length) % tracks.length;
    persist();
    const t = track();
    audio.src = endpoint('url', t.id);
    current = -1;
    loadLyrics();
    emit('track', { index, track: t });
    if (autoplay) {
      // play 失败（接口没给这首）交给 error 事件说明
      audio.play().catch(() => emit('state', 'error'));
    } else {
      emit('state', 'idle');
    }
  };

  // 公共接口没登录态时，有些歌只回一段试听；拿它跟 tracks 里记的整首时长比就知道是不是残的
  const short = (dur) => {
    const whole = track().dur;
    return Number.isFinite(dur) && dur > 0 && Number.isFinite(whole) && dur + 8 < whole;
  };

  audio.addEventListener('play', () => emit('state', 'playing'));
  audio.addEventListener('pause', () => emit('state', 'paused'));
  audio.addEventListener('waiting', () => emit('state', 'loading'));
  audio.addEventListener('playing', () => emit('state', 'playing'));
  audio.addEventListener('error', () => emit('state', 'error'));
  audio.addEventListener('loadedmetadata', () =>
    emit('time', { cur: audio.currentTime, dur: audio.duration, ratio: 0, short: short(audio.duration) })
  );
  audio.addEventListener('timeupdate', () => {
    const dur = audio.duration;
    emit('time', {
      cur: audio.currentTime,
      dur,
      ratio: Number.isFinite(dur) && dur > 0 ? audio.currentTime / dur : 0,
      short: short(dur),
    });
    if (lyricsState === 'ready' && lyrics.lines.length) {
      let hit = -1;
      for (let i = 0; i < lyrics.lines.length; i += 1) {
        if (lyrics.lines[i].t <= audio.currentTime + 0.15) hit = i;
        else break;
      }
      if (hit !== current) {
        current = hit;
        emit('line', hit);
      }
    }
  });
  audio.addEventListener('ended', () => load(index + 1, true));

  return {
    audio,
    fmt,
    get index() {
      return index;
    },
    get track() {
      return track();
    },
    get state() {
      return audio.paused ? 'paused' : 'playing';
    },
    get lyricsState() {
      return lyricsState;
    },
    get lyrics() {
      return lyrics;
    },
    on,
    init: () => {
      emit('track', { index, track: track() });
      emit('state', 'idle');
      loadLyrics();
    },
    toggle: () => {
      if (!audio.src) {
        load(index, true);
        return;
      }
      if (audio.paused) audio.play().catch(() => emit('state', 'error'));
      else audio.pause();
    },
    next: () => load(index + 1, true),
    prev: () => load(index - 1, true),
    pick: (i) => load(i, true),
    // 传来的是 0–1 的比例
    seek: (ratio) => {
      if (!audio.src) return;
      const dur = audio.duration;
      if (!Number.isFinite(dur) || dur <= 0) return;
      audio.currentTime = Math.max(0, Math.min(dur - 0.2, dur * ratio));
    },
    bump: (seconds) => {
      if (!audio.src) return;
      const dur = audio.duration;
      if (!Number.isFinite(dur) || dur <= 0) return;
      audio.currentTime = Math.max(0, Math.min(dur - 0.2, audio.currentTime + seconds));
    },
  };
}
