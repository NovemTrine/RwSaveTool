  /* ---------------- 几何图（W1-f）----------------
     与方块图是**两张不同的图**，不共用坐标系：
       · 方块图 = `map`（map_image 那张压扁的图标画布），按层分，能挂探索/珍珠/庇护所标记；
       · 几何图 = regmap 的排布结果，整区一间房不落，按真实尺寸画地形、覆盖物与贝塞尔连线。
     SVG 由后端 `regmap_svg` 拼好直接塞进来——页面看到的和导出的是同一份，不会走形。

     三件要紧的事：
     1. **缩放改 viewBox，不改 CSS transform。** transform:scale() 放大的是已经栅格化的
        位图，越放越糊；改 viewBox 让浏览器按新视口重新矢量化，放到十几倍还是锐的。
     2. **配色走 CSS 变量。** SVG 里每个元素是 `fill:var(--rg-air,#75ced5)`，页面只要在容器上
        改变量就能换色，不用重算、不用重传 0.4–1.4 MB 的字符串。
     3. **放大到 2.2 倍再换高清层**：默认密度 2，`vb.w < W/2.2` 时向后端再要一份密度 4 的，
        坐标空间完全相同，只换 <svg> 元素、viewBox 不动。 */

  /* 与 `core/regmap/svg.py` 的 PALETTE 一致：单独打开 SVG 文件时的兜底色。
     页面里的**默认色**不取这里，而是跟随房间卡配色（见 regmapDefaults）。 */
  var RG_FALLBACK = {
    sheet: '#0a0d12', air: '#75ced5', solid: '#1a2031', c: '#3f7f88', b: '#d5f4f7',
    p: '#e8c65a', x: '#5ec46e', d: '#c07ae0', k: '#6f9bff', s: '#2b3444',
    link: '#3f6f7a', door: '#9fe8ef'
  };
  var RG_ITEMS = [
    ['sheet', '区域背景'], ['air', '可通行'], ['solid', '岩壁'], ['c', '背景结构'],
    ['b', '杆子'], ['p', '管道'], ['x', '通道入口'], ['d', '巢穴'],
    ['k', '生物通道'], ['s', '斜面'], ['link', '连线'], ['door', '门点']
  ];

  /* 默认配色 = 房间卡那套（同一主题同一份）；没有对应项的两项保留自己的兜底 */
  function regmapDefaults(){
    var rp = roomPaletteOf(state.theme);
    return {
      sheet: '#0b0d11',
      air: rp.air, solid: rp.solid, s: rp.slope, c: rp.climb,
      p: rp.pipe, b: rp.beam, x: rp.exit, d: rp.den, k: rp.creature,
      link: RG_FALLBACK.link, door: RG_FALLBACK.door
    };
  }
  function regmapColorsOf(code){
    var base = regmapDefaults();
    var custom = (state.regmapColors || {})[String(code || '').toUpperCase()] || {};
    var out = {};
    RG_ITEMS.forEach(function(it){ out[it[0]] = custom[it[0]] || base[it[0]]; });
    return out;
  }
  function paintRegmapColors(el, code){
    var pal = regmapColorsOf(code);
    RG_ITEMS.forEach(function(it){ el.style.setProperty('--rg-' + it[0], pal[it[0]]); });
  }
  function saveRegmapColors(){
    if (!hasBridge()) return;
    bridgeCall('save_config', { ui: { regmapColors: state.regmapColors } }).catch(function(){});
  }

  /* ---- 配色弹窗：跟房间卡「配色」同一个壳，但按区域存 ---- */
  var rgCtx = null;
  function rgRender(){
    if (!rgCtx) return;
    var code = rgCtx.code;
    var pal = regmapColorsOf(code);
    var custom = (state.regmapColors || {})[code] || {};
    $('rg-title').textContent = '· ' + code;
    $('rg-note').textContent = '只影响 ' + code + '；默认跟随房间卡配色';
    $('rg-grid').innerHTML = RG_ITEMS.map(function(it){
      var v = pal[it[0]];
      return '<label class="rp-item"><input type="color" data-rgk="' + it[0] + '" value="' + v +
        '"><span>' + esc(it[1]) + '</span>' +
        (custom[it[0]] ? '<span class="rp-off">改</span>' : '') +
        '<span class="rp-hex">' + esc(v) + '</span></label>';
    }).join('');
    Array.prototype.forEach.call($('rg-grid').querySelectorAll('[data-rgk]'), function(inp){
      inp.addEventListener('input', function(){
        var k = inp.getAttribute('data-rgk');
        if (!state.regmapColors) state.regmapColors = {};
        if (!state.regmapColors[code]) state.regmapColors[code] = {};
        state.regmapColors[code][k] = inp.value;
        if (rgCtx.wrap) rgCtx.wrap.style.setProperty('--rg-' + k, inp.value);
        var hex = inp.parentNode.querySelector('.rp-hex');
        if (hex) hex.textContent = inp.value;
      });
      inp.addEventListener('change', function(){ saveRegmapColors(); rgRender(); });
    });
  }
  function openRegmapPalette(code, wrap){
    rgCtx = { code: String(code || '').toUpperCase(), wrap: wrap };
    $('rg-modal').hidden = false;
    rgRender();
  }
  function closeRegmapPalette(){ $('rg-modal').hidden = true; }
  if ($('rg-close')) $('rg-close').addEventListener('click', closeRegmapPalette);
  if ($('rg-modal')) $('rg-modal').addEventListener('click', function(e){
    if (e.target === $('rg-modal')) closeRegmapPalette();
  });
  if ($('rg-reset')) $('rg-reset').addEventListener('click', function(){
    if (!rgCtx) return;
    if (state.regmapColors) delete state.regmapColors[rgCtx.code];
    if (rgCtx.wrap) paintRegmapColors(rgCtx.wrap, rgCtx.code);
    saveRegmapColors();
    rgRender();
  });

  function openMapGeo(code){
    if (!hasBridge()){ toast('几何图要算布局，得有桌面壳'); return; }

    var KEY = String(code).toUpperCase();
    var campaign = currentCampaign();
    var slugcat = campaign ? campaign.slugcat : '';
    var visited = {};
    if (campaign){
      (campaign.regions || []).forEach(function(rg){
        if (String(rg.name).toUpperCase() !== KEY) return;
        (rg.roomList || []).forEach(function(n){ visited[String(n).toUpperCase()] = 1; });
      });
    }

    /* 图例色块直接用变量：改配色时它跟着变，不用重画 */
    var legend = '<div class="geo-legend">' + RG_ITEMS.slice(1, 10).map(function(it){
      return '<span><i style="background:var(--rg-' + it[0] + ',' + RG_FALLBACK[it[0]] + ')"></i>' +
        it[1] + '</span>';
    }).join('') + '</div>';

    var html = '<div class="map-wrap" id="geo-wrap"><div class="map-main">' +
      '<div class="map-tools">' +
        '<span class="mlabel">几何排布</span>' +
        '<button class="btn ghost" id="geo-back" type="button">← 方块图</button>' +
        '<button class="btn ghost" id="geo-pal" type="button" title="这个区域的配色，默认跟随房间卡">配色</button>' +
        '<span class="map-hint" id="geo-meta">正在算布局…</span>' +
      '</div>' +
      '<div class="geo-stage" id="geo-stage">' +
        '<div class="geo-hold" id="geo-hold">正在算布局…<br>大区域要几秒</div>' +
        '<div class="map-zoom" id="geo-zoom">' +
          '<button type="button" data-gz="out" title="缩小（滚轮下滚）">−</button>' +
          '<span id="geo-pct">100%</span>' +
          '<button type="button" data-gz="in" title="放大（滚轮上滚）">+</button>' +
          '<button type="button" data-gz="fit" title="整图铺满">适应</button>' +
        '</div>' +
      '</div>' +
      '</div>' +
      '<aside class="map-side">' + legend +
        '<div class="geo-note">' +
          '<b>这张图是算出来的</b>：房间按真实尺寸画地形，房间之间用三次贝塞尔连线，' +
          '线压在房间下面，只在缝里露出来。<br>' +
          '<b>未探索</b>的房间会压暗（跟随存档）。<br>' +
          '<b>放大 2 倍以上</b>会自动换一版更细的矢量图。<br>' +
          '点击房间开布局卡 · 滚轮缩放 · 拖拽平移 · 双击空白复位。' +
        '</div>' +
      '</aside></div>';

    openModal('区域地图 · ' + code + ' · 几何', rd_sub_of(code), html, false, true);

    var wrap = $('geo-wrap'), stage = $('geo-stage'), hold = $('geo-hold');
    var metaEl = $('geo-meta'), pctEl = $('geo-pct');
    paintRegmapColors(wrap, KEY);

    var palBtn = $('geo-pal');
    if (palBtn) palBtn.addEventListener('click', function(){ openRegmapPalette(KEY, wrap); });

    var backBtn = $('geo-back');
    if (backBtn) backBtn.addEventListener('click', function(){ openMap(code); });

    /* ---- 缩放 / 平移：改 viewBox（改 transform 会糊） ---- */
    var svgEl = null, W = 0, H = 0, baseW = 0;
    var vb = { x: 0, y: 0, w: 1, h: 1 };
    var hi = { loaded: false, busy: false, timer: 0 };

    function stageSize(){
      var b = stage.getBoundingClientRect();
      return { w: Math.max(1, b.width), h: Math.max(1, b.height) };
    }
    function applyVB(){
      if (!svgEl) return;
      svgEl.setAttribute('viewBox', vb.x.toFixed(2) + ' ' + vb.y.toFixed(2) + ' ' +
        vb.w.toFixed(2) + ' ' + vb.h.toFixed(2));
      if (pctEl && baseW) pctEl.textContent = Math.round(baseW / vb.w * 100) + '%';
      /* 放大够了才值得换高清：等滚轮停下来再问，免得一路拖一路请求 */
      if (hi.timer) clearTimeout(hi.timer);
      hi.timer = setTimeout(maybeHiRes, 420);
    }
    function fitVB(){
      if (!svgEl) return;
      var s = stageSize();
      var k = Math.min(s.w / W, s.h / H);
      var w = s.w / k, h = s.h / k;
      baseW = w;
      vb = { x: (W - w) / 2, y: (H - h) / 2, w: w, h: h };
      applyVB();
    }
    function zoomAt(px, py, f){
      if (!svgEl) return;
      var s = stageSize();
      var ux = vb.x + px / s.w * vb.w, uy = vb.y + py / s.h * vb.h;
      var w2 = Math.max(W / 40, Math.min(W * 1.8, vb.w / f));
      var h2 = w2 * (s.h / s.w);
      vb = { x: ux - px / s.w * w2, y: uy - py / s.h * h2, w: w2, h: h2 };
      applyVB();
    }

    function markDim(){
      var nSeen = 0, nAll = 0;
      Array.prototype.forEach.call(stage.querySelectorAll('.rm'), function(g){
        var nm = g.getAttribute('data-room') || '';
        var seen = roomSeen(code, nm, !!visited[String(nm).toUpperCase()]);
        nAll++;
        if (seen){ g.classList.remove('dim'); nSeen++; } else g.classList.add('dim');
      });
      return { seen: nSeen, all: nAll };
    }
    function setMeta(extra){
      if (!metaEl) return;
      var c = markDim();
      metaEl.textContent = c.all + ' 间 · 已探索 ' + c.seen + '/' + c.all + (extra || '');
    }

    function loadSvg(r, keepView){
      var old = stage.querySelector('svg');
      if (old) old.parentNode.removeChild(old);
      stage.insertAdjacentHTML('beforeend', r.svg);
      svgEl = stage.querySelector('svg');
      if (!svgEl) return false;
      svgEl.classList.add('geo-svg');
      W = r.w; H = r.h;
      if (keepView) applyVB(); else fitVB();
      return true;
    }

    function maybeHiRes(){
      if (hi.loaded || hi.busy || !svgEl) return;
      if (!document.getElementById('geo-stage')) return;
      if (!(baseW && vb.w < W / 2.2)) return;         /* 没放大到 2.2 倍就别折腾 */
      hi.busy = true;
      var seqW = W;
      bridgeCall('regmap_svg', code, slugcat || '', null, 2400, false, 4).then(function(r2){
        hi.busy = false;
        if (!r2 || !r2.ok || W !== seqW) return;
        if (!document.getElementById('geo-stage')) return;
        if (!loadSvg(r2, true)) return;
        hi.loaded = true;
        setMeta(' · 高清 ' + (r2.bytes / 1024).toFixed(0) + ' KB');
      }, function(){ hi.busy = false; });
    }

    stage.addEventListener('wheel', function(ev){
      if (!svgEl || !ev.deltaY) return;
      ev.preventDefault();
      var b = stage.getBoundingClientRect();
      zoomAt(ev.clientX - b.left, ev.clientY - b.top, Math.pow(1.0022, -ev.deltaY));
    }, { passive: false });

    var drag = null;
    function onMove(ev){
      if (!drag) return;
      var dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
      drag.moved = true;
      stage.classList.add('dragging');
      var s = stageSize();
      vb.x -= dx / s.w * vb.w;
      vb.y -= dy / s.h * vb.h;
      drag.sx = ev.clientX; drag.sy = ev.clientY;
      applyVB();
    }
    function onUp(){
      stage.classList.remove('dragging');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      setTimeout(function(){ drag = null; }, 0);   /* click 比 setTimeout 先到，吃掉这次点击 */
    }
    stage.addEventListener('mousedown', function(ev){
      if (ev.button !== 0 || !svgEl) return;
      if (ev.target.closest && ev.target.closest('.map-zoom')) return;
      ev.preventDefault();
      drag = { sx: ev.clientX, sy: ev.clientY, moved: false };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
    stage.addEventListener('click', function(ev){
      if (drag && drag.moved) return;                 /* 拖完不算点击 */
      var t = ev.target;
      while (t && t !== stage && !(t.getAttribute && t.getAttribute('data-room'))) t = t.parentNode;
      if (t && t !== stage) openRoomCard(code, t.getAttribute('data-room'));
    });
    stage.addEventListener('dblclick', fitVB);

    Array.prototype.forEach.call(document.querySelectorAll('#geo-zoom [data-gz]'), function(btn){
      btn.addEventListener('click', function(){
        var act = btn.getAttribute('data-gz');
        if (act === 'fit'){ fitVB(); return; }
        var s = stageSize();
        zoomAt(s.w / 2, s.h / 2, act === 'in' ? 1.45 : 1 / 1.45);
      });
    });

    var onResize = function(){
      if (!document.getElementById('geo-stage')){ window.removeEventListener('resize', onResize); return; }
      if (baseW && Math.abs(vb.w - baseW) < 0.5) fitVB();   /* 只在"没放大"时重排 */
    };
    window.addEventListener('resize', onResize);

    bridgeCall('regmap_svg', code, slugcat || '', null, 2400, false).then(function(r){
      if (!r || !r.ok){
        hold.classList.add('err');
        hold.innerHTML = '这个区域算不出来：' + esc((r && (r.error || r.detail)) || '未知错误') +
          '<br><span style="opacity:.7">可能是房间文件缺失或区域没有可排布的房间</span>';
        return;
      }
      hold.style.display = 'none';
      if (!loadSvg(r, false)){ hold.style.display = ''; hold.textContent = 'SVG 插入失败'; return; }
      setMeta(' · ' + r.links + ' 边');
    }, function(){
      hold.classList.add('err');
      hold.textContent = '桥接调用失败（后端没起来？）';
    });
  }

