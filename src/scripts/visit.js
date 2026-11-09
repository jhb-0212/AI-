// 访客采集：每打开一个页面，往后台打一条。
// 开关和地址由 Base.astro 通过 window.__VISIT 注入（构建时读 PUBLIC_VISIT_ENDPOINT）。
// 设计取舍：
// - 发 text/plain 的 JSON 字符串，跨域也不触发 CORS 预检；
// - 同一天同一路径只发一次（localStorage 记账），不给库灌无意义的重复；
// - 尊重 Do Not Track；后台自己的页面 / 接口不发；
// - 等 800ms 再发，不跟首屏抢带宽。
(function () {
  var cfg = window.__VISIT || {};
  if (!cfg.on || !cfg.endpoint) return;
  if (navigator.doNotTrack === '1' || window.doNotTrack === '1') return;

  var path = location.pathname;
  if (path.indexOf('/admin') === 0 || path.indexOf('/api') === 0) return;

  var day = new Date().toISOString().slice(0, 10);
  var key = 'nepenthe:visit:' + day + ':' + path;
  try {
    if (localStorage.getItem(key)) return;
  } catch (err) {}

  function send() {
    var payload = JSON.stringify({
      path: path,
      ref: document.referrer ? document.referrer.split('/')[2] || '' : '',
    });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(cfg.endpoint, new Blob([payload], { type: 'text/plain;charset=UTF-8' }));
      } else {
        fetch(cfg.endpoint, {
          method: 'POST',
          body: payload,
          headers: { 'content-type': 'text/plain;charset=UTF-8' },
          keepalive: true,
        });
      }
      localStorage.setItem(key, '1');
    } catch (err) {}
  }

  if (document.visibilityState === 'hidden') return;
  setTimeout(send, 800);
})();
