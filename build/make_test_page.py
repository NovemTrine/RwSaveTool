"""生成端到端测试页：给界面注入「假桥接」+ 真实导入数据，用无头浏览器验证。

用法：
    python build/make_test_page.py            # 生成 _test/rw_test.html
然后：
    cd _test && python -m http.server 8801
    chrome --headless ... "http://127.0.0.1:8801/rw_test.html#regions"

支持的 hash：
    overview / regions / items / global
    regions-all      区域页 + 完成度口径切到「含附加」
    regions-sorted   区域页 + 按完成度排序
    modal            区域数据管理
    map:RF           地图（RF）
    map:GW           地图（GW，多图层）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import region_store  # noqa: E402

SAVE_SOURCE = os.path.join(os.path.dirname(ROOT), "sav")
TEST_DIR = os.path.join(ROOT, "_test")

FAKE_BRIDGE = """
<script>
(function(){
  function P(v){ return Promise.resolve(v); }
  var FIXTURE = __FIXTURE__;
  function findLayer(code, layerId){
    var d = FIXTURE.details[code];
    if (!d || !d.layers) return null;
    for (var i = 0; i < d.layers.length; i++){
      if (d.layers[i].id === layerId) return d.layers[i];
    }
    return d.layers[0] || null;
  }
  window.pywebview = { api: {
    app_info: function(){ return P({dataDir:'D:/.../RwSaveTool/region_data',
      defaultSaveDir:'<USERPROFILE>/AppData/LocalLow/Videocult/Rain World'}); },
    config: function(){ return P({ui:{regionSort:'code',regionSortDir:'asc'}}); },
    save_config: function(){ return P({}); },
    list_slots: function(){ return P([{name:'sav',path:'sav',size:12580864,
      mtime:0,mtimeText:'2026-10-31 14:00'}]); },
    read_save: function(){ return P({ok:false,error:'test uses __rwTest hook'}); },
    regions: function(){ return P(FIXTURE.summary); },
    region_detail: function(code){ return P({ok:true, region: FIXTURE.details[code]}); },
    game_info: function(){ return P(FIXTURE.game); },
    map_image: function(code, layerId){
      var L = findLayer(code, layerId);
      var path = L && L.map && L.map.imagePath;
      if (!path) return P({ok:false, error:'no map'});
      return fetch(path).then(function(r){ return r.blob(); })
        .then(function(b){ return new Promise(function(res){ var fr = new FileReader();
          fr.onload = function(){ res({ok:true, dataUrl:fr.result,
            width:(L.map.width||0), height:(L.map.height||0), layerId:L.id}); };
          fr.readAsDataURL(b); }); });
    },
    delete_region: function(){ return P({ok:true}); },
    delete_layer: function(){ return P({ok:true}); },
    open_data_dir: function(){ return P({ok:true,path:'D:/...'}); },
    pick_mod_dir: function(){ return P({canceled:true}); },
    pick_game_dir: function(){ return P({canceled:true}); },
    import_mod_path: function(){ return P({ok:true,saved:[],mods:[],warnings:[]}); },
    import_official_path: function(){ return P({ok:true,saved:[],warnings:[]}); }
  }};
})();
</script>
"""

HOOK = """  window.__rwTest = function(text){
    state.file = { name:'sav', size: text.length };
    var res = parseSaveMain(text, function(){});
    finish(res);
  };
  window.__rwOpenRegions = function(){ openRegionsModal(); };
  window.__rwOpenMap = function(code){ openMap(code); };
  window.__setMode = function(m){
    state.completionMode = m;
    if (state.result) computeCompletions(state.result);
    renderDetail();
  };
  setTimeout(function(){
    fetch('sav').then(function(r){ return r.text(); }).then(function(t){
      window.__rwTest(t);
      var h = (location.hash || '').replace('#','');
      function openTab(name){
        setTimeout(function(){
          var tab = document.querySelector('[data-tab="' + name + '"]');
          if (tab) tab.click();
        }, 150);
      }
      if (h === 'regions' || h === 'overview' || h === 'items' || h === 'global'){ openTab(h); }
      else if (h === 'regions-all'){
        openTab('regions');
        setTimeout(function(){ window.__setMode('all'); }, 260);
      }
      else if (h === 'regions-sorted'){
        openTab('regions');
        setTimeout(function(){
          var b = document.querySelector('[data-sort="completion"]');
          if (b) b.click();
        }, 260);
      }
      else if (h === 'modal'){ setTimeout(window.__rwOpenRegions, 220); }
      else if (h.indexOf('map:') === 0){
        var code = h.split(':')[1] || 'RF';
        setTimeout(function(){ window.__rwOpenMap(code); }, 220);
      }
    });
  }, 500);
  // 初始聚焦拖拽区"""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name))


def build() -> str:
    os.makedirs(TEST_DIR, exist_ok=True)
    summary = region_store.summary()
    details = {}
    for item in summary:
        region = region_store.get_region(item["code"])
        if not region:
            continue
        for layer in region.get("layers") or []:
            map_info = layer.get("map") or {}
            src = map_info.get("imagePath")
            if src and os.path.isfile(src):
                local = "map_%s_%s.png" % (item["code"], _safe(layer.get("id")))
                target = os.path.join(TEST_DIR, local)
                if not os.path.isfile(target) or os.path.getsize(target) != os.path.getsize(src):
                    shutil.copy(src, target)
                map_info["imagePath"] = local
        details[item["code"]] = region

    fixture = json.dumps(
        {
            "summary": summary,
            "details": details,
            "game": {
                "ok": True,
                "root": "<STEAM_LIBRARY>/steamapps/common/Rain World",
                "regionCount": len(summary),
                "packs": [
                    {"id": "official:base", "label": "游戏原版", "regions": 12},
                    {"id": "official:moreslugcats", "label": "Downpour（倾盆大雨）", "regions": 10},
                    {"id": "official:watcher", "label": "The Watcher（观望者）", "regions": 30},
                ],
            },
        },
        ensure_ascii=False,
    )

    html = open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8").read()
    html = html.replace("<body>", "<body>\n" + FAKE_BRIDGE.replace("__FIXTURE__", fixture), 1)
    html = html.replace("  // 初始聚焦拖拽区", HOOK, 1)

    out = os.path.join(TEST_DIR, "rw_test.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    if os.path.isfile(SAVE_SOURCE):
        shutil.copy(SAVE_SOURCE, os.path.join(TEST_DIR, "sav"))
    return out


if __name__ == "__main__":
    path = build()
    print("测试页：", path, os.path.getsize(path), "bytes")
