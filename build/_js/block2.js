
(function(){
  'use strict';

  var PARSER_SRC = document.getElementById('parser-source').textContent;

  var WORKER_GLUE = "\nself.onmessage = function(e){\n" +
    "  try{\n" +
    "    var res = parseSave(e.data.raw, function(stage, pct, detail){\n" +
    "      self.postMessage({ type:'progress', stage:stage, pct:pct, detail:detail||'' });\n" +
    "    });\n" +
    "    self.postMessage({ type:'done', result:res });\n" +
    "  }catch(err){\n" +
    "    self.postMessage({ type:'error', message:(err && err.message) || String(err), stack:(err && err.stack) || '' });\n" +
    "  }\n" +
    "};\n";

  var parseSaveMain = new Function(PARSER_SRC + '\nreturn parseSave;')();

  /* ---------------- 名称映射 ---------------- */
  var SLUGCAT_ZH = {White:'幸存者',Yellow:'僧侣',Red:'猎手',Gourmand:'美食家',Artificer:'工匠',
    Rivulet:'溪流',Spear:'长矛大师',Saint:'圣徒',Inv:'邀请',Watcher:'守望者',Void:'虚空'};
  /* 区域缩写 → [中文, English]，逐行转录自 5 张对照表截图（100 条，region_map.json） */
  var REGION_MAP = {
    "55":["荒凉街道","Barren Streets"],
    "AB":["干旱荒原","Arid Barrens"],
    "BI":["生物工程中心","Bioengineering Center"],
    "BL":["恶地","Badlands"],
    "BPL":["黑色管道 7","Black Pipeline VII"],
    "CC":["烟囱天棚","Chimney Canopy"],
    "CL":["无声构造","Silent Construct"],
    "CW":["追逐清风","Chasing Wind"],
    "DC":["排水渠","Drainage Canal"],
    "DM":["仰望皓月","Looks to the Moon"],
    "DS":["排水系统","Drainage System"],
    "ER":["蚀化炼油厂","Eroded Refinery"],
    "EU":["夜光海湾","Luminous Cove"],
    "FO":["雾谷","Fog Gulch"],
    "FS":["远岸","Far Shore"],
    "FT":["遗弃车站","Forsaken Station"],
    "GH":["悬苑","Hanging Gardens"],
    "GS":["镀金圣殿","Gilded Sanctuary"],
    "GU":["荒芜都市","Gray Urban"],
    "GW":["垃圾堆","Garbage Wastes"],
    "HC":["嚎叫裂隙","Howling Rift"],
    "HH":["神圣洞穴","Hallowed Grotto"],
    "HI":["工业区","Industrial Complex"],
    "HR":["魔方节点","Rubicon"],
    "IP":["辅助取水口","Auxiliary Intake"],
    "JJ":["凌霄望台","Soaring Lookout"],
    "KF":["古风设施","Archaic Facility"],
    "LC":["大都会","Metropolis"],
    "LF":["农场阵列","Farm Arrays"],
    "LH":["月球大道","Lunar Byway"],
    "LM":["海滨设施","Waterfront Facility"],
    "LW":["葱郁沼泽","Lush Mire"],
    "M1":["畸变蔓延","Metastasis"],
    "MF":["苔藓田野","Moss Fields"],
    "MS":["沉没巨构","Submerged Superstructure"],
    "NP":["墓地","Necropolis"],
    "O7":["荒芜都市","Overgrown Urban"],
    "OA":["渡槽","Aqueducts"],
    "OE":["外层空间","Outer Expanse"],
    "PA":["朝圣天路","Pilgrims' Ascent"],
    "PV":["保护区","Preservatory"],
    "QL":["灰烬弓湾","Ashen Bow"],
    "RF":["珊瑚洞穴","Coral Caves"],
    "RGN":["雨中花园","Rain Garden"],
    "RM":["腐化之地","The Rot"],
    "RTAA":["附属区域","The Annex"],
    "SB":["地底","Subterranean"],
    "SC":["圣园","Sacred Garden"],
    "SD":["焦土区","Scorched District"],
    "SE":["蒸汽大厦","Steaming Edifice"],
    "SEC":["隐蔽幽径","Secluded Pass"],
    "SH":["阴影城堡","Shaded Citadel"],
    "SI":["天空群岛","Sky Islands"],
    "SK":["风暴海岸","Stormy Coast"],
    "SL":["海岸线","Shoreline"],
    "SP":["阳光发电厂","Sunlit Power Plant"],
    "SS":["五块卵石","Five Pebbles"],
    "SU":["郊区","Outskirts"],
    "TL":["地铁","Subway"],
    "TM":["诡杆","The Mast"],
    "TX":["地下通道","Underpass"],
    "UB":["腹底暗域","Underbelly"],
    "UF":["灼热下水道","Sizzling Sewers"],
    "UG":["地下森林","Underground"],
    "US":["海底","Undersea"],
    "UU":["城堡","Citadel"],
    "UW":["外缘","The Exterior"],
    "VS":["管道堆场","Pipeyard"],
    "WARA":["破碎露台","Shattered Terrace"],
    "WARB":["盐化区","Salination"],
    "WARC":["腐臭幽谷","Fetid Glen"],
    "WARD":["冷库","Cold Storage"],
    "WARE":["供热管道","Heat Ducts"],
    "WARF":["以太山脊","Aether Ridge"],
    "WARG":["表面","The Surface"],
    "WAUA":["上古城市","Ancient Urban"],
    "WBLA":["不毛之地","Badlands"],
    "WCSA":["城市天际线","City Skyline"],
    "WDSR":["衰败隧道","Decaying Tunnels"],
    "WGWR":["受浸染的废土","Infested Wastes"],
    "WHTR":["腐化工厂","Corrupted Factories"],
    "WMPA":["迁徙之路","Migration Path"],
    "WORA":["外缘（观望者）","Outer Rim"],
    "WPGA":["柱林","Pillar Grove"],
    "WPTA":["信号尖塔","Signal Spires"],
    "WRFA":["珊瑚洞穴","Coral Caves"],
    "WRFB":["涡流泵","Turbulent Pump"],
    "WRRA":["锈蚀残骸","Rusted Wrecks"],
    "WRSA":["间域","daemon"],
    "WSKA":["暴雨铁路","Torrential Railways"],
    "WSKB":["曝日巷","Sunbaked Alley"],
    "WSKC":["风暴海岸","Stormy Coast"],
    "WSKD":["隐蔽堆层","Shrouded Stacks"],
    "WSSR":["不幸演化","Unfortunate Evolution"],
    "WSUR":["欲坠边缘","Crumbling Fringes"],
    "WTDA":["炎热沙漠","Torrid Desert"],
    "WTDB":["凄凉地带","Desolate Tract"],
    "WVWA":["翠绿水道","Verdant Waterways"],
    "WVWB":["断裂通道","Fractured Gateways"],
    "ZZ":["天线阵列","Aerial Arrays"]
  };
  /* 通行证内置译名。键是存档里的原始键：注意「The Wanderer（漫游者）」在本程序里叫 Traveller
     —— 存档里根本没有 Wanderer 这个键（实测 0 次），两边 14 条恰好只差这一对。改名前务必确认。 */
  var PASSAGE_ZH = {Traveller:'漫游者',Survivor:'求生者',Monk:'僧侣',Hunter:'猎手',Saint:'圣徒',
    Chieftain:'酋长',DragonSlayer:'屠龙者',Pilgrim:'朝圣者',Mother:'慈母',Friend:'朋友',Scholar:'学者',Outlaw:'暴徒',Martyr:'殉道者',Nomad:'流浪者'};
  var COMMUNITY_ZH = {All:'全部',Scavengers:'拾荒者',Lizards:'蜥蜴',Cicadas:'蝉乌贼',GarbageWorms:'垃圾虫',
    Deer:'雨鹿',JetFish:'蛙鱼',BoxWorms:'箱虫',TintedBeetles:'染色甲虫'};

  /* 击杀生物中文名（金蜥蜴 / 光鼠 / 蝉乌贼等已按最终确认定案；模组生物为暂定译名） */
  var CREATURE_ZH = {
    Fly:'蝠蝇', SmallCentipede:'幼年蜈蚣', Centipede:'蜈蚣', Centiwing:'飞蜈蚣', RedCentipede:'烈焰蜈蚣',
    PoleMimic:'拟态草', MonsterKelp:'红树', WormGrass:'舌草',
    WhiteLizard:'白蜥蜴', BlueLizard:'蓝蜥蜴', PinkLizard:'粉蜥蜴', GreenLizard:'绿蜥蜴',
    BlackLizard:'黑蜥蜴', YellowLizard:'金蜥蜴', Salamander:'蝾螈', RedLizard:'烈焰蜥蜴', CyanLizard:'青蜥蜴',
    CaramelLizard:'焦糖蜥蜴', EelLizard:'鳗蜥蜴', StrawberryLizard:'草莓蜥蜴', TrainLizard:'火车蜥蜴',
    BasiliskLizard:'蛇怪蜥蜴', BlizzardLizard:'暴雪蜥蜴', IndigoLizard:'靛蓝蜥蜴', PeachLizard:'桃蜥蜴',
    Snail:'波动龟', CicadaA:'蝉乌贼', CicadaB:'蝉乌贼', EggBug:'蛋虫', LanternMouse:'光鼠',
    BigSpider:'狼蛛', SpitterSpider:'烈焰狼蛛', Spiders:'小蜘蛛', Coalescipede:'小蜘蛛',
    DropBug:'落网虫', BigNeedleWorm:'成年面条蝇', SmallNeedleWorm:'幼年面条蝇',
    VultureGrub:'射线虫', Hazer:'墨鱼', Overseer:'监视者', JetFish:'蛙鱼', Inspector:'监察者',
    Scavenger:'拾荒者', EliteScavenger:'精英拾荒者', ScavengerTemplar:'拾荒者圣堂武士',
    ScavengerDisciple:'拾荒者门徒', ScavengerTrader:'拾荒者商人',
    GarbageWorm:'垃圾虫', Deer:'雨鹿', Yeek:'跃客', Aquapede:'水蜈蚣', JungleLeech:'丛林水蛭',
    Vulture:'秃鹫', KingVulture:'魔王鹫', MirosBird:'钢鸟', MirosVulture:'钢秃鹫', Leviathan:'利维坦',
    BigMoth:'大蛾', SmallMoth:'小蛾', Firebug:'火虫', Stowaway:'偷渡者', MotherSpider:'蛛母',
    /* 模组生物：暂无官方译名，按词义暂定 */
    SilverLizard:'银蜥蜴', Gecko:'壁虎', BabyCroaker:'幼蛙', Polliwog:'蝌蚪',
    MoleSalamander:'鼹螈', ExplodingMosquito:'爆裂蚊', AngryMosquito:'愤怒蚊', Mosquito:'蚊子',
    TintedBeetle:'染色甲虫', BoxWorm:'箱虫', Bigrub:'大虫', Blizzor:'寒怪'
  };
  /* 同种生物的不同变体后缀标注 */
  var CREATURE_VARIANT_ZH = {CicadaA:'白', CicadaB:'黑'};

  /* ---------------- 分数（剧情模式估算） ----------------
     分值表是 <script id="creature-score"> 里的严格 JSON（单一数据源，
     data/creature_score.json 由 build/sync_score.py 从它生成）。 */
  var CREATURE_SCORE = (function(){
    try {
      var el = document.getElementById('creature-score');
      return JSON.parse(el.textContent);
    } catch(e){ return { mode:'story', scores:{} }; }
  })();

  function scoreEntry(key){
    return (CREATURE_SCORE.scores || {})[String(key)] || null;
  }
  function scoreOf(key){
    var e = scoreEntry(key);
    return e ? (e.score == null ? 0 : e.score) : null;
  }
  function fmtNum(n){
    if (n == null || isNaN(n)) return '—';
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /* ---------------- 自定义译名 ----------------
     内置表是只读的“出厂值”，用户改过的条目存在 region_data/_translations.json，
     读入后覆盖下面这些字典；BASE_ZH 保留出厂值用于「恢复默认」和差异判断。 */
  var BASE_ZH = {
    slugcats: Object.assign({}, SLUGCAT_ZH),
    creatures: Object.assign({}, CREATURE_ZH),
    passages: Object.assign({}, PASSAGE_ZH),
    communities: Object.assign({}, COMMUNITY_ZH),
    regions: (function(){
      var m = {};
      Object.keys(REGION_MAP).forEach(function(k){ m[k] = REGION_MAP[k][0]; });
      return m;
    })()
  };
  var TR = { slugcats:{}, creatures:{}, regions:{}, passages:{}, communities:{} };
  var TR_KINDS = [
    { key:'creatures',   label:'生物' },
    { key:'regions',     label:'区域' },
    { key:'slugcats',    label:'角色' },
    { key:'passages',    label:'通行证' },
    { key:'communities', label:'好感' }
  ];

  function trCount(){
    var n = 0;
    Object.keys(TR).forEach(function(k){ n += Object.keys(TR[k] || {}).length; });
    return n;
  }

  function applyTranslations(data){
    TR = { slugcats:{}, creatures:{}, regions:{}, passages:{}, communities:{} };
    if (data && typeof data === 'object'){
      Object.keys(TR).forEach(function(kind){
        var bucket = data[kind];
        if (!bucket || typeof bucket !== 'object') return;
        Object.keys(bucket).forEach(function(code){
          var value = String(bucket[code] == null ? '' : bucket[code]).trim();
          if (!value) return;
          TR[kind][code] = value;
        });
      });
    }
    /* 先把五张表全部还原成出厂值，再叠加覆盖项 —— 否则「恢复默认」时会残留旧名字 */
    Object.keys(BASE_ZH.slugcats).forEach(function(k){ SLUGCAT_ZH[k] = BASE_ZH.slugcats[k]; });
    Object.keys(BASE_ZH.creatures).forEach(function(k){ CREATURE_ZH[k] = BASE_ZH.creatures[k]; });
    Object.keys(BASE_ZH.passages).forEach(function(k){ PASSAGE_ZH[k] = BASE_ZH.passages[k]; });
    Object.keys(BASE_ZH.communities).forEach(function(k){ COMMUNITY_ZH[k] = BASE_ZH.communities[k]; });
    /* 覆盖进展示用的字典（这些字典是渲染时的唯一来源） */
    Object.keys(TR.slugcats).forEach(function(k){ SLUGCAT_ZH[k] = TR.slugcats[k]; });
    Object.keys(TR.creatures).forEach(function(k){ CREATURE_ZH[k] = TR.creatures[k]; });
    Object.keys(TR.passages).forEach(function(k){ PASSAGE_ZH[k] = TR.passages[k]; });
    Object.keys(TR.communities).forEach(function(k){ COMMUNITY_ZH[k] = TR.communities[k]; });
    Object.keys(BASE_ZH.regions).forEach(function(k){
      if (!REGION_MAP[k]) REGION_MAP[k] = [BASE_ZH.regions[k], ''];
      REGION_MAP[k][0] = BASE_ZH.regions[k];
    });
    Object.keys(TR.regions).forEach(function(k){
      var code = String(k).toUpperCase();
      if (!REGION_MAP[code]) REGION_MAP[code] = [TR.regions[k], ''];
      else REGION_MAP[code][0] = TR.regions[k];
    });
    refreshAfterTranslation();
  }

  /* 译名变化后：重算区域中文名 → 重画侧栏与详情 */
  function refreshAfterTranslation(){
    if (!state.result) return;
    try{ decorateRegions(state.result); }catch(e){}
    try{ computeCompletions(state.result); }catch(e){}
    renderSidebar();
    if (state.selected) renderDetail();
  }

  function loadTranslations(){
    if (!hasBridge()) return Promise.resolve();
    return bridgeCall('translations').then(function(data){
      applyTranslations(data);
    }).catch(function(){});
  }

  function trOptions(kind){
    var out = [];
    if (kind === 'regions'){
      /* 区域这份列表要能覆盖到三类：
         ① 内置对照表里的（有出厂中文名）
         ② 导入了区域数据、但表里没有的（模组 / 变体）→ 用数据里的 DisplayName 当名，base 留空
         ③ 只出现在存档里、既没导入也没内置译名的 → 也要能加译名，否则永远改不了 */
      var seen = {};
      function pushRegion(code, base, en){
        var key = String(code || '').toUpperCase();
        if (!key || seen[key]) return;
        seen[key] = 1;
        out.push({ code: key, base: base || '', en: en || '' });
      }
      Object.keys(BASE_ZH.regions).forEach(function(code){
        var en = (REGION_MAP[code] && REGION_MAP[code][1]) || '';
        pushRegion(code, BASE_ZH.regions[code], en);
      });
      Object.keys(state.regions || {}).forEach(function(code){
        var rd = state.regions[code] || {};
        pushRegion(code, '', rd.displayName || rd.nameZh || '');
      });
      (TR.regions ? Object.keys(TR.regions) : []).forEach(function(code){ pushRegion(code, '', ''); });
      ((state.result && state.result.campaigns) || []).forEach(function(c){
        (c.regions || []).forEach(function(r){ pushRegion(r.name, '', ''); });
        if (c.denRegionAbbr) pushRegion(c.denRegionAbbr, '', '');
      });
      out.sort(function(a, b){ return a.code.localeCompare(b.code); });
      return out;
    }
    if (kind === 'creatures'){
      var seen = {};
      Object.keys(CREATURE_ZH).forEach(function(code){
        seen[code] = 1;
        var e = scoreEntry(code);
        out.push({ code: code, base: CREATURE_ZH[code], en: (e && e.en) || '' });
      });
      Object.keys(CREATURE_SCORE.scores || {}).forEach(function(code){
        if (seen[code]) return;
        var e2 = scoreEntry(code);
        out.push({ code: code, base: (e2 && e2.zh) || '', en: (e2 && e2.en) || '' });
      });
      out.sort(function(a, b){ return a.code.localeCompare(b.code); });
      return out;
    }
    var dict = BASE_ZH[kind] || {};
    Object.keys(dict).sort().forEach(function(code){
      out.push({ code: code, base: dict[code], en: '' });
    });
    return out;
  }

  /* ---------------- 批量翻译：解析 / 匹配 ----------------
     玩家的对照表按「英文名 | 中文」写，条目可能是代码也可能是显示名。
     统一归一化（BOM/全角/大小写/空格标点/前导 the）后建一张索引，就不必为每条规则写特判。
     The Wanderer 在存档里叫 Traveller —— 这个别名必须留着，否则「漫游者」永远匹配不上。 */
  var PASSAGE_ALIAS = { wanderer:'Traveller', traveller:'Traveller' };

  function trNorm(s){
    return String(s == null ? '' : s)
      .replace(/^\uFEFF/, '')
      .replace(/｜/g, '|')
      .trim()
      .toLowerCase()
      .replace(/[^0-9a-z\u4e00-\u9fff]+/g, '')
      .replace(/^the/, '');
  }

  /* 分类 → { 大写代码: 真实代码 } */
  function trCodes(kind){
    var m = {};
    if (kind === 'regions'){
      Object.keys(REGION_MAP).forEach(function(c){ m[String(c).toUpperCase()] = c; });
      Object.keys(state.regions || {}).forEach(function(c){ m[String(c).toUpperCase()] = c; });
      return m;
    }
    if (kind === 'creatures'){
      Object.keys(CREATURE_ZH).forEach(function(c){ m[c] = c; });
      Object.keys((typeof CREATURE_SCORE !== 'undefined' && CREATURE_SCORE && CREATURE_SCORE.scores) || {})
        .forEach(function(c){ m[c] = c; });
      return m;
    }
    Object.keys(BASE_ZH[kind] || {}).forEach(function(c){ m[c] = c; });
    return m;
  }

  /* 一次性把五类的「归一化键 → 代码」索引建好（每次预览建一次，足够快） */
  function trBuildCtx(){
    var ctx = { codes:{}, idx:{} };
    TR_KINDS.forEach(function(k){
      var kind = k.key, codes = trCodes(kind), idx = {};
      ctx.codes[kind] = codes;
      function put(key, code){
        var n = trNorm(key);
        if (!n || n.length < 3) return;          /* 太短的键（All）只认代码精确匹配 */
        if (!(n in idx)) idx[n] = code;
      }
      Object.keys(codes).forEach(function(up){ put(codes[up], codes[up]); });
      if (kind === 'creatures'){
        Object.keys(codes).forEach(function(c){
          var e = scoreEntry(c);
          if (e && e.en) put(e.en, c);
        });
      } else if (kind === 'regions'){
        Object.keys(codes).forEach(function(c){
          var pair = REGION_MAP[c];
          if (pair && pair[1]) put(pair[1], c);
          var rd = (state.regions || {})[c];
          if (rd){ put(rd.displayName || '', c); put(rd.nameEn || '', c); }
        });
      } else if (kind === 'passages'){
        Object.keys(PASSAGE_ALIAS).forEach(function(a){ put(a, PASSAGE_ALIAS[a]); });
      }
      ctx.idx[kind] = idx;
    });
    return ctx;
  }

  function trMatch(key, curKind, cross, ctx){
    var raw = String(key == null ? '' : key).trim();
    if (!raw) return null;
    var upper = raw.toUpperCase(), n = trNorm(raw);
    var order = [curKind];
    if (cross) TR_KINDS.forEach(function(k){ if (k.key !== curKind) order.push(k.key); });
    var i, codes = ctx.codes, idx = ctx.idx;
    for (i = 0; i < order.length; i++){          /* ① 代码精确命中优先 */
      if (codes[order[i]][upper]) return { kind:order[i], code:codes[order[i]][upper], how:'code' };
    }
    if (!n) return null;
    for (i = 0; i < order.length; i++){          /* ② 归一化英文命中 */
      if (idx[order[i]][n]) return { kind:order[i], code:idx[order[i]][n], how:'en' };
    }
    return null;
  }

  function trParseTable(text){
    var rows = [];
    String(text == null ? '' : text).replace(/^\uFEFF/, '').split(/\r?\n/).forEach(function(line, i){
      var s = line.replace(/｜/g, '|').trim();
      if (!s) return;
      if (s.charAt(0) === '#' || s.indexOf('//') === 0) return;
      var sep = s.indexOf('|');
      if (sep < 0){
        var tab = s.indexOf('\t');
        if (tab < 0){ rows.push({ line:i + 1, raw:s, key:s, val:'', bad:'缺少分隔符' }); return; }
        sep = tab;
      }
      var key = s.slice(0, sep).trim(), val = s.slice(sep + 1).trim();
      if (!key){ rows.push({ line:i + 1, raw:s, key:'', val:val, bad:'缺少条目名' }); return; }
      rows.push({ line:i + 1, raw:s, key:key, val:val, extra: val.indexOf('|') >= 0 });
    });
    return rows;
  }

  function trBulkPreview(text, curKind, cross){
    var rows = trParseTable(text), ctx = trBuildCtx();
    var out = { rows:rows, hits:[], miss:[], skipped:0, dups:0, same:0, byKind:{} };
    var seen = {};
    rows.forEach(function(r){
      if (r.bad){ out.miss.push(r); return; }
      if (!r.val){ out.skipped++; return; }      /* 中文留空 = 不导入，不当作"清空该条" */
      var m = trMatch(r.key, curKind, cross, ctx);
      if (!m){ out.miss.push(r); return; }
      var sig = m.kind + '|' + m.code;
      if (seen[sig]) out.dups++; else seen[sig] = 1;
      var val = r.val.slice(0, 32);
      var base = (BASE_ZH[m.kind] || {})[m.code] || '';
      var same = (val === base);            /* 与内置译名相同 → 不写覆盖，也要在预览里说清楚 */
      if (same) out.same++;
      out.hits.push({ kind:m.kind, code:m.code, val:val, base:base,
                      line:r.line, how:m.how, same:same });
      out.byKind[m.kind] = (out.byKind[m.kind] || 0) + 1;
    });
    return out;
  }

  /* 命中项 → 可提交的 payload：以现有 TR 为底，值等于出厂值时删掉覆盖（与列表保存同口径） */
  function trBulkPayload(res){
    var buckets = {};
    res.hits.forEach(function(h){
      var base = (BASE_ZH[h.kind] || {})[h.code] || '';
      if (!h.val || h.val === base) return;
      if (!buckets[h.kind]) buckets[h.kind] = {};
      buckets[h.kind][h.code] = h.val;
    });
    Object.keys(buckets).forEach(function(kind){
      var merged = {};
      Object.keys(TR[kind] || {}).forEach(function(c){ merged[c] = TR[kind][c]; });
      Object.keys(buckets[kind]).forEach(function(c){ merged[c] = buckets[kind][c]; });
      buckets[kind] = merged;
    });
    return buckets;
  }

  function trKindLabel(kind){
    var hit = TR_KINDS.filter(function(k){ return k.key === kind; })[0];
    return (hit && hit.label) || kind;
  }

  function trTabsHTML(withSearch){
    var h = '<div class="sortbar" style="margin-bottom:12px;flex-wrap:wrap">' +
      TR_KINDS.map(function(k){
        var on = state.trKind === k.key;
        var n = Object.keys(TR[k.key] || {}).length;
        return '<button class="sort-btn' + (on ? ' on' : '') + '" type="button" data-trkind="' + k.key + '">' +
          esc(k.label) + (n ? ' <b>' + n + '</b>' : '') + '</button>';
      }).join('');
    if (withSearch){
      h += '<input id="tr-search" class="text-input" type="search" spellcheck="false" placeholder="搜索代码 / 中文 / English" ' +
        'value="' + esc(state.trQuery || '') + '" style="margin-left:auto;min-width:220px">';
    }
    return h + '</div>';
  }

  function trImportHTML(){
    return trTabsHTML(false) +
      '<div class="format-note" style="margin-bottom:10px">' +
        '每行一条 <code>English | 中文</code>；<code>//</code> 或 <code>#</code> 开头是注释；中文留空的行会被跳过。' +
        '键可以写代码（<code>RF</code>）也可以写英文名（<code>Coral Caves</code>）。' +
        '当前分类：<b>' + esc(trKindLabel(state.trKind)) + '</b>' +
      '</div>' +
      '<textarea id="tr-bulk" class="text-input tr-bulk" spellcheck="false" rows="10" ' +
        'placeholder="Coral Caves|珊瑚洞穴&#10;Aether Ridge|以太山脊&#10;BlueLizard|蓝蜥蜴"></textarea>' +
      '<div class="sortbar" style="margin-top:10px">' +
        '<button class="btn ghost" type="button" id="tr-bulk-file">从文件读取…</button>' +
        '<button class="btn ghost" type="button" id="tr-bulk-clear">清空</button>' +
        '<label class="tr-flag" title="打开后会在生物/区域/角色/通行证/好感五类里依次查找，适合一张表混写多种条目">' +
          '<input type="checkbox" id="tr-bulk-cross"' + (state.trCross ? ' checked' : '') + '> 跨分类自动匹配</label>' +
        '<span style="margin-left:auto;color:var(--dim)" id="tr-bulk-note"></span>' +
      '</div>' +
      '<div class="tr-prev" id="tr-prev"></div>' +
      '<div class="sortbar" style="margin-top:14px">' +
        '<button class="btn primary" type="button" id="tr-bulk-apply" disabled>应用</button>' +
        '<button class="btn ghost" type="button" id="tr-bulk-back">返回列表</button>' +
        '<span style="color:var(--dim)">保存后立即生效，写入 <code>region_data/_translations.json</code></span>' +
      '</div>';
  }

  function trBulkRender(){
    var box = $('tr-prev'), note = $('tr-bulk-note'), apply = $('tr-bulk-apply');
    if (!box) return;
    var res = trBulkPreview(state.trBulkText || '', state.trKind, state.trCross);
    state.trBulkRes = res;
    var eff = res.hits.length - res.same;
    var parts = Object.keys(res.byKind).map(function(k){ return trKindLabel(k) + ' ' + res.byKind[k]; });
    if (note){
      note.textContent = '解析 ' + res.rows.length + ' 行 · 命中 ' + res.hits.length + ' 条' +
        (parts.length ? '（' + parts.join(' / ') + '）' : '') +
        (res.same ? ' · 其中 ' + res.same + ' 条与内置相同、不会写入' : '') +
        ' · 跳过 ' + res.skipped + ' · 未匹配 ' + res.miss.length + (res.dups ? ' · 重复 ' + res.dups : '');
    }
    var html = '';
    if (res.miss.length){
      html += '<div class="tr-prev-h bad">未匹配 ' + res.miss.length + ' 条 —— 检查英文拼写，或确认对应区域是否已导入</div>' +
        '<div class="tr-prev-list">' + res.miss.slice(0, 24).map(function(m){
          return '<code>' + esc(m.key || m.raw) + (m.bad ? ' · ' + esc(m.bad) : '') + '</code>';
        }).join('') + (res.miss.length > 24 ? '<i>…还有 ' + (res.miss.length - 24) + ' 条</i>' : '') + '</div>';
    }
    if (res.hits.length){
      html += '<div class="tr-prev-h">命中 ' + res.hits.length + ' 条' +
        (res.same ? '（' + res.same + ' 条与内置相同，标灰）' : '') + '</div>' +
        res.hits.slice(0, 10).map(function(h){
          return '<div class="tr-hit' + (h.same ? ' same' : '') + '"' +
            (h.same ? ' title="与内置译名相同，不会写入覆盖"' : '') + '>' +
            '<span class="k">' + esc(h.code) + '</span>' +
            '<span class="b">' + esc(h.base || '（无内置）') + '</span>' +
            '<span class="v">' + esc(h.val) + '</span>' +
            '<span class="t">' + esc(trKindLabel(h.kind)) + '</span></div>';
        }).join('') + (res.hits.length > 10 ? '<i style="font-size:11px;color:var(--dim)">…还有 ' + (res.hits.length - 10) + ' 条</i>' : '');
    }
    if (!html) html = '<div style="font-size:11.5px;color:var(--dim)">把表格粘贴到上面，或点「从文件读取…」</div>';
    box.innerHTML = html;
    if (apply){
      apply.disabled = eff <= 0;
      apply.textContent = eff > 0
        ? (state.trBulkArmed ? ('确认写入 ' + eff + ' 条？') : ('应用到 ' + eff + ' 条'))
        : (res.hits.length ? '无需改动' : '应用');
    }
  }

  /* 两步确认：第一次点变「确认写入」，再点才落盘。
     不用原生 confirm —— WebView2 下它不弹窗、直接返回 false，会把流程静默掐断。 */
  function trBulkApplyNow(){
    var res = state.trBulkRes;
    if (!res || !res.hits.length) return;
    if (res.hits.length - res.same <= 0){ toast('这些条目与内置译名相同，无需写入'); return; }
    if (!state.trBulkArmed){
      state.trBulkArmed = true;
      trBulkRender();
      toast('再点一次确认：将写入 ' + res.hits.length + ' 条，同一条目以表格里靠后的行为准');
      if (state.trBulkTimer) clearTimeout(state.trBulkTimer);
      state.trBulkTimer = setTimeout(function(){
        state.trBulkArmed = false;
        trBulkRender();
      }, 6000);
      return;
    }
    state.trBulkArmed = false;
    if (state.trBulkTimer){ clearTimeout(state.trBulkTimer); state.trBulkTimer = null; }
    var buckets = trBulkPayload(res);
    var kinds = Object.keys(buckets);
    if (!kinds.length){ toast('没有需要写入的改动（全部与内置译名相同）'); trBulkRender(); return; }
    var parts = Object.keys(res.byKind).map(function(k){ return trKindLabel(k) + ' ' + res.byKind[k]; });
    function done(data){
      applyTranslations(data || {});
      state.trView = 'list';
      state.trBulkText = '';
      modalBody.innerHTML = translationModalHTML();
      bindTranslationModal();
      toast('批量导入 ' + res.hits.length + ' 条（' + parts.join(' / ') + '）');
    }
    if (hasBridge()){
      bridgeCall('save_translations', buckets).then(done)
        .catch(function(e){ toast('导入失败：' + ((e && e.message) || e)); });
    } else {
      Object.keys(buckets).forEach(function(kind){ TR[kind] = buckets[kind]; });
      done(TR);
    }
  }

  function translationModalHTML(){
    if (state.trView === 'import') return trImportHTML();
    var kind = state.trKind;
    var q = (state.trQuery || '').trim().toLowerCase();
    var opts = trOptions(kind).filter(function(o){
      if (!q) return true;
      return (o.code + ' ' + (o.base || '') + ' ' + (o.en || '')).toLowerCase().indexOf(q) >= 0;
    });

    var h = trTabsHTML(true) +
      '<div class="format-note" style="margin-bottom:12px">只改<b>中文显示名</b>，英文与代码不变；留空 = 用回内置译名。' +
        '共 ' + opts.length + ' 条，已自定义 ' + trCount() + ' 条。</div>' +
      '<div class="tr-list">' +
        (opts.length ? opts.map(function(o){
          var cur = TR[kind] && TR[kind][o.code] != null ? TR[kind][o.code] : o.base;
          var changed = TR[kind] && TR[kind][o.code] != null && TR[kind][o.code] !== o.base;
          var sub = (o.en && o.en !== o.code) ? o.en : '';
          return '<div class="tr-row' + (changed ? ' changed' : '') + '">' +
            '<span class="tr-code">' + esc(o.code) + '</span>' +
            '<span class="tr-en">' + esc(sub) + '</span>' +
            '<input class="text-input tr-input" type="text" spellcheck="false" data-tr="' + esc(o.code) + '" ' +
              'data-base="' + esc(o.base || '') + '" value="' + esc(cur || '') + '" ' +
              'placeholder="' + esc(o.base || '内置：无') + '">' +
            '</div>';
        }).join('') : '<div class="empty">没有匹配的条目</div>') +
      '</div>' +
      '<div class="sortbar" style="margin-top:14px">' +
        '<button class="btn primary" type="button" id="tr-save">保存</button>' +
        '<button class="btn ghost" type="button" id="tr-bulk-open" title="把一张 English | 中文 对照表整批导入">批量翻译</button>' +
        '<span style="color:var(--dim)">保存后立即生效，写入 <code>region_data/_translations.json</code></span>' +
      '</div>';
    return h;
  }

  function bindTranslationModal(){
    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-trkind]'), function(btn){
      btn.addEventListener('click', function(){
        state.trKind = btn.getAttribute('data-trkind');
        modalBody.innerHTML = translationModalHTML();
        bindTranslationModal();
      });
    });
    var search = $('tr-search');
    if (search){
      search.addEventListener('input', function(){
        state.trQuery = search.value;
        var pos = search.selectionStart;
        modalBody.innerHTML = translationModalHTML();
        bindTranslationModal();
        var again = $('tr-search');
        if (again){ again.focus(); try{ again.setSelectionRange(pos, pos); }catch(e){} }
      });
    }
    var saveBtn = $('tr-save');
    if (saveBtn) saveBtn.addEventListener('click', function(){
      var kind = state.trKind;
      /* 以「已有的整表」为底再叠加本次可见行的改动：
         搜索过滤时 DOM 里只有几行，不能直接拿它当整表，否则会把没显示的条目删掉。 */
      var bucket = {};
      Object.keys(TR[kind] || {}).forEach(function(code){ bucket[code] = TR[kind][code]; });
      Array.prototype.forEach.call(modalBody.querySelectorAll('[data-tr]'), function(inp){
        var code = inp.getAttribute('data-tr');
        var base = inp.getAttribute('data-base') || '';
        var val = String(inp.value || '').trim();
        if (!val || val === base) delete bucket[code];
        else bucket[code] = val;
      });
      /* 只提交「本类」的整表（含清空），其余分类保持不变 */
      var payload = {};
      payload[kind] = bucket;
      if (hasBridge()){
        bridgeCall('save_translations', payload).then(function(res){
          applyTranslations(res || {});
          modalBody.innerHTML = translationModalHTML();
          bindTranslationModal();
          toast('已保存「' + (TR_KINDS.filter(function(k){ return k.key === kind; })[0] || {}).label + '」译名 ' + Object.keys(bucket).length + ' 条');
        }).catch(function(e){ toast('保存失败：' + (e && e.message || e)); });
      } else {
        TR[kind] = bucket;
        applyTranslations(TR);
        toast('浏览器模式：译名只在本次会话生效');
      }
    });
    var bulkOpen = $('tr-bulk-open');
    if (bulkOpen) bulkOpen.addEventListener('click', function(){
      state.trView = 'import';
      state.trBulkArmed = false;
      modalBody.innerHTML = translationModalHTML();
      bindTranslationModal();
    });

    /* ---- 批量翻译面板 ---- */
    var bulk = $('tr-bulk');
    if (bulk){
      bulk.value = state.trBulkText || '';
      trBulkRender();
      var timer = null;
      bulk.addEventListener('input', function(){
        state.trBulkText = bulk.value;
        state.trBulkArmed = false;
        if (timer) clearTimeout(timer);
        timer = setTimeout(trBulkRender, 200);
      });
      var cross = $('tr-bulk-cross');
      if (cross) cross.addEventListener('change', function(){
        state.trCross = !!cross.checked;
        trBulkRender();
      });
      var fileBtn = $('tr-bulk-file');
      if (fileBtn) fileBtn.addEventListener('click', function(){
        if (!hasBridge()){ toast('浏览器模式读不了本地文件，请直接粘贴表格'); return; }
        bridgeCall('pick_text_file').then(function(res){
          if (!res || res.canceled) return;
          if (!res.ok){ toast(res.error || '读取失败'); return; }
          state.trBulkText = res.text || '';
          bulk.value = state.trBulkText;
          trBulkRender();
          var name = String(res.path || '').split(/[\\/]/).pop();
          toast('已读入 ' + name + '（' + (res.encoding || 'utf-8') + '）');
        }).catch(function(e){ toast('读取失败：' + ((e && e.message) || e)); });
      });
      var clearBtn = $('tr-bulk-clear');
      if (clearBtn) clearBtn.addEventListener('click', function(){
        state.trBulkText = '';
        state.trBulkArmed = false;
        bulk.value = '';
        trBulkRender();
        bulk.focus();
      });
      var applyBtn = $('tr-bulk-apply');
      if (applyBtn) applyBtn.addEventListener('click', trBulkApplyNow);
      var backBtn = $('tr-bulk-back');
      if (backBtn) backBtn.addEventListener('click', function(){
        state.trView = 'list';
        state.trBulkArmed = false;
        modalBody.innerHTML = translationModalHTML();
        bindTranslationModal();
      });
    }
  }

  function openTranslationModal(){
    state.trView = 'list';          /* 每次打开都回到逐条列表，别停在上次的批量面板 */
    openModal('自定义译名', '觉得哪个中文名不合适，就在这里改；也可以整批导入对照表', translationModalHTML(), true);
    bindTranslationModal();
  }

  var FIELD_DOCS = {
    seed:'世界随机种子，决定地图与生物分布的生成结果。',
    cycle:'已度过的周期数（天数）；每次成功冬眠 +1。',
    food:'当前饱食度（食物 pip 数），冬眠需要填满。',
    den:'当前冬眠点（庇护所）所在房间代码，格式为「区域缩写_房间号」，如 RF_S04。',
    denRegion:'冬眠点缩写匹配出的区域：内置译名用中文 + English，模组/变体区域用数据里的原名 + 缩写。',
    lastDen:'上一个冬眠点房间代码。',
    karma:'业力值 / 上限。存档里是 0 基（KARMA 0~9），界面按游戏内习惯 +1 显示为 1~10；穿过区域大门通常需要足够业力。',
    glow:'神经元发光（HASTHEGLOW）：与神经元相关的能力标志。',
    mark:'交流印记（HASTHEMARK）：是否获得五块卵石的交流印记。',
    deaths:'该战役累计死亡次数。',
    survives:'该战役累计成功冬眠次数。',
    quits:'中途退出（未结束周期）的次数。',
    totalFood:'累计吃下的食物总量。',
    totalTime:'玩家在该存档的真实游玩总时长 = 存活时长 TOTTIME + 死亡相关时长 DEATHTIME。这个总时长不单独存在存档里，需要两者相加（与游戏内速通计时器同口径）。',
    aliveTime:'TOTTIME：成功存活的循环累计的时间 —— 表示这段循环成功存活。',
    deathTime:'DEATHTIME：以死亡告终的那段循环累计的时间 —— 表示这段循环时间里没有活下来。',
    alivePct:'真存活时长（TOTTIME）占总时长的百分比；总时长 = TOTTIME + DEATHTIME。',
    kills:'按生物种类统计的击杀数（同种的体型/实例变体已合并，蝉乌贼按白/黑细分）。',
    friends:'跟随的蛞蝓猫幼崽数量。',
    passage:'通行证挑战的完成状态与进度。',
    region:'区域世界状态：最后更新周期、探索房间数、物品与生物数量。',
    community:'各生物对你的好感度，范围 -1 ~ 1。',
    pearl:'已交付 / 重要的数据珍珠清单。',
    shelters:'已发现的庇护所（按区域统计）。',
    tokens:'关卡 / 沙盒等收集 token 数量。',
    worldVersion:'世界数据版本号，用于兼容不同游戏版本。'
  };

  var FIELD_GROUPS = [
    {title:'玩家进度', fields:[
      ['SEED','世界随机种子'],['CYCLENUM','周期数（天数）'],['FOOD','当前饱食度'],
      ['DENPOS','当前冬眠点房间'],['denRegion','冬眠点所属区域（中文 / English，按对照表匹配）'],['LASTVDENPOS','上一个冬眠点'],['KARMA','业力 / 上限'],
      ['HASTHEGLOW','神经元发光（是否具备）'],['HASTHEMARK','交流印记（是否获得）']
    ]},
    {title:'统计', fields:[
      ['DEATHS','死亡次数'],['SURVIVES','成功冬眠次数'],['QUITS','中途退出次数'],
      ['TOTFOOD','累计食物'],['TOTTIME','存活时长（成功存活的循环累计，秒）'],
      ['DEATHTIME','死亡相关时长（以死亡告终的循环累计，秒）'],
      ['总时长','TOTTIME + DEATHTIME，即速通计时器口径'],['KILLS','按种类的击杀统计'],
      ['FRIENDS','幼崽伙伴数量']
    ]},
    {title:'通行证 / 解锁', fields:[
      ['WINSTATE','通行证完成状态与进度'],['SHELTERLIST','已发现庇护所'],
      ['LEVELTOKENS','关卡 token'],['SANDBOXTOKENS','沙盒 token'],['PLAYEDARENAS','已玩竞技场'],
      ['LORE / BROADCASTS','已解锁剧情与广播']
    ]},
    {title:'世界与生物', fields:[
      ['REGIONSTATE','每个区域的世界状态'],['POPULATION','区域生物种群数量'],
      ['COMMUNITIES','各生物好感度'],['SWARMROOMS','蝠蝇房数量（房间列表）'],['LINEAGES','蜥蜴血统计数']
    ]},
    {title:'物品', fields:[
      ['OBJECTS','区域内掉落物'],['SWALLOWEDITEMS','被吞下的物品'],['PLAYERGRASPS','手持物品'],
      ['significantPearls','已交付 / 重要珍珠']
    ]}
  ];

  /* ---------------- 状态 ---------------- */
  var state = { result:null, selected:null, tab:'overview', file:null, killsExpanded:false };
  state.theme = 'dark';        /* 'dark' | 'light' */
  state.accent = 'amber';      /* 强调色预设 id */
  /* 首屏先套一遍配色，避免加载完成时闪一下默认色；配置读回来后再校正 */
  (function bootTheme(){
    try{
      var saved = JSON.parse(localStorage.getItem('rwTheme') || 'null');
      if (saved && saved.t){ state.theme = saved.t === 'light' ? 'light' : 'dark'; }
      if (saved && saved.a){ state.accent = saved.a; }
    }catch(e){}
    document.documentElement.setAttribute('data-theme', state.theme);
    document.documentElement.setAttribute('data-accent', state.accent);
  })();
  state.killsTopN = 8;         /* 击杀扇形图显示前 N 种（配置持久化，按角色物种数夹取） */
  state.killTable = false;     /* 明细表是否展开 */
  state.campSort = 'time';     /* 各战役统计表排序键 */
  state.campSortDir = 'desc';
  state.trKind = 'creatures';  /* 译名编辑器当前分类 */
  state.trQuery = '';          /* 译名编辑器搜索词 */
  state.trView = 'list';       /* list = 逐条编辑 / import = 批量翻译 */
  state.trBulkText = '';       /* 批量面板里的表格文本（切分类不丢） */
  state.trCross = true;        /* 批量翻译：是否跨分类自动匹配 */
  state.trBulkArmed = false;   /* 批量翻译：是否已点过一次「应用」（两步确认） */
  state.regions = {};          /* code -> 导入的区域详情 */
  state.regionList = [];       /* 导入缓存摘要 */
  state.regionPick = {};       /* slugcat -> [手动加进总览的区域代码]（配置持久化） */
  state.regionAccess = { regions:{} };   /* data/region_access.json：可达性提示（只提示不过滤） */
  state.regionReach = { regions:{} };    /* data/region_reach.json：角色可达区域表（世界拓扑用） */
  state.roomPalette = { dark:{}, light:{} };  /* 房间卡自定义配色：只存改过的项，按主题分开 */
  state.graphOpts = {};        /* 关系图参数（力/显示/动画），缺省回落 GX_OPT_DEFAULT */
  state.graphColors = { dark:{}, light:{} };  /* 关系图状态配色，只存改过的项 */
  state.roomMarks = {};        /* 手动探索标记：{区域:{房间:1|-1}}，缺省跟随存档 */
  state.regmapColors = {};     /* 几何图配色：{区域:{air/solid/…: '#hex'}}，只存改过的项 */
  state.roomExcluded = {};     /* 手动"此角色到不了"：{角色:{区域:[房间]}}，直接剔除出分母 */
  state.roomStrict = true;     /* 完成度口径：true=只算当前角色可达的房间 */
  /* 房间卡是否全屏：默认全屏（P4 起）。右栏清单只在全屏时可见，默认紧凑会让
     「出口跳转 / 悬停高亮」没有入口；config.ui.roomCardFull 有值时以配置为准。 */
  state.roomCardFull = true;
  /* 房间卡的画法：vector＝格子示意图（现状）｜live＝实机渲染图（V1.2）。
     默认矢量——实机图要 0.4~3.7 s 才算得出来，不打招呼就换成它等于让每间房都变慢。
     config.ui.roomCardStyle 有值时以配置为准（已在 DEFAULT_UI 登记）。 */
  state.roomCardStyle = 'vector';
  /* 区域地图底图（P0）：默认关。底图是游戏自带的 map_<reg>.png（1px = 1tile，
     与房间方块同一坐标系），只作背景参考，不替代矢量方块。
     config.ui.mapBase 有值时以配置为准（已在 DEFAULT_UI 登记）。 */
  state.mapBase = false;
  state.muFilter = 'unseen';   /* 地图弹窗里的房间号清单标签：all / unseen / seen */
  state.sources = [];          /* 来源清单（Original / Downpour / Watcher / 各模组） */
  state.sourcePresets = ['Original','Downpour','Watcher','Mod'];
  state.regionSort = 'code';
  state.regionSortDir = 'asc';
  state.hasBridge = false;
  state.dataDir = '';
  state.mapCache = {};

  /* ================= 桌面桥接（无壳时全部降级） ================= */
  function hasBridge(){ return !!(window.pywebview && window.pywebview.api); }

  function bridgeCall(name){
    var args = Array.prototype.slice.call(arguments, 1);
    return new Promise(function(resolve, reject){
      if (!hasBridge()){ reject(new Error('NATIVE_UNAVAILABLE')); return; }
      try {
        var result = window.pywebview.api[name].apply(window.pywebview.api, args);
        if (result && typeof result.then === 'function') result.then(resolve, reject);
        else resolve(result);
      } catch (err){ reject(err); }
    });
  }

  /* ================= 区域数据 ================= */
  function regionSummary(code){
    var key = String(code || '').toUpperCase();
    var list = state.regionList || [];
    for (var i = 0; i < list.length; i++){
      if (String(list[i].code).toUpperCase() === key) return list[i];
    }
    return null;
  }

  function regionData(code){
    if (!code) return null;
    return state.regions[String(code).toUpperCase()] || null;
  }

  /* ================= 来源 ================= */
  function loadSources(){
    if (!hasBridge()) return Promise.resolve();
    return bridgeCall('sources').then(function(res){
      if (res && res.ok){
        state.sources = res.sources || [];
        if (res.presets && res.presets.length) state.sourcePresets = res.presets;
      }
    }).catch(function(){});
  }

  function sourceById(id){
    for (var i = 0; i < state.sources.length; i++){
      if (state.sources[i].id === id) return state.sources[i];
    }
    return null;
  }

  function sourceOn(id){
    var s = sourceById(id);
    return s ? !!s.enabled : true;
  }

  /* 点亮 / 熄灭一个来源：同时改注册表（持久化）与内存里的每一层 */
  function toggleSource(id, force){
    if (!id) return;
    var next = (force === undefined) ? !sourceOn(id) : !!force;
    var s = sourceById(id);
    if (s) s.enabled = next;
    else state.sources.push({ id:id, name:id, kind:'mod', enabled:next, order:999 });

    Object.keys(state.regions).forEach(function(code){
      (state.regions[code].layers || []).forEach(function(L){
        if ((L.sourceId || L.id) === id) L.enabled = next;
      });
    });
    state.regionList.forEach(function(item){
      (item.layers || []).forEach(function(L){
        if ((L.sourceId || L.id) === id) L.enabled = next;
      });
    });

    /* 重新统计每个区域的「参与计算房间数」 */
    Object.keys(state.regions).forEach(function(code){
      var rd = state.regions[code];
      var active = {}, list = [];
      (rd.layers || []).forEach(function(L){
        if (!L.enabled || L.mapOnly) return;
        list.push(L.sourceId || L.id);
        (L.rooms || []).forEach(function(room){ active[String(room.name).toUpperCase()] = 1; });
      });
      rd.activeRooms = Object.keys(active).length;
      rd.activeSources = list;
      var sum = null;
      for (var i = 0; i < state.regionList.length; i++){
        if (state.regionList[i].code === code){ sum = state.regionList[i]; break; }
      }
      if (sum){ sum.activeRooms = rd.activeRooms; sum.activeSources = list; }
    });

    if (hasBridge()){
      bridgeCall('set_source_enabled', id, next).catch(function(){});
    }
    recompute();
  }

  function recompute(){
    if (!state.result) return;
    computeCompletions(state.result);
    renderMeta(); renderSidebar(); renderDetail();
  }

  function loadRegions(){
    if (!hasBridge()) return Promise.resolve();
    var p = loadSources().then(function(){
      return bridgeCall('regions');
    }).then(function(list){
      state.regionList = list || [];
      var loads = state.regionList.map(function(item){
        return bridgeCall('region_detail', item.code).then(function(detail){
          if (detail && detail.ok && detail.region) state.regions[item.code] = detail.region;
        }).catch(function(){});
      });
      return Promise.all(loads);
    }).then(function(){
      state.regionList.forEach(function(item){
        if (item.nameZh && !REGION_MAP[item.code]) REGION_MAP[item.code] = [item.nameZh, item.nameEn || ''];
      });
      if (state.result){
        decorateRegions(state.result);
        computeCompletions(state.result);
        renderMeta(); renderSidebar(); renderDetail();
      }
      renderRegionsModal();
    }).catch(function(){});
    rmNameIndex = null;   /* 区域数据换了一批（首次加载 / 重导 / 删区域），房间名索引重建 */
    state.regionsPromise = p;   /* 世界拓扑要等它加载完，否则只能画出一半区域 */
    return p;
  }

  /* 一个区域可能有多个来源（Original / Downpour / Watcher / 各模组），
     每个来源各带一份房间清单。计算时只取「点亮」且「有完整清单」的来源，取并集。
     只有地图、没有 world 文件的来源（仅地图）不参与分母：它的房间表来自地图矩形，
     缺庇护所/大门标记，也不保证完整。 */
  function usableLayers(rd, slugcat){
    if (!rd || !rd.layers) return [];
    return rd.layers.filter(function(L){
      if (!L.enabled || !(L.rooms || []).length) return false;
      /* 仅地图来源不给分母；但如果它带着当前角色的专属地图变体，就按变体清单参与 */
      if (L.mapOnly) return !!findVariantInLayer(L, slugcat);
      return true;
    });
  }

  /* 存档里的角色键（White / Spear / Saint …）→ 世界文件与地图文件用的正式名 */
  var SLUGCAT_ALIAS = {
    white:'survivor', yellow:'monk', red:'hunter', night:'nightcat',
    spear:'spearmaster', pale:'monk', enot:'enot'
  };
  /* 正式名 → 地图变体后缀候选（map_image_<reg>-<suffix>.txt） */
  var VARIANT_OF = {
    survivor:['survivor'], monk:['monk'], hunter:['red','hunter'], nightcat:['night','nightcat'],
    spearmaster:['spear','spearmaster'], artificer:['artificer'], saint:['saint'],
    rivulet:['rivulet'], gourmand:['gourmand'], inv:['inv'], watcher:['watcher']
  };

  function canonSlugcat(slugcat){
    var k = String(slugcat == null ? '' : slugcat).trim().toLowerCase().replace(/[\s\-_]/g, '');
    return SLUGCAT_ALIAS[k] || k;
  }
  /* 条件房间筛选用的「我叫什么」：白猫既是 WHITE 也是 SURVIVOR */
  function mySlugcatNames(slugcat){
    var raw = String(slugcat == null ? '' : slugcat).trim().toUpperCase();
    var canon = canonSlugcat(slugcat).toUpperCase();
    if (!raw) return canon ? [canon] : [];
    return raw === canon ? [canon] : [raw, canon];
  }
  function variantCandidates(slugcat){
    var canon = canonSlugcat(slugcat);
    return VARIANT_OF[canon] || (canon ? [canon] : []);
  }

  /* 在某一层里找当前角色的地图变体（圣徒 / 工匠 / 矛大师……） */
  function findVariantInLayer(layer, slugcat){
    var cands = variantCandidates(slugcat);
    if (!cands.length) return null;
    var vs = (layer && layer.variants) || {};
    var found = null;
    Object.keys(vs).forEach(function(suffix){
      if (found) return;
      var s = String(suffix).toLowerCase();
      var hit = cands.some(function(c){ return s === c || s.indexOf(c) === 0 || c.indexOf(s) === 0; });
      if (hit && Object.keys((vs[suffix] || {}).rooms || {}).length) found = suffix;
    });
    return found;
  }
  function findVariant(rd, slugcat){
    var hit = null;
    ((rd && rd.layers) || []).forEach(function(L){
      if (hit || !L.enabled) return;
      var suffix = findVariantInLayer(L, slugcat);
      if (suffix){
        hit = { suffix: suffix, layer: L, rooms: ((L.variants || {})[suffix] || {}).rooms || {} };
      }
    });
    return hit;
  }

  /* 变体房间集：以该变体地图的房间为准（它就是这一版该角色能走的房间）。
     只有「任何一版地图里都没出现过」的房间才按无坐标房间补进来，
     否则会把别的角色版本的房间算进分母，导致圣徒之类永远差几间。 */
  function variantRoomSets(rd, hit){
    var names = {}, shelters = {}, gates = {}, coords = {}, nbr = {}, subs = {};
    var anyMap = {};
    ((rd && rd.layers) || []).forEach(function(L){
      (L.rooms || []).forEach(function(room){
        if (room.map) anyMap[String(room.name).toUpperCase()] = 1;
      });
      var vs = L.variants || {};
      Object.keys(vs).forEach(function(suf){
        Object.keys((vs[suf] || {}).rooms || {}).forEach(function(n){ anyMap[n.toUpperCase()] = 1; });
      });
    });
    var flags = {};
    ((rd && rd.layers) || []).forEach(function(L){
      (L.rooms || []).forEach(function(room){
        var k = String(room.name).toUpperCase();
        var slot = flags[k] || (flags[k] = { shelter:false, gate:false });
        if (room.shelter) slot.shelter = true;
        if (room.gate) slot.gate = true;
      });
    });
    Object.keys(hit.rooms).forEach(function(name){
      var k = name.toUpperCase();
      names[k] = 1;
      coords[k] = hit.rooms[name];
      var src = null;
      ((rd && rd.layers) || []).forEach(function(L){
        if (src) return;
        (L.rooms || []).forEach(function(room){
          if (String(room.name).toUpperCase() !== k) return;
          if (room.neighbors && room.neighbors.length) src = room.neighbors;
          if (room.subregion) subs[k] = room.subregion;
        });
      });
      if (src) nbr[k] = src.map(function(t){ return String(t).toUpperCase(); });
      var f = flags[k];
      if (f && f.shelter) shelters[k] = 1;
      if (f && f.gate) gates[k] = 1;
    });
    /* 所有地图里都没坐标的房间（少数只写在 world 文件里的）仍然算存在 */
    ((rd && rd.layers) || []).forEach(function(L){
      if (!L.enabled || !(L.rooms || []).length) return;
      (L.rooms || []).forEach(function(room){
        var k = String(room.name).toUpperCase();
        if (anyMap[k] || names[k]) return;
        names[k] = 1;
        if (room.shelter) shelters[k] = 1;
        if (room.gate) gates[k] = 1;
      });
    });
    return {
      names: names, shelters: shelters, gates: gates, coords: coords, nbr: nbr, subs: subs,
      total: Object.keys(names).length, layerCount: 1,
      layerNames: [(hit.layer.sourceName || hit.layer.label || hit.layer.id) + ' 变体'],
      variant: hit.suffix,
      variantLayerId: hit.layer.id
    };
  }

  function regionRoomSets(rd, slugcat){
    if (!rd || !rd.layers) return null;
    var vhit = findVariant(rd, slugcat);
    if (vhit) return applyConditional(rd, variantRoomSets(rd, vhit), slugcat);

    var use = usableLayers(rd, slugcat);
    if (!use.length) return null;
    var names = {}, shelters = {}, gates = {}, coords = {}, nbr = {}, subs = {};
    use.forEach(function(L){
      (L.rooms || []).forEach(function(room){
        var k = String(room.name).toUpperCase();
        names[k] = 1;
        if (room.shelter) shelters[k] = 1;
        if (room.gate) gates[k] = 1;
        if (room.map) coords[k] = room.map;
        if (room.subregion) subs[k] = room.subregion;
        (room.neighbors || []).forEach(function(t){
          var n = String(t).toUpperCase();
          var list = nbr[k] || (nbr[k] = []);
          if (list.indexOf(n) < 0) list.push(n);
        });
      });
    });
    return applyConditional(rd, {
      names: names, shelters: shelters, gates: gates, coords: coords,
      nbr: nbr, subs: subs,
      total: Object.keys(names).length,
      layerCount: use.length,
      layerNames: use.map(function(L){ return L.sourceName || L.label || L.id; })
    }, slugcat);
  }

  /* 条件房间：{AR} 这类「只在某角色下存在」的房间不能算进分母，
     否则玩家永远做不到 100%。带剧情条件的（Watcher）无法静态判定，只标注不筛选。 */
  function conditionalIndex(rd){
    var cond = {};
    ((rd && rd.layers) || []).forEach(function(L){
      (L.rooms || []).forEach(function(room){
        if (!room.exclusive && !room.hidden) return;
        var k = String(room.name).toUpperCase();
        var slot = cond[k] || (cond[k] = { exclusive: [], hidden: [] });
        (room.exclusive || []).forEach(function(n){ if (slot.exclusive.indexOf(n) < 0) slot.exclusive.push(n); });
        (room.hidden || []).forEach(function(n){ if (slot.hidden.indexOf(n) < 0) slot.hidden.push(n); });
      });
    });
    return cond;
  }

  /* 房间名里带角色后缀的（RF_SAINTB02 / LM_BRIDGE04ARTY …）：这类房间只对那个角色存在，
     但模组大多没写 CONDITIONAL LINKS 声明，只能靠命名 + "它是孤岛"两条一起判。 */
  var ROOM_OWNER = [
    { re: /SAINT/i,           cats: ['SAINT'] },
    { re: /ARTIFICER|ARTY/i,  cats: ['ARTIFICER'] },
    { re: /SPEARMASTER|SPEAR/i, cats: ['SPEARMASTER', 'SPEAR'] },
    { re: /RIVULET/i,         cats: ['RIVULET'] },
    { re: /GOURMAND|GOURM/i,  cats: ['GOURMAND'] },
    { re: /HUNTER/i,          cats: ['HUNTER'] },
    { re: /NIGHT/i,           cats: ['NIGHTCAT', 'NIGHT'] }
  ];

  function roomOwners(name){
    var up = String(name).toUpperCase();
    for (var i = 0; i < ROOM_OWNER.length; i++){
      if (ROOM_OWNER[i].re.test(up)) return ROOM_OWNER[i].cats;
    }
    return null;
  }

  function applyConditional(rd, sets, slugcat){
    var cond = conditionalIndex(rd);
    var mine = {};
    mySlugcatNames(slugcat).forEach(function(n){ mine[n] = 1; });
    var code = String((rd && rd.code) || '').toUpperCase();
    var manual = roomExcludedMap(slugcat, code);

    /* 先算"有效度数"：邻居里真正存在于这一层的才算。全层孤岛才可能是专属房间 */
    var deg = {};
    Object.keys(sets.names).forEach(function(k){
      var list = (sets.nbr && sets.nbr[k]) || [];
      var n = 0;
      for (var i = 0; i < list.length; i++) if (sets.names[list[i]]) n++;
      deg[k] = n;
    });

    var dropped = 0, roleDropped = 0, manualDropped = 0, condDropped = 0;
    Object.keys(sets.names).forEach(function(k){
      var c = cond[k];
      var exclusiveOut = c && c.exclusive.length && !c.exclusive.some(function(n){ return mine[n]; });
      var hidden = c && c.hidden.length && c.hidden.some(function(n){ return mine[n]; });
      var byHand = state.roomStrict !== false && !!manual[k];
      var owners = roomOwners(k);
      /* 三条同时成立才按"角色专属"剔：① 名字带别的角色后缀 ② 当前不是那个角色 ③ 在本层是孤岛 */
      var byRole = state.roomStrict !== false && !!owners &&
        !owners.some(function(n){ return mine[n]; }) && deg[k] === 0;
      if (!(exclusiveOut || hidden || byHand || byRole)) return;
      delete sets.names[k];
      delete sets.shelters[k];
      delete sets.gates[k];
      delete sets.coords[k];
      if (sets.nbr) delete sets.nbr[k];
      if (sets.subs) delete sets.subs[k];
      dropped++;
      if (exclusiveOut || hidden) condDropped++;
      if (byRole) roleDropped++;
      if (byHand) manualDropped++;
    });
    if (dropped){
      sets.total = Object.keys(sets.names).length;
      sets.conditionalDropped = condDropped;   /* 只算 EXCLUSIVEROOM/HIDEROOM，别把角色专属混进来 */
      sets.roleDropped = roleDropped;
      sets.manualDropped = manualDropped;
    }
    return sets;
  }

  /* 为每个角色 / 区域计算完成度 */
  function computeCompletions(res){
    var withData = 0, allRegions = 0, pcts = [];
    (res.campaigns || []).forEach(function(c){
      (c.regions || []).forEach(function(r){
        allRegions++;
        var rd = regionData(r.name);
        var visited = r.roomList || [];
        var out = {
          total: null, visited: 0, unknown: 0, pct: null,
          source: 'none', partial: false, sheltersTotal: null, sheltersVisited: 0,
          gatesTotal: null, gatesVisited: 0, unvisited: [],
          addonNew: 0, reason: 'none', layerNames: []
        };

        if (rd){
          out.addonNew = rd.addonNewRooms || 0;
          out.baseRooms = rd.baseRooms || 0;
          out.unionRooms = rd.unionRooms || 0;
          out.officialAvailable = !!rd.officialAvailable;
        }

        var sets = regionRoomSets(rd, c.slugcat);
        if (sets && sets.total){
          out.total = sets.total;
          out.source = 'import';
          out.layerNames = sets.layerNames || [];
          out.variant = sets.variant || null;
          out.conditionalDropped = sets.conditionalDropped || 0;
          out.roleDropped = sets.roleDropped || 0;
          out.manualDropped = sets.manualDropped || 0;
          var hit = 0;
          visited.forEach(function(name){
            var key = String(name).toUpperCase();
            if (sets.names[key]){
              hit++;
              delete sets.names[key];
            } else out.unknown++;
          });
          out.visited = hit;
          out.pct = sets.total ? hit / sets.total * 100 : null;
          out.unvisited = Object.keys(sets.names).sort();
          out.sheltersTotal = Object.keys(sets.shelters).length;
          out.gatesTotal = Object.keys(sets.gates).length;
          visited.forEach(function(name){
            var key = String(name).toUpperCase();
            if (sets.shelters[key]) out.sheltersVisited++;
            if (sets.gates[key]) out.gatesVisited++;
          });
          withData++;
        } else if (rd && (rd.layers || []).length){
          /* 有数据但算不出分母：区分「全是仅地图」和「来源被全部熄灭」 */
          var anyUsable = usableLayers(rd, c.slugcat).length > 0;
          out.partial = true;
          out.reason = anyUsable ? 'disabled' : 'maponly';
          out.source = 'partial';
        }

        if (out.pct != null) pcts.push(out.pct);
        r.completion = out;
      });
    });
    res.completionSummary = {
      regionsWithData: withData,
      regionsTotal: allRegions,
      avgPct: pcts.length ? pcts.reduce(function(a, b){ return a + b; }, 0) / pcts.length : null,
      importedCodes: Object.keys(state.regions).length,
      activeSources: state.sources.filter(function(s){ return s.enabled; }).length,
      totalSources: state.sources.length
    };
    return res;
  }
  var worker = null;
  var parseToken = 0;
  var dragDepth = 0;

  /* ---------------- DOM ---------------- */
  var $ = function(id){ return document.getElementById(id); };
  var drop = $('drop'), loading = $('loading'), error = $('error'), result = $('result');

  /* ---------------- 工具 ---------------- */
  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function fmtBytes(n){
    if (n == null) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KiB';
    return (n / 1048576).toFixed(2) + ' MiB';
  }
  function fmtInt(n){ return (typeof n === 'number' && isFinite(n)) ? n.toLocaleString('en-US') : '—'; }
  /* 秒 → 24:46:52（小时不补零，分秒补零；不进位成“天”） */
  function fmtHMS(sec){
    if (typeof sec !== 'number' || !isFinite(sec) || sec < 0) return '—';
    var s = Math.round(sec);
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    return h + ':' + (m < 10 ? '0' : '') + m + ':' + (ss < 10 ? '0' : '') + ss;
  }
  /* 生命周期时长：
     存档里分两个独立累加器 —— TOTTIME（成功存活的循环累计）与 DEATHTIME（以死亡告终的那段循环累计）。
     两者相加 = 玩家在该存档的真实游玩总时长（游戏速通计时器口径），这个总时长本身不单独存字段。 */
  function lifetime(c){
    var alive = (typeof c.totalTime === 'number') ? c.totalTime : null;
    var dead  = (typeof c.deathTime === 'number') ? c.deathTime : null;
    if (alive == null && dead == null) return { total:null, alive:null, dead:null, pct:null };
    var total = (alive || 0) + (dead || 0);
    return {
      total: total,
      alive: alive,
      dead: dead,
      pct: (total > 0 && alive != null) ? (alive / total * 100) : null
    };
  }
  /* 击杀按物种聚合：去掉 -Creature-N 后缀，同种不同代码（如蝉乌贼 A/B）合并显示 */
  function killGroups(kills){
    var map = {}, order = [];
    Object.keys(kills || {}).forEach(function(raw){
      var base = raw.replace(/-Creature-\d+$/, '');
      var entry = scoreEntry(base);
      var zh = CREATURE_ZH[base] || (entry && entry.zh) || '';
      var key = zh || base;
      if (!map[key]){ map[key] = { name:key, en:zh ? base : '', total:0, variants:{}, score:0, unknown:0 }; order.push(key); }
      map[key].total += kills[raw];
      map[key].variants[base] = (map[key].variants[base] || 0) + kills[raw];
    });
    var list = order.map(function(k){ return map[k]; });
    list.forEach(function(g){
      var s = 0, unk = 0;
      Object.keys(g.variants).forEach(function(v){
        var sc = scoreOf(v);
        if (sc == null) unk += g.variants[v];
        else s += sc * g.variants[v];
      });
      g.score = s;
      g.unknown = unk;
    });
    list.sort(function(a, b){ return b.total - a.total; });
    return list;
  }

  /* 剧情模式分数（估算）：
       基础分 = 食物 + 雨眠×10 − 死亡×3 − 退出×3 − 存活分钟 + Σ(击杀×分值)
       最终分 = 基础分 × (通行证已获 + 1)，圣徒再 ×1.35
     剧情加成（神经元 / 珍珠 / 飞升 / 遇见迭代器）存档无字段，全部不含。 */
  function calcScore(c){
    if (!c) return null;
    var groups = killGroups(c.kills);
    var killScore = 0, unknownKinds = 0, unknownCount = 0, unknownNames = [];
    groups.forEach(function(g){
      killScore += g.score;
      if (g.unknown){
        unknownKinds++;
        unknownCount += g.unknown;
        unknownNames.push(g.name);
      }
    });
    var food = c.totalFood == null ? 0 : c.totalFood;
    var survives = c.survives == null ? 0 : c.survives;
    var deaths = c.deaths == null ? 0 : c.deaths;
    var quits = c.quits == null ? 0 : c.quits;
    var alive = c.totalTime == null ? 0 : c.totalTime;
    var minutes = Math.floor(alive / 60);
    var base = food + survives * 10 - deaths * 3 - quits * 3 - minutes + killScore;
    var passages = (c.passages || []).filter(function(p){ return p.earned; }).length;
    var multiplier = passages + 1;
    var saint = /^saint$/i.test(String(c.slugcat || '')) ? 1.35 : 1;
    return {
      food: food, survives: survives, deaths: deaths, quits: quits, minutes: minutes,
      killScore: killScore, base: base, passages: passages, multiplier: multiplier,
      saint: saint, total: Math.round(base * multiplier * saint),
      unknownKinds: unknownKinds, unknownCount: unknownCount, unknownNames: unknownNames
    };
  }
  /* 多个代码名取公共前缀简写：CicadaA + CicadaB → CicadaA/B */
  function shortEn(keys){
    if (!keys || !keys.length) return '';
    if (keys.length === 1) return keys[0];
    var p = keys[0];
    keys.forEach(function(k){ while (p && k.indexOf(p) !== 0) p = p.slice(0, -1); });
    return p + keys.map(function(k){ return k.slice(p.length); }).join('/');
  }
  function variantLabel(g){
    var keys = Object.keys(g.variants);
    if (keys.length < 2) return '';
    return keys.map(function(k){
      var v = CREATURE_VARIANT_ZH[k];
      return (v ? v : k) + ' ' + g.variants[k];
    }).join(' · ');
  }
  function slugZh(s){ return SLUGCAT_ZH[s] || ''; }
  function importedRegion(code){
    var key = String(code == null ? '' : code).toUpperCase();
    return (state.regions && state.regions[key]) || null;
  }
  function regionInfo(code){
    var v = REGION_MAP[String(code == null ? '' : code).toUpperCase()];
    return v ? { zh: v[0], en: v[1] } : null;
  }
  /* 内置对照表里有中文名的才算「已识别」；用户自定义译名补进来的条目不算，
     这样能给模组区域加译名，但不会把"没内置译名"这件事糊过去。 */
  function regionIsBuiltin(code){
    var b = (typeof BASE_ZH !== 'undefined' && BASE_ZH && BASE_ZH.regions) || null;
    return !!(b && b[String(code == null ? '' : code).toUpperCase()]);
  }
  /* 名称优先级：内置/自定义中文 → 导入数据里的区域原名（NameZh / DisplayName）→ 空 */
  function regionZh(code){
    var i = regionInfo(code);
    if (i && i.zh) return i.zh;
    var rd = importedRegion(code);
    return (rd && (rd.nameZh || rd.displayName)) || '';
  }
  function regionEn(code){
    var i = regionInfo(code);
    if (i && i.en) return i.en;
    var rd = importedRegion(code);
    return (rd && rd.displayName) || '';
  }
  /* 统一标签：内置 →「中文 English」；只有中文（自定义译名）→「中文 代码」；
     只有原名 →「原名 代码」；都没有 → 代码本身。 */
  function regionLabel(code){
    var c = String(code == null ? '' : code).toUpperCase();
    var i = regionInfo(c);
    if (i && i.zh && i.en) return i.zh + ' ' + i.en;
    if (i && i.zh) return i.zh + ' ' + c;
    var rd = importedRegion(c);
    if (rd && rd.displayName) return rd.displayName + ' ' + c;
    return c || '—';
  }
  /* 冬眠点形如 RF_S04 / LC_shelter_above：取第一个下划线前的片段作为区域缩写 */
  function denAbbr(denPos){
    var d = String(denPos == null ? '' : denPos);
    if (!d) return '';
    var i = d.indexOf('_');
    return (i > 0 ? d.slice(0, i) : d).toUpperCase();
  }
  function passageZh(s){ return PASSAGE_ZH[s] || s; }
  function commZh(s){ return COMMUNITY_ZH[s] || s; }

  var tipEl = $('tip');
  function showTip(text, el){
    if (!text) return;
    tipEl.textContent = text;
    tipEl.classList.add('on');
    var r = el.getBoundingClientRect();
    var tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
    var x = r.left + r.width / 2 - tw / 2;
    var y = r.top - th - 8;
    if (y < 8) y = r.bottom + 8;
    x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
    tipEl.style.left = x + 'px';
    tipEl.style.top = y + 'px';
  }
  function hideTip(){ tipEl.classList.remove('on'); }
  document.addEventListener('mouseover', function(e){
    var t = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (t) showTip(t.getAttribute('data-tip'), t);
  });
  document.addEventListener('mouseout', function(e){
    var t = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (t) hideTip();
  });
  document.addEventListener('focusin', function(e){
    var t = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (t) showTip(t.getAttribute('data-tip'), t);
  });
  document.addEventListener('focusout', hideTip);

  var toastTimer = null;
  function toast(msg){
    var el = $('toast');
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function(){ el.classList.remove('on'); }, 2200);
  }

  /* ---------------- 视图切换 ---------------- */
  function showDrop(){
    drop.hidden = false; loading.hidden = true; error.hidden = true; result.hidden = true;
    drop.focus({ preventScroll:true });
  }
  function showLoading(file){
    drop.hidden = true; error.hidden = true; result.hidden = true; loading.hidden = false;
    $('load-file').textContent = file.name + '  ·  ' + fmtBytes(file.size);
    setProgress('准备读取', 2, '—');
  }
  function setProgress(stage, pct, detail){
    pct = Math.max(0, Math.min(100, pct || 0));
    $('progress-fill').style.width = pct + '%';
    $('load-stage').textContent = stage || '处理中';
    $('load-detail').textContent = detail || '—';
    $('load-pct').textContent = Math.round(pct) + '%';
  }
  function showError(title, msg, detail){
    drop.hidden = true; loading.hidden = true; result.hidden = true; error.hidden = false;
    $('err-title').textContent = title || '解析失败';
    $('err-msg').textContent = msg || '未知错误';
    var d = $('err-details');
    if (detail){
      d.hidden = false;
      $('err-stack').textContent = detail;
    } else {
      d.hidden = true;
      $('err-stack').textContent = '';
    }
  }

  /* ---------------- 文件输入 ---------------- */
  drop.addEventListener('click', function(e){
    /* 槽位按钮是 #drop 的子元素，点它们不该再弹出「选择文件」 */
    if (e.target && e.target.closest && e.target.closest('#slot-list')) return;
    $('file').click();
  });
  drop.addEventListener('keydown', function(e){
    if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); $('file').click(); }
  });
  $('file').addEventListener('change', function(e){
    var f = e.target.files && e.target.files[0];
    if (f) handleFile(f);
    e.target.value = '';
  });

  ['dragenter','dragover'].forEach(function(ev){
    drop.addEventListener(ev, function(e){
      e.preventDefault(); e.stopPropagation();
      if (ev === 'dragenter') dragDepth++;
      drop.classList.add('drag');
    });
  });
  ['dragleave','dragend'].forEach(function(ev){
    drop.addEventListener(ev, function(e){
      e.preventDefault(); e.stopPropagation();
      if (ev === 'dragleave') dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) drop.classList.remove('drag');
    });
  });
  drop.addEventListener('drop', function(e){
    e.preventDefault(); e.stopPropagation();
    dragDepth = 0; drop.classList.remove('drag');
    var files = e.dataTransfer && e.dataTransfer.files;
    if (!files || !files.length){ toast('没有检测到文件'); return; }
    if (files.length > 1) toast('一次只处理第一个文件');
    handleFile(files[0]);
  });
  // 阻止浏览器在页面其他区域打开拖入文件
  window.addEventListener('dragover', function(e){ e.preventDefault(); });
  window.addEventListener('drop', function(e){ e.preventDefault(); });

  /* ---------------- 处理文件 ---------------- */
  function handleFile(file){
    state.file = file;
    if (!file || file.size === 0){
      showError('空文件', '这个文件大小为 0，无法解析。');
      return;
    }
    if (file.size > 128 * 1024 * 1024){
      showError('文件过大', '该文件超过 128 MiB，浏览器端解析可能会占用较多内存。请确认它确实是雨世界存档。');
      return;
    }
    showLoading(file);

    var reader = new FileReader();
    reader.onprogress = function(e){
      if (e.lengthComputable){
        var pct = Math.min(11, (e.loaded / e.total) * 11);
        setProgress('读取文件', pct, fmtBytes(e.loaded) + ' / ' + fmtBytes(e.total));
      }
    };
    reader.onerror = function(){
      showError('读取失败', '无法读取该文件，可能权限不足或文件已损坏。',
        reader.error ? (reader.error.name + ': ' + reader.error.message) : '');
    };
    reader.onload = function(){ startParse(reader.result); };
    reader.readAsText(file, 'utf-8');
  }

  function startParse(raw){
    var token = ++parseToken;
    if (worker){ worker.terminate(); worker = null; }

    function done(res){
      if (token !== parseToken) return;
      finish(res);
    }
    function fail(msg, stack){
      if (token !== parseToken) return;
      showError('解析失败', msg, stack);
    }
    function runFallback(reason){
      setProgress('解析数据段', 15, reason || '正在主线程解析…');
      setTimeout(function(){
        if (token !== parseToken) return;
        try{
          var res = parseSaveMain(raw, function(stage, pct, detail){
            if (token === parseToken) setProgress(stage, pct, detail);
          });
          done(res);
        }catch(err){
          fail((err && err.message) || String(err), (err && err.stack) || '');
        }
      }, 30);
    }

    // file:// 下部分浏览器会限制 Blob Worker，直接走主线程更稳
    if (location.protocol === 'file:'){
      runFallback('本地文件模式，使用主线程解析');
      return;
    }

    try{
      var blob = new Blob([PARSER_SRC + WORKER_GLUE], { type:'text/javascript' });
      var url = URL.createObjectURL(blob);
      worker = new Worker(url);
      worker.onmessage = function(e){
        var m = e.data || {};
        if (m.type === 'progress') setProgress(m.stage, m.pct, m.detail);
        else if (m.type === 'done'){ done(m.result); if (worker){ worker.terminate(); worker = null; } }
        else if (m.type === 'error'){ fail(m.message, m.stack); if (worker){ worker.terminate(); worker = null; } }
      };
      worker.onerror = function(){
        // Worker 启动失败：不要直接报错，降级到主线程
        if (worker){ worker.terminate(); worker = null; }
        if (token === parseToken) runFallback('后台线程不可用，改用主线程解析');
      };
      worker.postMessage({ raw: raw });
    }catch(ex){
      runFallback('后台线程不可用，改用主线程解析');
    }
  }

  $('cancel').addEventListener('click', function(){
    parseToken++;
    if (worker){ worker.terminate(); worker = null; }
    toast('已取消解析');
    showDrop();
  });

  /* ---------------- 区域名补全 ---------------- */
  /* 给每个角色补上「当前冬眠点所属区域」，并给每个区域补中英文名。
     缩写在对照表里的 → 写入中文 / 英文；不在表里的 → 用区域数据里的原名（DisplayName），
     连数据都没有才退回原始缩写。 */
  function decorateRegions(res){
    var matched = 0, missed = 0;
    (res.campaigns || []).forEach(function(c){
      var ab = denAbbr(c.denPos);
      var info = ab ? regionInfo(ab) : null;
      c.denRegionAbbr = ab;
      c.denRegionMatched = !!info;
      c.denRegionZh = ab ? (regionZh(ab) || '未识别') : '—';
      c.denRegionEn = ab ? regionEn(ab) : '';
      c.denRegion = info ? { abbr: ab, zh: info.zh, en: info.en } : null;
      if (info) matched++; else if (ab) missed++;

      (c.regions || []).forEach(function(r){
        var i2 = regionInfo(r.name);
        r.zh = regionZh(r.name) || '未识别';
        r.en = regionEn(r.name);
        r.regionMatched = !!i2;
      });
    });
    res.regionMatch = { matched: matched, missed: missed, total: matched + missed };
    return res;
  }

  /* ---------------- 完成渲染 ---------------- */
  function finish(res){
    res.meta.fileName = state.file ? state.file.name : '—';
    res.meta.fileSize = state.file ? state.file.size : 0;
    decorateRegions(res);
    computeCompletions(res);
    state.result = res;
    state.tab = 'overview';
    var cur = res.progression.currentSlugcat;
    var exists = res.campaigns.some(function(c){ return c.slugcat === cur; });
    state.selected = exists ? cur : (res.campaigns[0] && res.campaigns[0].slugcat) || null;

    drop.hidden = true; loading.hidden = true; error.hidden = true;
    result.hidden = false;

    renderMeta();
    renderSidebar();
    renderDetail();
    window.scrollTo({ top:0, behavior:'smooth' });
  }

  function renderMeta(){
    var m = state.result.meta;
    $('meta-file').textContent = m.fileName;

    var cells = [
      ['文件大小', fmtBytes(m.fileSize)],
      ['角色战役', m.campaignCount],
      ['当前角色', m.currentSlugcat || state.result.progression.currentSlugcat || '—'],
      ['数据段', fmtInt(m.proglineCount)],
      ['存档串长度', fmtInt(m.saveStringLength) + ' 字符'],
      ['地图缩略图', fmtInt(m.mapThumbnails) + ' 张'],
      ['读取键', m.chosen],
      ['区域缩写匹配', (state.result.regionMatch ? state.result.regionMatch.matched + ' / ' + state.result.regionMatch.total : '—')],
      ['区域数据', (state.result.completionSummary
        ? state.result.completionSummary.regionsWithData + ' / ' + state.result.completionSummary.regionsTotal + ' 有分母'
        : '—')],
      ['校验和', m.checksum || '—']
    ];
    $('meta-grid').innerHTML = cells.map(function(c){
      return '<div class="meta-cell"><div class="k">' + esc(c[0]) + '</div><div class="v">' + esc(c[1]) + '</div></div>';
    }).join('');

    var warns = (state.result.warnings || []).slice();
    warns.unshift('校验和未在浏览器端校验（缺少 SALT，不影响读取）');
    $('warn-row').innerHTML = warns.map(function(w){
      return '<span class="chip-warn">' + esc(w) + '</span>';
    }).join('');
  }

  function renderSidebar(){
    var list = $('camplist');
    var current = state.result.progression.currentSlugcat;
    list.innerHTML = state.result.campaigns.map(function(c){
      var zh = slugZh(c.slugcat);
      var earned = c.passages.filter(function(p){ return p.earned; }).length;
      var total = c.passages.length;
      var pct = total ? Math.round(earned / total * 100) : 0;
      var active = c.slugcat === state.selected ? ' active' : '';
      var isCur = c.slugcat === current ? '<span class="camp-current">当前</span>' : '';
      return '<button class="camp' + active + '" type="button" data-slug="' + esc(c.slugcat) + '">' +
        '<div class="camp-top"><span class="camp-name">' + esc(c.slugcat) + '</span>' +
        (zh ? '<span class="camp-zh">' + esc(zh) + '</span>' : '') + isCur + '</div>' +
        '<div class="camp-meta"><span>周期 ' + esc(c.cycle == null ? '—' : c.cycle) + '</span>' +
        '<span>业力 ' + esc((c.karma == null ? '—' : c.karma) + '/' + (c.karmaCap == null ? '—' : c.karmaCap)) + '</span></div>' +
        '<div class="camp-region' + (c.denRegionMatched || (c.denRegionZh && c.denRegionZh !== '未识别') ? '' : ' unrec') + '" data-tip="' +
          esc('冬眠点 ' + (c.denPos || '—') + ' → ' + ((c.denRegionZh && c.denRegionZh !== '未识别')
            ? (c.denRegionZh + ' ' + (c.denRegionEn || c.denRegionAbbr || ''))
            : ('缩写 ' + (c.denRegionAbbr || '—') + '（既没有译名、也没导入这个区域的数据）'))) + '">' +
          ((c.denRegionZh && c.denRegionZh !== '未识别')
            ? esc(c.denRegionZh) + '<em>' + esc(c.denRegionEn || c.denRegionAbbr || '') + '</em>'
            : '未识别<em>' + esc(c.denRegionAbbr || '—') + '</em>') +
        '</div>' +
        '<div class="camp-bar"><span style="width:' + pct + '%"></span></div>' +
        '</button>';
    }).join('');

    Array.prototype.forEach.call(list.querySelectorAll('.camp'), function(btn){
      btn.addEventListener('click', function(){
        state.selected = btn.getAttribute('data-slug');
        state.tab = 'overview';
        state.killsExpanded = false;
        renderSidebar();
        renderDetail();
      });
    });
  }

  function currentCampaign(){
    return state.result.campaigns.filter(function(c){ return c.slugcat === state.selected; })[0] || null;
  }

  var TABS = [
    ['overview','概览'],
    ['passages','通行证'],
    ['regions','区域'],
    ['communities','好感度'],
    ['kills','击杀统计'],
    ['global','全局解锁'],
    ['docs','字段说明']
  ];

  function renderDetail(){
    var c = currentCampaign();
    if (!c) return;

    var zh = slugZh(c.slugcat);
    $('detail-head').innerHTML =
      '<div class="detail-title"><h2>' + esc(c.slugcat) + '</h2>' +
      (zh ? '<span class="zh">' + esc(zh) + '</span>' : '') + '</div>' +
      '<div class="detail-sub">种子 ' + esc(c.seed || '—') + ' · 冬眠点 ' + esc(c.denPos || '—') +
      ' <span class="sub-region' + (c.denRegionMatched || (c.denRegionZh && c.denRegionZh !== '未识别') ? '' : ' unrec') + '">（' +
        ((c.denRegionZh && c.denRegionZh !== '未识别')
          ? esc(c.denRegionZh) + (c.denRegionEn ? ' / ' + esc(c.denRegionEn) : '') + ' ' + esc(c.denRegionAbbr || '')
          : '未识别区域 ' + esc(c.denRegionAbbr || '—')) +
      '）</span>' +
      ' · 区域 ' + c.regions.length + ' · 通行证 ' + c.passages.filter(function(p){return p.earned;}).length + '/' + c.passages.length + '</div>' +
      '<div class="hero-stats">' +
        heroStat('周期', c.cycle, '', 'cycle') +
        heroStat('食物', c.food, '', 'food') +
        heroStat('业力', (c.karma == null ? '—' : c.karma), (c.karmaCap == null ? '' : ' / ' + c.karmaCap), 'karma') +
        heroStat('死亡', c.deaths, '', 'deaths') +
        heroStat('生存', c.survives, '', 'survives') +
      '</div>';

    $('tabs').innerHTML = TABS.map(function(t){
      return '<button class="tab' + (state.tab === t[0] ? ' active' : '') + '" type="button" data-tab="' + t[0] + '">' + t[1] + '</button>';
    }).join('');
    Array.prototype.forEach.call($('tabs').querySelectorAll('.tab'), function(btn){
      btn.addEventListener('click', function(){
        state.tab = btn.getAttribute('data-tab');
        renderDetail();
      });
    });

    var html = '';
    switch(state.tab){
      case 'overview': html = overviewHTML(c); break;
      case 'passages': html = passagesHTML(c); break;
      case 'regions': html = regionsHTML(c); break;
      case 'communities': html = communitiesHTML(c); break;
      case 'kills': html = killsHTML(c); break;
      case 'global': html = globalHTML(state.result.progression); break;
      case 'docs': html = docsHTML(); break;
    }
    $('detail-body').innerHTML = html;
    /* 击杀页：明细表开关 + Top N 滑块 + 扇区 hover */
    var kt = $('detail-body').querySelector('[data-killtable]');
    if (kt) kt.addEventListener('click', function(){
      state.killTable = !state.killTable;
      renderDetail();
    });
    bindKillsUI(c);

    Array.prototype.forEach.call($('detail-body').querySelectorAll('[data-sort]'), function(btn){
      btn.addEventListener('click', function(){
        var key = btn.getAttribute('data-sort');
        if (state.regionSort === key){
          state.regionSortDir = state.regionSortDir === 'asc' ? 'desc' : 'asc';
        } else {
          state.regionSort = key;
          state.regionSortDir = (key === 'completion') ? 'desc' : 'asc';
        }
        if (hasBridge()) bridgeCall('save_config', { ui: { regionSort: state.regionSort, regionSortDir: state.regionSortDir } }).catch(function(){});
        renderDetail();
      });
    });

    Array.prototype.forEach.call($('detail-body').querySelectorAll('[data-campsort]'), function(btn){
      btn.addEventListener('click', function(){
        var key = btn.getAttribute('data-campsort');
        if (state.campSort === key){
          state.campSortDir = state.campSortDir === 'asc' ? 'desc' : 'asc';
        } else {
          state.campSort = key;
          state.campSortDir = (key === 'name') ? 'asc' : 'desc';
        }
        renderDetail();
      });
    });

    Array.prototype.forEach.call($('detail-body').querySelectorAll('[data-src]'), function(btn){
      btn.addEventListener('click', function(e){
        e.preventDefault();
        e.stopPropagation();
        toggleSource(btn.getAttribute('data-src'));
      });
    });

    var manageBtn = $('src-manage');
    if (manageBtn) manageBtn.addEventListener('click', function(){ openRegionsModal(); });

    var rmBtn = $('reach-mode');
    if (rmBtn) rmBtn.addEventListener('click', function(){
      state.roomStrict = state.roomStrict === false;
      rmBtn.textContent = '口径：' + (state.roomStrict ? '严格' : '宽松');
      if (hasBridge()) bridgeCall('save_config', { ui: { roomStrict: state.roomStrict } }).catch(function(){});
      recompute();
      toast(state.roomStrict ? '完成度只算当前角色可达的房间' : '完成度按全部房间计算');
    });

    var worldBtn = $('world-graph');
    if (worldBtn) worldBtn.addEventListener('click', function(){ openWorldGraph(); });

    var pickBtn = $('ov-pick');
    if (pickBtn) pickBtn.addEventListener('click', function(){ openRegionPicker(currentCampaign()); });

    var ovBtn = $('ov-toggle');
    if (ovBtn) ovBtn.addEventListener('click', function(){
      var grid = $('ov-grid');
      if (!grid) return;
      var collapsed = grid.classList.toggle('collapsed');
      ovBtn.textContent = collapsed ? '展开' : '收起';
    });

    Array.prototype.forEach.call($('detail-body').querySelectorAll('[data-map]'), function(btn){
      btn.addEventListener('click', function(){
        openMap(btn.getAttribute('data-map'));
      });
    });
    Array.prototype.forEach.call($('detail-body').querySelectorAll('[data-graph]'), function(btn){
      btn.addEventListener('click', function(){
        openGraph(btn.getAttribute('data-graph'));
      });
    });
  }

  function heroStat(k, v, suffix, tipKey){
    var tip = tipKey && FIELD_DOCS[tipKey] ? ' data-tip="' + esc(FIELD_DOCS[tipKey]) + '"' : '';
    var val = (v == null || v === '') ? '—' : v;
    return '<div class="hero-stat"><div class="k">' + esc(k) + '</div>' +
      '<div class="v"' + tip + '>' + esc(val) + (suffix ? '<small>' + esc(suffix) + '</small>' : '') + '</div></div>';
  }

  function stat(k, v, tipKey, suffix){
    var tip = tipKey && FIELD_DOCS[tipKey] ? ' data-tip="' + esc(FIELD_DOCS[tipKey]) + '"' : '';
    var val = (v == null || v === '') ? '—' : v;
    return '<div class="stat"><div class="k">' + esc(k) +
      (tipKey ? '<span class="q"' + tip + '>?</span>' : '') + '</div>' +
      '<div class="v">' + esc(val) + (suffix ? '<small>' + esc(suffix) + '</small>' : '') + '</div></div>';
  }

  function statRegion(k, zh, en, tipKey, badge, unmatched){
    var tip = tipKey && FIELD_DOCS[tipKey] ? ' data-tip="' + esc(FIELD_DOCS[tipKey]) + '"' : '';
    return '<div class="stat"><div class="k">' + esc(k) +
      (tipKey ? '<span class="q"' + tip + '>?</span>' : '') + '</div>' +
      '<div class="v region' + (unmatched ? ' unrec' : '') + '">' +
        '<span>' + esc(zh || '—') + (badge ? '<small> ' + esc(badge) + '</small>' : '') + '</span>' +
        (en ? '<em>' + esc(en) + '</em>' : '') +
      '</div></div>';
  }

  function section(title, inner){
    return '<div class="section"><div class="section-title"><span>' + esc(title) + '</span><span class="line"></span></div>' + inner + '</div>';
  }

  function overviewHTML(c){
    var h = '';
    h += section('基础进度', '<div class="stat-grid">' +
      stat('种子 SEED', c.seed || '—', 'seed') +
      stat('周期 CYCLENUM', c.cycle, 'cycle', ' 天') +
      stat('食物 FOOD', c.food, 'food') +
      stat('冬眠点 DENPOS', c.denPos || '—', 'den') +
      statRegion('所在区域', c.denRegionZh, c.denRegionMatched ? c.denRegionEn : '', 'denRegion',
        c.denRegionMatched ? '' : ('缩写 ' + (c.denRegionAbbr || '—')), !c.denRegionMatched) +
      stat('上一冬眠点', c.lastDenPos || '—', 'lastDen') +
      stat('业力 KARMA', (c.karma == null ? '—' : c.karma) + ' / ' + (c.karmaCap == null ? '—' : c.karmaCap), 'karma', c.reinforced ? ' 强化' : '') +
      stat('神经元发光 HASTHEGLOW', c.hasGlow ? '是' : '否', 'glow') +
      stat('交流印记 HASTHEMARK', c.hasMark ? '是' : '否', 'mark') +
      '</div>');

    var lt = lifetime(c);
    h += section('统计', '<div class="stat-grid">' +
      stat('死亡 DEATHS', c.deaths, 'deaths') +
      stat('生存 SURVIVES', c.survives, 'survives') +
      stat('退出 QUITS', c.quits, 'quits') +
      stat('总食物 TOTFOOD', c.totalFood, 'totalFood') +
      stat('击杀总数', sumKills(c.kills), 'kills', ' 次') +
      stat('幼崽伙伴', c.friends, 'friends') +
      stat('数据版本', (c.version || '—') + ' / ' + (c.worldVersion || '—'), 'worldVersion') +
      '</div>');

    h += section('时间统计', '<div class="stat-grid">' +
      stat('总时长', lt.total == null ? '—' : fmtHMS(lt.total), 'totalTime') +
      stat('存活时长 TOTTIME', lt.alive == null ? '—' : fmtHMS(lt.alive), 'aliveTime') +
      stat('死亡相关时长 DEATHTIME', lt.dead == null ? '—' : fmtHMS(lt.dead), 'deathTime') +
      stat('存活占比', lt.pct == null ? '—' : lt.pct.toFixed(1) + '%', 'alivePct') +
      '</div>' +
      (lt.pct == null ? '' :
        '<div style="margin-top:12px" class="pass-progress"><span style="width:' + Math.max(0, Math.min(100, lt.pct)).toFixed(1) + '%"></span></div>' +
        '<div style="margin-top:7px;color:var(--muted);font-size:12px">存活 ' + fmtHMS(lt.alive) + ' ／ 总计 ' + fmtHMS(lt.total) +
        '　·　其中死亡相关 ' + fmtHMS(lt.dead) + '</div>'));

    // 进度概览条
    var earned = c.passages.filter(function(p){ return p.earned; }).length;
    var total = c.passages.length;
    var pct = total ? Math.round(earned / total * 100) : 0;
    h += section('收集进度', 
      '<div class="stat-grid">' +
        stat('通行证', earned + ' / ' + total, 'passage', ' 完成') +
        stat('区域', c.regions.length, 'region', ' 个') +
        stat('击杀总数', sumKills(c.kills), 'kills', ' 次') +
      '</div>' +
      '<div style="margin-top:12px" class="pass-progress"><span style="width:' + pct + '%"></span></div>' +
      '<div style="margin-top:7px;color:var(--muted);font-size:12px">通行证完成度 ' + pct + '%</div>');

    // 收集品：重要珍珠（从原「物品」页挪过来，0 枚时不占位）
    if (c.significantPearls.length){
      h += section('收集品',
        '<div class="stat-grid">' +
          stat('重要珍珠', c.significantPearls.length, 'pearl', ' 枚') +
        '</div>' +
        '<div class="chips" style="margin-top:12px">' +
          c.significantPearls.map(function(p){ return '<span class="chip">' + esc(p) + '</span>'; }).join('') +
        '</div>' +
        '<div class="format-note" style="margin-top:10px">已交付 / 已记录的重要珍珠所在房间；普通珍珠不计入。</div>');
    }

    return h;
  }

  function passagesHTML(c){
    var earned = c.passages.filter(function(p){ return p.earned; }).length;
    var total = c.passages.length;
    var pct = total ? Math.round(earned / total * 100) : 0;
    var h = '<div class="pass-head">' +
      '<div class="pass-count"><b>' + earned + '</b> / ' + total + ' 已完成</div>' +
      '<div class="pass-progress"><span style="width:' + pct + '%"></span></div>' +
      '<div class="pass-count">' + pct + '%</div></div>';
    if (!total) return h + '<div class="empty">该角色没有通行证数据。</div>';
    h += '<div class="pass-list">' + c.passages.map(function(p){
      var prog = p.progress && p.progress.length ? p.progress[0] : '';
      if (prog.length > 18) prog = prog.slice(0, 18) + '…';
      var zh = PASSAGE_ZH[p.name] || '';
      return '<div class="pass' + (p.earned ? ' done' : '') + '">' +
        '<span class="mark">' + (p.earned ? '✓' : '·') + '</span>' +
        '<span class="pn">' + esc(zh || p.name) + (zh ? '<span style="color:var(--dim);font-size:10.5px;margin-left:5px">' + esc(p.name) + '</span>' : '') + '</span>' +
        '<span class="pp">' + (prog ? '进度 ' + esc(prog) : '') + '</span>' +
        '</div>';
    }).join('') + '</div>';
    return h;
  }

  /* 数据列：把该区域所有来源纵向排开，点一下就切换是否参与计算 */
  function sourceChipsHTML(code, fallbackTag){
    var rd = regionData(code);
    if (!rd || !rd.layers || !rd.layers.length){
      return fallbackTag || '<span class="tag off">缺数据</span>';
    }
    var rows = rd.layers.map(function(L){
      var on = !!L.enabled;
      var name = L.sourceName || L.label || L.id;
      var cls = 'src-chip' + (on ? ' on' : '') + ' k-' + (L.sourceKind || 'mod') + (L.mapOnly ? ' maponly' : '');
      var tip = name + ' · ' + (L.roomCount || 0) + ' 间';
      tip += L.mapOnly
        ? ' · 仅地图：没有 world 文件，不参与分母'
        : (on ? ' · 参与计算' : ' · 已熄灭，不参与计算');
      if (L.upToDate === false) tip += ' · 源文件已变化，建议重新导入';
      if (L.hasMap) tip += ' · 有底图';
      tip += '（点击' + (on ? '熄灭' : '点亮') + '）';
      return '<button class="' + cls + '" type="button" data-src="' + esc(L.sourceId || L.id) + '" data-tip="' + esc(tip) + '">' +
        '<span class="sc-n">' + esc(name) + '</span>' +
        '<b>' + (L.roomCount || 0) + '</b>' +
        (L.mapOnly ? '<i>仅地图</i>' : '') +
        '</button>';
    }).join('');
    return '<div class="src-col">' + rows + '</div>';
  }

  var lastOverview = null;   /* 最近一次算出的全域探索总览，供自检脚本读取 */

  function regionsHTML(c){
    if (!c.regions.length) return '<div class="empty">没有区域状态数据。</div>';

    var SORTS = [
      { key:'code',       label:'区域缩写' },
      { key:'lastCycle',  label:'最后更新周期' },
      { key:'completion', label:'已访房间百分比' }
    ];
    var onCount = state.sources.filter(function(s){ return s.enabled; }).length;
    var totalSrc = state.sources.length;

    var sortBar = '<div class="sortbar"><span>排序</span>' + SORTS.map(function(s){
      var on = state.regionSort === s.key;
      return '<button class="sort-btn' + (on ? ' on' : '') + '" type="button" data-sort="' + s.key + '">' +
        s.label + (on ? '<span class="dir">' + (state.regionSortDir === 'asc' ? '↑' : '↓') + '</span>' : '') +
        '</button>';
    }).join('') +
      '<span style="margin-left:6px;color:var(--dim)">点击同一项切换升降序</span>' +
      '<button class="sort-btn" type="button" id="src-manage" style="margin-left:auto" ' +
        'data-tip="管理数据来源：改名、点亮/熄灭、移除。点亮状态会影响所有区域的完成度分母。">来源 ' +
        onCount + ' / ' + totalSrc + '</button>' +
      '<button class="sort-btn" type="button" id="reach-mode" style="margin-left:8px" ' +
        'data-tip="完成度分母口径。严格：只算当前角色能到的房间（会标出剔除了几间）；宽松：所有房间都算">' +
        '口径：' + (state.roomStrict === false ? '宽松' : '严格') + '</button>' +
      '<button class="btn ghost world-btn" type="button" id="world-graph" ' +
        'data-tip="把整张地图画成拓扑图：一个区域一个点，业力门是连线">◈ 世界拓扑</button></div>';

    var rowsData = c.regions.slice();
    var dir = state.regionSortDir === 'asc' ? 1 : -1;
    rowsData.sort(function(a, b){
      if (state.regionSort === 'lastCycle'){
        var va = a.lastCycle == null ? -1 : a.lastCycle;
        var vb = b.lastCycle == null ? -1 : b.lastCycle;
        return (va - vb) * dir;
      }
      if (state.regionSort === 'completion'){
        var ca = a.completion || {}, cb = b.completion || {};
        var pa = ca.pct == null ? -1 : ca.pct;
        var pb = cb.pct == null ? -1 : cb.pct;
        if (pa !== pb) return (pa - pb) * dir;
        return String(a.name).localeCompare(String(b.name));
      }
      return String(a.name).localeCompare(String(b.name)) * dir;
    });

    var maxRooms = Math.max.apply(null, c.regions.map(function(r){ return r.roomsVisited || 0; }).concat([1]));
    var cycle = c.cycle;
    var ghostMap = {};
    Object.keys(c.ghosts || {}).forEach(function(k){ ghostMap[String(k).toUpperCase()] = c.ghosts[k]; });

    var rows = rowsData.map(function(r){
      var cp = r.completion || {};
      var barW = Math.round((r.roomsVisited || 0) / maxRooms * 100);

      var compCell;
      if (cp.pct != null){
        var sub = [];
        if (cp.variant) sub.push('变体 ' + cp.variant);
        /* 来源名最多列 3 个：分层导入后一个区域可能有十几个来源，全列出来会把表格撑宽 */
        if (cp.layerNames && cp.layerNames.length > 1){
          var ln = cp.layerNames;
          sub.push(ln.length > 3
            ? ln.slice(0, 3).join(' + ') + ' 等 ' + ln.length + ' 个来源'
            : ln.join(' + '));
        }
        if (cp.conditionalDropped) sub.push('条件房间 −' + cp.conditionalDropped);
        if (cp.roleDropped) sub.push('角色专属 −' + cp.roleDropped);
        if (cp.manualDropped) sub.push('手动排除 −' + cp.manualDropped);
        if (cp.unknown) sub.push('来源未知 ' + cp.unknown);
        compCell = '<div class="comp">' +
          '<div class="comp-top"><span><b>' + cp.visited + '</b> / ' + cp.total + '</span>' +
          '<span class="pct">' + cp.pct.toFixed(1) + '%</span></div>' +
          '<div class="comp-bar"><span style="width:' + Math.max(1, Math.min(100, cp.pct)).toFixed(1) + '%"></span></div>' +
          (sub.length ? '<div class="numsub">' + esc(sub.join(' · ')) + '</div>' : '') +
          '</div>';
      } else {
        var noTip = cp.reason === 'disabled'
          ? '这个区域的数据源都被熄灭了：点亮「数据」列里的来源才会计算分母'
          : (cp.reason === 'maponly'
            ? '这个区域只有地图数据，没有房间清单（world 文件），不能作为分母'
            : '尚未导入该区域的房间数据，无法计算百分比；当前只显示已访房间数');
        compCell = '<div class="comp dim" data-tip="' + esc(noTip) + '">' +
          '<div class="comp-top"><span><b>' + (r.roomsVisited || 0) + '</b> 间已访</span>' +
          '<span class="pct">—</span></div>' +
          '<div class="comp-bar"><span style="width:' + barW + '%"></span></div>' +
          '</div>';
      }

      var away = (cycle != null && r.lastCycle != null) ? (cycle - r.lastCycle) : null;

      var shelterCell = cp.sheltersTotal
        ? cp.sheltersVisited + ' / ' + cp.sheltersTotal
        : '—';
      var gateCell = cp.gatesTotal ? cp.gatesVisited + ' / ' + cp.gatesTotal : '—';
      var pearlCount = (r.objectTypes && r.objectTypes.DataPearl) || 0;
      var echoCount = ghostMap[String(r.name).toUpperCase()] || 0;

      var tag;
      if (cp.source === 'import') tag = '<span class="tag ok">已导入</span>';
      else if (cp.reason === 'disabled') tag = '<span class="tag warn">未点亮</span>';
      else if (cp.reason === 'maponly') tag = '<span class="tag warn">仅地图</span>';
      else tag = '<span class="tag off">缺数据</span>';

      return '<tr>' +
        '<td><span class="region-code">' + esc(r.name) + '</span>' +
          (hasMapCoords(r.name)
            ? '<button class="sort-btn" style="margin-left:6px;padding:2px 7px" type="button" data-map="' + esc(String(r.name).toUpperCase()) + '">图</button>'
            : '') +
          (gxGraphable(r.name)
            ? '<button class="sort-btn" style="margin-left:4px;padding:2px 7px" type="button" data-graph="' + esc(String(r.name).toUpperCase()) + '">关系</button>'
            : '') +
        '</td>' +
        '<td class="region-name' + (r.regionMatched ? '' : ' unrec') + '">' +
          '<div class="rn-zh">' + esc(r.zh || '未识别') + '</div>' +
          (r.en ? '<div class="rn-en">' + esc(r.en) + '</div>' : '') +
        '</td>' +
        '<td>' + compCell + '</td>' +
        '<td class="num">' + esc(r.lastCycle == null ? '—' : r.lastCycle) + '</td>' +
        '<td class="num">' + (away == null ? '—' : (away === 0 ? '<span style="color:var(--teal)">本周期</span>' : away)) + '</td>' +
        '<td class="num">' + shelterCell + '</td>' +
        '<td class="num">' + gateCell + '</td>' +
        '<td class="num">' + (r.swarmRooms || 0) + '</td>' +
        '<td class="num">' + (pearlCount || '—') + '</td>' +
        '<td class="num">' + echoCount + '</td>' +
        '<td>' + sourceChipsHTML(r.name, tag) + '</td>' +
        '</tr>';
    }).join('');

    var withData = c.regions.filter(function(r){ return r.completion && r.completion.pct != null; }).length;
    var note = '<div class="format-note" style="margin-bottom:10px">' +
      '完成度分母 = <b>点亮来源</b>的房间并集（' + withData + ' / ' + c.regions.length + ' 个区域有分母，' +
      onCount + ' / ' + totalSrc + ' 个来源点亮）。点「数据」列里的来源可以单独点亮/熄灭，右上角「来源」按钮可改名或移除。' +
      '「仅地图」的来源没有 world 文件，不参与分母；「来源未知」= 存档里去过的房间但没有任何已导入来源认领，<b>不计入分母</b>。' +
      '角色有专属地图版本时（圣徒 / 工匠 / 矛大师…）分母自动换成该版本清单，行内标「变体 xxx」；' +
      '「条件房间 −N」= 只对别的角色存在（EXCLUSIVEROOM）或对本角色隐藏（HIDEROOM）的房间，已从分母剔除。' +
      '「最后更新周期」是该区域状态最后一次被刷新的周期；「距今」= 本战役周期 − 最后更新周期。' +
      '</div>';

    /* 这个角色「有没有活动」以存档里的区域状态为准 —— 没进过的区域一律不进总览。
       理由：区域能不能去是剧情决定的（LM 只有工匠/矛大师、WA* 只有守护者…），
       游戏数据里没有这张表，硬猜会把玩家能去的地方藏掉。想统计别的区域，用「区域选择」手动加。 */
    var touched = {};
    c.regions.forEach(function(r){ touched[String(r.name).toUpperCase()] = 1; });
    var allImported = Object.keys(state.regions || {}).sort();

    var pickKey = String(c.slugcat || '');
    var picked = {};
    ((state.regionPick || {})[pickKey] || []).forEach(function(k){
      picked[String(k).toUpperCase()] = 1;
    });

    /* ---- 全域探索总览 ----
       口径：分母 = 每个区域「点亮来源 + 角色变体 − 条件房间」的房间数，与下表完全一致。 */
    var ovList = [], ovSeen = {};
    c.regions.forEach(function(r){
      var cp = r.completion || {};
      if (cp.pct == null || !cp.total) return;
      var key = String(r.name).toUpperCase();
      ovSeen[key] = 1;
      ovList.push({ code: key, pct: cp.pct, visited: cp.visited || 0, total: cp.total, touched: true });
    });
    allImported.forEach(function(code){
      var key = String(code).toUpperCase();
      if (ovSeen[key] || !picked[key]) return;
      var rd = regionData(key);
      if (!rd) return;
      var sets = regionRoomSets(rd, c.slugcat);
      if (!sets || !sets.total) return;
      ovSeen[key] = 1;
      ovList.push({ code: key, pct: 0, visited: 0, total: sets.total, touched: false, picked: true });
    });

    var ovTotal = 0, ovVisited = 0, ovTouchTotal = 0, ovTouchVisited = 0, ovTouched = 0, ovFull = 0;
    var ovSkipped = 0;   /* 手动加了但算不出分母（只有地图 / 来源被熄灭）的区域 */
    ovList.forEach(function(o){
      ovTotal += o.total; ovVisited += o.visited;
      if (o.touched){ ovTouched++; ovTouchTotal += o.total; ovTouchVisited += o.visited; }
      if (o.pct >= 99.95) ovFull++;
    });
    Object.keys(picked).forEach(function(key){
      if (!ovSeen[key] && state.regions[key]) ovSkipped++;
    });
    var ovPct = ovTotal ? ovVisited / ovTotal * 100 : 0;
    var ovTouchPct = ovTouchTotal ? ovTouchVisited / ovTouchTotal * 100 : 0;
    var ovAdded = ovList.length - ovTouched;
    lastOverview = {
      regions: ovList.length, touched: ovTouched, added: ovAdded, full: ovFull,
      total: ovTotal, visited: ovVisited,
      pct: Math.round(ovPct * 100) / 100,
      touchedTotal: ovTouchTotal, touchedVisited: ovTouchVisited,
      touchedPct: Math.round(ovTouchPct * 100) / 100,
      imported: allImported.length, hidden: allImported.length - ovList.length,
      skipped: ovSkipped,
      picked: Object.keys(picked)
    };

    var ovCells = ovList.slice().sort(function(a, b){
      /* 有活动的排前面（完成度高的更靠前），手动加进来的按缩写列在后面 */
      if (a.touched !== b.touched) return a.touched ? -1 : 1;
      if (a.touched && Math.abs(a.pct - b.pct) > 0.05) return b.pct - a.pct;
      return a.code.localeCompare(b.code);
    }).map(function(o){
      var info = regionData(o.code) || {};
      var zh = info.zh || info.nameZh || '';
      var cls = 'ov-cell' + (o.pct >= 99.95 ? ' full' : (o.pct <= 0 ? ' zero' : ''));
      var shown = o.pct >= 99.95 ? '100' : (o.pct > 0 ? String(Math.max(1, Math.min(99, Math.round(o.pct)))) : '0');
      var tip = o.code + (zh ? ' ' + zh : '') + ' · ' + o.visited + ' / ' + o.total + ' 间' +
        (o.touched ? '（' + o.pct.toFixed(1) + '%）'
          : (o.picked ? '（手动添加，这个角色还没进去过）' : '（这个角色没踏足过）')) + ' · 点开看地图';
      return '<button class="' + cls + '" type="button" data-map="' + esc(o.code) +
        '" data-tip="' + esc(tip) + '">' +
        '<b>' + esc(o.code) + '</b>' +
        '<span class="ov-p">' + shown + '<i>%</i></span>' +
        '<span class="ov-mini"><i style="width:' + Math.max(1.5, Math.min(100, o.pct)).toFixed(1) + '%"></i></span>' +
        '</button>';
    }).join('');

    var overviewHTML = ovList.length
      ? '<div class="ov-box">' +
          '<div class="ov-head">' +
            '<div>' +
              '<div class="ov-big">全域探索 ' + ovPct.toFixed(1) + '%</div>' +
              '<div class="ov-stat">已踏足 <b>' + ovTouched + '</b> 个区域 · ' +
                '<b>' + ovTouchVisited + '</b> / <b>' + ovTouchTotal + '</b> 间 = <b>' +
                ovTouchPct.toFixed(1) + '%</b> · 已走遍 <b>' + ovFull + '</b> 个</div>' +
              '<div class="ov-stat">计入 <b>' + ovList.length + '</b> 个区域（有活动 <b>' + ovTouched +
                '</b> + 手动 <b>' + ovAdded + '</b>）· 合计 <b>' + ovVisited + '</b> / <b>' + ovTotal + '</b> 间' +
                (ovSkipped ? ' · <b>' + ovSkipped + '</b> 个手动区域缺数据未计入' : '') +
                (allImported.length > ovList.length + ovSkipped
                  ? ' · 另有 <b>' + (allImported.length - ovList.length - ovSkipped) + '</b> 个区域未计入' : '') +
              '</div>' +
              '<div class="ov-hint">默认只统计该角色进去过的区域，用「区域选择」可以再加 · ' +
                '点格子打开该区域地图</div>' +
            '</div>' +
            '<button class="btn ghost" type="button" id="ov-pick">区域选择 ' +
              ovList.length + ' / ' + allImported.length + '</button>' +
            '<button class="btn ghost" type="button" id="ov-toggle">收起</button>' +
          '</div>' +
          '<div class="ov-bar"><i style="width:' + Math.max(0.6, Math.min(100, ovPct)).toFixed(1) + '%"></i></div>' +
          '<div class="ov-grid" id="ov-grid">' + ovCells + '</div>' +
        '</div>'
      : '';

    /* 没有进总览、也没挑中的导入区域：点开能看该区域全部房间号（等于「全未探索」清单） */
    var untouched = allImported.filter(function(k){
      var key = String(k).toUpperCase();
      return !touched[key] && !picked[key];
    });
    var untouchedHTML = untouched.length
      ? '<details class="untouched-box"><summary>还有 ' + untouched.length +
        ' 个导入区域没有计入（默认只统计这个角色进去过的区域）· 点开可看全部房间号</summary>' +
        '<div class="untouched-chips">' + untouched.map(function(k){
          var info = regionData(k) || {};
          var zh = info.zh || info.nameZh || '';
          return '<button class="mu-chip' + (hasMapCoords(k) ? '' : ' nocoord') + '" type="button" data-map="' +
            esc(k) + '">' + esc(k) + (zh ? ' ' + esc(zh) : '') + '</button>';
        }).join('') + '</div></details>'
      : '';

    return sortBar + overviewHTML + note +
      untouchedHTML +
      '<div class="table-wrap"><table class="reg-table"><thead><tr>' +
      '<th>区域</th><th>名称（中文 / English）</th><th>完成度</th>' +
      '<th style="text-align:right">最后更新</th><th style="text-align:right">距今</th>' +
      '<th style="text-align:right">庇护所</th><th style="text-align:right">大门</th>' +
      '<th style="text-align:right">蝠蝇房</th><th style="text-align:right">珍珠</th>' +
      '<th style="text-align:right">回响</th><th>数据</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  /* 区域可达性提示（data/region_access.json）：只拿来说一句「通常只有谁能进」，
     不做任何过滤 —— 真正的显示集合由「有活动 + 手动挑选」决定。 */
  /* 这个角色能不能到某个区域。
     规则：存档里去过 = 一定可达（事实优先）；否则查 region_reach.json；表里没写 = 可达。 */
  function regionReachInfo(code, slugcat, touched){
    var up = String(code || '').toUpperCase();
    var cat = canonSlugcat(slugcat);
    var table = (state.regionReach && state.regionReach.regions) || {};
    var hit = table[up] || null;
    if (!hit){
      Object.keys(table).forEach(function(k){
        if (hit) return;
        if (table[k] && table[k].prefix && up.indexOf(k) === 0) hit = table[k];
      });
    }
    if (touched) return { reach: true, note: '', why: 'visited' };
    if (!hit) return { reach: true, note: '', why: 'default' };
    var allow = (hit.only || []).concat(hit.unlock || []);
    if (!allow.length) return { reach: true, note: hit.note || '', why: 'default' };
    var ok = allow.some(function(c){ return canonSlugcat(c) === cat; });
    var names = allow.map(function(c){ return regionOwnerName(c); }).filter(Boolean).join(' / ');
    return { reach: ok, note: hit.note || ('通常只有 ' + names + ' 能进'), why: 'table' };
  }

  var OWNER_ZH = {
    survivor: '白猫', monk: '黄猫', hunter: '红猫', nightcat: '夜猫',
    spearmaster: '矛大师', artificer: '工匠', saint: '圣徒',
    rivulet: '溪流', gourmand: '饕餮', inv: '无敌', watcher: '守护者', enot: 'Enot'
  };
  function regionOwnerName(c){
    var k = canonSlugcat(c);
    return OWNER_ZH[k] || String(c);
  }

  function regionAccessNote(code){
    var key = String(code).toUpperCase();
    var map = (state.regionAccess && state.regionAccess.regions) || {};
    var hit = map[key];
    if (!hit && key.charAt(0) === 'W') hit = map.W;
    return (hit && hit.note) ? hit.note : '';
  }

  /* ---------------- 区域选择：手动指定总览里统计哪些区域 ---------------- */
  function openRegionPicker(campaign){
    var slugcat = String((campaign && campaign.slugcat) || '');
    var touched = {};
    ((campaign && campaign.regions) || []).forEach(function(r){
      touched[String(r.name).toUpperCase()] = 1;
    });
    var codes = Object.keys(state.regions || {}).sort();
    var picked = {};
    ((state.regionPick || {})[slugcat] || []).forEach(function(k){
      picked[String(k).toUpperCase()] = 1;
    });

    var rows = codes.map(function(code){
      var key = String(code).toUpperCase();
      var info = regionData(key) || {};
      var zh = info.zh || info.nameZh || '';
      var on = !!touched[key];
      var note = regionAccessNote(key);
      return '<label class="pick-row' + (on ? ' on' : '') + '"' +
          ' data-q="' + esc((key + ' ' + zh).toLowerCase()) + '">' +
        '<input type="checkbox" data-pick="' + esc(key) + '"' +
          ((on || picked[key]) ? ' checked' : '') + (on ? ' disabled' : '') + '>' +
        '<b>' + esc(key) + '</b>' +
        '<span class="pr-zh">' + esc(zh || '未识别') + '</span>' +
        (on ? '<span class="pr-tag">有活动</span>' : '') +
        (note ? '<span class="pr-note">' + esc(note) + '</span>' : '') +
        '</label>';
    }).join('');

    var onCount = codes.filter(function(c){ return touched[String(c).toUpperCase()]; }).length;

    openModal('区域选择 · ' + esc(slugcat), 
      '默认只统计这个角色进去过的区域（' + onCount + ' 个）；其余想看的勾上即可，按角色分别记住。',
      '<div class="pick-tools">' +
        '<input class="pick-search" id="pick-search" type="search" placeholder="搜索区域缩写 / 名称" autocomplete="off">' +
        '<button class="btn ghost" type="button" id="pick-all">全选</button>' +
        '<button class="btn ghost" type="button" id="pick-none">清空</button>' +
        '<span class="pick-stat" id="pick-stat"></span>' +
      '</div>' +
      '<div class="pick-list" id="pick-list">' + rows + '</div>' +
      '<div class="pick-foot">' +
        '<span>「有活动」的区域始终计入，取消不掉；勾选只影响总览的统计范围，不影响区域表的完成度。</span>' +
        '<button class="btn" type="button" id="pick-apply">应用</button>' +
      '</div>');

    var listEl = $('pick-list');
    var statEl = $('pick-stat');
    function boxes(){ return listEl ? listEl.querySelectorAll('input[data-pick]') : []; }
    function refreshStat(){
      if (!statEl) return;
      var on = 0;
      Array.prototype.forEach.call(boxes(), function(b){ if (b.checked) on++; });
      statEl.textContent = '已选 ' + on + ' / ' + codes.length;
    }
    function filter(q){
      q = String(q || '').trim().toLowerCase();
      Array.prototype.forEach.call(listEl.querySelectorAll('.pick-row'), function(row){
        var hit = !q || (row.getAttribute('data-q') || '').indexOf(q) >= 0;
        row.style.display = hit ? '' : 'none';
      });
    }
    Array.prototype.forEach.call(boxes(), function(b){
      b.addEventListener('change', refreshStat);
    });
    var searchEl = $('pick-search');
    if (searchEl) searchEl.addEventListener('input', function(){ filter(searchEl.value); });
    var allBtn = $('pick-all');
    if (allBtn) allBtn.addEventListener('click', function(){
      Array.prototype.forEach.call(listEl.querySelectorAll('.pick-row'), function(row){
        if (row.style.display === 'none') return;
        var b = row.querySelector('input[data-pick]');
        if (b && !b.disabled) b.checked = true;
      });
      refreshStat();
    });
    var noneBtn = $('pick-none');
    if (noneBtn) noneBtn.addEventListener('click', function(){
      Array.prototype.forEach.call(listEl.querySelectorAll('.pick-row'), function(row){
        if (row.style.display === 'none') return;
        var b = row.querySelector('input[data-pick]');
        if (b && !b.disabled) b.checked = false;
      });
      refreshStat();
    });
    var applyBtn = $('pick-apply');
    if (applyBtn) applyBtn.addEventListener('click', function(){
      var list = [];
      Array.prototype.forEach.call(boxes(), function(b){
        if (b.checked && !b.disabled) list.push(b.getAttribute('data-pick'));
      });
      state.regionPick = state.regionPick || {};
      if (list.length) state.regionPick[slugcat] = list.sort();
      else delete state.regionPick[slugcat];
      if (hasBridge()) bridgeCall('save_config', { ui: { regionPick: state.regionPick } }).catch(function(){});
      closeModal();
      renderDetail();
      toast(list.length ? ('已加入 ' + list.length + ' 个区域') : '已恢复为只统计有活动的区域');
    });
    refreshStat();
  }

  function communitiesHTML(c){
    if (!c.communities.length) return '<div class="empty">没有好感度数据。</div>';
    var rows = c.communities.map(function(comm){
      var v = comm.values['EVERY'];
      if (v == null) v = 0;
      var pos = (v + 1) / 2 * 100;
      var posClamped = Math.max(0, Math.min(100, pos));
      var fillStyle = v >= 0
        ? 'left:50%;width:' + Math.max(0, posClamped - 50) + '%'
        : 'left:' + posClamped + '%;width:' + Math.max(0, 50 - posClamped) + '%';
      var cls = v >= 0 ? 'comm-fill' : 'comm-fill neg';
      return '<div class="comm">' +
        '<div class="comm-name">' + esc(commZh(comm.name)) + '<span>' + esc(comm.name) + '</span></div>' +
        '<div class="comm-track"><div class="comm-zero"></div><div class="' + cls + '" style="' + fillStyle + '"></div></div>' +
        '<div class="comm-val">' + (v >= 0 ? '+' : '') + v.toFixed(2) + '</div>' +
        '</div>';
    }).join('');
    return '<div class="section"><div class="section-title"><span>全局好感度（EVERY）</span><span class="line"></span></div>' + rows + '</div>' +
           '<div class="format-note" style="margin-top:12px">数值范围 -1 ~ 1：越高表示该生物对你越友好；负值表示敌意。</div>';
  }

  /* ---------------- 击杀分布（纯 SVG 环形图，无三方库） ---------------- */
  var SLICE_COLORS = ['#63d2c4','#e8b04a','#e8794a','#9b7fe8','#5aa9e6','#d96ba0',
    '#8fbf5a','#c9a227','#7fd1e8','#b06bd9','#e05c5c','#88c0a0'];
  var OTHER_COLOR = '#6b7280';
  var lastSlices = [];   /* 供 hover 绑定时取用：最近一次画出的扇区模型 */

  function clampTopN(n, count){
    var k = parseInt(n, 10);
    if (isNaN(k)) k = 8;
    if (count < 1) return 1;
    if (k < 1) k = 1;
    if (k > count) k = count;
    return k;
  }

  function legendRow(item, total, extraClass){
    var pct = total ? (item.total / total * 100) : 0;
    var en = item.en ? ' data-tip="' + esc(item.en) + '"' : '';
    return '<div class="dl-row' + (extraClass ? ' ' + extraClass : '') + '" data-lg="' + item.idx + '"' + en + '>' +
      '<span class="dl-dot" style="background:' + item.color + '"></span>' +
      '<span class="dl-name">' + esc(item.name) + '</span>' +
      '<span class="dl-num">' + item.total + ' · ' + pct.toFixed(1) + '%</span>' +
      '<span class="dl-score">' + (item.score ? item.score + ' 分' : '—') + '</span>' +
      '</div>';
  }

  /* 返回 HTML；同时把扇区模型存进 lastSlices 供交互绑定 */
  function donutHTML(groups, topN){
    var total = groups.reduce(function(n, g){ return n + g.total; }, 0);
    if (!total) return '<div class="empty">没有击杀数据</div>';
    var k = clampTopN(topN, groups.length);
    var shown = groups.slice(0, k);
    var rest = groups.slice(k);
    var items = [], start = 0;
    var R = 84, W = 26, C = 2 * Math.PI * R;

    shown.forEach(function(g, i){
      items.push({ idx: items.length, name: g.name, en: shortEn(Object.keys(g.variants)),
        total: g.total, score: g.score, color: SLICE_COLORS[i % SLICE_COLORS.length] });
    });
    if (rest.length){
      items.push({ idx: items.length, name: '其他 ' + rest.length + ' 种', en: '',
        total: rest.reduce(function(n, g){ return n + g.total; }, 0),
        score: rest.reduce(function(n, g){ return n + g.score; }, 0),
        color: OTHER_COLOR, other: true });
    }

    var slices = items.map(function(it, i){
      var len = it.total / total * C;
      var dash = Math.max(0, len - 1.4).toFixed(2) + ' ' + (C - Math.max(0, len - 1.4)).toFixed(2);
      var el = '<circle class="slice" data-slice="' + i + '" cx="110" cy="110" r="' + R + '" fill="none" stroke="' + it.color +
        '" stroke-width="' + W + '" stroke-dasharray="' + dash + '" stroke-dashoffset="' + (-start).toFixed(2) +
        '" transform="rotate(-90 110 110)"></circle>';
      start += len;
      return el;
    }).join('');

    var legend = items.map(function(it){ return legendRow(it, total, it.other ? 'other' : ''); }).join('');
    lastSlices = items;

    return '<div class="donut-wrap">' +
      '<svg class="donut-svg" id="donut" viewBox="0 0 220 220" role="img" aria-label="击杀分布环形图">' +
        slices +
        '<text class="dc-main" id="dc-main" x="110" y="106">' + fmtNum(total) + '</text>' +
        '<text class="dc-sub" id="dc-sub" x="110" y="128">总击杀</text>' +
      '</svg>' +
      '<div class="donut-legend' + (items.length > 20 ? ' dense' : '') + '" id="donut-legend">' + legend + '</div>' +
      '</div>';
  }

  function killsHTML(c){
    var groups = killGroups(c.kills);
    if (!groups.length) return '<div class="empty">这个战役还没有击杀记录。</div>';
    var totalKills = groups.reduce(function(n, g){ return n + g.total; }, 0);
    var sc = calcScore(c);
    var k = clampTopN(state.killsTopN, groups.length);

    var h = '<div class="section"><div class="section-title"><span>击杀分布</span><span class="line"></span></div>' +
      '<div class="kill-head">' +
        '<span class="kh-note">' + groups.length + ' 种 · 合计 ' + totalKills + ' 次 · 击杀得分 ' + fmtNum(sc.killScore) +
          (sc.unknownKinds ? '（' + sc.unknownKinds + ' 种未收录按 0 分）' : '') + '</span>' +
        '<button class="btn ghost" type="button" data-killtable="1" style="margin-left:auto">' +
          (state.killTable ? '收起明细表' : '明细表') + '</button>' +
      '</div>' +
      '<div class="killslider">' +
        '<span class="ks-edge">Top 1</span>' +
        '<input id="kill-topn" type="range" min="1" max="' + groups.length + '" step="1" value="' + k + '">' +
        '<span class="ks-edge">Top ' + groups.length + '</span>' +
        '<span class="ks-now" id="kill-topn-now">当前：Top ' + k + '</span>' +
      '</div>' +
      '<div id="kill-chart">' + donutHTML(groups, k) + '</div>';

    if (state.killTable){
      var max = groups[0].total || 1;
      h += '<div style="margin-top:18px">' + groups.map(function(g){
        var w = Math.round(g.total / max * 100);
        var vl = variantLabel(g);
        var enLabel = shortEn(Object.keys(g.variants));
        return '<div class="kill"><div class="kill-name"><span class="kn-main">' + esc(g.name) +
          (enLabel ? '<span class="kill-en">' + esc(enLabel) + '</span>' : '') + '</span>' +
          (vl ? '<span class="kill-var">' + esc(vl) + '</span>' : '') + '</div>' +
          '<div class="kill-bar"><span style="width:' + w + '%"></span></div>' +
          '<div class="kill-n">' + g.total + (g.score ? '<span style="color:var(--teal);font-size:10.5px"> · ' + g.score + '</span>' : '') + '</div></div>';
      }).join('') + '</div>';
    }
    h += '<div class="format-note" style="margin-top:14px">' +
      '扇形图为前 Top ' + k + ' 种单独成片，其余合并为「其他」；蓝色数字为该物种的估算得分。' +
      '分数按官方剧情规则估算（食物 + 雨眠×10 − 死亡×3 − 退出×3 − 存活分钟 + 击杀分），' +
      '不含神经元 / 珍珠 / 飞升等剧情加成，仅供参考。' +
      (sc.unknownKinds ? '另有 ' + sc.unknownKinds + ' 种生物未收录分值（' + esc(sc.unknownNames.slice(0, 6).join('、')) +
        (sc.unknownNames.length > 6 ? ' 等' : '') + '，共 ' + sc.unknownCount + ' 次），按 0 分处理。' : '') +
      '</div></div>';
    return h;
  }

  /* 击杀页交互：扇区 hover 换中心数字 + 滑块重建图表（不重建整页） */
  function bindKillsUI(c){
    var chart = document.getElementById('kill-chart');
    if (!chart) return;
    var groups = killGroups(c.kills);
    var total = groups.reduce(function(n, g){ return n + g.total; }, 0) || 1;

    function wire(){
      var svg = document.getElementById('donut');
      var main = document.getElementById('dc-main');
      var sub = document.getElementById('dc-sub');
      var legend = document.getElementById('donut-legend');
      var rows = legend ? legend.querySelectorAll('.dl-row') : [];

      function clear(){
        if (svg) svg.classList.remove('dimall');
        Array.prototype.forEach.call(chart.querySelectorAll('.slice'), function(el){ el.classList.remove('on'); });
        Array.prototype.forEach.call(rows, function(r){ r.classList.remove('hl'); });
        if (main) main.textContent = fmtNum(total);
        if (sub) sub.textContent = '总击杀';
      }
      function focus(idx){
        var it = lastSlices[parseInt(idx, 10)];
        if (!it) return;
        if (svg) svg.classList.add('dimall');
        Array.prototype.forEach.call(chart.querySelectorAll('.slice'), function(el){
          el.classList.toggle('on', el.getAttribute('data-slice') === String(idx));
        });
        Array.prototype.forEach.call(rows, function(r){
          r.classList.toggle('hl', r.getAttribute('data-lg') === String(idx));
        });
        if (main) main.textContent = fmtNum(it.total);
        if (sub){
          sub.textContent = it.name + ' · ' + (it.total / total * 100).toFixed(1) + '%' +
            (it.score ? ' · ' + fmtNum(it.score) + ' 分' : '');
        }
      }
      Array.prototype.forEach.call(chart.querySelectorAll('.slice'), function(el){
        var idx = el.getAttribute('data-slice');
        el.addEventListener('mouseenter', function(){ focus(idx); });
        el.addEventListener('mouseleave', clear);
      });
    }
    wire();

    var slider = document.getElementById('kill-topn');
    if (slider) slider.addEventListener('input', function(){
      var n = clampTopN(slider.value, groups.length);
      state.killsTopN = n;
      var now = document.getElementById('kill-topn-now');
      if (now) now.textContent = '当前：Top ' + n;
      chart.innerHTML = donutHTML(groups, n);
      wire();
      if (hasBridge()) bridgeCall('save_config', { ui: { killsTopN: n } }).catch(function(){});
    });
  }

  function globalHTML(p){
    var h = '';
    var shelterRegions = Object.keys(p.shelters || {}).sort(function(a,b){
      return (p.shelters[b].length || 0) - (p.shelters[a].length || 0);
    });
    var totalRooms = shelterRegions.reduce(function(n, r){ return n + p.shelters[r].length; }, 0);
    h += '<div class="section"><div class="stat-grid">' +
      stat('当前角色', p.currentSlugcat || '—') +
      stat('庇护所区域', shelterRegions.length, 'shelters', ' 个') +
      stat('庇护所房间', totalRooms, 'shelters', ' 间') +
      stat('关卡 token', (p.levelTokens || []).length, 'tokens') +
      stat('沙盒 token', (p.sandboxTokens || []).length, 'tokens') +
      stat('已玩竞技场', (p.playedArenas || []).length, 'tokens') +
      '</div></div>';

    if (shelterRegions.length){
      h += '<div class="section"><div class="section-title"><span>已发现庇护所</span><span class="line"></span></div><div class="chips">' +
        shelterRegions.map(function(r){
          var code = String(r).toUpperCase();
          var info = regionInfo(code);
          var zh = regionZh(code), en = regionEn(code);
          /* 只有「既没有内置译名、也没有导入数据」时才标琥珀色：那种情况只能显示代码本身 */
          var unknown = !info && !zh && !en;
          var tip = unknown
            ? ('缩写 ' + code + '：没有内置译名，也没导入这个区域的数据')
            : (code + (info ? ' · 内置译名' : zh && zh !== en ? ' · 自定义译名' : ' · 区域原名'));
          return '<span class="chip' + (unknown ? ' unrec' : '') + '" data-code="' + esc(code) +
            '" data-tip="' + esc(tip) + '">' +
            esc(regionLabel(code)) + ' <b>' + p.shelters[r].length + '</b></span>';
        }).join('') + '</div>' +
        '</div>';
    }

    var extra = [];
    if (p.classTokens && p.classTokens.length) extra.push(['特殊解锁标记', p.classTokens.join(', ')]);
    if (p.safariTokens && p.safariTokens.length) extra.push(['远征区域', p.safariTokens.length + ' 个']);
    if (p.lore && p.lore.length) extra.push(['剧情 LORE', p.lore.length + ' 条']);
    if (p.broadcasts && p.broadcasts.length) extra.push(['广播', p.broadcasts.length + ' 条']);
    if (extra.length){
      h += '<div class="section"><div class="section-title"><span>其他解锁</span><span class="line"></span></div>' +
        '<div class="doc-list">' + extra.map(function(e){
          return '<div class="doc-item"><span class="dk">' + esc(e[0]) + '</span><span class="dv">' + esc(e[1]) + '</span></div>';
        }).join('') + '</div></div>';
    }

    h += campaignsStatsHTML();
    return h;
  }

  /* ---------------- 各战役统计 ----------------
     数据源：战役块里的 TOTTIME / DEATHTIME（CAMPAIGNTIME 只做交叉校验）。 */
  function campaignsStatsHTML(){
    var camps = (state.result && state.result.campaigns) || [];
    if (!camps.length) return '';
    var times = (state.result.progression && state.result.progression.campaignTimes) || {};
    var rows = camps.map(function(c){
      var lt = lifetime(c);
      var sc = calcScore(c);
      var ct = times[c.slugcat] || times[String(c.slugcat).toUpperCase()];
      var drift = null;
      if (ct && ct[1] != null && c.totalTime != null){
        var d = Math.abs(ct[1] / 1000 - c.totalTime);
        if (d > 600) drift = Math.round(d);
      }
      return { name: c.slugcat, lt: lt, sc: sc, drift: drift };
    });

    var key = state.campSort, dir = state.campSortDir === 'asc' ? 1 : -1;
    rows.sort(function(a, b){
      if (key === 'name') return (a.name < b.name ? -1 : a.name > b.name ? 1 : 0) * dir;
      var av, bv;
      if (key === 'pct'){ av = a.lt.pct == null ? -1 : a.lt.pct; bv = b.lt.pct == null ? -1 : b.lt.pct; }
      else if (key === 'score'){ av = a.sc.total; bv = b.sc.total; }
      else { av = a.lt.total == null ? -1 : a.lt.total; bv = b.lt.total == null ? -1 : b.lt.total; }
      return (av - bv) * dir;
    });

    function head(label, k, alignRight){
      var on = state.campSort === k;
      return '<button class="sort-btn' + (on ? ' on' : '') + '" type="button" data-campsort="' + k + '"' +
        (alignRight ? ' style="float:right"' : '') + '>' + label +
        (on ? '<span class="dir">' + (state.campSortDir === 'asc' ? '↑' : '↓') + '</span>' : '') + '</button>';
    }

    var body = rows.map(function(r){
      var lt = r.lt, sc = r.sc;
      var pct = lt.pct == null ? null : lt.pct;
      var driftTag = r.drift == null ? '' :
        ' <span style="color:var(--dim);cursor:help" data-tip="全局计时 CAMPAIGNTIME 与战役计时相差 ' +
        r.drift + ' 秒（可能迁移过存档），本行以战役块为准">⚠</span>';
      return '<tr>' +
        '<td>' + esc(r.name) + (slugZh(r.name) ? ' <span style="color:var(--muted);font-size:11.5px">' + esc(slugZh(r.name)) + '</span>' : '') + driftTag + '</td>' +
        '<td class="num">' + (lt.total == null ? '—' : fmtHMS(lt.total)) + '</td>' +
        '<td><div style="display:flex;align-items:center;gap:9px">' +
          '<div class="comp-bar" style="flex:1;min-width:64px"><span style="width:' +
            (pct == null ? 0 : Math.max(1, Math.min(100, pct))).toFixed(1) + '%"></span></div>' +
          '<span class="num" style="min-width:46px;text-align:right">' + (pct == null ? '—' : pct.toFixed(1) + '%') + '</span>' +
        '</div></td>' +
        '<td class="num" data-tip="基础分 ' + fmtNum(sc.base) + ' × 通行证 ' + sc.multiplier +
          (sc.saint > 1 ? ' × 圣徒 ' + sc.saint : '') + '（估算，不含剧情加成）">≈ ' + fmtNum(sc.total) + '</td>' +
        '</tr>';
    }).join('');

    var grand = rows.reduce(function(n, r){ return n + (r.lt.total || 0); }, 0);
    var grandAlive = rows.reduce(function(n, r){ return n + (r.lt.alive || 0); }, 0);
    var grandScore = rows.reduce(function(n, r){ return n + (r.sc.total || 0); }, 0);
    var grandPct = grand ? (grandAlive / grand * 100) : null;

    return '<div class="section"><div class="section-title"><span>各战役统计</span><span class="line"></span></div>' +
      '<div class="table-wrap"><table><thead><tr>' +
        '<th>' + head('角色', 'name') + '</th>' +
        '<th>' + head('总游玩时间', 'time', true) + '</th>' +
        '<th>' + head('存活占比', 'pct') + '</th>' +
        '<th>' + head('分数', 'score', true) + '</th>' +
      '</tr></thead><tbody>' + body + '</tbody>' +
      '<tfoot><tr class="total-row">' +
        '<td>全部 ' + rows.length + ' 个战役</td>' +
        '<td class="num">' + fmtHMS(grand) + '</td>' +
        '<td><span class="num" style="color:var(--muted)">' + (grandPct == null ? '—' : grandPct.toFixed(1) + '%') + '</span></td>' +
        '<td class="num">≈ ' + fmtNum(grandScore) + '</td>' +
      '</tr></tfoot></table></div>' +
      '<div class="format-note" style="margin-top:10px">' +
        '总游玩时间 = <code>TOTTIME</code> + <code>DEATHTIME</code>（与游戏内速通计时器同口径），' +
        '不使用 <code>CAMPAIGNTIME</code> 的全局计时——它只累计存活时间，不含死亡耗时。' +
        '末行「全部 N 个战役」是本存档所有角色的合计，跨战役相加会包含不同角色重复游玩的部分。' +
        '分数按官方剧情规则估算，已乘（通行证数 + 1），圣徒额外 ×1.35，<b>不含</b>神经元 / 珍珠 / 飞升等剧情加成。' +
      '</div></div>';
  }

  function docsHTML(){
    var h = '<div class="format-note" style="margin-bottom:20px">' +
      '存档是 .NET Hashtable 的 XML 信封，<code>save</code> 段 = <b>32 位 MD5 校验和</b> + HTML 转义后的明文序列化串。' +
      '数据按 <code>&lt;progDivA&gt;</code> 切分为 <code>MISCPROG</code>（全局进度）、多个 <code>SAVE STATE</code>（每个角色一整块）与 <code>MAP_*</code>（地图缩略图）。' +
      '角色块内再用 <code>&lt;svA&gt;/&lt;svB&gt;</code> 切字段，区域用 <code>&lt;rgA&gt;/&lt;rgB&gt;</code>，死亡持久数据用 <code>&lt;dpA&gt;/&lt;dpB&gt;</code>。' +
      '布尔标志通常“只有为真才写入裸字段名”。' +
      '</div>';
    h += '<div class="format-note" style="margin-bottom:20px">' +
      '区域名优先用《地图缩写对照表》（100 条，逐行转录自 5 张截图），冬眠点 <code>DENPOS</code> 取第一个下划线前的缩写，' +
      '如 <code>RF_S04</code> → <code>RF</code> → <b>珊瑚洞穴 Coral Caves</b>。' +
      '表里没有的缩写（模组 / 变体区域）显示<b>区域数据里的原名 + 缩写</b>，例如 <b>Conduit Reliquary Z1</b>；' +
      '既没译名也没导入数据的，才只剩原始代码。想给它们起中文名，去顶栏「译名 → 区域」里搜代码即可。' +
      '</div>';
    h += '<div class="format-note" style="margin-bottom:20px">' +
      '<b>来源与分母</b>：同一块区域可能有不止一份地图数据——原版、Downpour、Watcher、以及各个模组，' +
      '它们各自带一份房间清单（模组还会用 <code>GATE_RF_GW</code>、<code>GW_RF02</code> 这类房间把区域连起来）。<br>' +
      '· 区域页「数据」列把该区域的每个<b>来源</b>纵向排开，显示来源名与房间数；<b>点一下点亮或熄灭</b>它。<br>' +
      '· 分母 = 所有<b>点亮</b>来源的房间<b>并集</b>，同名房间只算一次。页顶的来源栏可以一次性切换某个来源。<br>' +
      '· 只有地图、没有 <code>world_&lt;reg&gt;.txt</code> 的来源标「仅地图」，不参与分母（缺庇护所/大门标记，也不保证完整）。<br>' +
      '· 「来源未知」= 存档里去过的房间，但没有任何已导入来源认领，<b>不计入分母</b>，只在行内标出。<br>' +
      '· 来源名称可以在「区域数据」里改名，也可以导入时直接填（快捷标签 Original / Downpour / Watcher / Mod）。<br>' +
      '地图视图按来源切层：每层坐标属于各自的底图，<b>不会跨层混画</b>，切层时整张底图一起换。' +
      '</div>';
    h += FIELD_GROUPS.map(function(g){
      return '<div class="doc-group"><h4>' + esc(g.title) + '</h4><div class="doc-list">' +
        g.fields.map(function(f){
          return '<div class="doc-item"><span class="dk">' + esc(f[0]) + '</span><span class="dv">' + esc(f[1]) + '</span></div>';
        }).join('') + '</div></div>';
    }).join('');
    return h;
  }

  function sumKills(k){
    var n = 0;
    Object.keys(k).forEach(function(key){ n += k[key]; });
    return n;
  }

  /* ---------------- 顶栏按钮 ---------------- */
  $('reset').addEventListener('click', function(){ state.result = null; showDrop(); });
  $('err-retry').addEventListener('click', function(){ showDrop(); });
  $('err-home').addEventListener('click', function(){ showDrop(); });

  /* ---------------- 导出（JSON / Markdown） ---------------- */
  function downloadBlob(filename, mime, text){
    var blob = new Blob([text], { type: mime });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ document.body.removeChild(a); URL.revokeObjectURL(a.href); }, 0);
  }
  function fileBase(){
    var n = (state.file && state.file.name) || 'rainworld';
    return String(n).replace(/[\\/:*?"<>|]/g, '_').replace(/\.[^.]+$/, '');
  }
  function exportJSON(){
    if (!state.result) return;
    try{
      downloadBlob(fileBase() + '.analysis.json', 'application/json', JSON.stringify(state.result, null, 2));
      toast('已导出 JSON');
    }catch(e){ toast('导出失败：' + e.message); }
  }
  function mdCell(v){
    return String(v == null ? '' : v).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ').trim();
  }
  function buildMarkdown(res){
    var c = currentCampaign();
    var L = [];
    var stamp = new Date().toLocaleString('zh-CN', { hour12: false });
    L.push('# 雨世界存档分析报告');
    L.push('');
    L.push('- 存档文件：`' + mdCell(state.file && state.file.name) + '`' +
      (state.file && state.file.size ? '（' + fmtBytes(state.file.size) + '）' : ''));
    L.push('- 导出时间：' + stamp);
    L.push('- 角色战役：' + res.campaigns.length + ' 个 · 当前查看：' +
      (c ? c.slugcat + (slugZh(c.slugcat) ? '（' + slugZh(c.slugcat) + '）' : '') : '—'));
    if (res.completionSummary){
      L.push('- 区域数据：' + res.completionSummary.importedCodes + ' 个区域已导入；本次统计里 ' +
        res.completionSummary.regionsWithData + ' / ' + res.completionSummary.regionsTotal + ' 个区域有分母');
    }
    L.push('');

    if (c){
      var life = lifetime(c);
      L.push('## 一、' + c.slugcat + (slugZh(c.slugcat) ? '（' + slugZh(c.slugcat) + '）' : ''));
      L.push('');
      L.push('| 项目 | 数值 |');
      L.push('|---|---|');
      L.push('| 周期 | ' + mdCell(c.cycle == null ? '—' : c.cycle) + ' |');
      L.push('| 存活时长（TOTTIME） | ' + fmtHMS(life.alive) + ' |');
      L.push('| 死亡相关时长（DEATHTIME） | ' + fmtHMS(life.dead) + ' |');
      L.push('| 总游玩时长 | ' + fmtHMS(life.total) + ' |');
      L.push('| 死亡 / 生存 | ' + mdCell(c.deaths == null ? '—' : c.deaths) + ' / ' +
        mdCell(c.survives == null ? '—' : c.survives) + ' |');
      L.push('| 业力 | ' + mdCell(c.karma == null ? '—' : c.karma) +
        (c.karmaCap == null ? '' : ' / ' + c.karmaCap) + ' |');
      L.push('| 通行证 | ' + c.passages.filter(function(p){ return p.earned; }).length + ' / ' + c.passages.length + ' |');
      var msc = calcScore(c);
      L.push('| 估算分数 | ≈ ' + fmtNum(msc.total) + '（基础分 ' + fmtNum(msc.base) + ' × ' +
        msc.multiplier + (msc.saint > 1 ? ' × 圣徒 1.35' : '') + '） |');
      L.push('');

      var rows = c.regions.slice().sort(function(a, b){ return String(a.name).localeCompare(String(b.name)); });
      L.push('## 二、区域完成度');
      L.push('');
      L.push('| 区域 | 名称 | 已访 / 分母 | 完成度 | 庇护所 | 大门 | 珍珠 | 回响 | 最后更新 |');
      L.push('|---|---|---|---|---|---|---|---|---|');
      rows.forEach(function(r){
        var cp = r.completion || {};
        var zhName = r.zh || regionZh(r.name) || '';
        var enName = r.en || regionEn(r.name) || '';
        var name = (zhName + (enName ? ' / ' + enName : '')) || '未识别';
        var comp = cp.pct == null ? '—' : cp.pct.toFixed(1) + '%';
        var sub = [];
        if (cp.variant) sub.push('变体 ' + cp.variant);
        if (cp.conditionalDropped) sub.push('条件房间 −' + cp.conditionalDropped);
        if (cp.unknown) sub.push('来源未知 ' + cp.unknown);
        L.push('| ' + mdCell(r.name) + ' | ' + mdCell(name) + ' | ' +
          (cp.total == null ? mdCell((r.roomsVisited || 0) + ' 间已访') : (cp.visited + ' / ' + cp.total)) + ' | ' +
          comp + ' | ' +
          (cp.sheltersTotal ? cp.sheltersVisited + ' / ' + cp.sheltersTotal : '—') + ' | ' +
          (cp.gatesTotal ? cp.gatesVisited + ' / ' + cp.gatesTotal : '—') + ' | ' +
          mdCell((r.pearlTotal || 0) || '—') + ' | ' +
          mdCell((c.ghosts || {})[r.name] || 0) + ' | ' +
          mdCell(r.lastCycle == null ? '—' : r.lastCycle) +
          (sub.length ? '（' + mdCell(sub.join(' · ')) + '）' : '') + ' |');
      });
      L.push('');

      var kp = killGroups(c.kills).slice(0, 10);
      if (kp.length){
        L.push('## 三、击杀统计（前 10）');
        L.push('');
        L.push('| 物种 | 次数 | 估算得分 |');
        L.push('|---|---|---|');
        kp.forEach(function(k){
          L.push('| ' + mdCell(k.name + (k.en ? '（' + k.en + '）' : '')) + ' | ' + k.total + ' | ' +
            (k.score ? k.score : (k.unknown ? '未收录' : '0')) + ' |');
        });
        L.push('');
      }
    }

    L.push('## 全部角色');
    L.push('');
    L.push('| 角色 | 周期 | 业力 | 存活时长 | 总时长 | 存活占比 | 死亡 | 生存 | 区域 | 平均完成度 | 估算分数 |');
    L.push('|---|---|---|---|---|---|---|---|---|---|---|');
    res.campaigns.forEach(function(item){
      var lf = lifetime(item);
      var isc = calcScore(item);
      var pcts = (item.regions || []).map(function(r){ return r.completion && r.completion.pct; })
        .filter(function(v){ return v != null; });
      var avg = pcts.length ? (pcts.reduce(function(a, b){ return a + b; }, 0) / pcts.length).toFixed(1) + '%' : '—';
      L.push('| ' + mdCell(item.slugcat + (slugZh(item.slugcat) ? '（' + slugZh(item.slugcat) + '）' : '')) + ' | ' +
        mdCell(item.cycle == null ? '—' : item.cycle) + ' | ' +
        mdCell((item.karma == null ? '—' : item.karma) + (item.karmaCap == null ? '' : ' / ' + item.karmaCap)) + ' | ' +
        fmtHMS(lf.alive) + ' | ' + fmtHMS(lf.total) + ' | ' +
        (lf.pct == null ? '—' : lf.pct.toFixed(1) + '%') + ' | ' +
        mdCell(item.deaths == null ? '—' : item.deaths) + ' | ' +
        mdCell(item.survives == null ? '—' : item.survives) + ' | ' +
        (item.regions || []).length + ' | ' + avg + ' | ' +
        '≈ ' + fmtNum(isc.total) + ' |');
    });
    L.push('');
    L.push('---');
    L.push('');
    L.push('> 说明：总时长 = 存活时长 TOTTIME + 死亡相关时长 DEATHTIME（与游戏内速通计时器同口径）。');
    L.push('> 业力按游戏内显示口径（存档为 0 基，界面 +1 并夹在 1~10）。');
    L.push('> 分数 = 食物×1 + 雨眠×10 − 死亡×3 − 退出×3 − 存活分钟 + Σ(击杀×剧情分值)，再 ×(通行证数+1)，圣徒 ×1.35；');
    L.push('> 不含神经元 / 珍珠 / 飞升 / 遇见迭代器等剧情加成，属**估算值**；未收录物种按 0 分。');
    L.push('> 分母 = 点亮来源的房间并集；「仅地图」来源不参与分母；角色有专属地图版本时按该版本清单计算；');
    L.push('> 只对特定角色存在（EXCLUSIVEROOM）或对该角色隐藏（HIDEROOM）的房间已从分母剔除；');
    L.push('> 「来源未知」= 存档去过但没有任何已导入来源认领的房间，不计入分母。');
    L.push('');
    return L.join('\n');
  }
  function exportMarkdown(){
    if (!state.result) return;
    try{
      downloadBlob(fileBase() + '.report.md', 'text/markdown;charset=utf-8', buildMarkdown(state.result));
      toast('已导出 Markdown');
    }catch(e){ toast('导出失败：' + e.message); }
  }

  $('export').addEventListener('click', exportJSON);
  $('export-md').addEventListener('click', exportMarkdown);

  /* ---------------- 房间卡配色 ----------------
     默认值就是编辑器几何视图的原色：实心/背景 #2F2F2F、可攀爬墙 #3C3C3C、空气 #535353、管道 #777777。
     用户可以逐项改成自己的色板，暗色 / 亮色各存一套，写进 config.json 的 ui.roomPalette。 */
  var ROOM_PALETTE_ITEMS = [
    { key:'air',      label:'空气',        css:'--rm-air' },
    { key:'solid',    label:'实心 / 背景', css:'--rm-solid' },
    { key:'slope',    label:'斜面',        css:'--rm-slope' },
    { key:'climb',    label:'可攀爬墙',    css:'--rm-climb' },
    { key:'pipe',     label:'管道',        css:'--rm-pipe' },
    { key:'beam',     label:'杆子',        css:'--rm-beam' },
    { key:'exit',     label:'出口',        css:'--rm-exit' },
    { key:'den',      label:'巢穴',        css:'--rm-den' },
    { key:'creature', label:'生物通道',    css:'--rm-creature' }
  ];
  var ROOM_PALETTE_DEFAULT = {
    dark: { air:'#535353', solid:'#2f2f2f', slope:'#2f2f2f', climb:'#3c3c3c',
            pipe:'#777777', beam:'#f2c66d', exit:'#2fed2f', den:'#ed2f2f', creature:'#2f2fed' },
    light:{ air:'#ffffff', solid:'#c3c3c3', slope:'#c3c3c3', climb:'#e2e2e2',
            pipe:'#6a6a6a', beam:'#b4761a', exit:'#12a012', den:'#b01818', creature:'#2020c0' }
  };
  var rpTheme = 'dark';

  function roomPaletteOf(theme){
    var t = theme === 'light' ? 'light' : 'dark';
    var base = ROOM_PALETTE_DEFAULT[t];
    var custom = (state.roomPalette && state.roomPalette[t]) || {};
    var out = {};
    ROOM_PALETTE_ITEMS.forEach(function(it){
      out[it.key] = custom[it.key] || base[it.key];
    });
    return out;
  }

  /* 写到 :root 的 inline style，覆盖 CSS 里的默认值；切换主题时按当前主题重算 */
  function applyRoomPalette(){
    var pal = roomPaletteOf(state.theme);
    var root = document.documentElement;
    ROOM_PALETTE_ITEMS.forEach(function(it){
      root.style.setProperty(it.css, pal[it.key]);
    });
  }

  function saveRoomPalette(){
    if (!hasBridge()) return;
    bridgeCall('save_config', { ui: { roomPalette: state.roomPalette } }).catch(function(){});
  }

  function rpModalRender(){
    var pal = roomPaletteOf(rpTheme);
    var custom = state.roomPalette[rpTheme] || {};
    $('rp-tabs').innerHTML = ['dark', 'light'].map(function(t){
      return '<button type="button" data-rp-t="' + t + '"' + (rpTheme === t ? ' class="on"' : '') +
        '>' + (t === 'dark' ? '暗色主题' : '亮色主题') + '</button>';
    }).join('');
    $('rp-grid').innerHTML = ROOM_PALETTE_ITEMS.map(function(it){
      var v = pal[it.key];
      return '<label class="rp-item"><input type="color" data-rp-k="' + it.key + '" value="' + v + '">' +
        '<span>' + esc(it.label) + '</span>' +
        (custom[it.key] ? '<span class="rp-off">改</span>' : '') +
        '<span class="rp-hex">' + esc(v) + '</span></label>';
    }).join('');
    Array.prototype.forEach.call($('rp-tabs').querySelectorAll('[data-rp-t]'), function(btn){
      btn.addEventListener('click', function(){
        rpTheme = btn.getAttribute('data-rp-t');
        rpModalRender();
      });
    });
    Array.prototype.forEach.call($('rp-grid').querySelectorAll('[data-rp-k]'), function(inp){
      inp.addEventListener('input', function(){
        var k = inp.getAttribute('data-rp-k');
        if (!state.roomPalette[rpTheme]) state.roomPalette[rpTheme] = {};
        state.roomPalette[rpTheme][k] = inp.value;
        applyRoomPalette();
        if (rmData) drawRoom();
        var hex = inp.parentNode.querySelector('.rp-hex');
        if (hex) hex.textContent = inp.value;
      });
      /* change 在松手 / 关掉取色器时才触发，这时候再落盘，避免拖动过程狂写配置 */
      inp.addEventListener('change', function(){ saveRoomPalette(); rpModalRender(); });
    });
  }

  function openRoomPalette(){
    rpTheme = state.theme === 'light' ? 'light' : 'dark';
    $('rp-modal').hidden = false;
    rpModalRender();
  }
  function closeRoomPalette(){ $('rp-modal').hidden = true; }

  $('rp-close').addEventListener('click', closeRoomPalette);
  $('rp-modal').addEventListener('click', function(e){
    if (e.target === $('rp-modal')) closeRoomPalette();
  });
  $('rp-reset').addEventListener('click', function(){
    state.roomPalette[rpTheme] = {};
    applyRoomPalette();
    if (rmData) drawRoom();
    saveRoomPalette();
    rpModalRender();
  });
  $('rp-reset-all').addEventListener('click', function(){
    state.roomPalette = { dark: {}, light: {} };
    applyRoomPalette();
    if (rmData) drawRoom();
    saveRoomPalette();
    rpModalRender();
  });

  /* ================= 桌面版：模态框 / 导入 / 地图 ================= */
  var modalEl = $('modal'), modalTitle = $('modal-title'), modalSub = $('modal-sub');
  var modalBody = $('modal-body'), modalCard = $('modal-card');

  function openModal(title, sub, html, narrow, full){
    if (GX) gxClose();
    modalTitle.textContent = title;
    modalSub.textContent = sub || '';
    modalBody.innerHTML = html;
    modalCard.classList.toggle('narrow', !!narrow);
    modalCard.classList.toggle('full', !!full);
    modalEl.hidden = false;
  }

  /* 二次确认（比 window.confirm 好看，也不会卡住 WebView） */
  function confirmBox(title, text, okText, onOk){
    var el = document.getElementById('confbox');
    if (!el){
      el = document.createElement('div');
      el.id = 'confbox';
      el.className = 'modal confbox';
      el.hidden = true;
      el.innerHTML = '<div class="modal-card narrow">' +
        '<div class="modal-head"><h3 id="cf-title"></h3><span class="grow"></span>' +
        '<button class="modal-close" type="button" data-cf="no">×</button></div>' +
        '<div class="modal-body"><div class="cf-text" id="cf-text"></div>' +
        '<div class="cf-actions"><button class="btn ghost" type="button" data-cf="no">取消</button>' +
        '<button class="btn primary" type="button" data-cf="yes"></button></div></div></div>';
      document.body.appendChild(el);
      el.addEventListener('click', function(e){
        var act = e.target && e.target.getAttribute ? e.target.getAttribute('data-cf') : null;
        if (act === 'no' || e.target === el){ el.hidden = true; el._ok = null; }
        else if (act === 'yes'){
          el.hidden = true;
          var fn = el._ok; el._ok = null;
          if (fn) fn();
        }
      });
    }
    document.getElementById('cf-title').textContent = title;
    document.getElementById('cf-text').textContent = text;
    el.querySelector('[data-cf="yes"]').textContent = okText || '确定';
    el._ok = onOk;
    el.hidden = false;
    return el;
  }
  function closeModal(){ modalEl.hidden = true; modalBody.innerHTML = ''; window.__rwMapCtx = null; if (GX) gxClose(); }
  $('modal-close').addEventListener('click', closeModal);
  modalEl.addEventListener('click', function(e){ if (e.target === modalEl) closeModal(); });
  document.addEventListener('keydown', function(e){
    if (e.key !== 'Escape') return;
    var rp = document.getElementById('rp-modal');      /* 最上层：房间卡配色 */
    if (rp && !rp.hidden){ closeRoomPalette(); return; }
    var rm = document.getElementById('room-modal');   /* 再关房间卡 */
    if (rm && !rm.hidden){ closeRoomCard(); return; }
    if (!modalEl.hidden) closeModal();
  });

  /* ---------------- 外观与配色 ---------------- */
  var THEMES = [
    { key:'dark',  label:'暗色' },
    { key:'light', label:'亮色' }
  ];
  var ACCENTS = [
    { key:'amber',  label:'琥珀',   color:'#e8b04a' },
    { key:'teal',   label:'青瓷',   color:'#3ec9b8' },
    { key:'violet', label:'紫罗兰', color:'#9b7fe8' },
    { key:'rose',   label:'玫红',   color:'#e0709a' },
    { key:'blue',   label:'天蓝',   color:'#4f9de0' },
    { key:'green',  label:'苔绿',   color:'#6fbf7c' }
  ];

  function applyTheme(theme, accent, persist){
    var t = (theme === 'light') ? 'light' : 'dark';
    var a = ACCENTS.some(function(x){ return x.key === accent; }) ? accent : 'amber';
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.setAttribute('data-accent', a);
    state.theme = t;
    state.accent = a;
    applyRoomPalette();     /* 房间卡的色板跟着主题走（亮/暗各一套） */
    try{ localStorage.setItem('rwTheme', JSON.stringify({ t: t, a: a })); }catch(e){}
    if (persist && hasBridge()){
      bridgeCall('save_config', { theme: t, accent: a }).catch(function(){});
    }
  }

  function themeModalHTML(){
    var h = '<div class="theme-sec"><h4>背景</h4><div class="theme-row">';
    THEMES.forEach(function(t){
      var on = state.theme === t.key;
      h += '<button class="theme-opt' + (on ? ' on' : '') + '" type="button" data-theme-opt="' + t.key + '">' +
        (t.key === 'dark' ? '◑ ' : '◐ ') + esc(t.label) + '</button>';
    });
    h += '</div></div>';
    h += '<div class="theme-sec"><h4>强调色</h4><div class="theme-row">';
    ACCENTS.forEach(function(a){
      var on = state.accent === a.key;
      h += '<button class="theme-opt' + (on ? ' on' : '') + '" type="button" data-accent-opt="' + a.key + '">' +
        '<span class="theme-swatch" style="background:' + a.color + '"></span>' + esc(a.label) + '</button>';
    });
    h += '</div></div>';
    h += '<div class="theme-note">配色只影响界面，不改动任何存档或区域数据。选择会写进 <code>config.json</code>，下次启动保持。</div>';
    return h;
  }

  function openThemeModal(){
    openModal('外观与配色', '背景与强调色，立即生效', themeModalHTML(), true);
    openThemeModalBind();
  }
  function openThemeModalBind(){
    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-theme-opt]'), function(btn){
      btn.addEventListener('click', function(){
        applyTheme(btn.getAttribute('data-theme-opt'), state.accent, true);
        modalBody.innerHTML = themeModalHTML();
        openThemeModalBind();
      });
    });
    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-accent-opt]'), function(btn){
      btn.addEventListener('click', function(){
        applyTheme(state.theme, btn.getAttribute('data-accent-opt'), true);
        modalBody.innerHTML = themeModalHTML();
        openThemeModalBind();
      });
    });
  }
  $('theme-fab').addEventListener('click', openThemeModal);


  /* ---------------- 区域数据管理 ---------------- */
  function regionCard(r){
    var layers = r.layers || [];
    var tags = [];
    var onCount = layers.filter(function(L){ return L.enabled; }).length;
    tags.push('<span class="tag ' + (onCount ? 'ok' : 'off') + '">' + onCount + ' / ' + layers.length + ' 个来源点亮</span>');
    if (r.activeRooms) tags.push('<span class="tag">参与计算 ' + r.activeRooms + ' 间</span>');

    var meta = [];
    meta.push(layers.length + ' 个来源');
    if (layers.length > 1) meta.push('并集 ' + (r.unionRooms || 0) + ' 间');

    var layerRows = layers.map(function(L){
      var sub = [];
      sub.push((L.rooms || 0) + ' 间');
      sub.push(L.kind === 'official' ? '官方' : '模组');
      if (L.hasWorldFile === false){
        sub.push('仅地图（无 world 文件）');
      } else {
        sub.push('完整清单');
      }
      sub.push(L.hasMap ? '底图' : '无底图');
      if (L.upToDate === false) sub.push('源文件已变化');
      return '<div class="layer-row">' +
        '<button class="src-chip' + (L.enabled ? ' on' : '') + ' k-' + esc(L.sourceKind || 'mod') + (L.mapOnly ? ' maponly' : '') + '" type="button" ' +
          'data-src="' + esc(L.sourceId || L.id) + '" data-tip="' + esc((L.sourceName || L.label || '') + '：点击切换是否参与计算') + '">' +
          '<span class="sc-n">' + esc(L.sourceName || L.label || L.id) + '</span><b>' + (L.rooms || 0) + '</b></button>' +
        (L.hasMap ? '<button class="sort-btn lr-btn" type="button" data-map="' + esc(r.code) + '" data-layer="' + esc(L.id) + '">地图</button>' : '') +
        '<span class="lr-meta">' + esc(sub.join(' · ')) + '</span>' +
        '<button class="sort-btn lr-btn" type="button" data-rename="' + esc(L.sourceId || L.id) + '" data-current="' + esc(L.sourceName || L.label || '') + '">改名</button>' +
        '<button class="sort-btn lr-btn" type="button" data-dellayer="' + esc(L.id) + '" data-code="' + esc(r.code) + '">移除</button>' +
        '<button class="sort-btn lr-btn" type="button" data-delsrc="' + esc(L.sourceId || L.id) +
          '" data-name="' + esc(L.sourceName || L.label || L.id) +
          '" title="删掉这个来源在所有区域的全部数据（跨区域）">清来源</button>' +
        '</div>';
    }).join('');

    var dispZh = r.nameZh || (regionIsBuiltin(r.code) ? regionZh(r.code) : '') || '';
    var dispEn = r.nameEn || regionEn(r.code) || '';
    return '<div class="reg-card">' +
      '<div class="rc-code">' + esc(r.code) + '</div>' +
      '<div class="rc-main">' +
        '<div class="rc-name">' + esc(dispZh || dispEn || r.code) +
          (dispZh && dispEn ? '<em>' + esc(dispEn) + '</em>' : '') + '</div>' +
        '<div class="rc-meta">' + meta.map(esc).join(' · ') + '</div>' +
        '<div class="layer-list">' + layerRows + '</div>' +
      '</div>' +
      '<div class="rc-actions">' + tags.join('') +
        '<button class="btn ghost" type="button" data-del="' + esc(r.code) + '">移除全部</button>' +
      '</div></div>';
  }

  function renderRegionsModal(){
    if (modalEl.hidden || modalTitle.textContent !== '区域数据') return;
    var list = state.regionList || [];
    var head = '<div class="sortbar" style="margin-bottom:10px">' +
      '<button class="btn" type="button" id="m-import-official">导入游戏原版数据</button>' +
      '<button class="btn ghost" type="button" id="m-import">导入模组目录…</button>' +
      '<button class="btn ghost" type="button" id="m-open-dir">打开缓存目录</button>' +
      '</div>' +
      '<div class="cache-bar" id="m-room-cache"><span class="cb-txt">房间渲染缓存 · 统计中…</span></div>' +
      '<div class="format-note" style="margin-bottom:12px">同一区域可以有多个<b>来源</b>（原版 / Downpour / Watcher / 各模组），' +
      '每个来源独立保存、互不覆盖。点来源名可以<b>点亮或熄灭</b>它，只有点亮的来源参与完成度计算；' +
      '只有地图没有 world 文件的来源会标「仅地图」，不参与分母。</div>' +
      '<div id="m-game-hint" class="format-note" style="margin-bottom:12px"></div>';
    var body = list.length
      ? list.map(regionCard).join('')
      : '<div class="map-empty">还没有导入任何区域数据。<br>先点「导入游戏原版数据」拿到所有原版/DLC 区域的完整房间清单。</div>';
    // 底图只记路径：换机器 / 挪模组目录后路径会失效，这里给个可操作提示
    if (list.length){
      var withMap = list.filter(function(r){ return r.hasMap; }).length;
      if (!withMap){
        head += '<div class="format-note" style="margin-bottom:12px;color:#f0c674">' +
          '所有底图路径都不可用（多半是换了机器或移动过游戏/模组目录）。' +
          '点「导入游戏原版数据」重新扫描本机路径即可，房间清单不受影响。</div>';
      } else if (withMap < list.length){
        head += '<div class="format-note" style="margin-bottom:12px;color:var(--dim)">' +
          (list.length - withMap) + ' 个区域的底图路径不可用（模组被卸载或移动过）；清单与完成度照常。</div>';
      }
    }
    modalBody.innerHTML = head + body;
    bindRegionActions();
    showGameHint();
    rmCacheShow();
  }

  /* ---- 房间渲染缓存：占用统计 + 清理 ----
     房间图都是「渲一次、存一盘」的，看过的房间越多占得越多（上限 200 MB，超了按最旧淘汰）。
     给一个看得见数字的清理入口，省得用户去翻 region_data/_roomcache 手动删。
     清完必须把前端的 L1（整图 12 张）与裁块缓存一起倒掉——否则界面上还是旧图，
     用户会以为「点了没用」。 */
  function rmCacheShow(){
    var box = $('m-room-cache');
    if (!box) return;
    if (!hasBridge()){
      box.innerHTML = '<span class="cb-txt">房间渲染缓存 · 浏览器预览模式下不可用</span>';
      return;
    }
    bridgeCall('room_cache_info').then(function(res){
      var el = $('m-room-cache');
      if (!el) return;
      if (!res || !res.ok){
        el.innerHTML = '<span class="cb-txt">房间渲染缓存 · 读不到占用（' + esc(String((res && res.error) || '未知')) + '）</span>';
        return;
      }
      var mb = (res.bytes || 0) / 1048576;
      var n = res.files || 0;
      el.innerHTML = '<span class="cb-txt">房间渲染缓存 · <b>' +
        (mb < 0.1 ? '不足 0.1' : mb.toFixed(1)) + ' MB</b> · ' + n + ' 张' +
        '<span style="opacity:.6">（上限 ' + Math.round((res.limit || 0) / 1048576) + ' MB，超出自动淘汰最旧）</span></span>' +
        '<button class="btn ghost" type="button" id="m-room-clear"' + (n ? '' : ' disabled') + '>清理</button>';
      var btn = $('m-room-clear');
      if (btn) btn.addEventListener('click', function(){ rmCacheClear(n); });
    }).catch(function(err){
      var el = $('m-room-cache');
      if (el) el.innerHTML = '<span class="cb-txt">房间渲染缓存 · 读不到占用（' +
        esc(String((err && err.message) || err)) + '）</span>';
    });
  }

  function rmCacheClear(files){
    confirmBox('清理房间渲染缓存',
      '将删除 ' + (files || 0) + ' 张已缓存的房间图（只删 _roomcache，不动导入的区域数据）。' +
      '清理后再次打开房间需要重新渲染一次，之后照旧很快。',
      '清理', function(){
        bridgeCall('room_cache_clear').then(function(res){
          if (!res || !res.ok){
            toast('清理失败：' + String((res && res.error) || '未知错误'));
            return;
          }
          /* 前端两级缓存一起清：整图 L1 + 放大裁块。
             当前正显示的这张**故意保留**（`rmLive` 不动）——清了又立刻重渲一遍，
             等于白清；用户看到的效果是「空间回来了，画面没变」。 */
          rmLiveCache = {}; rmLiveOrder = []; rmLiveBytes = 0;
          rmHiDrop();
          drawRoom();
          rmCacheShow();
          toast('已清理 ' + (res.removed || 0) + ' 张房间图');
        }).catch(function(err){
          toast('清理失败：' + String((err && err.message) || err));
        });
      });
  }

  function showGameHint(){
    var box = $('m-game-hint');
    if (!box) return;
    bridgeCall('game_info').then(function(info){
      if (!info) return;
      if (info.ok){
        var packs = (info.packs || []).map(function(p){ return p.label + '(' + p.regions + ')'; }).join('、');
        box.innerHTML = '游戏目录：<code>' + esc(info.root) + '</code><br>' +
          '检测到 ' + (info.regionCount || 0) + ' 个官方区域：' + esc(packs);
      } else {
        box.innerHTML = '未检测到雨世界安装目录。点「导入游戏原版数据」后可以手动指定游戏根目录。';
      }
    }).catch(function(){});
  }

  function bindRegionActions(){
    var importBtn = $('m-import');
    if (importBtn) importBtn.addEventListener('click', doImport);
    var officialBtn = $('m-import-official');
    if (officialBtn) officialBtn.addEventListener('click', doImportOfficial);
    var openBtn = $('m-open-dir');
    if (openBtn) openBtn.addEventListener('click', function(){
      bridgeCall('open_data_dir').then(function(res){
        toast(res.ok ? '已打开：' + res.path : ('打开失败：' + res.error));
      }).catch(function(){ toast('浏览器模式不支持'); });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-del]'), function(btn){
      btn.addEventListener('click', function(){
        var code = btn.getAttribute('data-del');
        if (!window.confirm('删除区域 ' + code + ' 的导入数据？（不影响模组目录与存档）')) return;
        bridgeCall('delete_region', code).then(function(res){
          if (!res.ok) { toast(res.error || '删除失败'); return; }
          delete state.regions[code];
          toast('已删除 ' + code);
          loadRegions();
          if (state.result) renderDetail();
        }).catch(function(e){ toast('删除失败：' + (e && e.message || e)); });
      });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-reimport]'), function(btn){
      btn.addEventListener('click', function(){
        importByPath(btn.getAttribute('data-path'));
      });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-src]'), function(btn){
      btn.addEventListener('click', function(){
        toggleSource(btn.getAttribute('data-src'));
        loadRegions().then(renderRegionsModal);
      });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-rename]'), function(btn){
      btn.addEventListener('click', function(){
        askSourceName({
          title: '重命名来源',
          sub: '只改显示名称，不影响已经导入的数据',
          value: btn.getAttribute('data-current') || '',
          confirmText: '保存',
          allowEmpty: false,
          onOk: function(name){
            bridgeCall('rename_source', btn.getAttribute('data-rename'), name).then(function(res){
              if (!res || !res.ok){ toast((res && res.error) || '改名失败'); return; }
              loadRegions().then(renderRegionsModal);
            }).catch(function(e){ toast('改名失败：' + (e && e.message || e)); });
          }
        });
      });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-dellayer]'), function(btn){
      btn.addEventListener('click', function(){
        var code = btn.getAttribute('data-code');
        var lid = btn.getAttribute('data-dellayer');
        if (!window.confirm('只移除 ' + code + ' 的这一个来源层？（不影响模组目录与存档）')) return;
        bridgeCall('delete_layer', code, lid).then(function(res){
          if (!res || !res.ok){ toast((res && res.error) || '移除失败'); return; }
          toast('已移除该来源层');
          loadRegions().then(renderRegionsModal);
        }).catch(function(e){ toast('移除失败：' + (e && e.message || e)); });
      });
    });

    /* 清来源（S3）：模组数据是按区域存的，District4B 实测散在 37 个层里，
       只删一个区域的那层，地图上到处都还留着 SB_4B 这种残影。
       这里先算影响面给人看，确认后跨区域一次清干净。 */
    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-delsrc]'), function(btn){
      btn.addEventListener('click', function(){
        var sid = btn.getAttribute('data-delsrc');
        var nm = btn.getAttribute('data-name') || sid;
        bridgeCall('preview_source_delete', sid).then(function(res){
          if (!res || !res.ok){ toast((res && res.error) || '预览失败'); return; }
          var regs = (res.regions || []).map(function(x){ return x.code; });
          var msg = '删除来源「' + nm + '」的全部数据？\n\n' +
            '区域 ' + (res.regions || []).length + ' 个 · 层 ' + res.layerCount +
            ' 个 · 房间 ' + res.roomCount + ' 间\n' +
            '区域：' + regs.slice(0, 20).join(' / ') + (regs.length > 20 ? ' …' : '') + '\n';
          if ((res.emptyRegions || []).length){
            msg += '\n以下区域会被删空并整份移除：' + res.emptyRegions.join(' / ') + '\n';
          }
          msg += '\n其它层里指向这些房间的邻居/连接/出口去向会一并清掉。\n' +
                 '（会影响存档分析里的房间数与完成度，操作前已自动备份）';
          if (!window.confirm(msg)) return;
          bridgeCall('delete_source', sid).then(function(r2){
            if (!r2 || !r2.ok){ toast((r2 && r2.error) || '删除失败'); return; }
            toast('已删除 ' + r2.layers + ' 层 / ' + r2.rooms + ' 间房' +
              (r2.refs ? '，清理引用 ' + r2.refs + ' 处' : ''));
            rmNameIndex = null;
            loadRegions().then(renderRegionsModal);
          }).catch(function(e){ toast('删除失败：' + (e && e.message || e)); });
        }).catch(function(e){ toast('预览失败：' + (e && e.message || e)); });
      });
    });

    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-map]'), function(btn){
      btn.addEventListener('click', function(){
        openMap(btn.getAttribute('data-map'), btn.getAttribute('data-layer'));
      });
    });
  }

  function openRegionsModal(){
    openModal('区域数据', '导入一次即长期可用 · 只读取模组目录，不写入任何文件',
      '<div class="map-empty">读取中…</div>');
    if (!hasBridge()){
      modalBody.innerHTML = '<div class="map-empty">当前是浏览器窗口模式，无法访问本地目录。<br>请用桌面版打开（RwSaveTool.exe）。</div>';
      return;
    }
    loadRegions().then(renderRegionsModal);
  }

  /* 给导入的数据起来源名（默认 4 个快捷标签，也可自定义） */
  function askSourceName(opt){
    opt = opt || {};
    var presets = state.sourcePresets && state.sourcePresets.length
      ? state.sourcePresets : ['Original','Downpour','Watcher','Mod'];
    var value = opt.value || '';
    var html = '<div class="format-note">同一个区域可能同时有原版 / Downpour / Watcher / 模组好几份地图数据，' +
      '给这次导入起个「来源名称」，之后就能在区域页逐个点亮或熄灭。' +
      '<br><b>留空则用模组原名</b>（推荐）：比如「Shrouded Assembly」「Stormy Coast」，一眼能认出来源。</div>' +
      '<div class="sortbar" style="margin:14px 0 10px">' +
        '<button class="src-chip' + (value ? '' : ' on') + '" type="button" data-preset="">模组原名</button>' +
        presets.map(function(p){
          return '<button class="src-chip' + (p === value ? ' on' : '') + '" type="button" data-preset="' + esc(p) + '">' + esc(p) + '</button>';
        }).join('') + '</div>' +
      '<input id="src-name" class="text-input" type="text" spellcheck="false" placeholder="留空 = 使用模组原名（例如 Coral Caves）" value="' + esc(value) + '">' +
      '<div class="sortbar" style="margin-top:16px">' +
        '<button class="btn primary" type="button" id="src-ok">' + esc(opt.confirmText || '确定') + '</button>' +
        '<button class="btn ghost" type="button" id="src-cancel">取消</button>' +
      '</div>';
    openModal(opt.title || '来源名称', opt.sub || '', html, true);
    var input = $('src-name');
    function pickPreset(name){
      if (!input) return;
      input.value = name;
      Array.prototype.forEach.call(modalBody.querySelectorAll('[data-preset]'), function(b){
        b.classList.toggle('on', b.getAttribute('data-preset') === name);
      });
    }
    Array.prototype.forEach.call(modalBody.querySelectorAll('[data-preset]'), function(b){
      b.addEventListener('click', function(){ pickPreset(b.getAttribute('data-preset')); input.focus(); });
    });
    if (input){
      input.focus();
      input.select();
      input.addEventListener('keydown', function(e){
        if (e.key === 'Enter'){ e.preventDefault(); var ok = $('src-ok'); if (ok) ok.click(); }
      });
    }
    var okBtn = $('src-ok'), cancelBtn = $('src-cancel');
    if (okBtn) okBtn.addEventListener('click', function(){
      var name = input ? String(input.value || '').trim() : '';
      if (!name && opt.allowEmpty === false){ toast('请填写来源名称'); if (input) input.focus(); return; }
      closeModal();
      if (opt.onOk) opt.onOk(name);
    });
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
  }

  /* ---------------- 导入 ---------------- */
  function doImportOfficial(){
    if (!hasBridge()){ toast('浏览器模式不支持导入本地目录'); return; }
    openModal('导入游戏原版数据', '正在扫描游戏目录…',
      '<div class="map-empty">从游戏本体读取原版 / DLC 区域数据（只读）…</div>', true);
    bridgeCall('import_official_path', null, false).then(function(res){
      if (res && res.needConfirm){
        var detail = (res.shrink || []).map(function(s){
          return s.code + '：现有 ' + s.old + ' 间 → 新数据 ' + s.new + ' 间';
        }).join('<br>');
        openModal('确认覆盖', '官方数据明显少于已导入数据',
          '<div class="format-note" style="color:#f0c674">' + detail + '</div>' +
          '<div class="sortbar" style="margin-top:14px">' +
          '<button class="btn" type="button" id="m-force">仍然覆盖</button></div>', true);
        var fb = $('m-force');
        if (fb) fb.addEventListener('click', function(){
          bridgeCall('import_official_path', null, true).then(afterOfficialImport);
        });
        return;
      }
      if (!res || !res.ok){
        openModal('没找到游戏目录', (res && res.error) || '',
          '<div class="map-empty">请手动指定雨世界安装目录（含 RainWorld_Data 文件夹那一层）。</div>' +
          '<div class="sortbar" style="margin-top:14px"><button class="btn" type="button" id="m-pick-game">选择游戏目录…</button></div>', true);
        var pb = $('m-pick-game');
        if (pb) pb.addEventListener('click', function(){
          bridgeCall('pick_game_dir').then(function(r){
            if (r && r.canceled) return;
            if (!r || !r.ok){ toast((r && r.error) || '目录无效'); return; }
            doImportOfficialConfirm(r.root);
          }).catch(function(e){ toast(String(e && e.message || e)); });
        });
        return;
      }
      afterOfficialImport(res);
    }).catch(function(e){
      openModal('导入失败', '', '<div class="map-empty">' + esc(String(e && e.message || e)) + '</div>', true);
    });
  }

  function doImportOfficialConfirm(root){
    openModal('导入游戏原版数据', '正在扫描 ' + root,
      '<div class="map-empty">读取中…</div>', true);
    bridgeCall('import_official_path', root, false).then(afterOfficialImport).catch(function(e){
      openModal('导入失败', '', '<div class="map-empty">' + esc(String(e && e.message || e)) + '</div>', true);
    });
  }

  function afterOfficialImport(res){
    if (!res || !res.ok){
      openModal('导入失败', (res && res.error) || '',
        '<div class="map-empty">' + esc((res && res.error) || '未知错误') + '</div>', true);
      return;
    }
    var byPack = {};
    (res.saved || []).forEach(function(item){
      var pack = item.label || '官方';
      byPack[pack] = (byPack[pack] || 0) + 1;
    });
    var packLine = Object.keys(byPack).map(function(k){ return esc(k) + ' ' + byPack[k] + ' 区'; }).join(' · ');
    openModal('官方数据已导入', (res.root || '') + ' · 共 ' + (res.saved || []).length + ' 个区域',
      '<div class="format-note">' + (packLine || '—') + '<br>' +
      '这些数据作为<b>源文件层</b>保存；模组附加的房间会作为独立层叠加，不会覆盖它们。<br>' +
      '同名区域重复导入将覆盖同名层。</div>' +
      ((res.warnings || []).length ? '<div class="format-note" style="margin-top:10px;color:var(--dim)">' +
        esc((res.warnings || []).slice(0, 6).join('；')) + '</div>' : '') +
      '<div class="sortbar" style="margin-top:14px"><button class="btn" type="button" id="m-done">好</button></div>', true);
    var done = $('m-done');
    if (done) done.addEventListener('click', function(){ closeModal(); openRegionsModal(); });
    loadRegions();
    if (state.result){ renderDetail(); }
  }

  var pendingSourceName = null;

  function doImport(){
    if (!hasBridge()){ toast('浏览器模式不支持导入本地目录'); return; }
    askSourceName({
      title: '导入模组区域数据',
      sub: '先给这份数据起来源名，再选模组目录',
      confirmText: '选择模组目录…',
      onOk: function(name){
        pendingSourceName = name;
        openModal('导入模组目录', '正在扫描…', '<div class="map-empty">扫描模组目录中…</div>', true);
        bridgeCall('pick_mod_dir', name).then(handleImportResult).catch(function(e){
          openModal('导入失败', '', '<div class="map-empty">' + esc(String(e && e.message || e)) + '</div>', true);
        });
      }
    });
  }

  function importByPath(path, force){
    if (!path) { toast('缺少模组路径'); return; }
    openModal('导入模组目录', '正在扫描…', '<div class="map-empty">扫描中…</div>', true);
    bridgeCall('import_mod_path', path, !!force, pendingSourceName).then(handleImportResult).catch(function(e){
      openModal('导入失败', '', '<div class="map-empty">' + esc(String(e && e.message || e)) + '</div>', true);
    });
  }

  function handleImportResult(res){
    if (!res || res.canceled){ closeModal(); return; }
    if (res.needConfirm){
      var detail = (res.shrink || []).map(function(s){
        return s.code + '：现有 ' + s.old + ' 间 → 新数据 ' + s.new + ' 间';
      }).join('<br>');
      openModal('确认覆盖', '新数据明显少于现有数据', 
        '<div class="format-note" style="color:#f0c674">可能是导错了文件或是不完整的版本。<br>' + detail + '</div>' +
        '<div class="sortbar" style="margin-top:14px">' +
        '<button class="btn primary" type="button" id="cf-yes">确认覆盖</button>' +
        '<button class="btn ghost" type="button" id="cf-no">取消</button></div>', true);
      $('cf-yes').addEventListener('click', function(){ importByPath(res.path, true); });
      $('cf-no').addEventListener('click', closeModal);
      return;
    }
    if (!res.ok){
      var failed = (res.failed || []).map(function(f){ return f.code + '：' + f.error; }).join('<br>');
      openModal('导入失败', '', '<div class="map-empty">' + (failed || '未知错误') + '</div>', true);
      return;
    }

    var saved = res.saved || [];
    var srcLabel = res.sourceName ? ('来源「' + res.sourceName + '」') : '已写入缓存';
    var rows = saved.map(function(s){
      var st = s.stats || {};
      return '<div class="reg-card"><div class="rc-code">' + esc(s.code) + '</div>' +
        '<div class="rc-main"><div class="rc-name">' + esc(srcLabel) + '</div>' +
        '<div class="rc-meta">房间 ' + (st.rooms || 0) + ' · 庇护所 ' + (st.shelters || 0) +
        ' · 大门 ' + (st.gates || 0) + (st.partial ? ' · 仅地图（无 world 文件，不参与分母）' : '') + '</div></div>' +
        '<div class="rc-actions"><span class="tag ok">完成</span></div></div>';
    }).join('');
    var warns = (res.warnings || []).map(function(w){ return '<div class="rc-meta">· ' + esc(w) + '</div>'; }).join('');
    var mods = (res.mods || []).map(function(m){ return esc(m.name) + (m.version ? ' v' + esc(m.version) : ''); }).join('、');
    openModal('导入完成', mods + ' · 只读扫描，未修改模组目录',
      rows + (warns ? '<div class="format-note" style="margin-top:12px">' + warns + '</div>' : '') +
      '<div class="sortbar" style="margin-top:14px"><button class="btn" type="button" id="imp-done">好</button></div>', true);
    $('imp-done').addEventListener('click', function(){ openRegionsModal(); });
    loadRegions();
  }

  /* ---------------- 区域地图（矢量渲染，不读底图） ---------------- */

  /* 只要有一版地图给出过坐标就能画图——不再依赖 map_<reg>.png 是否还在 */
  function hasMapCoords(code){
    var rd = regionData(code);
    if (!rd) return false;
    return (rd.layers || []).some(function(L){
      return (L.rooms || []).some(function(room){ return room.map; });
    });
  }

  /* 房间矩形直接摊成 SVG：坐标就是 region_data 里的 map.x/y/w/h，
     房间集合走 regionRoomSets()，与区域表的完成度同一个口径。
     不再读取 map_<reg>.png —— 那张开发者截图既糊又抢视线。 */

  var MAP_VIEW_PAD = 26;

  function mapRoomMeta(rd){
    var layerOf = {}, nbOf = {};
    ((rd && rd.layers) || []).forEach(function(L){
      (L.rooms || []).forEach(function(room){
        var k = String(room.name).toUpperCase();
        if (layerOf[k] == null && room.layer != null) layerOf[k] = String(room.layer);
        if (!nbOf[k] && (room.neighbors || []).length){
          nbOf[k] = room.neighbors.map(function(n){ return String(n).toUpperCase(); });
        }
      });
    });
    return { layerOf: layerOf, nbOf: nbOf };
  }

  function mapBoxGap(a, b){
    var dx = Math.max(0, Math.max(a.x, b.x) - Math.min(a.x + a.w, b.x + b.w));
    var dy = Math.max(0, Math.max(a.y, b.y) - Math.min(a.y + a.h, b.y + b.h));
    return Math.sqrt(dx * dx + dy * dy);
  }

  /* 边到边连线：从 A 靠着 B 的那条边出发，落到 B 对应的边，取重叠段的中点。
     这样线短、方向对，不会从房间中心斜着穿出去。 */
  function mapLink(a, b){
    var acx = a.x + a.w / 2, acy = a.y + a.h / 2;
    var bcx = b.x + b.w / 2, bcy = b.y + b.h / 2;
    var dx = bcx - acx, dy = bcy - acy;
    var x1, y1, x2, y2;
    if (Math.abs(dx) >= Math.abs(dy)){
      var lo = Math.max(a.y, b.y), hi = Math.min(a.y + a.h, b.y + b.h);
      var yy = lo < hi ? (lo + hi) / 2 : (acy + bcy) / 2;
      y1 = y2 = yy;
      if (dx >= 0){ x1 = a.x + a.w; x2 = b.x; } else { x1 = a.x; x2 = b.x + b.w; }
    } else {
      var lx = Math.max(a.x, b.x), hx = Math.min(a.x + a.w, b.x + b.w);
      var xx = lx < hx ? (lx + hx) / 2 : (acx + bcx) / 2;
      x1 = x2 = xx;
      if (dy >= 0){ y1 = a.y + a.h; y2 = b.y; } else { y1 = a.y; y2 = b.y + b.h; }
    }
    return [x1, y1, x2, y2];
  }

  function mapBounds(list){
    if (!list.length) return null;
    var x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    list.forEach(function(r){
      x1 = Math.min(x1, r.m.x); y1 = Math.min(y1, r.m.y);
      x2 = Math.max(x2, r.m.x + r.m.w); y2 = Math.max(y2, r.m.y + r.m.h);
    });
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  }

  function mapViewBox(list){
    var b = mapBounds(list);
    if (!b) return null;
    return [b.x - MAP_VIEW_PAD, b.y - MAP_VIEW_PAD, b.w + MAP_VIEW_PAD * 2, b.h + MAP_VIEW_PAD * 2];
  }

  function openMap(code, layerId){
    var rd = regionData(code);
    if (!rd){ toast('该区域没有导入数据'); return; }

    var campaign = currentCampaign();
    var slugcat = campaign ? campaign.slugcat : '';

    /* 与区域表同口径：点亮来源的并集 + 变体 + 条件房间剔除 */
    var sets = regionRoomSets(rd, slugcat);
    if (!sets || !sets.total){
      var why = usableLayers(rd, slugcat).length ? '来源被全部熄灭' : '只有地图、没有房间清单';
      openModal('区域地图 · ' + code, esc(rd.zh || rd.nameZh || ''),
        '<div class="map-empty">该区域暂时算不出房间清单（' + esc(why) + '）。<br>去「区域数据」里点亮一个来源再试。</div>', true);
      return;
    }

    var visited = {}, pearls = {}, regionState = null;
    if (campaign){
      (campaign.regions || []).forEach(function(r){
        if (String(r.name).toUpperCase() !== String(code).toUpperCase()) return;
        regionState = r;
        (r.roomList || []).forEach(function(n){ visited[String(n).toUpperCase()] = 1; });
        (r.pearlRooms || []).forEach(function(n){ pearls[String(n).toUpperCase()] = 1; });
      });
    }
    var ghosts = (campaign && campaign.ghosts) || {};
    var echoCount = ghosts[code] || ghosts[String(code).toUpperCase()] || 0;

    var meta = mapRoomMeta(rd);
    var rooms = [], noCoord = [], unvisited = [];
    Object.keys(sets.names).sort().forEach(function(key){
      var item = {
        name: key,
        m: sets.coords[key] || null,
        layer: meta.layerOf[key] != null ? meta.layerOf[key] : '1',
        shelter: !!sets.shelters[key],
        gate: !!sets.gates[key],
        seen: roomSeen(code, key, !!visited[key]),
        pearl: !!pearls[key]
      };
      if (!item.seen) unvisited.push(key);
      if (item.m) rooms.push(item); else noCoord.push(item);
    });

    var total = Object.keys(sets.names).length;
    var seenCount = total - unvisited.length;
    var pct = total ? seenCount / total * 100 : 0;

    /* ---- 分层 ---- */
    var layerRooms = {};
    rooms.forEach(function(r){ (layerRooms[r.layer] = layerRooms[r.layer] || []).push(r); });
    var layerList = Object.keys(layerRooms).sort();

    /* ---- 同层连接（跨层不画：那是楼上楼下，不是平面邻居） ---- */
    var byName = {};
    rooms.forEach(function(r){ byName[r.name] = r; });

    /* 与其它层相通的房间（跨层不画线，改用角标提示） */
    var crossOf = {};
    rooms.forEach(function(r){
      (meta.nbOf[r.name] || []).forEach(function(nb){
        var o = byName[nb];
        if (o && o.layer !== r.layer) crossOf[r.name] = 1;
      });
    });

    var linkSeen = {}, linkHTML = '';
    rooms.forEach(function(r){
      (meta.nbOf[r.name] || []).forEach(function(nb){
        var other = byName[nb];
        if (!other || other.layer !== r.layer) return;
        var k = r.name < nb ? r.name + '|' + nb : nb + '|' + r.name;
        if (linkSeen[k]) return;
        linkSeen[k] = 1;
        if (mapBoxGap(r.m, other.m) <= 6) return;   /* 本来就贴着的，画线只会在缝里留线头 */
        var g = mapLink(r.m, other.m);
        linkHTML += '<line class="link" data-l="' + esc(r.layer) + '" x1="' + g[0].toFixed(1) +
          '" y1="' + g[1].toFixed(1) + '" x2="' + g[2].toFixed(1) + '" y2="' + g[3].toFixed(1) + '"/>';
      });
    });

    /* ---- 房间方块 ---- */
    var roomHTML = '';
    rooms.forEach(function(r){
      var cls = 'room' + (r.seen ? ' seen' : '') + (r.gate ? ' gate' : '') + (r.shelter ? ' shelter' : '');
      var tip = r.name + ' · 第 ' + r.layer + ' 层' +
        (r.shelter ? ' · 庇护所' : '') + (r.gate ? ' · 业力门' : '') +
        (r.pearl ? ' · 有珍珠' : '');
      var seenAttr = ' data-seen="' + (r.seen ? 1 : 0) + '"';
      roomHTML += '<rect class="' + cls + '" data-l="' + esc(r.layer) + '" data-room="' + esc(r.name) + '"' +
        seenAttr + ' x="' + r.m.x.toFixed(1) + '" y="' + r.m.y.toFixed(1) +
        '" width="' + r.m.w.toFixed(1) + '" height="' + r.m.h.toFixed(1) + '" rx="2.5">' +
        '<title>' + esc(tip) + '</title></rect>';
      if (r.pearl){
        var pr = Math.max(1.6, Math.min(6, Math.min(r.m.w, r.m.h) * 0.24));
        roomHTML += '<circle class="pearl" data-l="' + esc(r.layer) + '"' + seenAttr + ' cx="' +
          (r.m.x + r.m.w / 2).toFixed(1) + '" cy="' + (r.m.y + r.m.h / 2).toFixed(1) +
          '" r="' + pr.toFixed(1) + '"/>';
      }
      /* 庇护所不靠描边颜色（会和"已探索"的主题色撞），改用中心小方块 */
      if (r.shelter){
        var sw = Math.max(4, Math.min(9, Math.min(r.m.w, r.m.h) * 0.34));
        roomHTML += '<rect class="shelter-mark" data-l="' + esc(r.layer) + '"' + seenAttr + ' x="' +
          (r.m.x + r.m.w / 2 - sw / 2).toFixed(1) + '" y="' + (r.m.y + r.m.h / 2 - sw / 2).toFixed(1) +
          '" width="' + sw.toFixed(1) + '" height="' + sw.toFixed(1) + '" rx="1"/>';
      }
      /* 和别的层相通的房间：左上角点一下，解释它为什么在平面图上看起来是孤立的 */
      if (crossOf[r.name]){
        roomHTML += '<circle class="cross-mark" data-l="' + esc(r.layer) + '"' + seenAttr + ' cx="' +
          (r.m.x + 4.5).toFixed(1) + '" cy="' + (r.m.y + 4.5).toFixed(1) + '" r="2.1"/>';
      }
    });

    var vbAll = mapViewBox(rooms) || [0, 0, 100, 100];
    var vbOf = { all: vbAll };
    layerList.forEach(function(lv){
      var vb = mapViewBox(layerRooms[lv]);
      if (vb) vbOf[lv] = vb;
    });

    var layerBtns = layerList.map(function(lv){
      return '<button class="sort-btn" type="button" data-ml="' + esc(lv) + '">' +
        (lv === '0' ? '上层' : lv === '1' ? '中层' : lv === '2' ? '下层' : '第 ' + esc(lv) + ' 层') +
        ' <b>' + layerRooms[lv].length + '</b></button>';
    }).join('');

    /* ---- 房间号清单：全部 / 未探索 / 已探索 ----
       三者共用同一份分母（sets.names），所以「全部 = 未探索 + 已探索」恒成立。 */
    var allNames = Object.keys(sets.names).sort();
    function muList(filter){
      if (filter === 'all') return allNames;
      if (filter === 'seen') return allNames.filter(function(n){ return !!visited[n]; });
      return unvisited;
    }
    function muHintText(filter){
      var tail = '点房间号高亮定位';
      if (filter === 'unseen') return '地图上<b>已探索</b>的房间变暗 · ' + tail;
      if (filter === 'seen') return '地图上<b>未探索</b>的房间变暗 · ' + tail;
      return tail;
    }
    function muChipsHTML(filter){
      var list = muList(filter);
      if (!list.length){
        return '<div class="mu-none">' +
          (filter === 'unseen' ? '这个区域的房间全走过了' :
           filter === 'seen' ? '这间房一间都还没去过' : '没有房间') + '</div>';
      }
      return list.map(function(name){
        var hasCoord = !!byName[name];
        return '<button class="mu-chip' + (hasCoord ? '' : ' nocoord') +
          (visited[name] ? ' seen' : '') + '" type="button" data-focus="' + esc(name) + '"' +
          (hasCoord ? '' : ' title="这个房间没有任何一版地图给出坐标，只能列号"') +
          '>' + esc(name) + '</button>';
      }).join('');
    }
    var muTabs = [['all', '全部', total], ['unseen', '未探索', unvisited.length],
                  ['seen', '已探索', seenCount]];
    if (['all', 'unseen', 'seen'].indexOf(state.muFilter) < 0) state.muFilter = 'unseen';
    var unvisitedHTML = total
      ? '<div class="map-unvisited">' +
          '<div class="mu-head mu-tabs">' +
            muTabs.map(function(t){
              return '<button class="sort-btn' + (state.muFilter === t[0] ? ' on' : '') +
                '" type="button" data-mu="' + t[0] + '">' + t[1] + ' <b>' + t[2] + '</b></button>';
            }).join('') +
            '<span class="mu-spacer"></span>' +
            '<button class="btn ghost" type="button" id="mu-copy">复制这份</button>' +
            '<button class="btn ghost" type="button" id="mu-toggle">收起</button>' +
          '</div>' +
          '<div class="mu-hint" id="mu-hint">' + muHintText(state.muFilter) + '</div>' +
          '<div class="mu-body" id="mu-body">' + muChipsHTML(state.muFilter) + '</div>' +
          (noCoord.length ? '<div class="map-none-hint">其中 ' + noCoord.length +
            ' 间没有坐标（虚线框），只能列号，画不到图上。</div>' : '') +
        '</div>'
      : '<div class="map-unvisited"><div class="mu-head"><span class="mu-none">' +
        '这个区域没有可列的房间</span></div></div>';

    var legend =
      '<div class="map-legend">' +
        '<span><i style="background:color-mix(in srgb,var(--accent) 58%,transparent);border-color:var(--accent)"></i>已探索</span>' +
        '<span><i style="background:var(--rm-fill);border-color:var(--rm-line)"></i>未探索</span>' +
        '<span><i style="background:transparent;border:1.6px dashed var(--rm-line)"></i>业力门</span>' +
        '<span><i style="background:var(--amber);border:none"></i>庇护所</span>' +
        '<span><i style="background:#f0e2b6;border-radius:50%"></i>珍珠房间</span>' +
        '<span><i style="background:var(--rm-link);border-radius:50%;width:6px;height:6px"></i>与其它层相通</span>' +
        '<span>本次显示 ' + rooms.length + ' 间（另有 ' + noCoord.length + ' 间无坐标）· 已探索 ' +
          seenCount + ' / ' + total + '（' + pct.toFixed(1) + '%）' +
          (echoCount ? ' · 回响 ' + echoCount + '（区域级，无房间坐标）' : '') + '</span>' +
      '</div>';

    var sub = (rd.zh || rd.nameZh || '') + ' ' + (rd.en || rd.nameEn || '') +
      ' · ' + (sets.variant ? '变体：' + sets.variant : '来源：' +
        ((sets.layerNames || []).join(' / ') || '本层')) +
      (sets.conditionalDropped
        ? ' · 已剔除 ' + sets.conditionalDropped + ' 间'
          + (sets.roleDropped ? '（角色专属 ' + sets.roleDropped + '）' : '')
          + (sets.manualDropped ? '（手动 ' + sets.manualDropped + '）' : '')
        : '') +
      (slugcat ? ' · 角色：' + slugcat : '');

    var marks = roomMarkMap(code), nMark = Object.keys(marks).length;
    var markBar = nMark
      ? '<div class="map-marks"><span>手动标记 ' + nMark + ' 间</span>' +
        '<button class="btn ghost" id="map-mark-reset" type="button">还原</button></div>'
      : '';

    openModal('区域地图 · ' + code, sub,
      '<div class="map-wrap"><div class="map-main"><div class="map-tools" id="map-layers">' +
        '<span class="mlabel">地图层</span>' +
        '<button class="sort-btn on" type="button" data-ml="all">全部 <b>' + rooms.length + '</b></button>' +
        layerBtns +
        '<button class="sort-btn' + (state.mapBase ? ' on' : '') + '" id="map-base-btn" type="button" ' +
          'title="叠一层游戏自带的区域底图（只作背景参考，房间方块仍是主角）">▤ 底图</button>' +
        '<button class="btn map-graph-btn" id="map-geo" type="button" title="换成几何排布：地形上色 + 9 类覆盖物 + 三次贝塞尔连线">◱ 几何图</button>' +
        '<button class="btn map-graph-btn" id="map-graph" type="button" title="把整片区域的房间画成区域拓扑图">◈ 区域拓扑</button>' +
        '<span class="map-hint">滚轮缩放 · 拖拽平移 · 双击房间居中</span>' +
      '</div>' +
      '<div class="map-stage" id="map-stage" data-layer="all" data-filter="' + esc(state.muFilter) + '">' +
        '<svg id="map-svg" viewBox="' + vbAll.map(function(v){ return v.toFixed(1); }).join(' ') +
          '" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">' +
          '<rect class="map-sheet" id="map-sheet" x="' + vbAll[0].toFixed(1) + '" y="' + vbAll[1].toFixed(1) +
            '" width="' + vbAll[2].toFixed(1) + '" height="' + vbAll[3].toFixed(1) + '" rx="8"/>' +
          /* 底图（P0）：整张 map_<reg>.png 铺在 (0,0)-(W,H)。房间坐标本来就是底图像素坐标，
             所以不需要任何换算；W/H 由桥接返回后再写进来，没加载时是 0×0，不影响布局。 */
          '<image class="map-base" id="map-base" x="0" y="0" width="0" height="0" ' +
            'preserveAspectRatio="none" href=""/>' +
          '<g class="links">' + linkHTML + '</g>' +
          '<g class="rooms">' + roomHTML + '</g>' +
        '</svg>' +
        '<div class="map-zoom" id="map-zoom">' +
          '<button type="button" data-zoom="out" title="缩小（滚轮下滚）">−</button>' +
          '<span id="map-zoom-pct">100%</span>' +
          '<button type="button" data-zoom="in" title="放大（滚轮上滚）">+</button>' +
          '<button type="button" data-zoom="reset" title="复位（双击空白处也行）">复位</button>' +
        '</div>' +
        '<div class="map-tip" id="map-tip"></div>' +
      '</div>' +
        '</div>' +
        '<aside class="map-side" id="map-side">' + markBar + legend + unvisitedHTML + '</aside>' +
      '</div>', false, true);

    /* ---------------- 交互 ---------------- */
    var stageEl = $('map-stage');
    var svgEl = $('map-svg');
    var tipEl = $('map-tip');
    if (!stageEl || !svgEl) return;

    var gbtn = $('map-graph');
    if (gbtn) gbtn.addEventListener('click', function(){ openGraph(code); });

    var geobtn = $('map-geo');
    if (geobtn) geobtn.addEventListener('click', function(){ openMapGeo(code); });

    var mrk = $('map-mark-reset');
    if (mrk) mrk.addEventListener('click', function(){
      confirmBox('还原探索标记',
        '这会把「' + code + '」里你手动标记的 ' + nMark + ' 间房全部清掉，恢复成跟随存档的状态。这一步不能撤销。',
        '还原', function(){
          delete state.roomMarks[String(code).toUpperCase()];
          if (hasBridge()) bridgeCall('save_config', { ui: { roomMarks: state.roomMarks } }).catch(function(){});
          openMap(code);
        });
    });

    /* ---- 底图层（P0）--------------------------------------------------------
       底图是游戏自带的 map_<reg>.png，1px = 1tile，与房间方块共用同一坐标系，
       所以整张图铺在 (0,0)-(W,H) 就自动对齐，不需要任何缩放换算。
       加载全程异步、不 await：图没到之前这里什么都不做，界面照常可用。 */
    var baseEl = $('map-base');
    var baseBtn = $('map-base-btn');
    var baseCache = window.__rwMapBase || (window.__rwMapBase = {});
    var baseSeq = 0;

    function mapBasePaint(url, w, h){
      if (!baseEl) return;
      if (!url || !(w > 0) || !(h > 0)){
        baseEl.removeAttribute('href');
        baseEl.classList.remove('on');
        return;
      }
      /* 只有"完全不重叠"才判定为坐标系不同源、干脆不画。
         部分覆盖是正常的：模组/Downpour 层会把房间铺到底图范围之外（例如 GW 的
         moreslugcats 层 bbox 2012 宽，而 map_gw.png 只有 1574），那部分没底图可叠，
         画出来只是"边缘没有背景"，不影响对齐。 */
      var b = mapBounds(rooms);
      if (b && (b.x >= w || b.y >= h || b.x + b.w <= 0 || b.y + b.h <= 0)){
        console.warn('[map-base] 底图与房间坐标完全不重叠，已跳过', b, w, h);
        baseEl.removeAttribute('href');
        baseEl.classList.remove('on');
        return;
      }
      baseEl.setAttribute('href', url);
      baseEl.setAttribute('width', w);
      baseEl.setAttribute('height', h);
      baseEl.classList.add('on');
    }

    function mapBaseApply(){
      if (!baseEl) return;
      if (!state.mapBase){ baseEl.classList.remove('on'); return; }
      var hit = baseCache[code];
      if (hit){ mapBasePaint(hit.url, hit.w, hit.h); return; }
      if (!hasBridge()) return;
      var seq = ++baseSeq;
      /* bridgeCall 是位置参数展开（见 L2566），不能塞成一个对象 */
      bridgeCall('map_image', code, layerId || null, sets.variant || 'normal')
        .then(function(r){
          if (seq !== baseSeq || !r || !r.ok || !r.dataUrl) return;   /* 已经换区域了 */
          var keys = Object.keys(baseCache);
          if (keys.length >= 8) delete baseCache[keys[0]];            /* 只留最近 8 个区 */
          baseCache[code] = { url: r.dataUrl, w: r.width || 0, h: r.height || 0 };
          if (state.mapBase) mapBasePaint(r.dataUrl, baseCache[code].w, baseCache[code].h);
        })
        .catch(function(){});
    }

    if (baseBtn && baseEl){
      mapBaseApply();
      baseBtn.addEventListener('click', function(){
        state.mapBase = !state.mapBase;
        baseBtn.classList.toggle('on', state.mapBase);
        mapBaseApply();
        if (hasBridge()) bridgeCall('save_config', { ui: { mapBase: state.mapBase } }).catch(function(){});
      });
    }

    var curLayer = 'all';

    /* ---- 缩放 / 平移：改的是 svg 元素的 CSS transform，viewBox 不动 ---- */
    var K_MIN = 1, K_MAX = 16;
    var view = { k: 1, x: 0, y: 0 };
    var pctEl = $('map-zoom-pct');

    function curVB(){ return vbOf[curLayer] || vbOf.all; }

    /* viewBox + preserveAspectRatio=meet → 绘图区在元素里是居中的一小块，
       这里把「用户坐标 → 元素内像素」的映射算出来，缩放原点才对得上鼠标 */
    function proj(){
      var vb = curVB();
      var w = svgEl.clientWidth || 1, h = svgEl.clientHeight || 1;
      var s = Math.min(w / vb[2], h / vb[3]) || 1;
      return { s: s, w: w, h: h,
        ox: (w - vb[2] * s) / 2, oy: (h - vb[3] * s) / 2,
        dw: vb[2] * s, dh: vb[3] * s };
    }

    /* 单轴限位：内容比视口小时居中；比视口大时不许拖出边界 */
    function clampAxis(t, k, off, size, port){
      var c = size * k;
      if (c <= port) return (port - c) / 2 - k * off;
      var lo = port - k * (off + size), hi = -k * off;
      return Math.min(hi, Math.max(lo, t));
    }

    function applyView(){
      var p = proj();
      view.x = clampAxis(view.x, view.k, p.ox, p.dw, p.w);
      view.y = clampAxis(view.y, view.k, p.oy, p.dh, p.h);
      if (view.k <= 1.001){
        svgEl.style.transform = '';
      } else {
        svgEl.style.transform = 'translate(' + view.x.toFixed(2) + 'px,' + view.y.toFixed(2) +
          'px) scale(' + view.k.toFixed(3) + ')';
      }
      stageEl.classList.toggle('zoomed', view.k > 1.001);
      if (pctEl) pctEl.textContent = Math.round(view.k * 100) + '%';
    }

    function resetView(){
      view = measureHome();
      applyView();
    }

    /* 初始视图：绝大多数区域铺满舞台即可；但 53 个区域里有 16 个是「竖长条」
       （CC 0.4、RM/SS/DM 0.26、WSSR 0.11…），等比铺满会缩成中间一条细缝。
       这类内容默认放大到宽度约占一半，至少看得清房间；想拉远看全貌滚轮往下滚即可。 */
    function measureHome(){
      var p = proj(), vb = curVB(), home = { k: 1, x: 0, y: 0 };
      if (p.w > 1 && p.h > 1 && p.dw > 0 && p.dw / p.w < 0.42){
        var k = Math.min(2.6, Math.max(1.02, (p.w * 0.38) / p.dw));
        var ex = p.ox + (vb[2] / 2) * p.s;
        var ey = p.oy + (vb[3] / 2) * p.s;
        home = { k: k, x: p.w / 2 - ex * k, y: p.h / 2 - ey * k };
      }
      return home;
    }

    /* 指针在元素内的坐标（offsetLeft/offsetTop 不受 transform 影响，始终是布局位置） */
    function localPoint(ev){
      var b = stageEl.getBoundingClientRect();
      return { x: ev.clientX - b.left - (svgEl.offsetLeft || 0),
               y: ev.clientY - b.top - (svgEl.offsetTop || 0) };
    }

    function zoomAt(px, py, k2){
      k2 = Math.max(K_MIN, Math.min(K_MAX, k2));
      if (Math.abs(k2 - view.k) < 0.0005) return;
      var r = k2 / view.k;
      view.x = px - (px - view.x) * r;
      view.y = py - (py - view.y) * r;
      view.k = k2;
      applyView();
    }

    /* 把某个用户坐标点搬到视口中心（并保证至少 k2 倍放大） */
    function centerOn(ux, uy, k2){
      var p = proj(), vb = curVB();
      var k = Math.max(view.k, Math.min(K_MAX, k2 || 1));
      var ex = p.ox + (ux - vb[0]) * p.s;   /* 该点在元素里的像素位置 */
      var ey = p.oy + (uy - vb[1]) * p.s;
      view.k = k;
      view.x = p.w / 2 - ex * k;
      view.y = p.h / 2 - ey * k;
      applyView();
    }

    function setLayer(lv){
      curLayer = lv;
      stageEl.setAttribute('data-layer', lv);
      var vb = vbOf[lv] || vbOf.all;
      svgEl.setAttribute('viewBox', vb.map(function(v){ return v.toFixed(1); }).join(' '));
      var sheet = $('map-sheet');
      if (sheet){
        sheet.setAttribute('x', vb[0].toFixed(1));
        sheet.setAttribute('y', vb[1].toFixed(1));
        sheet.setAttribute('width', vb[2].toFixed(1));
        sheet.setAttribute('height', vb[3].toFixed(1));
      }
      Array.prototype.forEach.call(document.querySelectorAll('#map-layers [data-ml]'), function(b){
        b.classList.toggle('on', b.getAttribute('data-ml') === lv);
      });
      resetView();          /* 换层等于换坐标系，缩放必须归零 */
    }
    Array.prototype.forEach.call(document.querySelectorAll('#map-layers [data-ml]'), function(btn){
      btn.addEventListener('click', function(){ setLayer(btn.getAttribute('data-ml')); });
    });

    /* 滚轮缩放：以鼠标位置为锚点 */
    stageEl.addEventListener('wheel', function(ev){
      if (!ev.deltaY) return;
      ev.preventDefault();
      var pt = localPoint(ev);
      var f = Math.pow(1.0022, -ev.deltaY);
      zoomAt(pt.x, pt.y, view.k * f);
    }, { passive: false });

    /* 拖拽平移 */
    var drag = null;
    function onDragMove(ev){
      if (!drag) return;
      var dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
      drag.moved = true;
      stageEl.classList.add('dragging');
      view.x = drag.vx + dx;
      view.y = drag.vy + dy;
      applyView();
    }
    function onDragEnd(){
      drag = null;
      stageEl.classList.remove('dragging');
      window.removeEventListener('mousemove', onDragMove);
      window.removeEventListener('mouseup', onDragEnd);
    }
    stageEl.addEventListener('mousedown', function(ev){
      if (ev.button !== 0) return;
      if (view.k <= 1.001) return;                   /* 没放大时拖动没意义 */
      if (ev.target.closest && ev.target.closest('.map-zoom')) return;
      ev.preventDefault();
      drag = { sx: ev.clientX, sy: ev.clientY, vx: view.x, vy: view.y, moved: false };
      window.addEventListener('mousemove', onDragMove);
      window.addEventListener('mouseup', onDragEnd);
    });

    /* 双击房间 → 居中放大；双击空白 → 复位 */
    stageEl.addEventListener('dblclick', function(ev){
      var t = ev.target;
      if (t && t.getAttribute && t.getAttribute('data-room')){
        var r = byName[t.getAttribute('data-room')];
        if (r && r.m) centerOn(r.m.x + r.m.w / 2, r.m.y + r.m.h / 2, Math.max(3, view.k));
        return;
      }
      resetView();
    });

    Array.prototype.forEach.call(document.querySelectorAll('#map-zoom [data-zoom]'), function(btn){
      btn.addEventListener('click', function(){
        var act = btn.getAttribute('data-zoom');
        if (act === 'reset'){ resetView(); return; }
        var p = proj();
        zoomAt(p.w / 2, p.h / 2, view.k * (act === 'in' ? 1.45 : 1 / 1.45));
      });
    });

    /* 弹窗刚插入时元素尺寸可能还没算出来，下一帧再定一次位 */
    var booted = false;
    function boot(){
      if (booted || svgEl.clientWidth <= 1) return;
      booted = true;
      resetView();
    }
    boot();
    if (window.requestAnimationFrame) requestAnimationFrame(boot);

    /* 悬停提示：房间号 / 层 / 状态 */
    function showTip(ev, rect){
      var name = rect.getAttribute('data-room');
      var room = byName[name];
      if (!room) return;
      var state = room.seen ? '已探索' : '未探索';
      var extra = [];
      if (room.shelter) extra.push('庇护所');
      if (room.gate){
        var seg = room.name.split('_');
        extra.push('业力门' + (seg.length >= 3 ? ' → ' + seg[seg.length - 1] : ''));
      }
      if (room.pearl) extra.push('有珍珠');
      var cross = (meta.nbOf[name] || []).filter(function(nb){
        return byName[nb] && byName[nb].layer !== room.layer;
      });
      var crossTxt = cross.length ? '<div class="map-tier">上下连通：' + esc(cross.slice(0, 3).join('、')) +
        (cross.length > 3 ? ' 等 ' + cross.length + ' 间' : '') + '</div>' : '';
      tipEl.innerHTML = '<div><b>' + esc(name) + '</b> · 第 ' + esc(room.layer) + ' 层 · ' +
        (room.seen ? '<span style="color:var(--accent)">' + state + '</span>' : state) + '</div>' +
        (extra.length ? '<div class="map-tier">' + esc(extra.join(' · ')) + '</div>' : '') + crossTxt;
      tipEl.classList.add('on');
      var box = stageEl.getBoundingClientRect();
      var x = ev.clientX - box.left + 14;
      var y = ev.clientY - box.top + 14;
      x = Math.min(x, box.width - tipEl.offsetWidth - 8);
      tipEl.style.left = Math.max(4, x) + 'px';
      tipEl.style.top = Math.max(4, y) + 'px';
    }
    svgEl.addEventListener('mousemove', function(ev){
      var t = ev.target;
      if (t && t.tagName && t.tagName.toLowerCase() === 'rect' && t.getAttribute('data-room')){
        showTip(ev, t);
      } else {
        tipEl.classList.remove('on');
      }
    });
    svgEl.addEventListener('mouseleave', function(){ tipEl.classList.remove('on'); });

    /* 未探索清单：点房间号 → 切到它所在的层、居中放大并高亮 */
    var focusTimer = null;
    function focusRoom(name){
      var rect = svgEl.querySelector('[data-room="' + String(name).replace(/"/g, '\\"') + '"]');
      if (!rect){ toast('这个房间没有坐标，图上画不出来'); return; }
      var lv = rect.getAttribute('data-l');
      if (curLayer !== 'all' && curLayer !== lv) setLayer(lv);
      Array.prototype.forEach.call(svgEl.querySelectorAll('.room.focus'), function(el){
        el.classList.remove('focus');
      });
      rect.classList.add('focus');
      var room = byName[name];
      if (room && room.m){
        centerOn(room.m.x + room.m.w / 2, room.m.y + room.m.h / 2, Math.max(2.6, view.k));
      }
      /* 共用一支定时器：连续点不同的房间号时，不要让上一次的清除把这次的高亮擦掉 */
      if (focusTimer) clearTimeout(focusTimer);
      focusTimer = setTimeout(function(){
        rect.classList.remove('focus');
        focusTimer = null;
      }, 2600);
    }
    /* 清单里的房间号：点一下切层 + 居中高亮，同时弹出这间房的布局卡。
       切标签会重建这些按钮，所以抽成函数，每次重渲后重新绑。 */
    function bindMuChips(){
      Array.prototype.forEach.call(document.querySelectorAll('#mu-body [data-focus]'), function(chip){
        chip.addEventListener('click', function(){
          var nm = chip.getAttribute('data-focus');
          focusRoom(nm);
          openRoomCard(code, nm);
        });
      });
    }
    bindMuChips();

    /* 给「在地图上定位」按钮一个回跳入口；order 让房间卡的上一间/下一间跟当前标签同序 */
    window.__rwMapCtx = { code: code, focus: focusRoom, order: muList(state.muFilter) };

    /* 画布上直接点房间方块 → 打开布局卡 */
    stageEl.addEventListener('click', function(ev){
      var t = ev.target;
      if (!t || !t.getAttribute) return;
      var nm = t.getAttribute('data-room');
      if (nm) openRoomCard(code, nm);
    });

    var copyBtn = $('mu-copy');
    if (copyBtn) copyBtn.addEventListener('click', function(){
      var list = muList(state.muFilter);
      if (!list.length){ toast('这份列表是空的'); return; }
      var text = list.join('\n');
      var done = function(){ toast('已复制 ' + list.length + ' 个房间号'); };
      if (navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done).catch(function(){ toast('复制失败'); });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { toast('复制失败'); }
        document.body.removeChild(ta);
      }
    });

    /* 三个标签页：全部 / 未探索 / 已探索。只换列表内容，不动缩放与分层 */
    Array.prototype.forEach.call(document.querySelectorAll('[data-mu]'), function(btn){
      btn.addEventListener('click', function(){
        var f = btn.getAttribute('data-mu');
        if (f === state.muFilter) return;
        state.muFilter = f;
        Array.prototype.forEach.call(document.querySelectorAll('[data-mu]'), function(b){
          b.classList.toggle('on', b.getAttribute('data-mu') === f);
        });
        /* 地图跟着变暗：只压暗不在当前标签里的方块，缩放与分层不动 */
        if (stageEl) stageEl.setAttribute('data-filter', f);
        if (window.__rwMapCtx) window.__rwMapCtx.order = muList(f);
        var hintEl = $('mu-hint');
        if (hintEl) hintEl.innerHTML = muHintText(f);
        var body = $('mu-body');
        if (!body) return;
        var collapsed = body.classList.contains('collapsed');
        body.innerHTML = muChipsHTML(f);
        if (collapsed) body.classList.add('collapsed');
        bindMuChips();
      });
    });

    var toggleBtn = $('mu-toggle');
    var muBody = $('mu-body');
    if (toggleBtn && muBody) toggleBtn.addEventListener('click', function(){
      var collapsed = muBody.classList.toggle('collapsed');
      toggleBtn.textContent = collapsed ? '展开' : '收起';
    });
  }

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

  /* 默认配色 = 房间卡那套（同一主题同一份）；房间卡没有的两项用自己的兜底 */
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
        '<div class="geo-pal-pop" id="geo-pal-pop" hidden>' +
          '<div class="geo-pal-head"><span>本区配色</span>' +
            '<button class="btn ghost" data-rgpreset="room" type="button" title="跟随房间卡配色">房间卡</button>' +
            '<button class="btn ghost" data-rgpreset="map" type="button" title="雨世界地图配色（青底黄管）">地图</button>' +
            '<button class="btn ghost" id="geo-pal-reset" type="button" title="清掉本区自定义，回到房间卡配色">还原</button></div>' +
          '<div class="rp-grid" id="geo-pal-grid"></div>' +
          '<div class="geo-pal-note" id="geo-pal-note"></div>' +
        '</div>' +
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

    /* ---- 配色：一个「配色」按钮 + 舞台左上角的面板（跟房间卡同一套色板控件） ---- */
    var pop = $('geo-pal-pop'), grid = $('geo-pal-grid'), palNote = $('geo-pal-note');

    function rgRender(){
      var pal = regmapColorsOf(KEY);
      var custom = (state.regmapColors || {})[KEY] || {};
      grid.innerHTML = RG_ITEMS.map(function(it){
        var v = pal[it[0]];
        return '<label class="rp-item"><input type="color" data-rgk="' + it[0] + '" value="' + v +
          '"><span>' + esc(it[1]) + '</span>' +
          (custom[it[0]] ? '<span class="rp-off">改</span>' : '') + '</label>';
      }).join('');
      if (palNote) palNote.textContent = '只影响 ' + KEY + '，默认跟随房间卡';
      Array.prototype.forEach.call(grid.querySelectorAll('[data-rgk]'), function(inp){
        inp.addEventListener('input', function(){
          var k = inp.getAttribute('data-rgk');
          if (!state.regmapColors) state.regmapColors = {};
          if (!state.regmapColors[KEY]) state.regmapColors[KEY] = {};
          state.regmapColors[KEY][k] = inp.value;
          wrap.style.setProperty('--rg-' + k, inp.value);
        });
        inp.addEventListener('change', saveRegmapColors);
      });
    }
    rgRender();

    var palBtn = $('geo-pal');
    if (palBtn) palBtn.addEventListener('click', function(ev){
      ev.stopPropagation();
      pop.hidden = !pop.hidden;
      if (!pop.hidden) rgRender();
    });
    if (pop) pop.addEventListener('click', function(ev){ ev.stopPropagation(); });
    stage.addEventListener('click', function(){ if (!pop.hidden) pop.hidden = true; });

    /* 两套预设：房间卡（默认）/ 地图（青底黄管）。点一下整组写进本区，之后还能单项微调 */
    Array.prototype.forEach.call(pop.querySelectorAll('[data-rgpreset]'), function(btn){
      btn.addEventListener('click', function(ev){
        ev.stopPropagation();
        var src = btn.getAttribute('data-rgpreset') === 'map' ? RG_FALLBACK : regmapDefaults();
        if (!state.regmapColors) state.regmapColors = {};
        state.regmapColors[KEY] = {};
        RG_ITEMS.forEach(function(it){
          state.regmapColors[KEY][it[0]] = src[it[0]] || RG_FALLBACK[it[0]];
        });
        paintRegmapColors(wrap, KEY);
        saveRegmapColors();
        rgRender();
      });
    });

    var prst = $('geo-pal-reset');
    if (prst) prst.addEventListener('click', function(ev){
      ev.stopPropagation();
      if (state.regmapColors) delete state.regmapColors[KEY];
      paintRegmapColors(wrap, KEY);
      saveRegmapColors();
      rgRender();
    });

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

  /* 几何图弹窗的副标题：区域中英文名 */
  function rd_sub_of(code){
    var rd = regionData(code);
    if (!rd) return '几何排布';
    return (rd.zh || rd.nameZh || '') + ' ' + (rd.en || rd.nameEn || '');
  }

  /* ---------------- 房间关系图（Obsidian Graph View 复刻） ----------------
     数据：节点 = 房间，边 = world 文件里的连接（regionRoomSets().nbr，已按变体/条件房间过滤）。
     物理与渲染参数取自对 Obsidian 1.13.7 的逆向结论（见 runningZ1/obsidian-graph-replica 的分析文档）：
       · 物理 = d3-force 四力（向心 / 连线 / 电荷 / 碰撞）+ 速度保留 0.6 + 300 步 alpha 衰减
       · 半径 = max(8, min(3·√(度+1), 30))，屏幕大小按 √缩放 变化
       · 标签 alpha = clamp(log2(缩放) + 1 − 阈值)，字号 = 14 + 半径/4
       · 所有视觉属性每帧按 0.9 插值；缩放按 0.85 追赶目标；平移松手带惯性
       · 静止 60 帧休眠；打开时按"离视口中心最近"分批淡入（从中心长出来）
     播放顺序仍是本工具自己的：DFS 逐个"出现"（这点 Obsidian 没有，是我们加的）。 */
  var GX_VER = 2;
  var GX_ALPHA_DECAY = 1 - Math.pow(0.001, 1 / 300);   /* d3 的 300 步衰减 */
  var GX_VKEEP = 0.6;         /* 每步速度保留率（Obsidian 的值） */
  var GX_DIM = 0.2;           /* 悬停时无关元素的透明度 */
  var GX_COLLIDE = 60;        /* forceCollide 半径（成对即 120） */
  var GX_LINK_SOFT = 0.34;    /* 连线弹簧的软硬：越小越"自行伸长"，0.34 是实测边长方差合适的值 */
  /* 每步位移上限：全员挤在中心时斥力会瞬间爆开（一帧飞 400 单位），
     封顶之后就变成 2 秒左右"缓缓摊开"的观感，稳定后对正常物理没有影响 */
  var GX_MAX_STEP = 12;
  /* 力整体放大：形状不变（电荷 / 连线 / 向心同乘），但每秒走过的距离变大，
     拖动时邻居才会"跟着走"而不是软绵绵地拖。 */
  var GX_GAIN = 1.25;
  /* alpha 不再衰减到 0，而是停在这个下限上继续迭代，直到真的不动了。
     旧的写法在 300 帧就把 alpha 压到 0.001 强行冻结，此时残余应力还在，
     一拖动就"炸开重排"—— 这是用户报的「没有移到稳定位置」的根因。 */
  var GX_ALPHA_FLOOR = 0.8;
  var GX_SETTLE_TICKS = 900;   /* 收敛预算：warm 与可见那一遍跑同样多步，fit 才对得上 */
  var GX_EASE_TICKS = 45;      /* 前 45 拍一步一步走（"从一点摊开"要看得见），之后一步当三步 */
  /* 单击 / 拖动的分界：按下后以落点为圆心画一个半径 5px 的隐形圈，
     鼠标一旦移出圈就锁定为「拖动」——回圈也不改判（latch），
     否则拖完再松手会被当成单击，一下把人弹进房间卡。
     参考 Windows 系统拖拽阈值（SM_CXDRAG）默认 4px，这里取 5 略宽一点更好点。 */
  var GX_DRAG_RADIUS = 5;
  var GX_SETTLE_SPEED = 0.18;  /* 平均速度低于它算"站稳" */
  var GX_DRAG_STEP = 20;       /* 拖动时允许更大的单步位移，邻居跟得快 */
  var GX_NODE_PX = 1.0;       /* Obsidian 的世界半径 → 我们的屏幕像素 */
  /* Obsidian 的 max(8, min(3√(度+1), 30)) 下限 8 对我们太小图来说一坨一样大，
     改成 2.4 + 0.9√度：叶子 2.4px、度 8 约 4.9px、度 14 约 5.8px —— 小点，但枢纽看得出来 */
  var GX_NODE_BASE = 2.1;
  var GX_NODE_GROW = 0.52;
  var GX_NODE_MAX = 7.6;
  var GX_TEXT_PX = 0.75;
  var GX_OPT_DEFAULT = {
    ver: GX_VER,
    /* 四个力：存的是「滑块值」，用的时候再换算，和 Obsidian 的 graph.json 一致 */
    center: 0.5187, repel: 10, link: 1, dist: 250,
    textFade: -1.5, size: 1, line: 1,
    arrow: 0, pin: 0, gap: 120, speed: 1,
    settle: 1,        /* 布局速度：每帧迭代次数的倍数（0.5–3） */
    dragPull: 1.5,    /* 拖动时对邻居的拉力倍数（1–4），只作用于连线弹簧 */
    orphan: 1,                 /* 孤立房间（0 度）默认显示 */
    view: 'all',               /* all | visited | unvisited */
    reachMode: 'reach',        /* 世界拓扑：reach=只显示可达 / ghost=可达+灰显 / all=全部 */
    idle: 1,                   /* 1 = 保持微动（不冻结物理） */
    labelGap: 26,              /* 名字最小间距（屏幕 px）；0 = 从不隐藏 */
    labelFade: 0,              /* 0 = 整批浮现（默认）；1 = 每个名字各自淡出（旧行为） */
    labelCrowd: 0,             /* 可选项 A：0 = 名字只跟缩放整批显隐（默认）；1 = 按间距/密度逐个让位 */
    order: 'geo', mode: 'all', start: 'gate'
  };
  var GX_COL_DEFAULT = {
    dark: {
      visited: '#e8b04a', unvisited: '#6f8299', gate: '#7aa2ff',
      shelter: '#f0a35e', current: '#ffffff', trail: '#2fd39a', line: '#55657d'
    },
    light: {
      visited: '#b4761a', unvisited: '#8496a9', gate: '#2f6fd0',
      shelter: '#c2701c', current: '#1b2431', trail: '#0e8c80', line: '#aab8c9'
    }
  };
  var GX = null;

  function gxLerp(a, b, k){
    var f = (k == null) ? 0.9 : k;
    return a * f + b * (1 - f);
  }
  function gxRgb(hex){
    var h = String(hex || '').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (isNaN(n)) return { r: 128, g: 128, b: 128 };
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  function gxRgba(rgb, a){
    return 'rgba(' + Math.round(rgb.r) + ',' + Math.round(rgb.g) + ',' + Math.round(rgb.b) + ',' + a + ')';
  }

  function gxOpts(){
    var out = {}, k, saved = state.graphOpts || {};
    for (k in GX_OPT_DEFAULT) out[k] = GX_OPT_DEFAULT[k];
    if (saved.ver === GX_VER){
      for (k in out) if (saved[k] != null) out[k] = saved[k];
    } else {
      /* 旧版（11-04 之前）的力参数语义完全不同，只继承与物理无关的几项 */
      ['gap', 'speed', 'order', 'mode', 'start', 'arrow', 'pin'].forEach(function(key){
        if (saved[key] != null) out[key] = saved[key];
      });
      if (saved.fold != null) out.orphan = saved.fold ? 0 : 1;
    }
    /* 老配置里的 fold（折叠无连接）迁到 orphan（是否显示孤立房间） */
    if (saved.ver === GX_VER && saved.fold != null && saved.orphan == null) out.orphan = saved.fold ? 0 : 1;
    /* 名字显隐迁移：11-06 之前「逐个淡出名字」是独立开关，勾过的人其实一直在用密度让位。
       现在密度让位收进了可选项 A（labelCrowd），不迁移就会把老用户静默改成整批。 */
    if (saved.labelCrowd == null && saved.labelFade === 1){ out.labelCrowd = 1; out.labelFade = 1; }
    if (out.settle != null) out.settle = Math.max(0.35, Math.min(1.6, Number(out.settle) || 1));
    if (out.dragPull != null) out.dragPull = Math.max(1, Math.min(4, Number(out.dragPull) || 1.5));
    out.ver = GX_VER;
    return out;
  }
  function gxThemeName(){
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }
  function gxColors(){
    var t = gxThemeName();
    var base = GX_COL_DEFAULT[t] || GX_COL_DEFAULT.dark;
    var saved = (state.graphColors && state.graphColors[t]) || {};
    var out = {}, k;
    for (k in base) out[k] = saved[k] || base[k];
    return out;
  }
  /* 滑块 → 实际值：Obsidian 的 c0(v,t) = (t^(1-v) - t) / (1 - t)（对数曲线） */
  function gxC0(v, t){
    v = Math.max(0, Math.min(1, v));
    return (Math.pow(t, 1 - v) - t) / (1 - t);
  }
  function gxRepelActual(v){ var x = Math.max(0.5, v); return x * x * x; }

  function gxSaveGraphOpts(){
    if (!hasBridge()) return;
    bridgeCall('save_config', { ui: { graph: state.graphOpts } }).catch(function(){});
  }
  function gxSaveColors(){
    if (!hasBridge()) return;
    bridgeCall('save_config', { ui: { graphColors: state.graphColors } }).catch(function(){});
  }

  /* ---------------- 手动"探索过"标记 ----------------
     存档里没记、但玩家确实去过；允许逐间覆盖，存在 config.ui.roomMarks：
     { 区域: { 房间: 1(强制已探索) | -1(强制未探索) } }，0/缺省 = 跟随存档。 */
  function roomMarkMap(code){
    var m = (state.roomMarks || {})[String(code).toUpperCase()];
    return (m && typeof m === 'object') ? m : {};
  }
  function roomMarkOf(code, name){
    var v = roomMarkMap(code)[String(name).toUpperCase()];
    return (v === 1 || v === -1) ? v : 0;
  }
  function roomSeen(code, name, seen){
    var m = roomMarkOf(code, name);
    if (m === 1) return true;
    if (m === -1) return false;
    return !!seen;
  }
  /* ---------------- 手动"这个角色到不了"的房间 ----------------
     存 config.ui.roomExcluded：{ 角色: { 区域: [房间名] } }，直接不进分母。 */
  function roomExcludedMap(slugcat, code){
    var cat = canonSlugcat(slugcat).toUpperCase();
    var bucket = (state.roomExcluded || {})[cat] || {};
    var list = bucket[String(code || '').toUpperCase()] || [];
    var out = {};
    list.forEach(function(n){ out[String(n).toUpperCase()] = 1; });
    return out;
  }

  function isRoomExcluded(slugcat, code, name){
    return !!roomExcludedMap(slugcat, code)[String(name).toUpperCase()];
  }

  function setRoomExcluded(slugcat, code, name, on){
    var cat = canonSlugcat(slugcat).toUpperCase();
    var reg = String(code || '').toUpperCase();
    var key = String(name || '').toUpperCase();
    if (!state.roomExcluded) state.roomExcluded = {};
    var bucket = state.roomExcluded[cat] || (state.roomExcluded[cat] = {});
    var list = bucket[reg] || (bucket[reg] = []);
    var at = list.indexOf(key);
    if (on && at < 0) list.push(key);
    if (!on && at >= 0) list.splice(at, 1);
    if (!list.length) delete bucket[reg];
    if (!Object.keys(bucket).length) delete state.roomExcluded[cat];
    if (hasBridge()) bridgeCall('save_config', { ui: { roomExcluded: state.roomExcluded } }).catch(function(){});
  }

  function setRoomMark(code, name, val){
    var k = String(code).toUpperCase(), n = String(name).toUpperCase();
    if (!state.roomMarks) state.roomMarks = {};
    if (!state.roomMarks[k]) state.roomMarks[k] = {};
    if (val === 1 || val === -1) state.roomMarks[k][n] = val;
    else delete state.roomMarks[k][n];
    if (!Object.keys(state.roomMarks[k]).length) delete state.roomMarks[k];
    if (hasBridge()) bridgeCall('save_config', { ui: { roomMarks: state.roomMarks } }).catch(function(){});
  }

  function gxGraphable(code){
    var rd = regionData(code);
    if (!rd || !rd.layers) return false;
    return rd.layers.some(function(L){ return !!L.enabled && (L.rooms || []).length; });
  }

  /* ---------- 数据 ---------- */
  function gxBuildData(rd, campaign){
    var slugcat = campaign ? campaign.slugcat : '';
    var sets = regionRoomSets(rd, slugcat);
    if (!sets || !sets.total) return null;
    var visited = {};
    if (campaign){
      (campaign.regions || []).forEach(function(r){
        if (String(r.name).toUpperCase() !== String(rd.code).toUpperCase()) return;
        (r.roomList || []).forEach(function(n){ visited[String(n).toUpperCase()] = 1; });
      });
    }
    var names = Object.keys(sets.names).sort();
    var idx = {}, nodes = [];
    names.forEach(function(n, i){
      idx[n] = i;
      var m = sets.coords ? sets.coords[n] : null;
      nodes.push({
        name: n, deg: 0, visited: roomSeen(rd.code, n, visited[n]),
        shelter: !!(sets.shelters && sets.shelters[n]),
        gate: !!(sets.gates && sets.gates[n]),
        sub: (sets.subs && sets.subs[n]) || '',
        i: i, map: m || null,
        x: 0, y: 0, vx: 0, vy: 0, fx: null, fy: null
      });
    });
    var edges = [], seenE = {}, dangling = 0;
    names.forEach(function(n, i){
      var list = (sets.nbr && sets.nbr[n]) || [];
      list.forEach(function(t){
        var j = idx[t];
        if (j == null){ dangling++; return; }
        if (j === i) return;
        var a = i < j ? i : j, b = i < j ? j : i, key = a + ':' + b;
        if (seenE[key]) return;
        seenE[key] = 1;
        edges.push([a, b]);
      });
    });
    nodes.forEach(function(n){ n.deg = 0; });
    edges.forEach(function(e){ nodes[e[0]].deg++; nodes[e[1]].deg++; });
    var adj = nodes.map(function(){ return []; });
    edges.forEach(function(e){ adj[e[0]].push(e[1]); adj[e[1]].push(e[0]); });
    gxSeed(nodes);
    return {
      nodes: nodes, edges: edges, adj: adj, idx: idx,
      stats: {
        rooms: nodes.length,
        edges: edges.length,
        isolated: nodes.filter(function(n){ return n.deg === 0; }).length,
        visited: nodes.filter(function(n){ return n.visited; }).length,
        gates: nodes.filter(function(n){ return n.gate; }).length,
        shelters: nodes.filter(function(n){ return n.shelter; }).length,
        dangling: dangling,
        setsTotal: sets.total,
        layers: sets.layerNames || [],
        variant: sets.variant || ''
      }
    };
  }

  /* 固定种子的 LCG：同一份数据每次打开都长成同一个形状（不再是"每次随机") */
  var gxRandState = 1;
  function gxRand(){
    gxRandState = (1664525 * gxRandState + 1013904223) % 4294967296;
    return gxRandState / 4294967296;
  }

  /* ---------- 世界拓扑：节点 = 区域，边 = 业力门 ----------
     覆盖范围＝当前存档那个角色能走到的区域（campaign.regions），跨区连接靠 GATE_<A>_<B> 解析。 */
  /* 世界拓扑收录哪些区域：所有导入过数据的区域 ∪ 存档里出现过的区域。
     早先只用 campaign.regions（存档里有进度的那些），White 只有 32 个，用户会以为丢数据；
     现在把导入过的区域全铺上，没去过的点显示成"未探索"色，能用工具栏筛选收掉。 */
  function gxWorldRegionCodes(campaign){
    var slugcat = campaign ? campaign.slugcat : '';
    var seen = {}, out = [];
    function add(code){
      code = String(code || '').toUpperCase();
      if (!code || seen[code]) return;
      seen[code] = 1; out.push(code);
    }
    Object.keys(state.regions || {}).forEach(add);
    (state.regionList || []).forEach(function(it){ add(it.code); });
    ((campaign && campaign.regions) || []).forEach(function(r){ add(r.name); });
    ((state.regionPick || {})[slugcat] || []).forEach(add);
    out.sort();
    return out;
  }

  function gxBuildWorldData(campaign){
    var slugcat = campaign ? campaign.slugcat : '';
    var codes = gxWorldRegionCodes(campaign);
    if (!codes.length) return null;

    var touched = {};
    ((campaign && campaign.regions) || []).forEach(function(r){
      touched[String(r.name).toUpperCase()] = r;
    });

    var nodes = [], idx = {}, gatesOf = {};
    codes.forEach(function(code){
      var rd = regionData(code);
      var sets = rd ? regionRoomSets(rd, slugcat) : null;
      var sum = regionSummary(code) || {};
      var t = touched[code];
      var vm = {};
      ((t && t.roomList) || []).forEach(function(n){ vm[String(n).toUpperCase()] = 1; });
      var seen = 0, gates = [], total = 0;
      if (sets){
        total = sets.total;
        Object.keys(sets.names).forEach(function(nm){
          if (roomSeen(code, nm, vm[nm])) seen++;
        });
        Object.keys(sets.gates || {}).forEach(function(g){ gates.push(g); });
      }
      var reachInfo = regionReachInfo(code, slugcat, !!t);
      idx[code] = nodes.length;
      nodes.push({
        name: code, deg: 0, visited: seen > 0, seen: seen, rooms: total,
        reach: reachInfo.reach, reachNote: reachInfo.note, reachWhy: reachInfo.why,
        gate: false, shelter: false,
        zh: (rd && (rd.zh || rd.nameZh)) || sum.nameZh || '',
        en: (rd && (rd.nameEn || rd.en || rd.displayName)) || sum.nameEn || '',
        touched: !!t,
        sub: (rd && (rd.zh || rd.nameZh)) || '',
        map: null, i: nodes.length,
        x: 0, y: 0, vx: 0, vy: 0, fx: null, fy: null
      });
      gatesOf[code] = gates;
    });

    var pat = /^GATE_([A-Z0-9]+)_([A-Z0-9]+)$/;
    var edges = [], pair = {}, dangling = 0;
    nodes.forEach(function(n){
      (gatesOf[n.name] || []).forEach(function(g){
        var m = pat.exec(String(g).toUpperCase());
        if (!m) return;
        var a = m[1], b = m[2];
        if (a === b) return;
        var x = idx[a], y = idx[b];
        if (x == null || y == null){ dangling++; return; }
        if (x > y){ var t2 = x; x = y; y = t2; }
        var key = x + ':' + y;
        if (pair[key]) return;
        pair[key] = 1;
        edges.push([x, y]);
      });
    });
    nodes.forEach(function(n){ n.deg = 0; n.ghost = !n.reach; });
    edges.forEach(function(e){ nodes[e[0]].deg++; nodes[e[1]].deg++; });
    var adj = nodes.map(function(){ return []; });
    edges.forEach(function(e){ adj[e[0]].push(e[1]); adj[e[1]].push(e[0]); });
    gxSeed(nodes);
    return {
      nodes: nodes, edges: edges, adj: adj, idx: idx,
      stats: {
        rooms: nodes.length, edges: edges.length,
        reach: nodes.filter(function(n){ return n.reach; }).length,
        isolated: nodes.filter(function(n){ return n.deg === 0; }).length,
        visited: nodes.filter(function(n){ return n.visited; }).length,
        touched: nodes.filter(function(n){ return n.touched; }).length,
        gates: 0, shelters: 0, dangling: dangling,
        setsTotal: nodes.length, layers: [], variant: '', world: true
      }
    };
  }

  /* 初始位置：全员缩在中心一小团（半径 ≤6），打开时看起来就是"从一个点炸开"。
     这是 Obsidian 打开关系图谱的样子，也是用户要的"同时在一个小点的地方出现"。 */
  function gxSeed(nodes){
    gxRandState = 20261104;
    nodes.forEach(function(n){
      var a = gxRand() * Math.PI * 2, r = gxRand() * 6;
      n.x = Math.cos(a) * r;
      n.y = Math.sin(a) * r;
      n.vx = 0; n.vy = 0;
      n.fx = null; n.fy = null;
    });
  }

  /* ---------- 弹窗骨架 ---------- */
  function gxSub(rd, campaign, data){
    var st = data.stats;
    var bits = [(rd.zh || rd.nameZh || '') + ' ' + (rd.en || rd.nameEn || '')].filter(Boolean).join(' ');
    var parts = [];
    parts.push(st.rooms + ' 间');
    parts.push(st.edges + ' 条连接');
    parts.push('已探索 ' + st.visited + ' / ' + st.rooms);
    if (st.isolated) parts.push('无连接 ' + st.isolated);
    if (st.variant) parts.push('变体：' + st.variant);
    if (campaign) parts.push('角色：' + campaign.slugcat);
    return bits + ' · ' + parts.join(' · ');
  }

  function gxShellHTML(rd, data, o){
    var st = data.stats;
    var speeds = [0.5, 1, 1.5, 2, 3].map(function(v){
      return '<option value="' + v + '"' + (Math.abs(o.speed - v) < 0.01 ? ' selected' : '') + '>' + v + '×</option>';
    }).join('');
    var orders = [['geo', '就近'], ['name', '房间号'], ['deg', '度数优先']].map(function(x){
      return '<option value="' + x[0] + '"' + (o.order === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
    }).join('');
    var starts = [['gate', '业力门'], ['shelter', '庇护所'], ['den', '存档冬眠点'], ['custom', '选中节点']].map(function(x){
      return '<option value="' + x[0] + '"' + (o.start === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
    }).join('');

    function vbtn(key, label){
      return '<button class="gx-view' + (o.view === key ? ' on' : '') + '" type="button" data-gxview="' + key + '">' + label + '</button>';
    }

    return '' +
      '<div class="gx-tools">' +
        '<button class="btn ghost" id="gx-back" type="button" title="回到这个区域的地图">← 地图</button>' +
        '<span class="gx-playgrp">' +
          '<button class="btn primary" id="gx-play" type="button">▶ 播放</button>' +
          '<label class="gx-lab">起点<select id="gx-start">' + starts + '</select></label>' +
          '<label class="gx-lab">顺序<select id="gx-order">' + orders + '</select></label>' +
          '<label class="gx-lab">间隔<input type="range" id="gx-gap" min="30" max="600" step="10" value="' + o.gap + '"><b id="gx-gap-v">' + o.gap + 'ms</b></label>' +
          '<label class="gx-lab">速度<select id="gx-speed">' + speeds + '</select></label>' +
        '</span>' +
        '<span class="gx-lab">筛选</span>' +
        vbtn('all', '全部') + vbtn('visited', '已探索') + vbtn('unvisited', '未探索') +
        '<label class="gx-lab"><input type="checkbox" id="gx-orphan"' + (o.orphan ? ' checked' : '') + '>孤立房间</label>' +
        '<label class="gx-lab" id="gx-reach-wrap" hidden>可达<select id="gx-reach">' +
          [['reach', '只显示可达'], ['ghost', '可达+灰显'], ['all', '全部']].map(function(x){
            return '<option value="' + x[0] + '"' + ((o.reachMode || 'reach') === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
          }).join('') + '</select></label>' +
        '<span class="gx-stats">' + st.rooms + ' 间 · ' + st.edges + ' 条 · 双击节点开卡</span>' +
        '<button class="btn ghost" id="gx-settings" type="button">设置</button>' +
      '</div>' +
      '<div class="gx-stage" id="gx-stage">' +
        '<canvas id="gx-canvas"></canvas>' +
        '<div class="gx-zoom">' +
          '<button type="button" data-gzoom="out" title="缩小">−</button>' +
          '<span id="gx-pct">100%</span>' +
          '<button type="button" data-gzoom="in" title="放大">+</button>' +
          '<button type="button" data-gzoom="fit" title="缩放回全图">复位</button>' +
        '</div>' +
        '<div class="gx-legend" id="gx-legend"></div>' +
        '<div class="gx-tip" id="gx-tip"></div>' +
        '<div class="gx-panel" id="gx-panel" hidden></div>' +
        '<div class="gx-menu" id="gx-menu" hidden></div>' +
      '</div>';
  }

  function gxLegendHTML(){
    var c = GX.col;
    return '<span><i style="background:' + c.visited + '"></i>已探索</span>' +
      '<span><i style="background:' + c.unvisited + '"></i>未探索</span>' +
      '<span><i style="background:' + c.gate + '"></i>业力门</span>' +
      '<span><i style="background:' + c.shelter + '"></i>庇护所</span>' +
      '<span><i style="background:' + c.trail + '"></i>光带</span>';
  }

  function gxSettingsHTML(){
    var o = GX.opts, c = GX.col;
    function row(label, key, min, max, step, val, unit, hint, fmt){
      var shown = fmt ? fmt(val) : (val + (unit || ''));
      return '<div class="gx-row sl"><div class="gx-rl">' +
        '<label title="' + (hint || '') + '">' + label + '</label>' +
        '<b data-gxval="' + key + '">' + shown + '</b></div>' +
        '<input type="range" data-gxopt="' + key + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + val + '"></div>';
    }
    function colorRow(label, key, face){
      return '<div class="gx-row"><label>' + label + '</label>' +
        '<input type="color" data-gxcol="' + (face || key) + '" value="' + (c[face || key] || '#888888') + '"></div>';
    }
    function sec(title, body, open){
      return '<div class="gx-sec' + (open ? ' open' : '') + '">' +
        '<button type="button" class="gx-sec-h">' + title + '<i>▾</i></button>' +
        '<div class="gx-sec-b">' + body + '</div></div>';
    }
    var force = sec('力',
      row('向心力', 'center', 0, 1, 0.01, o.center, '', '对数曲线，实际值 ' + gxC0(o.center, 0.01).toFixed(3)) +
      row('排斥力', 'repel', 0, 20, 0.5, o.repel, '', '立方曲线，实际值 ' + Math.round(gxRepelActual(o.repel))) +
      row('吸引力', 'link', 0, 1, 0.01, o.link, '', '对数曲线，实际值 ' + gxC0(o.link, 0.01).toFixed(2)) +
      row('连线长度', 'dist', 30, 500, 5, o.dist) +
      row('布局速度', 'settle', 0.35, 1.6, 0.05, o.settle, '', '越大收敛越快。旁边是大概要几秒才停稳', function(v){ return gxSettleText(v); }) +
      row('拖动拉力', 'dragPull', 1, 4, 0.1, o.dragPull, '×', '拖一个节点时，邻居被拉过来的力度。只影响拖动过程，松手后布局照样归位'), true);
    var show = sec('显示',
      row('节点大小', 'size', 0.1, 5, 0.1, o.size) +
      row('连线粗细', 'line', 0.1, 5, 0.1, o.line) +
      row('文本透明度', 'textFade', -3, 3, 0.1, o.textFade, '', '越大越早隐藏标签（Obsidian 默认 0）') +
      '<div class="gx-row"><label title="默认关：名字只跟缩放走 —— 放大一起出现、缩小一起消失，不会有的有、有的没有。' +
        '打开后名字会按下面的「名字间距」逐间让位">名字挨挤时自动让位（A）</label>' +
        '<input type="checkbox" data-gxflag="labelCrowd"' + (o.labelCrowd ? ' checked' : '') + '></div>' +
      '<div data-gxdep="labelCrowd"' + (o.labelCrowd ? '' : ' style="display:none"') + '>' +
        row('名字间距', 'labelGap', 0, 60, 2, o.labelGap, 'px', '两个节点近于这个屏幕距离时，只留连接多的那个名字；0 = 从不隐藏') +
        '<div class="gx-row"><label title="只在打开 A 时有效：勾上后每个名字各自淡出，取消则整批硬切换">逐个淡出名字</label>' +
          '<input type="checkbox" data-gxflag="labelFade"' + (o.labelFade ? ' checked' : '') + '></div>' +
      '</div>' +
      '<div class="gx-row"><label title="打开后图不会停，会一直微微飘（费一点 CPU）">保持微动</label>' +
        '<input type="checkbox" data-gxflag="idle"' + (o.idle ? ' checked' : '') + '></div>' +
      '<div class="gx-row"><label>箭头</label><input type="checkbox" data-gxflag="arrow"' + (o.arrow ? ' checked' : '') + '></div>' +
      '<div class="gx-row"><label title="关掉就不画 0 连接的房间">孤立房间</label><input type="checkbox" data-gxflag="orphan"' + (o.orphan ? ' checked' : '') + '></div>' +
      '<div class="gx-row"><label title="关掉时：拖完松手，节点会被弹簧拉回原位">拖动后固定</label>' +
        '<input type="checkbox" data-gxflag="pin"' + (o.pin ? ' checked' : '') + '></div>', false);
    var colors = sec('状态颜色（' + (gxThemeName() === 'light' ? '亮色' : '暗色') + '）',
      '<div class="gx-cols">' +
      colorRow('已探索', 'visited') + colorRow('未探索', 'unvisited') +
      colorRow('业力门', 'gate') + colorRow('庇护所', 'shelter') +
      colorRow('当前节点', 'current') + colorRow('光带', 'trail') + colorRow('连线', 'line', 'line') +
      '</div>' +
      '<div class="gx-row" style="margin-top:8px"><button class="btn ghost" id="gx-col-reset" type="button">恢复默认颜色</button></div>', false);
    var anim = sec('动画',
      '<div class="gx-row"><label>播放口径</label><select id="gx-mode">' +
        [['all', '全部房间'], ['visited', '只走已探索'], ['visitedfirst', '已探索优先']].map(function(x){
          return '<option value="' + x[0] + '"' + (o.mode === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
        }).join('') + '</select></div>', false);
    return force + show + colors + anim;
  }

  /* ---------- 打开 ---------- */
  function openGraph(code, focusName){
    var rd = regionData(code);
    if (!rd){ toast('该区域没有导入数据'); return; }
    var campaign = currentCampaign();
    var data = gxBuildData(rd, campaign);
    if (!data){
      openModal('区域拓扑 · ' + code, esc(rd.zh || rd.nameZh || ''),
        '<div class="map-empty">该区域没有房间清单（只有地图，或来源被全部熄灭）。</div>', true);
      return;
    }
    var opts = gxOpts(), col = gxColors();
    openModal('区域拓扑 · ' + code, gxSub(rd, campaign, data), gxShellHTML(rd, data, opts), false, true);
    gxBoot({
      code: String(code).toUpperCase(), rd: rd, campaign: campaign, data: data,
      opts: opts, col: col, world: false, focus: focusName
    });
  }

  function openWorldGraph(retried){
    var campaign = currentCampaign();
    if (!campaign){ toast('先打开一个存档'); return; }
    var total = (state.regionList || []).length;
    var ready = state.regionsPromise;
    /* 只等一次：某个区域详情加载失败时长度永远追不上 total，再等就会无限递归 */
    if (!retried && ready && ready.then && total &&
        Object.keys(state.regions || {}).length < total){
      toast('正在加载区域数据…');
      ready.then(function(){ openWorldGraph(true); }).catch(function(){ openWorldGraph(true); });
      return;
    }
    var data = gxBuildWorldData(campaign);
    if (!data || !data.nodes.length){ toast('这个存档没有可用的区域数据'); return; }
    var opts = gxOpts(), col = gxColors();
    var sub = '以区域为节点、业力门为连线 · ' + data.stats.rooms + ' 个区域（可达 ' +
      (data.stats.reach || 0) + '） · ' + data.stats.edges + ' 条通道 · 有活动 ' +
      (data.stats.touched || 0) + ' 个 · 角色：' + campaign.slugcat;
    openModal('世界拓扑', sub, gxShellHTML(null, data, opts), false, true);
    var den = String(campaign.denPos || '').toUpperCase();
    var focus = den ? den.split('_')[0] : '';
    gxBoot({
      code: '', rd: null, campaign: campaign, data: data,
      opts: opts, col: col, world: true, focus: focus
    });
  }

  function gxBoot(cfg){
    GX = {
      code: cfg.code, rd: cfg.rd, campaign: cfg.campaign, world: !!cfg.world,
      opts: cfg.opts, col: cfg.col,
      nodes: cfg.data.nodes, edges: cfg.data.edges, adj: cfg.data.adj, idx: cfg.data.idx, stats: cfg.data.stats,
      view: { k: 1, x: 0, y: 0 }, prev: { k: 1, x: 0, y: 0 },
      targetK: 1, zoomSX: 0, zoomSY: 0,
      alpha: 1, alphaTarget: 0, force: null,
      ticks: 0, speed: 0, frozen: false, calm: 0, budget: 0,
      hover: -1, sel: -1, lit: -1, drag: null,
      pan: null, panvX: 0, panvY: 0, avgDt: 16, lastMove: 0,
      idle: 0, dpr: 1, raf: 0, kFit: 1, pctShown: '',
      eAlpha: [], startIdx: -1,
      play: { on: false, staged: false, i: -1, seq: [], timer: 0, trail: [], target: [],
              shown: 0, seg: 1, segTotal: 1 }
    };
    GX.nodes.forEach(function(n){
      n.cr = 0; n.cg = 0; n.cb = 0; n.tint = null;
      n.alpha = 0; n.base = 0; n.revealed = false; n.moveText = 0;
      n.labA = 1; n.crowd = 0;
    });
    GX.edges.forEach(function(){ GX.eAlpha.push(1); });
    gxParseColors();
    gxApplyForce();
    $('gx-legend').innerHTML = gxLegendHTML();
    gxSize();
    gxInitSim();
    gxWarm(200);        /* 这一步只为量出"最终会长多大"，用来定 fit */
    gxFit();
    gxRestage();        /* 再全员缩回中心，接下来这一遍是**看得见**的展开 */
    gxBind();
    if (cfg.world){
      var pg = document.querySelector('.gx-playgrp'); if (pg) pg.style.display = 'none';
      var bk = $('gx-back'); if (bk) bk.style.display = 'none';
      var rw = $('gx-reach-wrap');
      if (rw) rw.hidden = false;
      var st = document.querySelector('.gx-stats');
      if (st) st.textContent = GX.stats.rooms + ' 个区域（可达 ' + (GX.stats.reach || 0) + '） · ' +
        GX.stats.edges + ' 条通道 · 双击进入区域';
      var ob = $('gx-orphan');
      if (ob) ob.parentNode.title = '关掉后不画没有任何通道的区域';
    } else {
      var bk2 = $('gx-back');
      if (bk2) bk2.addEventListener('click', function(){ openMap(GX.code); });
    }
    if (cfg.focus && GX.idx[String(cfg.focus).toUpperCase()] != null){
      GX.sel = GX.idx[String(cfg.focus).toUpperCase()];
      GX.opts.start = 'custom';
      var ssel = $('gx-start'); if (ssel) ssel.value = 'custom';
    }
    gxSetStart(GX.opts.start, false);
    gxBuildPlaySeq();
    GX.raf = requestAnimationFrame(gxFrame);
  }

  function gxParseColors(){
    var c = GX.col, k;
    GX.cv = {};
    for (k in c) GX.cv[k] = gxRgb(c[k]);
  }

  function gxApplyForce(){
    if (!GX) return;
    var o = GX.opts;
    GX.force = {
      center: gxC0(o.center, 0.01),
      link: gxC0(o.link, 0.01),
      dist: o.dist,
      charge: -Math.max(1, gxRepelActual(o.repel))
    };
  }

  /* 缩回中心、重新给一点能量：同一份数据 → 同一条轨迹 → 同一个形状 */
  function gxRestage(){
    if (!GX) return;
    gxSeed(GX.nodes);
    GX.alpha = 1;
    GX.alphaTarget = 0;
    GX.ticks = 0; GX.speed = 0; GX.frozen = false; GX.calm = 0; GX.budget = 0;
    GX.nodes.forEach(function(n){ n.revealed = false; n.base = 0; n.alpha = 0; });
    GX.eAlpha = GX.eAlpha.map(function(){ return 0; });
  }

  /* 开图前先同步跑一段力导向（不然 fit 用的是初始的圆点，会缩得很怪） */
  /* 开图前先静默跑满同一份步数：量出最终范围给 fit 用。
     步数、alpha 曲线、随机种子都跟之后看得见那一遍完全一致，所以 fit 不会偏。 */
  function gxWarm(steps){
    if (!GX) return;
    GX.alpha = 1; GX.alphaTarget = 0;
    GX.ticks = 0; GX.speed = 0; GX.frozen = false; GX.calm = 0;
    var max = steps || GX_SETTLE_TICKS;
    for (var i = 0; i < max; i++){
      gxStep();
      if (GX.calm > 18) break;
      if (GX.ticks >= GX_SETTLE_TICKS && GX.speed < GX_SETTLE_SPEED) break;
    }
    GX.alpha = 1; GX.alphaTarget = 0;
    GX.ticks = 0; GX.speed = 0; GX.calm = 0; GX.frozen = false;
  }

  /* 交互后重新给能量并解冻（拖动 / 改力 / 重排都走它） */
  function gxReheat(a){
    if (!GX) return;
    GX.frozen = false; GX.calm = 0;
    GX.alpha = Math.max(GX.alpha, a == null ? 0.9 : a);
  }

  function gxClose(){
    if (GX && GX.raf) cancelAnimationFrame(GX.raf);
    if (GX && GX.play.timer) clearTimeout(GX.play.timer);
    /* 这几个挂在 window 上，不摘会随"每次打开"叠加 */
    window.removeEventListener('resize', gxOnResize);
    window.removeEventListener('keydown', gxKeyDown);
    window.removeEventListener('mouseup', gxMouseUp);
    GX = null;
  }

  /* ---------- 画布尺寸 / 视图 ---------- */
  function gxSize(){
    if (!GX) return;
    var stage = $('gx-stage'), cv = $('gx-canvas');
    if (!stage || !cv) return;
    var w = stage.clientWidth, h = stage.clientHeight;
    GX.dpr = window.devicePixelRatio || 1;
    GX.cw = w; GX.ch = h;
    cv.width = Math.max(1, Math.round(w * GX.dpr));
    cv.height = Math.max(1, Math.round(h * GX.dpr));
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
  }

  /* 稳健包围盒：掐掉两端 3% 的离群点，避免一两个飞远的节点把画面缩得很小 */
  function gxBounds(){
    if (!GX) return null;
    var xs = [], ys = [];
    GX.nodes.forEach(function(p){
      if (!gxShown(p)) return;
      xs.push(p.x); ys.push(p.y);
    });
    if (!xs.length) return null;
    xs.sort(function(a, b){ return a - b; });
    ys.sort(function(a, b){ return a - b; });
    var cut = Math.floor(xs.length * 0.03);
    var lo = cut, hi = Math.max(cut, xs.length - 1 - cut);
    /* 掐掉离群点后要再把框撑开一点：否则被掐掉的点会落到画面外，看上去像"被裁掉了" */
    var mx = (xs[hi] - xs[lo]) * 0.07 + 12, my = (ys[hi] - ys[lo]) * 0.07 + 12;
    return { x0: xs[lo] - mx, y0: ys[lo] - my, x1: xs[hi] + mx, y1: ys[hi] + my };
  }

  function gxFit(){
    if (!GX) return;
    var b = gxBounds();
    if (!b) return;
    var pad = 58;   /* 留够标签的位置：播放时节点会被甩出去一点，边距太小会贴边裁字 */
    var w = Math.max(1, b.x1 - b.x0 + pad * 2), h = Math.max(1, b.y1 - b.y0 + pad * 2);
    var k = Math.min(GX.cw / w, GX.ch / h);
    k = Math.max(1e-4, Math.min(8, k));
    GX.kFit = k;
    GX.view.k = k;
    GX.view.x = GX.cw / 2 - (b.x0 + b.x1) / 2 * k;
    GX.view.y = GX.ch / 2 - (b.y0 + b.y1) / 2 * k;
    GX.prev.k = k; GX.prev.x = GX.view.x; GX.prev.y = GX.view.y;
    GX.targetK = k;
    gxUpdatePct();
  }

  /* 相对缩放：1 = 刚好铺满（复位状态），标签阈值按它算 */
  function gxRel(){ return Math.max(1e-4, GX.view.k / Math.max(1e-6, GX.kFit)); }
  /* 节点的屏幕半径：Obsidian 的 size·√缩放，缩放越大节点越大（但比连线慢） */
  function gxBaseSize(n){
    return Math.min(GX_NODE_BASE + GX_NODE_GROW * n.deg, GX_NODE_MAX) * GX.opts.size;
  }
  function gxNodeSize(n){
    return gxBaseSize(n) * GX_NODE_PX * Math.sqrt(gxRel());
  }
  function gxTextAlpha(){
    var o = GX.opts;
    return Math.max(0, Math.min(1, Math.log(Math.max(1e-4, gxRel())) / Math.LN2 + 1 - o.textFade));
  }

  function gxUpdatePct(){
    var el = $('gx-pct');
    if (!el || !GX) return;
    var txt = Math.round(gxRel() * 100) + '%';
    if (txt !== GX.pctShown){ GX.pctShown = txt; el.textContent = txt; }
  }

  /* 世界拓扑的标签：中文名 + 区域缩写；没有译名就用数据里的英文原名 */
  function gxNodeLabel(n){
    if (GX && GX.world){
      var zh = n.zh || '', en = n.en || '';
      if (zh && zh !== n.name) return zh + ' ' + n.name;
      if (en && en !== n.name) return en + ' ' + n.name;
      return n.name;
    }
    return n.name;
  }

  function gxShown(n){
    if (n.ghost && (GX.opts.reachMode || 'reach') === 'reach') return false;
    if (!GX.opts.orphan && n.deg === 0) return false;
    var v = GX.opts.view || 'all';
    if (v === 'visited' && !n.visited) return false;
    if (v === 'unvisited' && n.visited) return false;
    return true;
  }

  /* ---------- 物理：d3-force 的四力组合（点数 ≤188，电荷用 O(n²)） ---------- */
  function gxInitSim(){
    var n = GX.nodes, i;
    for (i = 0; i < n.length; i++){
      n[i].vx = 0; n[i].vy = 0;
      n[i].fx = null; n[i].fy = null;
    }
    GX.alpha = 1;
    GX.alphaTarget = 0;
    GX.ticks = 0; GX.speed = 0; GX.frozen = false; GX.calm = 0;
  }

  function gxStep(){
    if (!GX) return;
    /* 拖动拉力只乘在「连线弹簧」上，不乘总 alpha。
       乘总 alpha 会同时放大斥力与向心，三者同比 ⇒ 平衡位置不变、只是更快到达，
       观感就是"滑块拉到最大也没把邻居拉近"。这里另外把目标边长一起缩短，
       才是"拉得更近"的直接来源。不拖动时 pull=1、distT=P.dist，与旧行为完全一致。 */
    var pull = (GX.drag && GX.drag.hit >= 0) ? (GX.opts.dragPull || 1.5) : 1;
    var dragIdx = (GX.drag && GX.drag.hit >= 0) ? GX.drag.hit : -1;
    var n = GX.nodes, e = GX.edges, P = GX.force, a = GX.alpha * GX_GAIN;
    var distT = P.dist / (1 + 0.5 * (pull - 1));   /* 1×→1×dist，2×→0.67×，4×→0.4× */
    var i, j, p, q, dx, dy, d2, d, f, l, bias;
    var min2 = 900;                      /* distanceMin 30 的平方 */
    var R2 = GX_COLLIDE * 2;

    /* 1) 电荷（forceManyBody，strength 负 = 斥，最小距离 30） */
    var charge = P.charge * a;
    for (i = 0; i < n.length; i++){
      p = n[i];
      for (j = i + 1; j < n.length; j++){
        q = n[j];
        dx = q.x - p.x; dy = q.y - p.y;
        d2 = dx * dx + dy * dy;
        if (d2 < min2) d2 = min2;
        f = charge / d2;
        p.vx += dx * f; p.vy += dy * f;
        q.vx -= dx * f; q.vy -= dy * f;
      }
    }

    /* 2) 连线（forceLink：距离 dist，强度按两端度数分摊） */
    var lk = P.link;
    for (i = 0; i < e.length; i++){
      p = n[e[i][0]]; q = n[e[i][1]];
      dx = q.x + q.vx - (p.x + p.vx);
      dy = q.y + q.vy - (p.y + p.vy);
      d = Math.sqrt(dx * dx + dy * dy) || 1e-6;
      /* 拖动拉力只作用在「碰到拖动节点的那几条边」上：
         若对所有边都缩短目标长度，整张图会被一起往内收，等于拖动导致全局重排。 */
      var touching = (dragIdx >= 0) && (e[i][0] === dragIdx || e[i][1] === dragIdx);
      var ldist = touching ? distT : P.dist;
      var lmul = touching ? pull : 1;
      /* 弹簧故意放软：距离不再由 dist 钉死，而由"两端各自被挤得多厉害"决定
         —— 枢纽之间被推开就长，叶子挨着就短。除以 min(度) 是 d3 的老规矩。 */
      l = (d - ldist) / d * a * lmul * lk * GX_LINK_SOFT / Math.min(p.deg, q.deg);
      bias = (p.deg + q.deg) ? p.deg / (p.deg + q.deg) : 0.5;
      p.vx += dx * l * bias;          p.vy += dy * l * bias;
      q.vx -= dx * l * (1 - bias);    q.vy -= dy * l * (1 - bias);
    }

    /* 3) 向心（forceX / forceY，目标 0） */
    var cs = P.center * a;
    if (cs){
      for (i = 0; i < n.length; i++){ n[i].vx -= n[i].x * cs; n[i].vy -= n[i].y * cs; }
    }

    /* 4) 碰撞（forceCollide：半径 60，强度 0.5；d3 里它不乘 alpha） */
    for (i = 0; i < n.length; i++){
      p = n[i];
      for (j = i + 1; j < n.length; j++){
        q = n[j];
        dx = q.x + q.vx - (p.x + p.vx);
        dy = q.y + q.vy - (p.y + p.vy);
        d2 = dx * dx + dy * dy;
        if (d2 >= R2 * R2 || d2 < 1e-9) continue;
        d = Math.sqrt(d2);
        f = (R2 - d) / d * 0.25;
        p.vx -= dx * f; p.vy -= dy * f;
        q.vx += dx * f; q.vy += dy * f;
      }
    }

    /* 5) 积分：速度保留 0.6；钉住的节点直接落到 fx/fy */
    var cap = GX.drag && GX.drag.hit >= 0 ? GX_DRAG_STEP : GX_MAX_STEP;
    var sum = 0;
    for (i = 0; i < n.length; i++){
      p = n[i];
      if (p.fx != null){
        p.x = p.fx; p.y = p.fy; p.vx = 0; p.vy = 0;
        continue;
      }
      p.vx *= GX_VKEEP; p.vy *= GX_VKEEP;
      var sp = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (sp > cap){
        var kk = cap / sp;
        p.vx *= kk; p.vy *= kk;
        sp = cap;
      }
      p.x += p.vx; p.y += p.vy;
      sum += sp;
      if (!isFinite(p.x) || !isFinite(p.y)){ p.x = 0; p.y = 0; p.vx = 0; p.vy = 0; }
    }

    GX.speed = n.length ? sum / n.length : 0;
    GX.ticks = (GX.ticks || 0) + 1;
    var tgt = GX.alphaTarget > 0 ? GX.alphaTarget : (GX.opts.idle ? 0.06 : GX_ALPHA_FLOOR);
    GX.alpha = GX.alpha + (tgt - GX.alpha) * GX_ALPHA_DECAY;
  }

  /* ---------- 主循环（含休眠） ---------- */
  function gxChanged(){
    if (!GX) return;
    GX.idle = 0;
    gxQueue();
  }
  function gxQueue(){
    if (GX && !GX.raf) GX.raf = requestAnimationFrame(gxFrame);
  }

  function gxFrame(){
    if (!GX) return;
    GX.raf = 0;
    if (GX.idle > 60) return;          /* 连续 60 帧没变化 → 休眠，零占用 */

    var active = false;
    if (!GX.frozen){
      /* 前段一步当三步跑（从一点炸开的阶段），后段两步：肉眼看到的是"摊开"，
         实际迭代次数够它走到平衡点，不会停在半路。 */
      var base = (GX.ticks || 0) < GX_EASE_TICKS ? 1 : 3;
      /* 用累加器而不是 Math.round：滑块每一格都真正生效，
         0.35 倍时是"每三帧走两步"，而不是被取整成 1 步/帧 */
      var rate = base * Math.max(0.1, Math.min(3, GX.opts.settle || 1));
      GX.budget = (GX.budget || 0) + rate;
      var guard = 0;
      for (var si = 0; GX.budget >= 1 && guard++ < 30; si++){
        if (GX.frozen) break;
        GX.budget -= 1;
        gxStep();
        if (!GX.opts.idle){
          if ((GX.ticks || 0) >= GX_SETTLE_TICKS && (GX.speed || 0) < GX_SETTLE_SPEED){
            GX.frozen = true;
          }
          if (GX.calm === undefined) GX.calm = 0;
          if ((GX.speed || 0) < GX_SETTLE_SPEED) GX.calm++; else GX.calm = 0;
          if (GX.calm > 18) GX.frozen = true;
        }
      }
      active = true;
    }
    gxUpdateZoom();
    if (gxPanInertia()) active = true;
    if (!GX.play.staged && gxReveal()) active = true;
    gxLabelCrowd();
    gxEaseNodes();
    gxAnimTrail();
    gxPlaceMenu();
    if (gxHoverFallback()) active = true;
    if (GX.opts.fold) { /* 折叠时被藏起来的节点不该继续吃算力：不动它就行 */ }
    gxDraw();

    if (active || GX.play.on) GX.idle = 0;
    GX.idle++;
    gxQueue();
  }

  /* 打开时"从视口中心向外生长"：每帧放出一批最近的点，靠 alpha 的 0.9 插值淡入 */
  function gxReveal(){
    var n = GX.nodes, list = [], i;
    for (i = 0; i < n.length; i++){
      if (!n[i].revealed && gxShown(n[i])) list.push(i);
    }
    if (!list.length) return false;
    var cx = (GX.cw / 2 - GX.view.x) / Math.max(1e-6, GX.view.k);
    var cy = (GX.ch / 2 - GX.view.y) / Math.max(1e-6, GX.view.k);
    list.sort(function(a, b){
      var na = GX.nodes[a], nb = GX.nodes[b];
      var da = (na.x - cx) * (na.x - cx) + (na.y - cy) * (na.y - cy);
      var db = (nb.x - cx) * (nb.x - cx) + (nb.y - cy) * (nb.y - cy);
      return da - db;
    });
    var per = Math.max(2, Math.ceil(n.length / 26));
    var take = Math.min(per, list.length);
    for (i = 0; i < take; i++){
      n[list[i]].revealed = true;
      n[list[i]].base = 1;
    }
    return true;
  }

  /* 屏幕距离小于「名字间距」的成对节点，只保留度数大的那个的名字 */
  /* 布局速度 → 大概几秒停稳：总 900 拍，前 45 拍 1 拍/帧、其余 3 拍/帧 × 速度。
     折算下来 ≈ 5.5 / 速度 秒（60fps）。 */
  function gxSettleText(v){
    var k = Math.max(0.1, Number(v) || 1);
    return '≈ ' + (5.5 / k).toFixed(1) + ' 秒';
  }

  /* 屏幕上的字号（跟 draw 里那一份完全一致） */
  function gxFontPx(n){
    return (12.4 + gxBaseSize(n) * 0.5) * Math.sqrt(gxRel()) * GX_TEXT_PX;
  }

  /* 名字拥挤判定：按"字宽"比，不是按"点到点的距离"比 ——
     52 个点彼此 40px 时，20 个字的名字照样压在一起。 */
  function gxLabelCrowd(){
    var nodes = GX.nodes, i, j;
    /* 可选项 A 关闭时：不算拥挤、也不留上一帧的残值 —— 名字只由缩放统一控制（整批） */
    if (!GX.opts.labelCrowd){
      for (i = 0; i < nodes.length; i++) nodes[i].crowd = 0;
      return;
    }
    var gap = GX.opts.labelGap || 0;
    for (i = 0; i < nodes.length; i++) nodes[i].crowd = 0;
    if (gap <= 0 || !GX.view) return;   /* 0 = 从不因拥挤隐藏 */
    var k = GX.view.k;
    var w = [], len = [];
    for (i = 0; i < nodes.length; i++){
      var txt = gxNodeLabel(nodes[i]) || '';
      len[i] = txt.length;
      w[i] = (txt.length * gxFontPx(nodes[i]) * 0.56 + gap) / 2;   /* 半个字宽 + 间距的一半 */
    }
    for (i = 0; i < nodes.length; i++){
      if (!gxShown(nodes[i]) || nodes[i].alpha < 0.05) continue;
      for (j = i + 1; j < nodes.length; j++){
        if (!gxShown(nodes[j]) || nodes[j].alpha < 0.05) continue;
        var dx = (nodes[i].x - nodes[j].x) * k, dy = (nodes[i].y - nodes[j].y) * k;
        var lim = w[i] + w[j];
        /* 滞回：已经藏起来的要拉开 1.25 倍才重新显示，
           否则两个节点在边界上轻微移动会让名字反复闪 */
        var exitLim = lim * 1.25;
        var keep = nodes[i].crowd || nodes[j].crowd;
        if (dx * dx + dy * dy < (keep ? exitLim * exitLim : lim * lim)){
          /* 留连接多的；度一样就留名字短的那个 */
          var meWorse = (nodes[i].deg < nodes[j].deg) ||
            (nodes[i].deg === nodes[j].deg && len[i] > len[j]);
          if (meWorse) nodes[i].crowd = 1; else nodes[j].crowd = 1;
        }
      }
    }
  }

  /* 悬停压暗 / 出现 / 变色：全部每帧按 0.9 插值 */
  function gxEaseNodes(){
    var hl = GX.drag && GX.drag.hit >= 0 ? GX.drag.hit : GX.hover;
    var keep = null;
    if (hl >= 0){
      keep = {};
      keep[hl] = 1;
      GX.adj[hl].forEach(function(w){ keep[w] = 1; });
    }
    var nodes = GX.nodes, o = GX.opts, i, n, tgt;
    for (i = 0; i < nodes.length; i++){
      n = nodes[i];
      tgt = n.base ? (hl < 0 || keep[i] ? 1 : GX_DIM) : 0;
      /* 出现/消失用更快的插值（约 0.15s），否则间隔设到 40ms 时会有十几个点半透明地糊在一起；
         悬停压暗仍用 0.9，保持 Obsidian 那种"慢慢退到背景"的感觉 */
      n.alpha = gxLerp(n.alpha, tgt, (n.base && tgt === 1) ? 0.75 : 0.9);
      if (n.alpha < 1e-3) n.alpha = 0;
      else if (n.alpha > 0.999) n.alpha = 1;
      n.moveText = gxLerp(n.moveText, (i === hl || i === GX.sel) ? 15 : 0);
      n.labA = gxLerp(n.labA == null ? 1 : n.labA, n.crowd ? 0 : 1, 0.86);
      if (!GX.opts.labelFade) n.labA = n.crowd ? 0 : 1;
      var fill = n.visited ? GX.cv.visited : GX.cv.unvisited;
      n.cr = gxLerp(n.cr, fill.r);
      n.cg = gxLerp(n.cg, fill.g);
      n.cb = gxLerp(n.cb, fill.b);
    }
    var hot = GX.hover;
    for (i = 0; i < GX.edges.length; i++){
      var e = GX.edges[i];
      var on = hot >= 0 && (e[0] === hot || e[1] === hot);
      var t = (hot >= 0 && !on) ? GX_DIM : 1;
      t = Math.min(t, nodes[e[0]].alpha, nodes[e[1]].alpha);
      GX.eAlpha[i] = gxLerp(GX.eAlpha[i], t);
      if (GX.eAlpha[i] < 1e-3) GX.eAlpha[i] = 0;
    }
  }

  /* 鼠标离开节点后 pointerout 可能不触发，每帧按"半径 + 2"补判 */
  function gxHoverFallback(){
    var hl = GX.hover;
    if (hl < 0 || GX.drag || GX.mouseSX == null) return false;
    var n = GX.nodes[hl];
    var wx = (GX.mouseSX - GX.view.x) / GX.view.k;
    var wy = (GX.mouseSY - GX.view.y) / GX.view.k;
    var rr = gxNodeSize(n) / GX.view.k + 2;
    if ((n.x - wx) * (n.x - wx) + (n.y - wy) * (n.y - wy) > rr * rr){
      GX.hover = -1;
      var t = $('gx-tip'); if (t) t.classList.remove('on');
      return true;
    }
    return false;
  }

  /* ---------- 缩放：目标先变，画面按 0.85 追 ---------- */
  function gxUpdateZoom(){
    var t = Math.max(GX.kFit / 8, Math.min(GX.kFit * 8, GX.targetK));
    GX.targetK = t;
    var s = GX.view.k, px = GX.view.x, py = GX.view.y;
    if (Math.abs(s / t - 1) >= 0.01){
      var cx = GX.zoomSX, cy = GX.zoomSY;
      if (!cx && !cy){ cx = GX.cw / 2; cy = GX.ch / 2; }
      var wx = (cx - px) / s, wy = (cy - py) / s;
      s = gxLerp(s, t, 0.85);
      px = cx - wx * s; py = cy - wy * s;
      GX.view.k = s; GX.view.x = px; GX.view.y = py;
      GX.idle = 0;
    } else if (Math.abs(s - t) > 1e-9){
      var cx2 = GX.zoomSX, cy2 = GX.zoomSY;
      if (!cx2 && !cy2){ cx2 = GX.cw / 2; cy2 = GX.ch / 2; }
      var wx2 = (cx2 - px) / s, wy2 = (cy2 - py) / s;
      GX.view.k = t; GX.view.x = cx2 - wx2 * t; GX.view.y = cy2 - wy2 * t;
    }
    gxUpdatePct();
  }

  function gxPanInertia(){
    if (GX.pan) return false;
    if (Math.abs(GX.panvX) < 1e-3 && Math.abs(GX.panvY) < 1e-3){
      GX.panvX = 0; GX.panvY = 0;
      return false;
    }
    GX.view.x += 1000 * GX.panvX / 60;
    GX.view.y += 1000 * GX.panvY / 60;
    GX.panvX = gxLerp(GX.panvX, 0);
    GX.panvY = gxLerp(GX.panvY, 0);
    return true;
  }

  /* ---------- 绘制（屏幕坐标，公式照 Obsidian 的 render） ---------- */
  function gxDraw(){
    if (!GX) return;
    var cv = $('gx-canvas');
    if (!cv) return;
    var ctx = cv.getContext('2d');
    var c = GX.col, o = GX.opts, p = GX.play, cv2 = GX.cv;
    var k = GX.view.k, tx = GX.view.x, ty = GX.view.y;
    var rel = gxRel(), vs = Math.sqrt(rel);
    var tAlpha = gxTextAlpha();
    var hl = GX.drag && GX.drag.hit >= 0 ? GX.drag.hit : GX.hover;
    var cur = p.on ? GX.nodes.length && p.trail.length ? p.trail[p.trail.length - 1] : -1 : -1;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.setTransform(GX.dpr, 0, 0, GX.dpr, 0, 0);

    var vx0 = 0, vy0 = 0, vx1 = GX.cw, vy1 = GX.ch;
    var i, n, a, b, sx, sy, r, isHot;

    /* 连线：屏幕恒定线宽；透明度按两端取小；与悬停相邻的用高亮色 */
    var lw = Math.max(0.5, o.line);
    for (i = 0; i < GX.edges.length; i++){
      a = GX.nodes[GX.edges[i][0]];
      b = GX.nodes[GX.edges[i][1]];
      var ea = GX.eAlpha[i];
      if (ea <= 0.004) continue;
      if (!gxShown(a) || !gxShown(b)) continue;
      var ax = a.x * k + tx, ay = a.y * k + ty, bx = b.x * k + tx, by = b.y * k + ty;
      if (Math.max(ax, bx) < vx0 - 20 || Math.min(ax, bx) > vx1 + 20 ||
          Math.max(ay, by) < vy0 - 20 || Math.min(ay, by) > vy1 + 20) continue;
      isHot = hl >= 0 && (GX.edges[i][0] === hl || GX.edges[i][1] === hl);
      ctx.strokeStyle = isHot ? c.trail : c.line;
      ctx.globalAlpha = ea;
      ctx.lineWidth = isHot ? lw + 1.2 : lw;
      /* 从圆的边缘画起，别插进节点里 */
      var dx = bx - ax, dy = by - ay, dd = Math.sqrt(dx * dx + dy * dy) || 1;
      var ra = gxNodeSize(a) + 1, rb = gxNodeSize(b) + 1;
      if (dd > ra + rb){
        ctx.beginPath();
        ctx.moveTo(ax + dx * ra / dd, ay + dy * ra / dd);
        ctx.lineTo(bx - dx * rb / dd, by - dy * rb / dd);
        ctx.stroke();
        if (o.arrow){
          var arA = Math.max(0, Math.min(1, 2 * (rel - 0.3)));
          if (arA > 0.02){
            var ang = Math.atan2(dy, dx), al = 7 * Math.sqrt(o.line), aw2 = al * 0.52;
            var tipx = bx - dx * rb / dd, tipy = by - dy * rb / dd;
            ctx.globalAlpha = ea * arA;
            ctx.fillStyle = isHot ? c.trail : c.line;
            ctx.beginPath();
            ctx.moveTo(tipx, tipy);
            ctx.lineTo(tipx - Math.cos(ang) * al - Math.sin(ang) * aw2,
                       tipy - Math.sin(ang) * al + Math.cos(ang) * aw2);
            ctx.lineTo(tipx - Math.cos(ang) * al + Math.sin(ang) * aw2,
                       tipy - Math.sin(ang) * al - Math.cos(ang) * aw2);
            ctx.closePath();
            ctx.fill();
          }
        }
      }
    }
    ctx.globalAlpha = 1;

    /* 光带（DFS 当前栈）：只在播放时出现 */
    if (p.on && p.shown >= 2 && p.trail.length >= 2){
      ctx.strokeStyle = c.trail;
      ctx.lineWidth = Math.max(2, lw + 1.1);
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.78;
      ctx.beginPath();
      var show = Math.min(p.trail.length, Math.round(p.shown));
      for (i = 1; i < show; i++){
        a = GX.nodes[p.trail[i - 1]];
        b = GX.nodes[p.trail[i]];
        ctx.moveTo(a.x * k + tx, a.y * k + ty);
        ctx.lineTo(b.x * k + tx, b.y * k + ty);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.lineCap = 'butt';
    }

    /* 节点 + 标签 */
    var fontBase = 12.4;
    for (i = 0; i < GX.nodes.length; i++){
      n = GX.nodes[i];
      if (!gxShown(n)) continue;
      if (n.alpha <= 0.004) continue;
      r = gxNodeSize(n);
      sx = n.x * k + tx; sy = n.y * k + ty;
      if (sx < vx0 - r - 2 || sx > vx1 + r + 2 || sy < vy0 - r - 2 || sy > vy1 + r + 2) continue;

      var alpha = n.alpha;
      ctx.globalAlpha = alpha;

      /* 不可达区域：只画一个空心圈（还能看见它存在，但不假装能走） */
      if (n.ghost){
        ctx.strokeStyle = gxRgba({ r: n.cr, g: n.cg, b: n.cb }, 0.55);
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath(); ctx.arc(sx, sy, Math.max(2.5, r * 0.8), 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
        continue;
      }

      /* 已探索：实心；未探索：低透明填充 + 细描边（颜色可改） */
      if (n.visited){
        ctx.fillStyle = gxRgba({ r: n.cr, g: n.cg, b: n.cb }, 1);
        ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.fillStyle = gxRgba({ r: n.cr, g: n.cg, b: n.cb }, 0.82);
        ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = gxRgba({ r: n.cr, g: n.cg, b: n.cb }, 0.85);
        ctx.lineWidth = Math.max(0.7, 1);
        ctx.stroke();
      }

      if (n.gate){
        ctx.beginPath();
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = gxRgba(cv2.gate, 0.95);
        ctx.lineWidth = Math.max(0.8, 1.1);
        ctx.arc(sx, sy, r + 3.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (n.shelter){
        var sq = Math.max(3, r * 0.72);
        ctx.fillStyle = c.shelter;
        ctx.fillRect(sx - sq / 2, sy - sq / 2, sq, sq);
      }
      /* 高亮描边：宽度取 max(1, 1/scale/ns) → 屏幕上恒定约 1px */
      if (i === hl || i === GX.sel || i === cur){
        ctx.beginPath();
        ctx.strokeStyle = gxRgba(cv2.current, i === hl ? 0.95 : 0.75);
        ctx.lineWidth = 1.4;
        ctx.arc(sx, sy, r + 3, 0, Math.PI * 2);
        ctx.stroke();
      }

      /* 标签：透明度 = textAlpha(全局,随缩放) × 节点自身 alpha。
         「整批」模式下不再乘逐节点的 labA —— 名字要么整批出现、要么整批隐去，
         只有缩放到阈值时才有一次整体淡出（tAlpha 本来就是全局的）。 */
      var ta = tAlpha * n.alpha;
      var hideByCrowd = GX.opts.labelCrowd && n.crowd && i !== hl && i !== GX.sel;
      if (GX.opts.labelFade && n.labA != null) ta *= n.labA;
      if (hideByCrowd && !GX.opts.labelFade) ta = 0;
      if (i === hl || i === GX.sel) ta = 1;
      if (ta > 0.01){
        var fpx = (fontBase + gxBaseSize(n) * 0.5) * vs * GX_TEXT_PX;
        var off = r + 5 + n.moveText;
        ctx.globalAlpha = ta;
        ctx.font = '500 ' + fpx.toFixed(1) + 'px ui-monospace, Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = gxThemeName() === 'light' ? 'rgba(24,36,52,.82)' : 'rgba(226,235,246,.8)';
        ctx.fillText(gxNodeLabel(n), sx, sy + off);
      }
    }
    ctx.globalAlpha = 1;
    ctx.textBaseline = 'alphabetic';
  }

  /* ---------- 交互 ---------- */
  function gxToWorld(ev){
    var cv = $('gx-canvas'), r = cv.getBoundingClientRect();
    var sx = ev.clientX - r.left, sy = ev.clientY - r.top;
    GX.mouseSX = sx; GX.mouseSY = sy;
    return { x: (sx - GX.view.x) / GX.view.k, y: (sy - GX.view.y) / GX.view.k, sx: sx, sy: sy };
  }
  function gxPick(ev){
    var w = gxToWorld(ev), best = -1, bestD = 1e9;
    GX.nodes.forEach(function(n, i){
      if (!gxShown(n) || n.alpha <= 0.05) return;
      var dx = n.x - w.x, dy = n.y - w.y, d = Math.sqrt(dx * dx + dy * dy);
      var lim = (gxNodeSize(n) + 8) / GX.view.k;
      if (d <= lim && d < bestD){ bestD = d; best = i; }
    });
    return best;
  }

  function gxZoomBy(sx, sy, factor){
    var before = GX.targetK;
    GX.targetK = Math.max(GX.kFit / 8, Math.min(GX.kFit * 8, before * factor));
    if (GX.targetK < GX.view.k){ GX.zoomSX = 0; GX.zoomSY = 0; }
    else { GX.zoomSX = sx; GX.zoomSY = sy; }
    gxChanged();
  }

  function gxBind(){
    var stage = $('gx-stage'), cv = $('gx-canvas');
    if (!stage || !cv) return;

    /* 滚轮：每 120 单位 1.5 倍；放大以光标为中心，缩小以画布中心为中心 */
    cv.addEventListener('wheel', function(ev){
      ev.preventDefault();
      var mm = $('gx-menu'); if (mm && !mm.hidden) mm.hidden = true;
      var d = ev.deltaY;
      if (ev.deltaMode === 1) d *= 40; else if (ev.deltaMode === 2) d *= 800;
      var r = cv.getBoundingClientRect();
      gxZoomBy(ev.clientX - r.left, ev.clientY - r.top, Math.pow(1.5, -d / 120));
    }, { passive: false });

    cv.addEventListener('mousedown', function(ev){
      if (ev.button !== 0) return;
      var mm = $('gx-menu'); if (mm && !mm.hidden) mm.hidden = true;
      var hit = gxPick(ev);
      var w = gxToWorld(ev);
      GX.drag = { hit: hit, sx: w.sx, sy: w.sy, x: w.x, y: w.y, moved: false, vx0: GX.view.x, vy0: GX.view.y, downX: w.sx, downY: w.sy };
      GX.panvX = 0; GX.panvY = 0;
      GX.lastMove = gxNow();
      if (hit >= 0){
        GX.sel = hit;
        GX.nodes[hit].fx = GX.nodes[hit].x;
        GX.nodes[hit].fy = GX.nodes[hit].y;
        gxReheat(0.75);
        GX.alphaTarget = 0.75;  /* 拖动期间保持能量：邻居才会被"拽"过来 */
      } else {
        GX.pan = { x: w.sx, y: w.sy };
      }
      stage.classList.add('dragging');
      gxChanged();
      ev.preventDefault();
    });

    cv.addEventListener('mousemove', function(ev){
      var w = gxToWorld(ev);
      var d = GX.drag;
      if (d){
        if (!d.moved){
          /* 圆圈判定：欧氏距离一旦超过半径就永久锁定为拖动（不只是"当前超标"） */
          var ddx = w.sx - d.downX, ddy = w.sy - d.downY;
          if (ddx * ddx + ddy * ddy > GX_DRAG_RADIUS * GX_DRAG_RADIUS) d.moved = true;
        }
        if (d.hit >= 0){
          var nn = GX.nodes[d.hit];
          nn.fx = nn.x = w.x; nn.fy = nn.y = w.y;
          nn.vx = 0; nn.vy = 0;
          gxReheat(0.9);
        } else if (d.moved || GX.pan){
          var nx = d.vx0 + (w.sx - d.sx), ny = d.vy0 + (w.sy - d.sy);
          var now = gxNow();
          GX.avgDt = gxLerp(GX.avgDt, now - GX.lastMove, 0.2);
          if (now - GX.lastMove > 0) GX.lastMove = now;
          GX.panvX = gxLerp(GX.panvX, nx - GX.view.x, 0.2);
          GX.panvY = gxLerp(GX.panvY, ny - GX.view.y, 0.2);
          GX.view.x = nx; GX.view.y = ny;
        }
        gxChanged();
        return;
      }
      var hit = gxPick(ev);
      if (hit !== GX.hover){
        GX.hover = hit;
        cv.style.cursor = hit >= 0 ? 'pointer' : 'grab';
        gxTip(hit, ev);
        gxChanged();
      } else if (hit >= 0) gxTip(hit, ev);
    });

    window.addEventListener('mouseup', gxMouseUp);
    cv.addEventListener('mouseleave', function(){
      if (!GX) return;
      GX.hover = -1; GX.mouseSX = null; GX.mouseSY = null;
      var t = $('gx-tip'); if (t) t.classList.remove('on');
      gxChanged();
    });
    /* 单击进入房间卡 / 区域；拖动只负责挪节点，不许顺手把人弹进去。
       GX.drag 在这之后（gxMouseUp）就被清空了，click 事件派发时拿不到它，
       所以判定结果必须提前写进 GX.suppressClick。 */
    cv.addEventListener('click', function(ev){
      if (GX.suppressClick){ GX.suppressClick = false; return; }
      var hit = gxPick(ev);
      if (hit < 0) return;
      GX.sel = hit;
      if (GX.world) openMap(GX.nodes[hit].name);
      else openRoomCard(GX.code, GX.nodes[hit].name);
    });
    /* 双击只处理空白（重排）：命中节点时第一下单击已经进去了，不能再响应 */
    cv.addEventListener('dblclick', function(ev){
      if (gxPick(ev) >= 0) return;
      /* 双击空白：取消所有钉住，让图重新排一次 */
      GX.nodes.forEach(function(n){ n.fx = null; n.fy = null; });
      GX.alpha = 1;
      GX.alphaTarget = 0;
      GX.ticks = 0; GX.speed = 0;
      gxReheat(1);
      gxChanged();
    });
    cv.addEventListener('contextmenu', function(ev){
      ev.preventDefault();
      var hit = gxPick(ev);
      if (hit < 0){ var mm = $('gx-menu'); if (mm) mm.hidden = true; return; }
      gxMenu(hit);
    });

    var bkBtn = $('gx-back');
    if (bkBtn) bkBtn.addEventListener('click', function(){ openMap(GX.code); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-gxview]'), function(b){
      b.addEventListener('click', function(){ gxSetView(b.getAttribute('data-gxview')); });
    });
    var reachSel = $('gx-reach');
    if (reachSel) reachSel.addEventListener('change', function(){
      GX.opts.reachMode = reachSel.value;
      state.graphOpts.reachMode = GX.opts.reachMode;
      state.graphOpts.ver = GX_VER;
      gxSaveGraphOpts();
      if (GX.play.staged) gxRestart();
      gxBuildPlaySeq();
      gxChanged();
    });

    var orb = $('gx-orphan');
    if (orb) orb.addEventListener('change', function(){
      GX.opts.orphan = orb.checked ? 1 : 0;
      state.graphOpts.orphan = GX.opts.orphan;
      state.graphOpts.ver = GX_VER;
      gxSaveGraphOpts();
      if (GX.play.staged) gxRestart();
      gxChanged();
    });

    var playBtn = $('gx-play');
    if (playBtn) playBtn.addEventListener('click', function(){ gxTogglePlay(); });
    var startSel = $('gx-start');
    if (startSel) startSel.addEventListener('change', function(){ gxSetStart(startSel.value, true); });
    var orderSel = $('gx-order');
    if (orderSel) orderSel.addEventListener('change', function(){
      GX.opts.order = orderSel.value; state.graphOpts.order = orderSel.value; gxSaveGraphOpts();
      gxRestart();
    });
    var gapEl = $('gx-gap');
    if (gapEl) gapEl.addEventListener('input', function(){
      GX.opts.gap = parseInt(gapEl.value, 10) || 120;
      state.graphOpts.gap = GX.opts.gap;
      var v = $('gx-gap-v'); if (v) v.textContent = GX.opts.gap + 'ms';
      gxSaveGraphOpts();
    });
    var spdEl = $('gx-speed');
    if (spdEl) spdEl.addEventListener('change', function(){
      GX.opts.speed = parseFloat(spdEl.value) || 1;
      state.graphOpts.speed = GX.opts.speed; gxSaveGraphOpts();
    });
    var setBtn = $('gx-settings');
    if (setBtn) setBtn.addEventListener('click', function(){
      var pn = $('gx-panel');
      pn.hidden = !pn.hidden;
      if (!pn.hidden){ pn.innerHTML = gxSettingsHTML(); gxBindPanel(); }
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-gzoom]'), function(b){
      b.addEventListener('click', function(){
        var act = b.getAttribute('data-gzoom');
        if (act === 'fit'){ GX.targetK = GX.kFit; GX.zoomSX = 0; GX.zoomSY = 0; gxChanged(); return; }
        gxZoomBy(GX.cw / 2, GX.ch / 2, act === 'in' ? 1.5 : 1 / 1.5);
      });
    });
    window.addEventListener('keydown', gxKeyDown);
    window.addEventListener('resize', gxOnResize);
  }

  function gxKeyDown(ev){
    if (!GX) return;
    var tag = (ev.target && ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    var step = ev.shiftKey ? 0.1 : 0.03;
    if (ev.key === '+' || ev.key === '=' ){ GX.targetK *= (1 + step); GX.zoomSX = GX.cw / 2; GX.zoomSY = GX.ch / 2; gxChanged(); ev.preventDefault(); }
    else if (ev.key === '-' || ev.key === '_'){ GX.targetK /= (1 + step); GX.zoomSX = GX.cw / 2; GX.zoomSY = GX.ch / 2; gxChanged(); ev.preventDefault(); }
    else if (ev.key === 'ArrowLeft'){ GX.panvX += 1; gxChanged(); ev.preventDefault(); }
    else if (ev.key === 'ArrowRight'){ GX.panvX -= 1; gxChanged(); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp'){ GX.panvY += 1; gxChanged(); ev.preventDefault(); }
    else if (ev.key === 'ArrowDown'){ GX.panvY -= 1; gxChanged(); ev.preventDefault(); }
  }

  function gxMouseUp(){
    if (!GX) return;
    var d = GX.drag;
    if (d){
      /* 「刚才那一下是拖拽」要传给紧接着派发的 click —— GX.drag 下面就被清空了，
         click 里读不到 moved，这正是老代码 `if (d && d.moved) return` 从未生效的原因。
         mouseup 若落在画布外不会有 click，用 setTimeout 兜底清掉，免得吞掉下一次点击。 */
      GX.suppressClick = !!d.moved;
      if (GX.suppressClick){
        setTimeout(function(){ if (GX) GX.suppressClick = false; }, 0);
      }
      if (d.hit >= 0){
        var nn = GX.nodes[d.hit];
        /* 默认"不固定"：拖动只是临时拽住（fx/fy），一松手就交回给力导向，节点会被拉回原位。
           想要钉住，在「设置 → 显示 → 拖动后固定」里打开。 */
        if (!d.moved || !GX.opts.pin){ nn.fx = null; nn.fy = null; }
        GX.alphaTarget = 0;
        gxReheat(0.9);
        GX.calm = 0;
      } else {
        var dt = gxNow() - GX.lastMove;
        if (dt > 100 || !d.moved){ GX.panvX = 0; GX.panvY = 0; }
        else {
          GX.panvX /= Math.max(1, GX.avgDt);
          GX.panvY /= Math.max(1, GX.avgDt);
        }
        GX.pan = null;
      }
      GX.drag = null;
    }
    var st = $('gx-stage'); if (st) st.classList.remove('dragging');
    gxChanged();
  }

  function gxOnResize(){
    if (!GX) return;
    var oldK = GX.view.k / Math.max(1e-6, GX.kFit);
    gxSize();
    gxFit();
    GX.targetK = GX.kFit * oldK;
    gxChanged();
  }

  function gxTip(i, ev){
    var t = $('gx-tip');
    if (!t) return;
    if (i < 0){ t.classList.remove('on'); return; }
    var n = GX.nodes[i];
    var bits;
    if (GX.world){
      bits = [n.name];
      if (n.zh) bits.push(n.zh);
      if (n.en && n.en !== n.zh) bits.push(n.en);
      bits.push(n.touched ? '有活动' : '未到访');
      if (n.reach === false) bits.push(n.reachNote || '这个角色到不了');
      bits.push((n.rooms || 0) + ' 间 · 到访 ' + (n.seen || 0));
      bits.push(n.deg + ' 条通道');
    } else {
      bits = [n.name, '连接 ' + n.deg];
    }
    if (n.visited) bits.push('已探索');
    if (n.gate) bits.push('业力门');
    if (n.shelter) bits.push('庇护所');
    if (n.sub) bits.push(n.sub);
    t.textContent = bits.join(' · ');
    t.classList.add('on');
    var r = $('gx-canvas').getBoundingClientRect();
    var x = ev.clientX - r.left + 12, y = ev.clientY - r.top + 12;
    t.style.left = Math.min(x, GX.cw - t.offsetWidth - 8) + 'px';
    t.style.top = Math.min(y, GX.ch - t.offsetHeight - 8) + 'px';
  }

  /* 菜单贴着节点放（不是贴着鼠标），并且每帧跟着节点走 */
  function gxPlaceMenu(){
    var m = $('gx-menu');
    if (!m || m.hidden || !GX || GX.menu == null || GX.menu < 0) return;
    var n = GX.nodes[GX.menu];
    if (!n) return;
    var sx = n.x * GX.view.k + GX.view.x;
    var sy = n.y * GX.view.k + GX.view.y;
    var nr = gxNodeSize(n);
    var mw = m.offsetWidth || 170, mh = m.offsetHeight || 130;
    var x = sx + nr + 10;
    if (x + mw > GX.cw - 6) x = sx - nr - 10 - mw;
    var y = sy - mh / 2;
    x = Math.max(6, Math.min(x, GX.cw - mw - 6));
    y = Math.max(6, Math.min(y, GX.ch - mh - 6));
    m.style.left = Math.round(x) + 'px';
    m.style.top = Math.round(y) + 'px';
  }

  function gxMenu(i){
    var m = $('gx-menu');
    if (!m) return;
    m.innerHTML = (GX.world
      ? '<button type="button" data-gxmenu="open">进入这个区域</button>' +
        '<button type="button" data-gxmenu="copy">复制区域代码</button>'
      : '<button type="button" data-gxmenu="open">打开房间布局卡</button>' +
        '<button type="button" data-gxmenu="copy">复制房间号</button>' +
        '<button type="button" data-gxmenu="start">设为起点</button>') +
      (GX.nodes[i].fx != null ? '<button type="button" data-gxmenu="unpin">取消固定</button>' : '');
    GX.menu = i;
    m.hidden = false;
    gxPlaceMenu();
    Array.prototype.forEach.call(m.querySelectorAll('[data-gxmenu]'), function(b){
      b.addEventListener('click', function(){
        var act = b.getAttribute('data-gxmenu');
        var n = GX.nodes[GX.menu];
        m.hidden = true;
        if (act === 'open'){
          if (GX.world) openMap(n.name);
          else openRoomCard(GX.code, n.name);
        }
        else if (act === 'copy'){
          var done = function(){ toast('已复制 ' + n.name); };
          if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(n.name).then(done).catch(function(){});
          else { toast(n.name); }
        } else if (act === 'start'){
          /* 之前只改了 GX.sel / opts.start，没动 startIdx，gxRestart 还是按旧起点重建序列
             —— 表现就是"设为起点没反应"。这里必须显式写 startIdx。 */
          GX.sel = GX.menu;
          GX.opts.start = 'custom';
          var sel = $('gx-start'); if (sel) sel.value = 'custom';
          gxSetStart('custom', true);
          toast('起点：' + n.name);
        } else if (act === 'unpin'){ n.fx = null; n.fy = null; gxReheat(0.9); gxChanged(); }
      });
    });
  }

  function gxBindPanel(){
    var pn = $('gx-panel');
    if (!pn) return;
    Array.prototype.forEach.call(pn.querySelectorAll('.gx-sec-h'), function(b){
      b.addEventListener('click', function(){ b.parentNode.classList.toggle('open'); });
    });
    Array.prototype.forEach.call(pn.querySelectorAll('[data-gxopt]'), function(inp){
      inp.addEventListener('input', function(){
        var key = inp.getAttribute('data-gxopt');
        var val = parseFloat(inp.value);
        GX.opts[key] = val;
        state.graphOpts[key] = val;
        state.graphOpts.ver = GX_VER;
        var out = pn.querySelector('[data-gxval="' + key + '"]');
        if (out) out.textContent = (key === 'settle') ? gxSettleText(val) : val;
        if (key === 'center' || key === 'repel' || key === 'link' || key === 'dist'){
          gxApplyForce();
          gxReheat(0.95);
          GX.alphaTarget = 0;
        }
        if (key === 'settle' || key === 'dragPull'){ gxReheat(0.9); }
        if (key === 'idle' && GX.opts.idle){ gxReheat(0.6); }
        if (key === 'fold'){ /* noop */ }
        gxSaveGraphOpts();
        gxChanged();
      });
      /* 松开滑块时补一次真正的"醒图"（照 Obsidian：alpha 0.3 重新找平衡） */
      inp.addEventListener('change', function(){
        var key = inp.getAttribute('data-gxopt');
        if (key === 'center' || key === 'repel' || key === 'link' || key === 'dist'){
          gxReheat(0.95);
          GX.ticks = 0;
          gxChanged();
        }
      });
    });
    Array.prototype.forEach.call(pn.querySelectorAll('[data-gxflag]'), function(inp){
      inp.addEventListener('change', function(){
        var key = inp.getAttribute('data-gxflag');
        GX.opts[key] = inp.checked ? 1 : 0;
        state.graphOpts[key] = GX.opts[key];
        state.graphOpts.ver = GX_VER;
        /* 关掉"拖动后固定"：把已经钉住的一并放回，不然看不出开关效果 */
        if (key === 'pin' && !GX.opts.pin){
          GX.nodes.forEach(function(n){ n.fx = null; n.fy = null; });
          GX.alpha = Math.max(GX.alpha, 0.25);
        }
        /* 依赖显隐：A（labelCrowd）没勾上时，「名字间距」与「逐个淡出名字」整个收起来 */
        Array.prototype.forEach.call(pn.querySelectorAll('[data-gxdep]'), function(el){
          var dep = el.getAttribute('data-gxdep');
          el.style.display = GX.opts[dep] ? '' : 'none';
        });
        gxSaveGraphOpts();
        GX.alpha = Math.max(GX.alpha, 0.05);
        gxChanged();
      });
    });
    Array.prototype.forEach.call(pn.querySelectorAll('[data-gxcol]'), function(inp){
      inp.addEventListener('input', function(){
        var key = inp.getAttribute('data-gxcol');
        if (key === 'line2') key = 'line';
        var theme = gxThemeName();
        if (!state.graphColors[theme]) state.graphColors[theme] = {};
        state.graphColors[theme][key] = inp.value;
        GX.col = gxColors();
        gxParseColors();
        var lg = $('gx-legend'); if (lg) lg.innerHTML = gxLegendHTML();
        gxSaveColors();
        gxChanged();
      });
    });
    var rst = pn.querySelector('#gx-col-reset');
    if (rst) rst.addEventListener('click', function(){
      var theme = gxThemeName();
      state.graphColors[theme] = {};
      GX.col = gxColors();
      gxParseColors();
      var lg = $('gx-legend'); if (lg) lg.innerHTML = gxLegendHTML();
      pn.innerHTML = gxSettingsHTML(); gxBindPanel();
      gxSaveColors();
      gxChanged();
    });
    var mode = pn.querySelector('#gx-mode');
    if (mode) mode.addEventListener('change', function(){
      GX.opts.mode = mode.value;
      state.graphOpts.mode = mode.value;
      state.graphOpts.ver = GX_VER;
      gxSaveGraphOpts();
      gxRestart();
    });
  }

  /* 已探索 / 未探索 筛选 */
  function gxSetView(v){
    if (!GX) return;
    GX.opts.view = v || 'all';
    state.graphOpts.view = GX.opts.view;
    state.graphOpts.ver = GX_VER;
    Array.prototype.forEach.call(document.querySelectorAll('[data-gxview]'), function(b){
      b.classList.toggle('on', b.getAttribute('data-gxview') === GX.opts.view);
    });
    gxSaveGraphOpts();
    if (GX.play.staged) gxRestart();
    gxChanged();
  }

  /* ---------- 起点 ---------- */
  function gxBest(cand){
    var best = -1, bd = -1;
    cand.forEach(function(i){
      if (GX.nodes[i].deg > bd){ bd = GX.nodes[i].deg; best = i; }
    });
    return best;
  }
  function gxStartIndex(kind){
    var nodes = GX.nodes, all = [], gates = [], shelters = [];
    nodes.forEach(function(n, i){
      if (gxShown(n)) all.push(i);
      if (n.gate) gates.push(i);
      if (n.shelter) shelters.push(i);
    });
    var mode = GX.opts.mode;
    var pool = function(list){ return mode === 'visited' ? list.filter(function(i){ return nodes[i].visited; }) : list; };
    if (kind === 'custom' && GX.sel >= 0 && gxShown(nodes[GX.sel])) return GX.sel;
    if (kind === 'gate'){ var g = gxBest(pool(gates)); if (g >= 0) return g; }
    if (kind === 'shelter'){ var s = gxBest(pool(shelters)); if (s >= 0) return s; }
    if (kind === 'den' && GX.campaign){
      var room = String(GX.campaign.denPos || '').toUpperCase();
      var di = GX.idx[room];
      if (di != null && gxShown(nodes[di])) return di;
      var sh = gxBest(pool(shelters)); if (sh >= 0) return sh;
    }
    var fallback = gxBest(pool(all));
    return fallback >= 0 ? fallback : 0;
  }

  /* 换起点：不把图清空（旧版会 restart，画面瞬间全黑，看起来像"没生效"），
     只是重新算序列 + 把起点那一间高亮出来；真正"从起点开播"还是按播放。 */
  function gxSetStart(kind, rebuild){
    if (!GX) return;
    GX.opts.start = kind || 'gate';
    state.graphOpts.start = GX.opts.start;
    state.graphOpts.ver = GX_VER;
    var idx = gxStartIndex(GX.opts.start);
    GX.startIdx = idx;
    GX.sel = idx;
    if (rebuild){
      var p = GX.play;
      p.on = false; p.staged = false; p.i = -1;
      p.trail = []; p.target = []; p.shown = 0; p.seg = 1;
      GX.nodes.forEach(function(n){ n.base = 1; });
      GX.eAlpha = GX.eAlpha.map(function(){ return 1; });
      var b = $('gx-play'); if (b) b.textContent = '▶ 播放';
      gxBuildPlaySeq();
    }
    gxSaveGraphOpts();
    gxChanged();
  }

  /* ---------- DFS 序列（邻居顺序三档） ---------- */
  function gxNeighborCmp(from){
    var o = GX.opts;
    if (o.order === 'name'){
      return function(a, b){ return GX.nodes[a].name < GX.nodes[b].name ? -1 : 1; };
    }
    if (o.order === 'deg'){
      return function(a, b){ return GX.nodes[b].deg - GX.nodes[a].deg; };
    }
    var p = GX.nodes[from];
    return function(a, b){
      var na = GX.nodes[a], nb = GX.nodes[b];
      var da = (na.x - p.x) * (na.x - p.x) + (na.y - p.y) * (na.y - p.y);
      var db = (nb.x - p.x) * (nb.x - p.x) + (nb.y - p.y) * (nb.y - p.y);
      if (Math.abs(da - db) < 1e-9) return na.name < nb.name ? -1 : 1;
      return da - db;
    };
  }

  function gxBuildSeq(startIdx){
    var nodes = GX.nodes, adj = GX.adj, mode = GX.opts.mode;
    var seenAll = {}, seq = [], seg = 1;
    function allow(i){
      if (!gxShown(nodes[i])) return false;
      if (mode === 'visited') return !!nodes[i].visited;
      return true;
    }
    function run(s){
      if (s == null || s < 0 || seenAll[s] || !allow(s)) return;
      var stack = [s];
      seenAll[s] = 1;
      seq.push({ n: s, trail: [s], seg: seg });
      while (stack.length){
        var v = stack[stack.length - 1];
        var cand = [];
        for (var q = 0; q < adj[v].length; q++){
          var w = adj[v][q];
          if (!seenAll[w] && allow(w)) cand.push(w);
        }
        if (!cand.length){ stack.pop(); continue; }
        cand.sort(gxNeighborCmp(v));
        var pick = cand[0];
        seenAll[pick] = 1;
        stack.push(pick);
        seq.push({ n: pick, trail: stack.slice(), seg: seg });
      }
    }

    if (mode === 'visitedfirst'){
      run(startIdx);
      var restV = nodes.map(function(_, i){ return i; }).filter(function(i){
        return !seenAll[i] && nodes[i].visited && nodes[i].deg > 0 && allow(i);
      });
      var guardV = 0;
      while (restV.length && guardV++ < nodes.length + 5){
        var s2 = gxBest(restV);
        if (s2 < 0) break;
        run(s2);
        restV = nodes.map(function(_, i){ return i; }).filter(function(i){
          return !seenAll[i] && nodes[i].visited && nodes[i].deg > 0 && allow(i);
        });
      }
      seg++;
    }
    run(startIdx);

    /* 注意必须带 allow()：被筛掉/不可达的节点 run() 会直接返回、不标记 seen，
       只按 "!seenAll && deg>0" 过滤会永远剩下它 → 死循环（世界拓扑开可达过滤时必定触发） */
    var rest = nodes.map(function(_, i){ return i; }).filter(function(i){
      return !seenAll[i] && nodes[i].deg > 0 && allow(i);
    });
    var guardR = 0;
    while (rest.length && guardR++ < nodes.length + 5){
      var s = gxBest(rest);
      if (s < 0) break;
      seg++;
      run(s);
      rest = nodes.map(function(_, i){ return i; }).filter(function(i){
        return !seenAll[i] && nodes[i].deg > 0 && allow(i);
      });
    }
    var iso = nodes.map(function(_, i){ return i; }).filter(function(i){
      return !seenAll[i] && gxShown(nodes[i]);
    });
    if (iso.length){
      seg++;
      seq.push({ iso: true, list: iso, seg: seg });
    }
    return { seq: seq, segTotal: Math.max(1, seg) };
  }

  /* 只建序列，不动画面（开图时用） */
  function gxBuildPlaySeq(){
    var built = gxBuildSeq(GX.startIdx);
    var p = GX.play;
    p.seq = built.seq;
    p.segTotal = built.segTotal;
    p.i = -1;
    p.staged = false;
  }

  /* ---------- 播放 ---------- */
  function gxRestart(){
    if (!GX) return;
    gxPause();
    var built = gxBuildSeq(GX.startIdx);
    var p = GX.play;
    p.seq = built.seq;
    p.segTotal = built.segTotal;
    p.i = -1; p.trail = []; p.target = []; p.shown = 0; p.seg = 1;
    p.staged = true;
    GX.nodes.forEach(function(n){ n.base = 0; n.revealed = true; n.alpha = 0; });
    GX.eAlpha = GX.eAlpha.map(function(){ return 0; });
    /* 起点那一间先亮出来：换起点时一眼能看出"从哪开始" */
    GX.sel = GX.startIdx;
    if (GX.nodes[GX.startIdx]) GX.nodes[GX.startIdx].base = 1;
    GX.alpha = Math.min(GX.alpha + 0.2, 1);
    gxChanged();
  }

  /* 回到起点后先亮出第一间，不至于是一片空白 */
  function gxAdvancedOnce(){
    if (!GX) return;
    gxAdvance();
  }

  function gxTogglePlay(){
    if (!GX) return;
    if (GX.play.on) gxPause();
    else gxPlay();
  }

  function gxPlay(){
    if (!GX) return;
    var p = GX.play;
    if (!p.seq.length || p.i >= p.seq.length - 1) gxRestart();
    if (!p.staged){
      /* 从"全量视图"直接开播：先收回，再一间一间长出来 */
      p.staged = true;
      GX.nodes.forEach(function(n){ n.base = 0; n.alpha = 0; });
      GX.eAlpha = GX.eAlpha.map(function(){ return 0; });
      p.i = -1; p.trail = []; p.target = []; p.shown = 0;
    }
    p.on = true;
    var b = $('gx-play'); if (b) b.textContent = '⏸ 暂停';
    gxAdvance();
    gxChanged();
  }

  function gxPause(){
    if (!GX) return;
    GX.play.on = false;
    if (GX.play.timer) clearTimeout(GX.play.timer);
    GX.play.timer = 0;
    var b = $('gx-play'); if (b) b.textContent = '▶ 播放';
  }

  function gxAdvance(){
    if (!GX) return;
    var p = GX.play;
    if (!p.seq.length){ gxBuildPlaySeq(); }
    /* 第一次播放：从"全量视图"切到"逐间出现"，先把已经摊开的都收回去 */
    if (!p.staged && p.i < 0){
      p.staged = true;
      GX.nodes.forEach(function(n){ n.base = 0; n.alpha = 0; n.revealed = true; });
      GX.eAlpha = GX.eAlpha.map(function(){ return 0; });
    }
    var item = p.seq[p.i + 1];
    if (!item){
      /* 播完就停在"全部亮着"的状态。以前这里有个 2s 后自动 gxRestart 的定时器，
         而 restart 会把所有节点 base/alpha 清零又不再推进 —— 表现就是"播完图没了" */
      p.on = false; p.staged = false;
      p.target = []; p.shown = 0;
      var b = $('gx-play'); if (b) b.textContent = '▶ 播放';
      gxChanged();
      return;
    }
    p.i++;
    if (item.iso){
      item.list.forEach(function(i){ gxPopOut(GX.nodes[i]); GX.nodes[i].base = 1; });
      p.target = []; p.shown = 0;
    } else {
      gxPopOut(GX.nodes[item.n]);
      GX.nodes[item.n].base = 1;
      p.trail = item.trail;
      p.target = item.trail;
      p.seg = item.seg;
      GX.sel = item.n;
    }
    gxChanged();
    if (p.on){
      var wait = GX.opts.gap / (GX.opts.speed || 1);
      if (item.iso) wait = 450;
      p.timer = setTimeout(function(){ gxAdvance(false); }, Math.max(16, wait));
    }
  }

  /* 新冒出来的节点不直接落在稳定位置：先在旁边随机偏移一段，交给弹簧和碰撞把它拽回去。
     偏移量取 0.35~0.9 个连线长度，够看得出来，又不至于飞出画面。 */
  function gxPopOut(n){
    if (!n || n.base) return;
    var a = gxRand() * Math.PI * 2, r = 90 + gxRand() * 130;
    n.x += Math.cos(a) * r;
    n.y += Math.sin(a) * r;
    n.vx = 0; n.vy = 0;
    GX.alpha = Math.max(GX.alpha, 0.25);   /* 把物理叫醒，让边真的去拉它 */
    GX.alphaTarget = 0;
  }

  function gxAnimTrail(){
    var p = GX.play;
    var target = p.target.length;
    if (Math.abs(p.shown - target) < 0.05){ p.shown = target; return; }
    p.shown += (target - p.shown) * 0.4;
    if (p.shown < 0.6) p.shown = 0;
  }

  function gxNow(){ return (window.performance && performance.now) ? performance.now() : Date.now(); }


  /* ---------------- 房间布局卡（.txt 地形网格 → canvas） ----------------
     数据来自 core/room_geo.py：cells 是**行优先**字符串，'0'=空气、'1'=实心、'2'..'f'=斜面/局部。
     和区域地图不同，这里要回答的是"哪里能走"，所以不铺底图、不描边，只做平涂。 */
  var roomModal = $('room-modal');
  var rmCode = '', rmRoom = '';
  var rmData = null, rmRuns = null, rmMarks = null, rmToken = 0, rmBound = false;
  /* 右栏读数：check_room 用它断言「清单条数 == 徽章数」。layer 记来源，truncated 记编号是否不全 */
  var rmSide = { rows: 0, layer: null, truncated: false };
  /* P4：右栏第 i 行 → 画布上第 i 个出口格（行优先编号在导入时已排好，i 就是编号）。
     画布画十字用的是「房间文件」，而右栏读的是「生效层」，实测有 76 间房两边出口条数
     不等（模组给房间文件加了格、却没改 world，或反过来）。所以先把「行 → 格子」的对应
     算清楚：优先按坐标匹配十字；条数相同才退化成按序号；都对不上就标 ok=false ——
     那几行悬停时不高亮，绝不画一个悬空的徽章。 */
  var rmExitLinks = [];
  var rmExitTargets = [];   /* 第 i 号出口指向的房间名（预取用；无去向是 null） */
  var rmHoverExit = -1;   /* 当前悬停的出口下标，-1 = 没有 */
  var rmOrder = [], rmIndex = -1;   /* 上一间/下一间：顺序＝地图弹窗当前标签的清单 */
  var rmShowClimb = true;      /* 「可攀爬墙」底色开关：大片底色，能一键关掉 */
  var rmView = { scale: 1, fit: 1, tx: 0, ty: 0, cw: 0, ch: 0, dpr: 1 };

  /* ---------------- 实机视图（V1.2 · M2） ----------------
     矢量图回答「哪里能走」，实机图回答「这间房我有没有印象」。后者由后端
     core/room_render.py 照游戏着色器算出来，前端只负责「发出去 → 回来贴上去」。

     四条铁律：
       1. openRoomCard 里**绝不 await 渲染**，否则开卡时间直接翻几倍；
       2. 位图只能盖住地形，出口十字 / 编号徽章 / 杆子 / 管道永远画在它上面；
       3. 没算完就继续显示矢量——任何时刻都不空屏、不抖动；
       4. 失败只是「少一层」，保留矢量 + 角落里一个感叹号，绝不弹窗。 */
  var rmStyle = 'vector';        /* 与 state.roomCardStyle 同步；drawRoom 读这个 */
  var rmLive = null;             /* {ok, img, w, h, px, ms, cached} | {ok:false} */
  var rmLiveSeq = 0;             /* 每次开卡 +1；回包时代号不符就丢弃（防串图） */
  var rmLiveLayer = null;        /* 当前卡的层 id：现在恒为 null，进缓存键防将来串图 */
  var rmLiveFade = 1;            /* 淡入进度 0..1 */
  var rmLiveCache = {};          /* L1：本次会话已渲过的图 */
  var rmLiveOrder = [];          /* L1 的 LRU 顺序，上限 12 间 */
  var rmLiveBytes = 0;           /* L1 已占的解码内存（w×h×4），按字节兜底 */
  var rmLiveCapable = {};        /* 区域 → 素材在不在（探测一次就够） */
  var RM_LIVE_BYTES_MAX = 48 * 1024 * 1024;   /* 一张 2200×700 ≈ 6 MB，48 MB 约 8 张 */
  var rmPrefetchTimer = 0;       /* 预取延迟计时器（开卡后 300 ms 才动，别抢首屏） */

  /* ---- B 档：放大后按视口裁剪补细节 ----
     整图是按「卡片宽度」取的密度（A 档：1400×dpr），宽房间只有 11–19 px/tile，
     放大到 150% 以上就开始糊。而在放大时，屏幕上真正看得见的只有几十格——
     让后端只渲这一块，同样的带宽就能给到 20 px/tile（素材上限，再高是插值放大）。
     裁块按 tile 坐标叠回去，与整图同位置逐像素一致（后端有断言守着）。 */
  var rmLiveHi = null;           /* {img, px, tx, ty, tw, th}：当前裁块（tile 坐标） */
  var rmLiveHiKey = '';          /* 裁块的身份：房间 + 密度 + 矩形 */
  var rmLiveHiSeq = 0;           /* 裁块请求代号；回包不符就丢（和整图那套一样防串图） */
  var rmLiveHiTimer = 0;         /* 缩放停滞 220 ms 才发请求，拖拽时不许刷屏 */
  var rmLiveHiCache = {};        /* 本次会话的裁块，最多 6 张（平移回原位就秒出） */
  var rmLiveHiOrder = [];
  var rmLiveHiBytes = 0;         /* 裁块解码后的内存，上限 24 MB（与 L1 的 48 MB 分开算） */
  var RM_HI_PX_MAX = 20;         /* 相机 1400×800 覆盖 70×40 tile → 素材上限 20 px/tile */
  var RM_HI_SIDE_MAX = 2048;     /* 单边像素上限：再大传 data URL 就肉疼了 */

  function roomCampaignInfo(code, name){
    var c = currentCampaign();
    var key = String(code).toUpperCase(), nm = String(name).toUpperCase();
    var info = { seen: false, pearl: false, touched: false };
    if (!c) return info;
    (c.regions || []).forEach(function(r){
      if (String(r.name).toUpperCase() !== key) return;
      info.touched = true;
      (r.roomList || []).forEach(function(n){ if (String(n).toUpperCase() === nm) info.seen = true; });
      (r.pearlRooms || []).forEach(function(n){ if (String(n).toUpperCase() === nm) info.pearl = true; });
    });
    return info;
  }

  function roomMetaOf(code, name){
    var rd = regionData(code), nm = String(name).toUpperCase();
    var out = { shelter: false, gate: false, layer: null };
    ((rd && rd.layers) || []).forEach(function(L){
      (L.rooms || []).forEach(function(r){
        if (String(r.name).toUpperCase() !== nm) return;
        if (r.shelter) out.shelter = true;
        if (r.gate) out.gate = true;
        if (r.layer != null && out.layer === null) out.layer = String(r.layer);
      });
    });
    return out;
  }

  /* 生效记录（P4 口径 A，见《出口编号规则》§15.4）：
     所有开启的来源里，order 最高、且**包含这间房**、且这间房**有出口数据**的那条。
     为什么不能只按 order 取最高层：模组补丁层（order 100）经常压根没有这间房，
     直接取会把 SL_C04 这种房间判成「没有出口」。徽章与右侧清单都读它，保证同源。 */
  function effectiveRoom(code, name){
    var rd = regionData(code), nm = String(name).toUpperCase();
    var best = null, bestOrder = -1e9;
    ((rd && rd.layers) || []).forEach(function(L){
      if (L.enabled === false) return;
      var order = (L.order == null ? 0 : Number(L.order));
      (L.rooms || []).forEach(function(r){
        if (String(r.name).toUpperCase() !== nm) return;
        if (!(r.exits && r.exits.length)) return;
        if (order >= bestOrder){
          bestOrder = order;
          best = { room: r, layerId: L.sourceId || L.id,
                   layerName: L.sourceName || L.label || L.id, order: order };
        }
      });
    });
    return best;
  }

  /* 出口落在房间框的哪一边：只给右侧清单补一个「左侧 / 上方」这类提示，不参与编号 */
  function rmExitSide(e, w, h){
    if (!w || !h) return '';
    var cx = (e.x || 0) / w, cy = (e.y || 0) / h;
    if (cx < 0.18) return '左侧';
    if (cx > 0.82) return '右侧';
    if (cy < 0.18) return '上方';
    if (cy > 0.82) return '下方';
    return '';
  }

  /* ---- 出口清单跳转（S2）----
     出口的 `to` 只有房间名，光看前缀推区域会错：`GATE_UW_LC` 这种门房间的实际归属
     要看 world 定义（可能在 LC 也可能在 UW），所以第一次用到时把全部已加载区域的
     房间名建成一张索引，之后 O(1)。区域数据变了（重导 / 删区域）就把索引置空重建。 */
  var rmNameIndex = null;
  var rmFrom = null;      /* 从别的房间跳进来时记一句来源，写进副标题 */

  function rmBuildNameIndex(){
    var idx = {};
    var regions = state.regions || {};
    Object.keys(regions).forEach(function(code){
      var rd = regions[code];
      ((rd && rd.layers) || []).forEach(function(L){
        (L.rooms || []).forEach(function(room){
          var k = String(room.name).toUpperCase();
          if (!idx[k]) idx[k] = code;   /* 同名只记第一个：跨区域重名极少，先到先得 */
        });
      });
    });
    rmNameIndex = idx;
    return idx;
  }

  function rmFindRoom(name){
    var k = String(name == null ? '' : name).trim().toUpperCase();
    if (!k) return null;
    var idx = rmNameIndex || rmBuildNameIndex();
    var code = idx[k];
    return code ? { code: code, name: k } : null;
  }

  /* 点右栏某一行：有去向就跳过去，没去向只提示一句（不静默、也不假跳） */
  function rmFollowExit(i){
    var eff = effectiveRoom(rmCode, rmRoom);
    var ex = (eff && eff.room && eff.room.exits) || [];
    var e = ex[i];
    if (!e) return false;
    var to = e.to || null;
    if (!to){
      toast('第 ' + (i + 1) + ' 号出口没有连接目标（编号不全，或本来就是断开的口）');
      return false;
    }
    var hit = rmFindRoom(to);
    if (!hit){
      toast('目标房间 ' + to + ' 不在已导入的数据里');
      return false;
    }
    openRoomCard(hit.code, hit.name, null, {
      fromName: rmRoom, fromCode: rmCode, exitIndex: i
    });
    return true;
  }

  /* 右栏第 i 行 → 画布上的出口格。十字（房间文件里的 type=4）是画布的唯一依据，
     所以以它为准；换不到的格子标 ok=false，悬停时不高亮、行尾提示一句。 */
  function rmBuildExitLinks(ex){
    var crosses = [];
    if (rmMarks && rmMarks.marks){
      rmMarks.marks.forEach(function(m){
        if (m[2] === 'exit') crosses.push({ x: m[0], y: m[1] });
      });
    }
    var used = [], out = [], i, k, hit;
    var sameCount = crosses.length === ex.length;
    for (i = 0; i < ex.length; i++){
      hit = -1;
      for (k = 0; k < crosses.length; k++){
        if (used[k]) continue;
        if (crosses[k].x === ex[i].x && crosses[k].y === ex[i].y){ hit = k; break; }
      }
      /* 坐标对不上但条数相同：两边都是行优先排过序的，顺序可以信任 */
      if (hit < 0 && sameCount && crosses[i] && !used[i]) hit = i;
      if (hit < 0){ out.push({ x: ex[i].x, y: ex[i].y, ok: false }); continue; }
      used[hit] = true;
      out.push({ x: crosses[hit].x, y: crosses[hit].y, ok: true });
    }
    return out;
  }

  /* 右栏出口清单（B5 骨架 + S2 跳转 + P4 悬停高亮） */
  function renderRoomSide(code, name){
    var box = $('rm-exits'), cnt = $('rm-exit-n'), note = $('rm-exit-note');
    if (!box) return;
    var eff = effectiveRoom(code, name);
    var w = rmData ? rmData.w : 0, h = rmData ? rmData.h : 0;
    if (!eff){
      box.innerHTML = '<div class="rm-side-empty">这间房没有 world 依据（或所有来源都缺连接数据），' +
        '无法标注管道去向。</div>';
      if (cnt) cnt.textContent = '';
      if (note) note.textContent = '';
      rmSide = { rows: 0, layer: null, truncated: false };
      rmExitLinks = [];
      rmExitTargets = [];
      rmHoverExit = -1;
      return;
    }
    var ex = eff.room.exits || [];
    var truncated = eff.room.exitNumbering === 'truncated';
    rmHoverExit = -1;
    rmExitLinks = rmBuildExitLinks(ex);
    rmExitTargets = ex.map(function(e){ return (e && e.to) ? String(e.to) : null; });
    var noCell = 0;
    var html = '';
    for (var i = 0; i < ex.length; i++){
      var to = ex[i].to || null;
      var side = rmExitSide(ex[i], w, h);
      var cellOk = !!(rmExitLinks[i] && rmExitLinks[i].ok);
      if (!cellOk) noCell++;
      html += '<div class="rm-exit-row' + (to ? ' is-link' : ' is-none') +
        (cellOk ? '' : ' is-nocell') + '" data-rmexit="' + i + '"' +
        ' title="第 ' + (i + 1) + ' 号出口' +
          (to ? ' → ' + esc(to) + '（点击过去）' : '（没有连接）') +
          (cellOk ? '（悬停看画布高亮）' : '（本层画布没有对应出口格）') + '"' +
        (to ? ' role="button" tabindex="0"' : '') + '>' +
        '<span class="rm-exit-n">' + (i + 1) + '</span>' +
        '<span class="rm-exit-to">' + (to ? esc(to) : '（未知）') + '</span>' +
        (side ? '<span class="rm-exit-dir">' + side + '</span>' : '') +
        '</div>';
    }
    box.innerHTML = html;
    if (cnt) cnt.textContent = ex.length + ' 个' + (truncated ? ' · 编号不全' : '');
    if (note) note.textContent = (truncated
      ? '出口数与连接数不等：尾部编号没有去向（标「未知」），编号仍按位置保留。'
      : '') +
      (noCell ? '其中 ' + noCell + ' 个出口在本层画布上没有对应格子，悬停不会高亮。' : '') +
      '来源：' + eff.layerName;
    rmSide = { rows: ex.length, layer: eff.layerId, truncated: truncated,
               noCell: noCell };
  }

  /* ---- 上一间 / 下一间 ----
     顺序取自地图弹窗「当前标签」的那份清单（全部 / 未探索 / 已探索），所以卡片里的顺序
     和你在清单里看到的顺序是同一个；不在清单里的房间（比如从地图方块点进来的业力门）就单独成表。 */
  function rmAdoptOrder(code, name){
    var ctx = window.__rwMapCtx;
    rmOrder = (ctx && ctx.code === code && ctx.order && ctx.order.length) ? ctx.order.slice() : [name];
    rmIndex = rmOrder.indexOf(name);
    if (rmIndex < 0){ rmOrder.unshift(name); rmIndex = 0; }
  }
  function rmSetNav(){
    var prev = $('rm-prev'), next = $('rm-next'), pos = $('rm-pos');
    var many = rmOrder.length > 1;
    if (prev) prev.disabled = !many || rmIndex <= 0;
    if (next) next.disabled = !many || rmIndex < 0 || rmIndex >= rmOrder.length - 1;
    if (pos) pos.textContent = many && rmIndex >= 0 ? (rmIndex + 1) + ' / ' + rmOrder.length : '';
  }
  function rmStep(delta){
    var target = rmOrder[rmIndex + delta];
    if (!target) return;                      /* 到头不循环，按钮本身就是 disabled */
    openRoomCard(rmCode, target);
  }

  /* ---- 全屏 / 紧凑（B5）----
     全屏只是给房间卡套一个 .full 类：右栏显隐、画布撑高都由 CSS 负责，JS 不碰布局。
     状态存 config.ui.roomCardFull（已在 core/paths.py 的 DEFAULT_UI 登记，
     否则 save_config 的白名单会把它裁掉、重启就退回紧凑）。 */
  function rmApplyFull(on, silent){
    var card = document.querySelector('#room-modal .room-card');
    if (!card) return;
    on = !!on;
    card.classList.toggle('full', on);
    var btn = $('rm-full');
    if (btn){
      btn.textContent = on ? '紧凑' : '全屏';
      btn.title = on ? '切回紧凑（F）' : '全屏（F）';
      btn.classList.toggle('on', on);
    }
    if (!silent){
      state.roomCardFull = on;
      if (hasBridge()) bridgeCall('save_config', { ui: { roomCardFull: on } }).catch(function(){});
    }
    /* 切回紧凑时右栏整块隐藏，残留的悬停高亮必须一起收掉，否则画布上会留一个没人对应的徽章 */
    if (!on) rmSetHoverExit(-1);
    /* 全屏前后 stage 的高度完全不同，必须重量一次，否则画布还停在旧尺寸 */
    if (rmData) setTimeout(function(){ rmEnsureSize(0); }, 40);
  }

  function openRoomCard(code, name, layerId, from){
    if (!roomModal) return;
    var token = ++rmToken;
    rmCode = code; rmRoom = name;
    /* 换房间就把实机图状态清掉：旧图属于上一间房，留着会先闪一下再被换掉。
       序号 +1 让在途的渲染回包自动作废（它已经在算的那间房用户已经不要了）。 */
    rmLiveLayer = layerId || null;
    rmLiveSeq++;
    rmLive = null;
    rmLiveFade = 1;
    rmHiDrop();                    /* 裁块属于上一间房，一起作废 */
    /* from 只在「从出口清单跳过来」时传；上一间/下一间、地图点选一律清空，
       免得副标题挂着上次的来路 */
    rmFrom = from || null;
    gxRoomMarkUI();
    rmAdoptOrder(code, name);
    rmSetNav();
    rmData = null; rmRuns = null; rmMarks = null;
    $('rm-title').textContent = name || '房间布局';
    $('rm-sub').textContent = '正在读取布局…';
    $('rm-legend').innerHTML = '';
    if ($('rm-exits')) $('rm-exits').innerHTML = '<div class="rm-side-empty">正在读取布局…</div>';
    if ($('rm-exit-n')) $('rm-exit-n').textContent = '';
    if ($('rm-exit-note')) $('rm-exit-note').textContent = '';
    rmSide = { rows: 0, layer: null, truncated: false };
    rmExitLinks = [];
    rmExitTargets = [];
    rmHoverExit = -1;
    roomModal.hidden = false;
    rmApplyFull(state.roomCardFull, true);
    if (!bridgeCall) return;
    bridgeCall('room_geometry', code, name, layerId || null).then(function(res){
      if (token !== rmToken) return;
      if (!res || !res.ok){ roomCardError(res); return; }
      renderRoomCard(code, name, res);
    }).catch(function(err){
      if (token !== rmToken) return;
      roomCardError({ error: 'bridge', detail: String((err && err.message) || err) });
    });
  }

  function closeRoomCard(){
    if (!roomModal) return;
    roomModal.hidden = true;
    if (rmPrefetchTimer){ clearTimeout(rmPrefetchTimer); rmPrefetchTimer = 0; }
    rmData = null; rmRuns = null; rmMarks = null;
    rmHoverExit = -1; rmExitLinks = []; rmExitTargets = [];
  }

  function roomCardError(res){
    var kind = (res && res.error) || 'unknown';
    var known = {
      no_file: '这间房没有布局文件：该来源可能只导入了地图、没有房间数据。',
      missing_dir: '找不到房间目录。区域数据来自别的机器时会这样，重新导入一次区域数据即可。',
      no_region: '这个区域没有导入数据。',
      bridge: '需要在桌面版里运行才能读取房间布局。'
    };
    var msg = known[kind] || ('布局解析失败：' + ((res && res.detail) || kind));
    $('rm-sub').textContent = '无法显示';
    $('rm-legend').innerHTML = '<div class="rm-empty">' + esc(msg) + '</div>';
    var cv = $('rm-canvas'), ctx = cv && cv.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, cv.width, cv.height);
  }

  function buildRoomRuns(res){
    var w = res.w, h = res.h, cells = res.cells;
    var air = [], solid = [], slope = [];
    for (var y = 0; y < h; y++){
      var row = y * w, x = 0;
      while (x < w){
        var v = cells.charAt(row + x), n = 1;
        while (x + n < w && cells.charAt(row + x + n) === v) n++;
        (v === '0' ? air : (v === '1' ? solid : slope)).push({ y: y, x: x, n: n });
        x += n;
      }
    }
    return { air: air, solid: solid, slope: slope };
  }

  /* 把解析层给的结构整理成可直接绘制的东西。编号语义见《房间几何渲染规范》：
       1/2 杆子      → 同列/同行连续的格子合并成线段（不合并会断成一截截）
       3  管道路线   → 含 6 的格子画管道口(T)，其余画路线点
       4/5/9 十字    → 出口 / 巢穴 / 生物通道
       6  可攀爬墙   → 底色（解析层已经滤掉非空气格与被占用格） */
  function buildRoomMarks(res){
    var vert = {}, horz = {}, list, i, o;
    for (i = 0; i < res.objects.length; i++){
      o = res.objects[i];
      if (o[2] === 1){ (vert[o[0]] = vert[o[0]] || []).push(o[1]); }
      else if (o[2] === 2){ (horz[o[1]] = horz[o[1]] || []).push(o[0]); }
    }
    function toRuns(map){
      var out = [];
      Object.keys(map).forEach(function(key){
        list = map[key].sort(function(a, b){ return a - b; });
        var from = list[0], prev = list[0], j;
        for (j = 1; j < list.length; j++){
          if (list[j] === prev + 1){ prev = list[j]; continue; }
          out.push({ k: +key, from: from, len: prev - from + 1 });
          from = prev = list[j];
        }
        out.push({ k: +key, from: from, len: prev - from + 1 });
      });
      return out;
    }
    var pipes = res.pipes || {};
    return {
      v: toRuns(vert),
      h: toRuns(horz),
      ports: pipes.ports || [],
      dots: pipes.dots || [],
      marks: res.marks || [],
      climb: res.climb || []
    };
  }

  function renderRoomCard(code, name, res){
    rmData = res;
    var info = roomCampaignInfo(code, name);
    var meta = roomMetaOf(code, name);
    var bits = [res.w + '×' + res.h + ' 格'];
    if (res.border) bits.push('边界 ' + res.border);
    if (res.cameras > 1) bits.push(res.cameras + ' 屏');
    if (meta.layer !== null) bits.push('第 ' + meta.layer + ' 层');
    bits.push(info.seen ? '已探索' : '未探索');
    if (meta.shelter) bits.push('庇护所');
    if (meta.gate) bits.push('业力门');
    if (info.pearl) bits.push('有珍珠');
    if (rmFrom && rmFrom.fromName){
      bits.push('← 来自 ' + rmFrom.fromName + ' 的 ' + (rmFrom.exitIndex + 1) + ' 号出口');
    }
    $('rm-sub').textContent = bits.join(' · ');
    $('rm-sub').title = $('rm-sub').textContent;   /* 头部单行省略，超长时悬停看全文 */

    var cells = res.cells, air = 0, solid = 0, slope = 0;
    for (var i = 0; i < cells.length; i++){
      var ch = cells.charAt(i);
      if (ch === '0') air++; else if (ch === '1') solid++; else slope++;
    }

    rmRuns = buildRoomRuns(res);
    rmMarks = buildRoomMarks(res);

    var beamCount = rmMarks.v.length + rmMarks.h.length;
    var portCount = rmMarks.ports.length;
    var dotCount = rmMarks.dots.length;
    var climbCount = rmMarks.climb.length;
    var byKind = { exit: 0, den: 0, creature: 0 };
    rmMarks.marks.forEach(function(m){ byKind[m[2]] = (byKind[m[2]] || 0) + 1; });

    $('rm-legend').innerHTML =
      '<span><i style="background:var(--rm-solid)"></i>实心 ' + solid + '</span>' +
      '<span><i style="background:var(--rm-air)"></i>空气 ' + air + '</span>' +
      (slope ? '<span><i style="background:var(--rm-slope)"></i>斜面 ' + slope + '</span>' : '') +
      (climbCount ? '<span><i style="background:var(--rm-climb)"></i>可攀爬墙 ' + climbCount + '</span>' : '') +
      (beamCount ? '<span><i class="rm-lg-beam"></i>杆子 ' + beamCount + ' 段</span>' : '') +
      (portCount ? '<span><i class="rm-lg-port"></i>管道口 ' + portCount + '</span>' : '') +
      (dotCount ? '<span><i class="rm-lg-pipe"></i>管道 ' + dotCount + '</span>' : '') +
      (byKind.exit ? '<span style="color:var(--rm-exit)"><i class="rm-lg-cross"></i>出口 ' + byKind.exit + '</span>' : '') +
      (byKind.den ? '<span style="color:var(--rm-den)"><i class="rm-lg-cross"></i>巢穴 ' + byKind.den + '</span>' : '') +
      (byKind.creature ? '<span style="color:var(--rm-creature)"><i class="rm-lg-cross"></i>生物通道 ' + byKind.creature + '</span>' : '') +
      (climbCount ? '<button class="rm-toggle' + (rmShowClimb ? ' on' : '') +
        '" type="button" id="rm-climb-toggle" title="显示 / 隐藏可攀爬墙底色">底色</button>' : '') +
      '<span class="rm-hint">滚轮缩放 · 按住拖动 · 双击复位</span>';

    var climbBtn = $('rm-climb-toggle');
    if (climbBtn){
      climbBtn.addEventListener('click', function(){
        rmShowClimb = !rmShowClimb;
        climbBtn.classList.toggle('on', rmShowClimb);
        drawRoom();
      });
    }

    renderRoomSide(code, name);
    bindRoomCardOnce();
    /* 实机视图：先问「这套素材渲不渲得出来」（几次 isfile，很便宜），
       再决定要不要真的去算。注意这里**没有 await**——rmMaybeRender 发出去就返回，
       开卡时间与有没有实机图完全无关。 */
    rmStylePaint();
    rmProbeStyle();
    if (rmStyle === 'live') rmMaybeRender();
    else rmFlag('', '');
    rmSchedulePrefetch();
    rmEnsureSize(0);
    /* 弹窗刚取消 hidden 时，元素尺寸可能还没算出来（clientWidth = 0），
       下一帧再量一次；仍然为 0 就按 30ms 轮询几轮。 */
    if (window.requestAnimationFrame) requestAnimationFrame(function(){
      if (rmData) rmEnsureSize(0);
    });
  }

  function rmEnsureSize(tries){
    var st = $('rm-stage');
    if (!st || !rmData) return;
    if (st.clientWidth <= 1 || st.clientHeight <= 1){
      if (tries < 10) setTimeout(function(){ rmEnsureSize(tries + 1); }, 30);
      return;
    }
    sizeRoomCanvas();
    resetRoomView();
  }

  function sizeRoomCanvas(){
    var st = $('rm-stage'), cv = $('rm-canvas');
    if (!st || !cv) return;
    var dpr = window.devicePixelRatio || 1;
    var w = Math.max(80, st.clientWidth), h = Math.max(80, st.clientHeight);
    rmView.cw = w; rmView.ch = h; rmView.dpr = dpr;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
  }

  /* 统一用「格」作为绘图单位：scale = 每格多少个 CSS 像素，tx/ty 也是像素。 */
  function resetRoomView(){
    if (!rmData) return;
    var px = rmData.w, py = rmData.h;
    var fit = Math.min(rmView.cw / px, rmView.ch / py);
    rmView.fit = fit;
    rmView.scale = fit;
    rmView.tx = (rmView.cw - px * fit) / 2;
    rmView.ty = (rmView.ch - py * fit) / 2;
    drawRoom();
    rmHiSchedule();          /* 窗口尺寸变了 = 需要的密度也变了 */
  }

  function updateRoomPct(){
    var el = $('rm-zoom-pct');
    if (el && rmView.fit > 0) el.textContent = Math.round(rmView.scale / rmView.fit * 100) + '%';
  }

  function clampRoomPan(){
    if (!rmData) return;
    var px = rmData.w * rmView.scale;
    var py = rmData.h * rmView.scale;
    var m = 48;
    rmView.tx = px <= rmView.cw ? (rmView.cw - px) / 2
      : Math.min(m, Math.max(rmView.cw - px - m, rmView.tx));
    rmView.ty = py <= rmView.ch ? (rmView.ch - py) / 2
      : Math.min(m, Math.max(rmView.ch - py - m, rmView.ty));
  }

  /* ---- 实机视图：请求 / 缓存 / 淡入（没有任何一处 await，全是回调） ---- */

  function rmSlugcat(){ return (currentCampaign() || {}).slugcat || ''; }

  /* 缓存键必须带角色：`<room>_settings-<角色>.txt` 会换 Palette，
     圣徒眼里的 cc_a02 和幸存者眼里的不是一张图（计划书 §4.9）。 */
  /* 位图密度按**设备像素**算，不是 CSS 像素。
     卡片宽度的上限（1400）是 CSS 像素，但画布 backing store 乘了 dpr，所以 dpr=1.5
     时真正需要的是 2100 设备像素。以前只按 CSS 算，宽房间被压到 13 / 7 px/tile，
     放大就糊（计划书 §18 A 档）。渲染端本来就有 20 px/tile 的上限，所以窄房间不会
     因此变大。 */
  function rmLiveFit(){
    return Math.round(1400 * (window.devicePixelRatio || 1));
  }

  function rmLiveKey(code, room){
    /* fit 进键：把窗口拖到另一块 dpr 不同的屏幕上时，旧位图不该被当成命中 */
    return [code, room, rmLiveLayer || '', rmSlugcat(), rmLiveFit()].join('|');
  }

  function rmLiveRemember(key, rec){
    /* 按字节算账而不只是按张数：密度一提上来，一张 2200×700 解码后就是 6 MB，
       12 张能吃掉 70 MB。两个上限取严的那个。 */
    rec.bytes = (rec.w || 0) * (rec.h || 0) * 4;
    var old = rmLiveCache[key];
    if (old && old.bytes) rmLiveBytes -= old.bytes;
    rmLiveCache[key] = rec;
    rmLiveBytes += rec.bytes;
    var i = rmLiveOrder.indexOf(key);
    if (i >= 0) rmLiveOrder.splice(i, 1);
    rmLiveOrder.push(key);
    while (rmLiveOrder.length > 12 || (rmLiveBytes > RM_LIVE_BYTES_MAX && rmLiveOrder.length > 1)){
      var dead = rmLiveOrder.shift();
      var gone = rmLiveCache[dead];
      if (gone && gone.bytes) rmLiveBytes -= gone.bytes;
      delete rmLiveCache[dead];
    }
  }

  /* ---------------- B 档：视口裁块 ---------------- */

  /* 屏幕当前需要多少 px/tile。`rmView.scale` 是 CSS px/tile，乘 dpr 才是设备像素。 */
  function rmHiWantPx(){
    var need = Math.round(rmView.scale * (rmView.dpr || 1));
    if (need < 4) need = 4;
    return Math.min(RM_HI_PX_MAX, need);
  }

  /* 裁块范围：视口覆盖的 tile 矩形，四周各留 4 格余量（平移几格不用重渲）。 */
  function rmHiRect(px){
    if (!rmData) return null;
    var s = rmView.scale;
    if (!(s > 0)) return null;
    var pad = 4;
    var tx0 = Math.floor((0 - rmView.tx) / s) - pad;
    var ty0 = Math.floor((0 - rmView.ty) / s) - pad;
    var tx1 = Math.ceil((rmView.cw - rmView.tx) / s) + pad;
    var ty1 = Math.ceil((rmView.ch - rmView.ty) / s) + pad;
    tx0 = Math.max(0, tx0); ty0 = Math.max(0, ty0);
    tx1 = Math.min(rmData.w, tx1); ty1 = Math.min(rmData.h, ty1);
    if (tx1 - tx0 < 2 || ty1 - ty0 < 2) return null;
    return [tx0, ty0, tx1, ty1];
  }

  function rmHiCapRect(rect, px){
    /* 单边超过 RM_HI_SIDE_MAX 就先降密度：带宽比清晰度更先撑不住 */
    var w = (rect[2] - rect[0]) * px, h = (rect[3] - rect[1]) * px;
    var over = Math.max(w / RM_HI_SIDE_MAX, h / RM_HI_SIDE_MAX, 1);
    if (over > 1.0001) px = Math.max(4, Math.floor(px / over));
    return px;
  }

  function rmHiDrop(){
    if (rmLiveHiTimer){ clearTimeout(rmLiveHiTimer); rmLiveHiTimer = 0; }
    rmLiveHiSeq++;
    rmLiveHi = null;
    rmLiveHiKey = '';
    rmLiveHiCache = {};
    rmLiveHiOrder = [];
    rmLiveHiBytes = 0;
  }

  function rmHiRequest(){
    if (rmStyle !== 'live' || !rmData || !rmLive || !rmLive.ok || !rmLive.img) return;
    if (!hasBridge()) return;
    var px = rmHiWantPx();
    var full = rmLive.px || 20;
    if (px <= full + 0.5) return;                     /* 整图已经够密，白渲 */
    var rect = rmHiRect(px);
    if (!rect) return;
    /* 裁块超过整间的 80% 就别裁了：省不下多少，还会和整图差一份缓存 */
    var area = (rect[2] - rect[0]) * (rect[3] - rect[1]);
    if (area >= rmData.w * rmData.h * 0.8) return;
    px = rmHiCapRect(rect, px);
    if (px <= full + 0.5) return;

    var key = [rmCode, rmRoom, rmLiveLayer || '', rmSlugcat(), px,
               rect[0], rect[1], rect[2], rect[3]].join('|');
    if (key === rmLiveHiKey) return;
    var hit = rmLiveHiCache[key];
    if (hit){ rmLiveHi = hit; rmLiveHiKey = key; drawRoom(); return; }

    var seq = ++rmLiveHiSeq;
    var code = rmCode, room = rmRoom;
    bridgeCall('room_render', code, room, rmLiveLayer, rmSlugcat(), 0,
               [rect[0], rect[1], rect[2], rect[3]], px).then(function(res){
      if (seq !== rmLiveHiSeq || code !== rmCode || room !== rmRoom) return;
      if (!res || !res.ok || !res.dataUrl) return;     /* 失败就继续用整图，不吭声 */
      var img = new Image();
      img.onload = function(){
        if (seq !== rmLiveHiSeq || code !== rmCode || room !== rmRoom) return;
        var cp = res.crop || rect;
        var rec = { img: img, px: res.pxPerTile || px,
                    tx: cp[0], ty: cp[1], tw: cp[2] - cp[0], th: cp[3] - cp[1] };
        rec.bytes = (res.width || 0) * (res.height || 0) * 4;
        rmLiveHiCache[key] = rec;
        rmLiveHiBytes += rec.bytes;
        rmLiveHiOrder.push(key);
        while (rmLiveHiOrder.length > 6
               || (rmLiveHiBytes > 24 * 1024 * 1024 && rmLiveHiOrder.length > 1)){
          var goneKey = rmLiveHiOrder.shift();
          var goneRec = rmLiveHiCache[goneKey];
          if (goneRec && goneRec.bytes) rmLiveHiBytes -= goneRec.bytes;
          delete rmLiveHiCache[goneKey];
        }
        rmLiveHi = rec;
        rmLiveHiKey = key;
        drawRoom();
      };
      img.src = res.dataUrl;
    }).catch(function(){});
  }

  function rmHiSchedule(){
    if (rmLiveHiTimer) clearTimeout(rmLiveHiTimer);
    rmLiveHiTimer = setTimeout(function(){ rmLiveHiTimer = 0; rmHiRequest(); }, 220);
  }

  /* 预取：开卡后 300 ms，把右栏那几个出口指向的房间排进后台队列。
     用户在真正点击之前什么都不用等——队列由后端 worker 消费，我们不等它的结果。
     依据：一间房平均 2.44 个出口，取前 3 个就能覆盖绝大多数跳转。 */
  function rmSchedulePrefetch(){
    if (rmPrefetchTimer) { clearTimeout(rmPrefetchTimer); rmPrefetchTimer = 0; }
    if (rmStyle !== 'live' || !hasBridge()) return;
    var targets = [];
    for (var i = 0; i < rmExitTargets.length && targets.length < 3; i++){
      var t = rmExitTargets[i];
      if (t && targets.indexOf(t) < 0) targets.push(t);
    }
    if (!targets.length) return;
    var code = rmCode, token = rmToken, layer = rmLiveLayer, slug = rmSlugcat();
    rmPrefetchTimer = setTimeout(function(){
      rmPrefetchTimer = 0;
      if (token !== rmToken || code !== rmCode) return;   /* 用户已经切走，别再排队 */
      bridgeCall('room_prefetch', code, targets, layer, slug, rmLiveFit()).catch(function(){});
    }, 300);
  }

  function rmFlag(kind, html){
    var el = $('rm-live-flag');
    if (!el) return;
    el.className = 'rm-live-flag' + (kind ? ' on' : '') + (kind === 'err' ? ' err' : '');
    el.innerHTML = html || '';
    if (kind !== 'err') el.title = '';
  }

  /* 错误码 → 人话。后端只保证「码」稳定，句子留在这里：改文案不用动 Python，
     用户也不会看到 `RenderError: ...` 这种英文串。每条 = [角标短句, 悬停解释]。 */
  var RM_ERR_TEXT = {
    no_texture:      ['没有地形纹理', '这间房缺地形图（_1.png）。多半是模组没带图，或游戏文件不完整；\n与存档内容无关，房间卡的其他信息照常可用。'],
    missing_dir:     ['找不到房间目录', '这个区域记下的房间目录不在本机了（换机器、卸了模组或挪过目录）。\n重新导入一次区域数据即可恢复。'],
    no_file:         ['找不到房间文件', '这间房的 .txt 不在当前来源里。可能是这个来源被关掉了，\n或该房间属于另一个来源。'],
    no_region:       ['区域数据未导入', '还没有这个区域的数据，先去「区域数据」导入一次。'],
    no_palette:      ['缺调色板', '这个区域的 palettes/palette*.png 找不到，渲不出颜色。\n模组通常自己带一张，缺的话只能是模组素材不全。'],
    bad_texture:     ['地形图格式异常', '地形纹理的通道数或尺寸不对，文件可能已损坏。'],
    bad_png:         ['素材文件损坏', '解码 PNG 失败，文件可能不完整。'],
    unsupported_png: ['素材格式不支持', '这张 PNG 的色彩类型目前解不了（例如带交错的位深变体）。'],
    io:              ['素材读不出来', '读文件时出错：文件被占用、权限不足，或磁盘有问题。'],
    unparsable:      ['房间文件解析失败', '房间 .txt 的结构不完整，可能文件被截断。'],
    render_failed:   ['渲染出错', '渲染过程中抛了异常，细节见下方。'],
    aborted:         ['已取消', '这次渲染被更新的请求打断；正常情况下会立刻重来，不用管。'],
    bad_room:        ['房间名为空', '没有拿到房间名。']
  };

  function rmErrText(res, err){
    var code = String((res && res.error) || '');
    var detail = String((res && res.detail) || '');
    if (err) detail = detail || String((err && err.message) || err);
    var hit = RM_ERR_TEXT[code];
    if (!hit){
      return ['实机图不可用', (code ? '错误码：' + code : '没有拿到错误码') + (detail ? '\n' + detail : '')];
    }
    return [hit[0], hit[1] + (detail ? '\n\n技术细节：' + detail : '')];
  }

  /* 把「降级成感叹号」收在一处：角标只放短句，长解释挂 title，不弹窗、不空屏。 */
  function rmFail(res, err){
    rmLive = { ok: false };
    var t = rmErrText(res, err);
    rmFlag('err', '<b>!</b> ' + esc(t[0]));
    var el = $('rm-live-flag');
    if (el) el.title = t[1];
    drawRoom();
  }

  function rmStylePaint(){
    var box = $('rm-style');
    if (!box) return;
    [].slice.call(box.querySelectorAll('button')).forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-rmstyle') === rmStyle);
    });
  }

  function rmStyleSet(next, silent){
    rmStyle = (next === 'live') ? 'live' : 'vector';
    state.roomCardStyle = rmStyle;
    rmStylePaint();
    if (!silent && hasBridge()){
      bridgeCall('save_config', { ui: { roomCardStyle: rmStyle } }).catch(function(){});
    }
    if (rmStyle === 'live'){
      rmMaybeRender();
      rmSchedulePrefetch();
    }
    else { rmHiDrop(); rmFlag('', ''); drawRoom(); }
  }

  /* 开关出不出现只看一件事：素材根里有没有调色板。没有就整体隐藏（不是禁用）——
     一个永远算不出图的开关，比没有这个开关更让人困惑。 */
  function rmProbeStyle(){
    var box = $('rm-style');
    if (!box) return;
    if (!hasBridge()){ box.hidden = true; return; }
    var code = rmCode;
    if (rmLiveCapable[code] === true){ box.hidden = false; return; }
    if (rmLiveCapable[code] === false){ box.hidden = true; return; }
    box.hidden = true;        /* 探测回来之前不露头，免得闪一下又消失 */
    bridgeCall('room_render_info', code).then(function(res){
      var ok = !!(res && res.ok && res.available);
      rmLiveCapable[code] = ok;
      if (rmCode !== code) return;
      var el = $('rm-style');
      if (el) el.hidden = !ok;
      /* 探测说不可用、但配置里选的是实机：悄悄退回矢量，别停在永远出不来图的视图 */
      if (!ok && rmStyle === 'live') rmStyleSet('vector', true);
    }).catch(function(){
      rmLiveCapable[code] = false;
      var el = $('rm-style');
      if (el) el.hidden = true;
    });
  }

  function rmFadeIn(){
    var raf = window.requestAnimationFrame;
    if (!raf){ rmLiveFade = 1; drawRoom(); return; }
    var t0 = (window.performance && performance.now) ? performance.now() : Date.now();
    rmLiveFade = 0;
    function step(){
      var now = (window.performance && performance.now) ? performance.now() : Date.now();
      rmLiveFade = Math.min(1, (now - t0) / 120);
      drawRoom();
      if (rmLiveFade < 1) raf(step);
    }
    raf(step);
  }

  function rmMaybeRender(){
    if (rmStyle !== 'live' || !rmData || !hasBridge()) return;
    var code = rmCode, room = rmRoom, seq = rmLiveSeq;
    var key = rmLiveKey(code, room);

    var hit = rmLiveCache[key];
    if (hit && hit.ok){
      rmLive = hit; rmLiveFade = 1;
      rmFlag('', '');
      drawRoom();
      rmHiSchedule();          /* 缓存命中也可能要补裁块（用户已经放大着看） */
      return;
    }

    rmLive = null;            /* 先退回矢量，任何时刻都不空屏 */
    rmFlag('on', '渲染中…');
    drawRoom();

    /* 宽度上限按设备像素算（见 rmLiveFit）：卡片最宽 1000 CSS px 出头，但有 dpr 在 */
    bridgeCall('room_render', code, room, rmLiveLayer, rmSlugcat(), rmLiveFit()).then(function(res){
      if (seq !== rmLiveSeq || code !== rmCode || room !== rmRoom) return;
      if (res && res.error === 'superseded') return;   /* 被更新的请求挤掉，那个会补上 */
      if (!res || !res.ok || !res.dataUrl){
        rmFail(res);
        return;
      }
      var img = new Image();
      img.onload = function(){
        if (seq !== rmLiveSeq || code !== rmCode) return;
        var rec = { ok: true, img: img, w: res.width, h: res.height,
                    px: res.pxPerTile || 20, ms: res.ms || 0,
                    src: res.source || '', cached: !!res.cached };
        rmLiveRemember(key, rec);
        rmLive = rec;
        rmFlag('', '');
        rmFadeIn();
        rmHiSchedule();        /* 整图到货后再看要不要补高密度裁块 */
      };
      img.onerror = function(){
        if (seq !== rmLiveSeq || code !== rmCode) return;
        rmFlag('err', '<b>!</b> 实机图解不开');
        var el = $('rm-live-flag');
        if (el) el.title = '后端出图成功，但浏览器解不开这张 PNG（数据在传输中被截断？）。\n' +
          '可以重开一次房间试试；反复出现请把 room_render 的日志留下。';
        rmLive = { ok: false };
        drawRoom();
      };
      img.src = res.dataUrl;
    }).catch(function(err){
      if (seq !== rmLiveSeq || code !== rmCode) return;
      rmFail(null, err);
    });
  }

  function drawRoom(){
    var cv = $('rm-canvas'), ctx = cv && cv.getContext('2d');
    if (!ctx || !rmData || !rmRuns) return;
    var cs = window.getComputedStyle($('rm-stage'));
    var air = (cs.getPropertyValue('--rm-air') || '').trim() || '#0d1219';
    var solidC = (cs.getPropertyValue('--rm-solid') || '').trim() || '#8ea4bd';
    var slopeC = (cs.getPropertyValue('--rm-slope') || '').trim() || '#4f6580';
    var gridC = (cs.getPropertyValue('--rm-grid') || '').trim() || 'rgba(255,255,255,.07)';
    var dpr = rmView.dpr, s = rmView.scale;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    /* 房间外＝实心色：编辑器里背景与岩体是同一个灰，房间形状全靠"空气那块亮"反衬出来 */
    ctx.fillStyle = solidC;
    ctx.fillRect(0, 0, rmView.cw, rmView.ch);

    /* 矢量地形先画：它很便宜（几百次 fillRect），而且在实机图淡入的那 120 ms 里
       它就是底色——先清空再淡入会闪一下实心色，看起来像房间跳了一下。 */
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * rmView.tx, dpr * rmView.ty);
    ctx.fillStyle = air;
    rmRuns.air.forEach(function(r){ ctx.fillRect(r.x, r.y, r.n, 1.02); });
    if (rmRuns.slope.length){
      ctx.fillStyle = slopeC;
      rmRuns.slope.forEach(function(r){ ctx.fillRect(r.x, r.y, r.n, 1.02); });
    }
    /* 实心格子不用画——画布底已经是实心色 */

    /* 可攀爬背景墙：只在"空的格子"上换底色（比空气暗一档，表示这面墙能爬）。
       解析层已经把实心格、以及被管道/十字占用的格子滤掉了。 */
    if (rmShowClimb && rmMarks && rmMarks.climb.length){
      ctx.fillStyle = (cs.getPropertyValue('--rm-climb') || '').trim() || '#1e2a38';
      rmMarks.climb.forEach(function(p){ ctx.fillRect(p[0], p[1], 1.02, 1.02); });
    }

    /* 实机图压在矢量层上：位图自带天空填色、是不透明的，盖住就完事。
       尺寸就是 w×h tile（1 px = 1 tile 再乘密度），在 tile 空间里正好铺满
       0..w / 0..h，所以一个坐标换算都不用做，缩放平移自动跟随。
       插值开关有个反直觉的地方：放大时必须关（像素美术一插值就糊），
       缩小时要开（否则满屏锯齿）——判据就是「当前是不是比源图更稀」。 */
    var live = (rmStyle === 'live' && rmLive && rmLive.ok && rmLive.img) ? rmLive : null;
    if (live){
      ctx.imageSmoothingEnabled = s < (live.px || 20);
      ctx.globalAlpha = rmLiveFade;
      ctx.drawImage(live.img, 0, 0, rmData.w, rmData.h);
      ctx.globalAlpha = 1;
      ctx.imageSmoothingEnabled = true;
    }
    /* 放大后的高密度裁块压在整图上：它只盖住自己那几格，其余地方仍是整图。
       两者同位置逐像素一致（后端断言守着），所以看得见的只有「变清楚了」。 */
    if (live && rmLiveHi && rmLiveHi.img && rmLiveFade >= 1){
      ctx.imageSmoothingEnabled = s < rmLiveHi.px;
      ctx.drawImage(rmLiveHi.img, rmLiveHi.tx, rmLiveHi.ty, rmLiveHi.tw, rmLiveHi.th);
      ctx.imageSmoothingEnabled = true;
    }

    /* 一格的边长 ≥ 9px 才画网格，否则会糊成一片灰。
       实机视图下不画：那层格线是给"量格子"用的，盖在渲染图上只会像一层脏网。 */
    if (s >= 9 && !live){
      var w = rmData.w, h = rmData.h, x, y;
      ctx.strokeStyle = gridC;
      ctx.lineWidth = 1.2 / s;
      ctx.beginPath();
      for (x = 0; x <= w; x++){ ctx.moveTo(x, 0); ctx.lineTo(x, h); }
      for (y = 0; y <= h; y++){ ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();
    }

    var pipeC = (cs.getPropertyValue('--rm-pipe') || '').trim() || '#7d8896';

    /* 管道路线：每格一个方块，连续几格看起来就是虚线 */
    if (rmMarks && rmMarks.dots.length){
      var DOT = 0.29;
      ctx.fillStyle = pipeC;
      rmMarks.dots.forEach(function(p){
        ctx.fillRect(p[0] + (1 - DOT) / 2, p[1] + (1 - DOT) / 2, DOT, DOT);
      });
    }

    /* 管道口：T 形，横条贴「外缘」、竖条朝同段管道内部 */
    if (rmMarks && rmMarks.ports.length){
      ctx.fillStyle = pipeC;
      rmMarks.ports.forEach(function(p){
        var rr = portRects(p[0], p[1], p[2], p[3]);
        ctx.fillRect(rr[0][0], rr[0][1], rr[0][2], rr[0][3]);
        ctx.fillRect(rr[1][0], rr[1][1], rr[1][2], rr[1][3]);
      });
    }

    /* 十字：出口 / 巢穴 / 生物通道。同一个 path 只 fill 一次，
       两个矩形重叠处不会叠出深色；同一类颜色合并成一次 fill，快得多。
       P4：悬停右栏某行时，出口这一类的其余十字压暗到 0.28，被悬停的那个不画
       （由屏幕空间的高亮环 + 数字接手），这样缩得再小也能一眼看出是哪一个。 */
    if (rmMarks && rmMarks.marks.length){
      var ARM = 0.9, TH = 0.32;
      var markC = {
        exit: (cs.getPropertyValue('--rm-exit') || '').trim() || '#3ae03a',
        den: (cs.getPropertyValue('--rm-den') || '').trim() || '#ee3b3b',
        creature: (cs.getPropertyValue('--rm-creature') || '').trim() || '#4d5cff'
      };
      var hot = (rmHoverExit >= 0) ? rmExitLinks[rmHoverExit] : null;
      ['exit', 'den', 'creature'].forEach(function(kind){
        var list = rmMarks.marks.filter(function(m){ return m[2] === kind; });
        if (!list.length) return;
        var dim = (kind === 'exit' && hot && hot.ok);
        if (dim){
          list = list.filter(function(m){ return !(m[0] === hot.x && m[1] === hot.y); });
          if (!list.length) return;
        }
        ctx.save();
        if (dim) ctx.globalAlpha = 0.28;
        ctx.fillStyle = markC[kind];
        ctx.beginPath();
        list.forEach(function(m){
          var mx = m[0] + 0.5, my = m[1] + 0.5;
          ctx.rect(mx - ARM / 2, my - TH / 2, ARM, TH);
          ctx.rect(mx - TH / 2, my - ARM / 2, TH, ARM);
        });
        ctx.fill();
        ctx.restore();
      });
    }

    /* 杆子画在最上层：格中心一条细线，屏幕宽度至少 1px，放大后不变粗 */
    if (rmMarks && (rmMarks.v.length || rmMarks.h.length)){
      var beamC = (cs.getPropertyValue('--rm-beam') || '').trim() || '#f2c66d';
      var lw = Math.max(1, s * 0.11) / s;
      ctx.strokeStyle = beamC;
      ctx.lineWidth = lw;
      ctx.lineCap = 'butt';
      ctx.beginPath();
      rmMarks.v.forEach(function(r){
        ctx.moveTo(r.k + 0.5, r.from);
        ctx.lineTo(r.k + 0.5, r.from + r.len);
      });
      rmMarks.h.forEach(function(r){
        ctx.moveTo(r.from, r.k + 0.5);
        ctx.lineTo(r.from + r.len, r.k + 0.5);
      });
      ctx.stroke();
    }

    /* P4：只在悬停时出现的编号徽章。必须切回屏幕空间画 —— 跟着 dpr*s 走的话，
       放大时徽章会跟着胀大、缩小时糊成一坨。 */
    drawExitBadge(ctx, dpr, cs);

    updateRoomPct();
  }

  /* 悬停右栏第 i 行 → 画布上第 i 个出口的「环 + 数字」。
     一次只画一个，所以不会像常驻徽章那样在出口密集处叠成一团。 */
  function drawExitBadge(ctx, dpr, cs){
    if (rmHoverExit < 0) return;
    var link = rmExitLinks[rmHoverExit];
    if (!link || !link.ok) return;
    var accent = (cs.getPropertyValue('--accent') || '').trim() || '#e8b04a';
    var ink = (cs.getPropertyValue('--on-accent') || '').trim() || '#0f1216';
    var s = rmView.scale;
    var cx = rmView.tx + (link.x + 0.5) * s;
    var cy = rmView.ty + (link.y + 0.5) * s;
    if (cx < -40 || cy < -40 || cx > rmView.cw + 40 || cy > rmView.ch + 40) return;

    var label = String(rmHoverExit + 1);
    var R = Math.max(7, Math.min(11, s * 0.55));
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    /* 光晕：把周围压暗的十字再衬一层，缩小后也能定位 */
    ctx.beginPath();
    ctx.arc(cx, cy, R + 5, 0, Math.PI * 2);
    ctx.globalAlpha = 0.2;
    ctx.fillStyle = accent;
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    ctx.globalAlpha = 1;
    ctx.fillStyle = ink;
    ctx.font = 'bold ' + Math.round(R * (label.length > 1 ? 0.92 : 1.2)) + 'px system-ui,-apple-system,sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, cx, cy + 0.5);
    ctx.restore();
  }

  /* 悬停切换：右栏行加 is-mark，画布重画一次。同一下标重复触发不重绘。 */
  function rmSetHoverExit(i){
    if (i === rmHoverExit) return;
    rmHoverExit = (i >= 0 && i < rmExitLinks.length) ? i : -1;
    var rows = document.querySelectorAll('#rm-exits .rm-exit-row');
    Array.prototype.forEach.call(rows, function(el){
      var k = parseInt(el.getAttribute('data-rmexit'), 10);
      el.classList.toggle('is-mark', k === rmHoverExit);
    });
    if (rmData && rmRuns) drawRoom();
  }

  /* 管道口的 T 形：横条 0.85×0.15 格贴着「外缘」，竖条 0.29×0.47 格朝段内伸。
     尺寸来自编辑器截图（cell=34 px 时 29×5 与 10×16 px）。dx/dy 指向同段的下一格。 */
  function portRects(x, y, dx, dy){
    var GAP = 0.07, THIN = 0.15, BAR = 0.85, THICK = 0.29, STEM = 0.47;
    if (dy !== 0){
      var barY = dy > 0 ? y + GAP : y + 1 - GAP - THIN;
      var stemY = dy > 0 ? barY + THIN : barY - STEM;
      return [[x + (1 - BAR) / 2, barY, BAR, THIN],
              [x + (1 - THICK) / 2, stemY, THICK, STEM]];
    }
    var barX = dx > 0 ? x + GAP : x + 1 - GAP - THIN;
    var stemX = dx > 0 ? barX + THIN : barX - STEM;
    return [[barX, y + (1 - BAR) / 2, THIN, BAR],
            [stemX, y + (1 - THICK) / 2, STEM, THICK]];
  }

  function rmZoomAt(px, py, factor){
    if (!rmData) return;
    var min = rmView.fit * 0.9, max = rmView.fit * 16;
    var next = Math.max(min, Math.min(max, rmView.scale * factor));
    if (Math.abs(next - rmView.scale) < 1e-5) return;
    var k = next / rmView.scale;
    rmView.tx = px - k * (px - rmView.tx);
    rmView.ty = py - k * (py - rmView.ty);
    rmView.scale = next;
    clampRoomPan();
    drawRoom();
    rmHiSchedule();          /* B 档：缩放停下 220 ms 后补一块高密度裁块 */
  }

  /* 房间卡上的「自动 / 已探索 / 未探索」三档 */
  function gxRoomMarkUI(){
    var cur = roomMarkOf(rmCode, rmRoom);
    Array.prototype.forEach.call(document.querySelectorAll('#rm-mark [data-rmmark]'), function(b){
      b.classList.toggle('on', parseInt(b.getAttribute('data-rmmark'), 10) === cur);
    });
    var ex = $('rm-exclude');
    if (ex){
      var cat = (currentCampaign() || {}).slugcat || '';
      var on = isRoomExcluded(cat, rmCode, rmRoom);
      ex.classList.toggle('on', on);
      ex.textContent = on ? '已标记不可达' : '不可达';
    }
  }

  function bindRoomCardOnce(){
    if (rmBound) return;
    rmBound = true;
    var st = $('rm-stage'), cv = $('rm-canvas');

    /* 右栏出口清单：点一行就跳到那间房（S2）。用事件委托，清单重绘后不用重新绑定。 */
    var exBox = $('rm-exits');
    if (exBox){
      /* P4：悬停某行 → 画布上对应的那个出口点亮（常驻不画徽章，避免视觉噪音）。
         委托到容器上：mouseover 一路冒泡上来，落在行内任一子元素都能定位到 data-rmexit。 */
      exBox.addEventListener('mouseover', function(ev){
        var el = ev.target;
        while (el && el !== exBox && el.getAttribute && el.getAttribute('data-rmexit') == null){
          el = el.parentNode;
        }
        if (!el || el === exBox || !el.getAttribute) { rmSetHoverExit(-1); return; }
        var i = parseInt(el.getAttribute('data-rmexit'), 10);
        rmSetHoverExit(isNaN(i) ? -1 : i);
      });
      exBox.addEventListener('mouseleave', function(){ rmSetHoverExit(-1); });
      /* 键盘焦点也算悬停，免得只能靠鼠标 */
      exBox.addEventListener('focusin', function(ev){
        var el = ev.target;
        if (el && el.getAttribute && el.getAttribute('data-rmexit') != null){
          var i = parseInt(el.getAttribute('data-rmexit'), 10);
          rmSetHoverExit(isNaN(i) ? -1 : i);
        }
      });
      exBox.addEventListener('focusout', function(){ rmSetHoverExit(-1); });
      exBox.addEventListener('click', function(ev){
        var el = ev.target;
        while (el && el !== exBox && el.getAttribute && el.getAttribute('data-rmexit') == null){
          el = el.parentNode;
        }
        if (!el || el === exBox || !el.getAttribute) return;
        var i = parseInt(el.getAttribute('data-rmexit'), 10);
        if (!isNaN(i)) rmFollowExit(i);
      });
      exBox.addEventListener('keydown', function(ev){
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var el = ev.target;
        if (el && el.getAttribute && el.getAttribute('data-rmexit') != null){
          ev.preventDefault();
          var i = parseInt(el.getAttribute('data-rmexit'), 10);
          if (!isNaN(i)) rmFollowExit(i);
        }
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('#rm-mark [data-rmmark]'), function(b){
      b.addEventListener('click', function(){
        setRoomMark(rmCode, rmRoom, parseInt(b.getAttribute('data-rmmark'), 10));
        gxRoomMarkUI();
        if (document.getElementById('map-stage')) openMap(rmCode);
      });
    });

    var fullBtn = $('rm-full');
    if (fullBtn) fullBtn.addEventListener('click', function(){ rmApplyFull(!state.roomCardFull); });

    /* 矢量 / 实机：委托到容器，按钮只有一个来源（HTML 里的静态结构），不用重绑 */
    var styleBox = $('rm-style');
    if (styleBox) styleBox.addEventListener('click', function(ev){
      var el = ev.target;
      while (el && el !== styleBox && !(el.getAttribute && el.getAttribute('data-rmstyle'))){
        el = el.parentNode;
      }
      if (!el || el === styleBox || !el.getAttribute) return;
      var next = el.getAttribute('data-rmstyle');
      if (next && next !== rmStyle) rmStyleSet(next);
    });

    /* F 键切全屏 / 紧凑：只在房间卡打开、且焦点不在输入框里时生效 */
    document.addEventListener('keydown', function(ev){
      if (!roomModal || roomModal.hidden) return;
      if (ev.key !== 'f' && ev.key !== 'F') return;
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
      var t = ev.target;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      ev.preventDefault();
      rmApplyFull(!state.roomCardFull);
    });

    var exBtn = $('rm-exclude');
    if (exBtn) exBtn.addEventListener('click', function(){
      var cat = (currentCampaign() || {}).slugcat || '';
      var on = isRoomExcluded(cat, rmCode, rmRoom);
      setRoomExcluded(cat, rmCode, rmRoom, !on);
      gxRoomMarkUI();
      toast((!on ? '已标记为 ' : '已恢复 ') + rmRoom + (!on ? ' 不可达' : ''));
      recompute();
      if (document.getElementById('map-stage')) openMap(rmCode);
    });

    cv.addEventListener('wheel', function(ev){
      if (!rmData) return;
      ev.preventDefault();
      var box = cv.getBoundingClientRect();
      rmZoomAt(ev.clientX - box.left, ev.clientY - box.top, Math.pow(1.0016, -ev.deltaY));
    }, { passive: false });

    var drag = null;
    function onMove(ev){
      if (!drag) return;
      rmView.tx = drag.tx + (ev.clientX - drag.sx);
      rmView.ty = drag.ty + (ev.clientY - drag.sy);
      clampRoomPan();
      drawRoom();
    }
    function onUp(){
      drag = null;
      st.classList.remove('dragging');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      rmHiSchedule();            /* 拖完了才补裁块，拖拽过程中一帧都不发请求 */
    }
    cv.addEventListener('mousedown', function(ev){
      if (ev.button !== 0 || !rmData) return;
      ev.preventDefault();
      drag = { sx: ev.clientX, sy: ev.clientY, tx: rmView.tx, ty: rmView.ty };
      st.classList.add('dragging');
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
    cv.addEventListener('dblclick', function(){ resetRoomView(); });

    Array.prototype.forEach.call(document.querySelectorAll('#rm-zoom [data-rzoom]'), function(btn){
      btn.addEventListener('click', function(){
        if (!rmData) return;
        var act = btn.getAttribute('data-rzoom');
        if (act === 'reset'){ resetRoomView(); return; }
        rmZoomAt(rmView.cw / 2, rmView.ch / 2, act === 'in' ? 1.4 : 1 / 1.4);
      });
    });

    window.addEventListener('resize', function(){
      if (roomModal && !roomModal.hidden && rmData){ sizeRoomCanvas(); resetRoomView(); }
    });
  }

  if (roomModal){
    $('rm-close').addEventListener('click', closeRoomCard);
    $('rm-graph').addEventListener('click', function(){
      var code = rmCode, nm = rmRoom;
      closeRoomCard();
      openGraph(code, nm);
    });
    $('rm-prev').addEventListener('click', function(){ rmStep(-1); });
    $('rm-next').addEventListener('click', function(){ rmStep(1); });
    $('rm-palette').addEventListener('click', openRoomPalette);
    roomModal.addEventListener('click', function(e){ if (e.target === roomModal) closeRoomCard(); });
    $('rm-locate').addEventListener('click', function(){
      var code = rmCode, nm = rmRoom;
      closeRoomCard();
      if (window.__rwMapCtx && window.__rwMapCtx.code === code){
        window.__rwMapCtx.focus(nm);
        return;
      }
      openMap(code);
      setTimeout(function(){
        if (window.__rwMapCtx && window.__rwMapCtx.code === code) window.__rwMapCtx.focus(nm);
      }, 140);
    });
  }

  /* ---------------- 存档打开（原生） ---------------- */
  function openSavePath(path){
    showLoading({ name: String(path).split(/[\\/]/).pop(), size: 0 });
    bridgeCall('read_save', path).then(function(res){
      if (!res || !res.ok){
        showError('无法读取存档', (res && res.error) || '未知错误', '');
        return;
      }
      state.file = { name: res.name, size: res.size };
      startParse(res.text);
    }).catch(function(e){
      showError('无法读取存档', String(e && e.message || e), '');
    });
  }

  function renderSlots(){
    bridgeCall('list_slots').then(function(slots){
      var el = $('slot-list');
      if (!slots || !slots.length){ el.hidden = true; return; }
      el.hidden = false;
      el.innerHTML = slots.map(function(s){
        return '<button class="slot" type="button" data-slot="' + esc(s.path) + '">' +
          '<b>' + esc(s.name) + '</b><span>' + esc(fmtBytes(s.size)) + ' · ' + esc(s.mtimeText) + '</span></button>';
      }).join('');
      Array.prototype.forEach.call(el.querySelectorAll('[data-slot]'), function(btn){
        btn.addEventListener('click', function(ev){
          /* 槽位按钮在 #drop 内部，不拦冒泡的话会顺带触发「选择文件」对话框 */
          ev.stopPropagation();
          openSavePath(btn.getAttribute('data-slot'));
        });
      });
    }).catch(function(){});
  }

  function initDesktop(){
    if (!hasBridge() || state.hasBridge) return;
    state.hasBridge = true;
    $('toolbar').hidden = false;

    bridgeCall('app_info').then(function(info){
      state.dataDir = (info && info.dataDir) || '';
      var el = $('toolbar-path');
      el.textContent = '缓存：' + state.dataDir;
      el.title = state.dataDir;
      if (info && info.defaultSaveDir) {
        var sub = document.querySelector('.drop-sub');
        if (sub) sub.textContent = '存档目录：' + info.defaultSaveDir;
      }
    }).catch(function(){});

    bridgeCall('region_reach').then(function(rr){
      if (rr && rr.regions) state.regionReach = rr;
    }).catch(function(){});
    bridgeCall('region_access').then(function(acc){
      if (acc && acc.regions) state.regionAccess = acc;
    }).catch(function(){});

    bridgeCall('config').then(function(cfg){
      if (cfg && (cfg.theme || cfg.accent)){
        applyTheme(cfg.theme || state.theme, cfg.accent || state.accent, false);
      }
      if (cfg && cfg.ui){
        if (cfg.ui.regionSort) state.regionSort = cfg.ui.regionSort;
        if (cfg.ui.regionSortDir) state.regionSortDir = cfg.ui.regionSortDir;
        if (cfg.ui.killsTopN) state.killsTopN = parseInt(cfg.ui.killsTopN, 10) || 8;
        if (cfg.ui.regionPick && typeof cfg.ui.regionPick === 'object'){
          state.regionPick = cfg.ui.regionPick;
          renderDetail();     /* 配置比存档晚到，到了再刷一次总览 */
        }
        if (cfg.ui.graph && typeof cfg.ui.graph === 'object') state.graphOpts = cfg.ui.graph;
        if (cfg.ui.roomMarks && typeof cfg.ui.roomMarks === 'object') state.roomMarks = cfg.ui.roomMarks;
        if (cfg.ui.regmapColors && typeof cfg.ui.regmapColors === 'object') state.regmapColors = cfg.ui.regmapColors;
        if (cfg.ui.roomExcluded && typeof cfg.ui.roomExcluded === 'object') state.roomExcluded = cfg.ui.roomExcluded;
        if (typeof cfg.ui.roomStrict === 'boolean') state.roomStrict = cfg.ui.roomStrict;
        if (typeof cfg.ui.roomCardFull === 'boolean') state.roomCardFull = cfg.ui.roomCardFull;
        if (typeof cfg.ui.mapBase === 'boolean') state.mapBase = cfg.ui.mapBase;
        if (cfg.ui.roomCardStyle === 'live' || cfg.ui.roomCardStyle === 'vector'){
          state.roomCardStyle = cfg.ui.roomCardStyle;
        }
        /* rmStyle 是绘图时真正读的那个副本，配置加载完必须同步过去 */
        rmStyle = state.roomCardStyle;
        rmStylePaint();
        if (cfg.ui.graphColors && typeof cfg.ui.graphColors === 'object'){
          state.graphColors = {
            dark: (cfg.ui.graphColors.dark && typeof cfg.ui.graphColors.dark === 'object') ? cfg.ui.graphColors.dark : {},
            light: (cfg.ui.graphColors.light && typeof cfg.ui.graphColors.light === 'object') ? cfg.ui.graphColors.light : {}
          };
        }
        if (cfg.ui.roomPalette && typeof cfg.ui.roomPalette === 'object'){
          state.roomPalette = {
            dark: (cfg.ui.roomPalette.dark && typeof cfg.ui.roomPalette.dark === 'object')
              ? cfg.ui.roomPalette.dark : {},
            light: (cfg.ui.roomPalette.light && typeof cfg.ui.roomPalette.light === 'object')
              ? cfg.ui.roomPalette.light : {}
          };
          applyRoomPalette();
          if (rmData) drawRoom();
        }
      }
      if (cfg && cfg._state && cfg._state.note){
        toast(cfg._state.note);
      } else if (cfg && cfg._state && cfg._state.migrated){
        toast('配置已升级到 v2（' + (cfg.configVersion || 2) + '）');
      }
    }).catch(function(){});

    renderSlots();
    loadRegions();
    loadTranslations();
  }

  $('btn-open').addEventListener('click', function(){
    if (!hasBridge()){ $('file').click(); return; }
    bridgeCall('pick_save').then(function(res){
      if (!res || res.canceled) return;
      if (!res.ok){ showError('无法读取存档', res.error || '未知错误', ''); return; }
      state.file = { name: res.name, size: res.size };
      startParse(res.text);
    }).catch(function(e){ showError('无法读取存档', String(e && e.message || e), ''); });
  });
  $('btn-import').addEventListener('click', doImport);
  $('btn-regions').addEventListener('click', openRegionsModal);
  $('btn-translations').addEventListener('click', openTranslationModal);

  document.addEventListener('keydown', function(e){
    var tag = (e.target && e.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable);
    if (!e.ctrlKey && !e.metaKey){
      /* 1–7 切标签：只在结果页、且不在输入框里时生效 */
      if (typing || !state.result) return;
      if (e.key >= '1' && e.key <= String(TABS.length)){
        var idx = parseInt(e.key, 10) - 1;
        if (TABS[idx]){
          e.preventDefault();
          state.tab = TABS[idx][0];
          renderDetail();
        }
      }
      return;
    }
    if (e.key === 'o' || e.key === 'O'){
      e.preventDefault();
      if (e.shiftKey) doImport(); else $('btn-open').click();
    }
    if (e.key === 'r' || e.key === 'R'){ e.preventDefault(); openRegionsModal(); }
    if (e.key === 'e' || e.key === 'E'){
      e.preventDefault();
      if (e.shiftKey) exportMarkdown(); else exportJSON();
    }
  });

  window.addEventListener('pywebviewready', initDesktop);
  if (hasBridge()) initDesktop();

  /* 回归测试钩子（build/check_*.py 用无头窗口读取导出内容，不参与界面逻辑） */
  window.__rwTest = {
    ready: function(){ return !!(state.result && state.result.campaigns && state.result.campaigns.length); },
    markdown: function(){ return state.result ? buildMarkdown(state.result) : ''; },
    campaign: function(name){
      return state.result
        ? state.result.campaigns.filter(function(c){ return c.slugcat === name; })[0] || null
        : null;
    },
    summary: function(){ return state.result ? state.result.completionSummary : null; },
    tab: function(){ return state.tab; },
    karma: function(name){
      var c = window.__rwTest.campaign(name);
      return c ? { karma: c.karma, cap: c.karmaCap, raw: c.karmaRaw, capRaw: c.karmaCapRaw } : null;
    },
    score: function(name){
      var c = window.__rwTest.campaign(name);
      if (!c) return null;
      var s = calcScore(c);
      s.groups = killGroups(c.kills).length;
      s.karma = c.karma;
      s.karmaCap = c.karmaCap;
      return s;
    },
    tabKeys: function(){ return TABS.map(function(t){ return t[0]; }); },
    sliceCount: function(){ return lastSlices.length; },
    overview: function(){ return lastOverview; },
    pick: function(){ return state.regionPick || {}; },
    resetPick: function(){
      state.regionPick = {};
      if (hasBridge()){
        bridgeCall('save_config', { ui: { regionPick: {} } }).catch(function(){});
      }
      renderDetail();
      return true;
    },
    accessNotes: function(){ return (state.regionAccess && state.regionAccess.regions) || {}; },
    openRoom: function(code, room){ openRoomCard(code, room); return true; },
    openGraph: function(code, room){ openGraph(code, room || ''); return true; },
    openWorld: function(){ openWorldGraph(); return true; },
    marks: function(){ return state.roomMarks || {}; },
    /* 底图层（P0）读数：供 check_map 断言，避免靠 DOM 文本猜状态 */
    mapBase: function(){
      var el = document.getElementById('map-base');
      return {
        enabled: !!state.mapBase,
        on: !!(el && el.classList.contains('on')),
        hasHref: !!(el && el.getAttribute('href')),
        url: el ? String(el.getAttribute('href') || '').slice(0, 22) : '',
        w: el ? (+el.getAttribute('width') || 0) : 0,
        h: el ? (+el.getAttribute('height') || 0) : 0,
        cached: Object.keys(window.__rwMapBase || {}).length
      };
    },
    setMapBase: function(on){
      state.mapBase = !!on;
      var b = document.getElementById('map-base-btn');
      if (b) b.classList.toggle('on', state.mapBase);
      var el = document.getElementById('map-base');
      if (el){
        if (!state.mapBase) el.classList.remove('on');
        else if (el.getAttribute('href')) el.classList.add('on');
      }
      return true;
    },
    setMark: function(code, room, v){ setRoomMark(code, room, v); return true; },
    exclude: function(code, room, on){
      setRoomExcluded((currentCampaign() || {}).slugcat, code, room, on !== false);
      recompute();
      return true;
    },
    isExcluded: function(code, room){
      return isRoomExcluded((currentCampaign() || {}).slugcat, code, room);
    },
    /* 当前已加载区域里「房间最多」的那个，测最坏情况用 */
    biggestGraph: function(){
      var best = '', bestN = 0, camp = currentCampaign();
      Object.keys(state.regions || {}).forEach(function(code){
        if (!gxGraphable(code)) return;
        var sets = regionRoomSets(state.regions[code], camp ? camp.slugcat : '');
        var n = sets ? sets.total : 0;
        if (n > bestN){ bestN = n; best = code; }
      });
      return { code: best, rooms: bestN };
    },
    graphNode: function(i){
      if (!GX || !GX.nodes[i]) return null;
      var n = GX.nodes[i];
      return { name: n.name, deg: n.deg, x: n.x, y: n.y,
               appear: Math.round(n.alpha * 100) / 100, dim: Math.round(n.alpha * 100) / 100,
               lab: Math.round((n.labA == null ? 1 : n.labA) * 100) / 100,
               label: gxNodeLabel(n), zh: n.zh || '', en: n.en || '',
               ghost: !!n.ghost, reach: n.reach !== false, reachWhy: n.reachWhy || '',
               visited: !!n.visited,
               pinned: n.fx != null, nb: GX.adj[i].slice(),
               sx: GX.view.x + n.x * GX.view.k, sy: GX.view.y + n.y * GX.view.k,
               r: Math.round(gxNodeSize(n) * 10) / 10 };
    },
    graph: function(){
      if (!GX) return { open: false };
      var p = GX.play;
      var litCount = 0, k;
      for (k = 0; k < GX.nodes.length; k++) if (GX.nodes[k].base) litCount++;
      var isolated = GX.nodes.filter(function(n){ return n.deg === 0; }).length;
      return {
        open: true, code: GX.code, rooms: GX.nodes.filter(gxShown).length,
        total: GX.nodes.length, edges: GX.edges.length,
        setsTotal: GX.stats.setsTotal, layers: GX.stats.layers, timer: !!p.timer,
        isolated: isolated, folded: GX.opts.orphan ? 0 : 1,
        orphan: GX.opts.orphan, view: GX.opts.view, world: !!GX.world,
        size: { cw: GX.cw, ch: GX.ch, kFit: Math.round(GX.kFit * 1000) / 1000, k: Math.round(GX.view.k * 1000) / 1000 },
        full: (document.getElementById('modal-card') || {}).classList ? document.getElementById('modal-card').classList.contains('full') : false,
        visited: GX.nodes.filter(function(n){ return n.visited; }).length,
        gates: GX.nodes.filter(function(n){ return n.gate; }).length,
        shelters: GX.nodes.filter(function(n){ return n.shelter; }).length,
        start: GX.opts.start, startRoom: (GX.nodes[GX.startIdx] || {}).name || '',
        order: GX.opts.order, mode: GX.opts.mode, gap: GX.opts.gap, speed: GX.opts.speed,
        seqLen: p.seq.length, index: p.i, lit: litCount, seg: p.seg, segTotal: p.segTotal,
        playing: p.on, trail: p.trail.length,
        speed: Math.round((GX.speed || 0) * 100) / 100, frozen: !!GX.frozen,
        ticks: GX.ticks || 0,
        zoom: Math.round(gxRel() * 100) / 100,
        zoomTarget: Math.round((GX.targetK / Math.max(1e-6, GX.kFit)) * 100) / 100,
        quality: (function(){
          var q = { overlap: 0, edgePx: 0, minPx: 9999, spread: 0 };
          var shown = GX.nodes.filter(gxShown);
          var k = GX.view.k, i, j, dx, dy, d;
          for (i = 0; i < shown.length; i++){
            for (j = i + 1; j < shown.length; j++){
              dx = shown[i].x - shown[j].x; dy = shown[i].y - shown[j].y;
              d = Math.sqrt(dx * dx + dy * dy) * k;
              if (d < q.minPx) q.minPx = Math.round(d);
              if (d < gxNodeSize(shown[i]) + gxNodeSize(shown[j])) q.overlap++;
            }
          }
          var lens = GX.edges.map(function(e){
            var p1 = GX.nodes[e[0]], p2 = GX.nodes[e[1]];
            var ddx = p1.x - p2.x, ddy = p1.y - p2.y;
            return Math.sqrt(ddx * ddx + ddy * ddy) * k;
          }).sort(function(a, b){ return a - b; });
          q.edgePx = lens.length ? Math.round(lens[Math.floor(lens.length / 2)]) : 0;
          q.edgeMin = lens.length ? Math.round(lens[0]) : 0;
          q.edgeP90 = lens.length ? Math.round(lens[Math.floor(lens.length * 0.9)]) : 0;
          q.edgeMax = lens.length ? Math.round(lens[lens.length - 1]) : 0;
          var b = gxBounds();
          var w = b ? (b.x1 - b.x0) * k : 0, hh = b ? (b.y1 - b.y0) * k : 0;
          q.spread = GX.cw && GX.ch ? Math.round(Math.min(w / GX.cw, hh / GX.ch) * 100) / 100 : 0;
          return q;
        })(),
        node0: GX.nodes[0] ? { name: GX.nodes[0].name, deg: GX.nodes[0].deg } : null,
        colors: { visited: GX.col.visited, unvisited: GX.col.unvisited, trail: GX.col.trail }
      };
    },
    /* 仅供回归：把布局退回「刚展开完」的确定状态（同种子 → 同一形状），
       用来做「拖动拉力 1× vs 4×」这类 A/B 对比；否则两次拖动的起点位置不同，数字没法比。 */
    reloadGraph: function(){
      if (!GX) return false;
      GX.nodes.forEach(function(n){ n.fx = null; n.fy = null; });   /* 清掉上一次拖拽留下的钉子 */
      gxRestage();
      gxWarm();
      gxFit();
      GX.alpha = 0; GX.alphaTarget = 0; GX.ticks = 0; GX.speed = 0; GX.calm = 99; GX.frozen = true;
      return true;
    },
    roomCard: function(){
      var open = !!(roomModal && !roomModal.hidden);
      var info = { open: open, code: rmCode, room: rmRoom, bound: rmBound };
      if (rmData){
        info.w = rmData.w; info.h = rmData.h;
        info.cells = rmData.cells.length;
        info.air = rmData.cells.split('0').length - 1;
        info.border = rmData.border;
        info.cameras = rmData.cameras;
        info.scale = Math.round(rmView.scale / rmView.fit * 100);
        info.tx = Math.round(rmView.tx); info.ty = Math.round(rmView.ty);
        info.solidRuns = rmRuns ? rmRuns.solid.length : 0;
        info.objects = (rmData.objects || []).length;
        info.beamV = rmMarks ? rmMarks.v.length : 0;
        info.beamH = rmMarks ? rmMarks.h.length : 0;
        info.ports = rmMarks ? rmMarks.ports.length : 0;
        info.pipeDots = rmMarks ? rmMarks.dots.length : 0;
        info.marks = rmMarks ? rmMarks.marks.length : 0;
        info.markKinds = {};
        if (rmMarks) rmMarks.marks.forEach(function(m){
          info.markKinds[m[2]] = (info.markKinds[m[2]] || 0) + 1;
        });
        info.climb = rmMarks ? rmMarks.climb.length : 0;
        info.climbShown = rmShowClimb;
        info.portDirs = rmMarks ? rmMarks.ports.slice(0, 12) : [];
      }
      info.sub = $('rm-sub') ? $('rm-sub').textContent : '';
      info.title = $('rm-title') ? $('rm-title').textContent : '';
      info.order = rmOrder.length;
      info.index = rmIndex;
      info.pos = $('rm-pos') ? $('rm-pos').textContent : '';
      info.prevOff = $('rm-prev') ? $('rm-prev').disabled : null;
      info.nextOff = $('rm-next') ? $('rm-next').disabled : null;
      info.nextRoom = rmOrder[rmIndex + 1] || '';
      info.prevRoom = rmOrder[rmIndex - 1] || '';
      var cv = $('rm-canvas');
      info.canvas = cv ? [cv.width, cv.height] : [0, 0];
      /* B5：全屏状态与右栏读数（check_room 用这几条断言两栏布局与清单） */
      var cardEl = document.querySelector('#room-modal .room-card');
      var sideEl = $('rm-side'), bodyEl = $('rm-body');
      info.full = !!(cardEl && cardEl.classList.contains('full'));
      info.sideShown = !!(sideEl && window.getComputedStyle(sideEl).display !== 'none');
      info.exits = document.querySelectorAll('#rm-exits .rm-exit-row').length;
      info.exitsCounted = rmSide.rows || 0;
      info.exitsLayer = rmSide.layer || null;
      info.exitTruncated = !!rmSide.truncated;
      info.exitsEmpty = document.querySelectorAll('#rm-exits .rm-side-empty').length;
      info.exitsUnknown = document.querySelectorAll('#rm-exits .rm-exit-row.is-none').length;
      /* P4：悬停高亮的读数（check_room 用来断言「行 i → 格子 i」和徽章真的画出来了） */
      info.hoverExit = rmHoverExit;
      info.exitNoCell = rmSide.noCell || 0;
      info.exitLinks = rmExitLinks.map(function(l){ return l.ok ? 1 : 0; });
      info.hoverRowMark = document.querySelectorAll('#rm-exits .rm-exit-row.is-mark').length;
      info.hoverCell = (rmHoverExit >= 0 && rmExitLinks[rmHoverExit])
        ? [rmExitLinks[rmHoverExit].x, rmExitLinks[rmHoverExit].y, rmExitLinks[rmHoverExit].ok ? 1 : 0]
        : null;
      info.exitNote = $('rm-exit-note') ? $('rm-exit-note').textContent : '';
      info.sideW = sideEl ? sideEl.clientWidth : 0;
      info.stageH = $('rm-stage') ? $('rm-stage').clientHeight : 0;
      info.bodyOverflow = bodyEl ? bodyEl.scrollWidth - bodyEl.clientWidth : 0;
      info.cardW = cardEl ? cardEl.clientWidth : 0;
      info.cardH = cardEl ? cardEl.clientHeight : 0;
      info.viewW = window.innerWidth || 0;
      info.viewH = window.innerHeight || 0;
      /* V1.2 实机视图：开关状态与位图读数
         （check_room 用这几条断言「能切过去、位图真的到位、失败不炸」） */
      info.style = rmStyle;
      info.styleShown = !!($('rm-style') && !$('rm-style').hidden);
      info.live = rmLive
        ? { ok: !!rmLive.ok, w: rmLive.w || 0, h: rmLive.h || 0,
            px: rmLive.px || 0, ms: rmLive.ms || 0, src: rmLive.src || '',
            cached: !!rmLive.cached }
        : null;
      info.liveFlag = $('rm-live-flag') ? $('rm-live-flag').textContent : '';
      /* B 档：高密度裁块（check_room 断言「放大后 px 顶到 20、范围小于整间」） */
      info.hi = rmLiveHi
        ? { px: rmLiveHi.px, tx: rmLiveHi.tx, ty: rmLiveHi.ty,
            tw: rmLiveHi.tw, th: rmLiveHi.th }
        : null;
      info.liveFlagOn = !!($('rm-live-flag') && $('rm-live-flag').classList.contains('on'));
      info.liveCached = rmLiveOrder.length;
      info.liveBytes = rmLiveBytes;
      info.prefetchPending = !!rmPrefetchTimer;
      return info;
    },
    /* 实机视图有没有盖住出口十字：读每个出口格中心的像素回来自己比色。
       位图一旦画在十字上面，这些像素就变成地形色，断言立刻红。
       （注意必须在「无悬停」时读：悬停会把那个十字抠掉换成徽章。） */
    roomMarkPixels: function(){
      var cv2 = $('rm-canvas');
      if (!cv2 || !rmData || !rmMarks) return { ready: false };
      var ctx2 = cv2.getContext('2d'), dpr2 = rmView.dpr, s2 = rmView.scale;
      var hex2 = (window.getComputedStyle($('rm-stage')).getPropertyValue('--rm-exit') || '').trim() || '#3ae03a';
      var want2 = [parseInt(hex2.substr(1, 2), 16), parseInt(hex2.substr(3, 2), 16), parseInt(hex2.substr(5, 2), 16)];
      var out2 = [];
      rmMarks.marks.forEach(function(m){
        if (m[2] !== 'exit') return;
        var cx = (rmView.tx + (m[0] + 0.5) * s2) * dpr2;
        var cy = (rmView.ty + (m[1] + 0.5) * s2) * dpr2;
        if (cx < 1 || cy < 1 || cx >= cv2.width - 1 || cy >= cv2.height - 1){
          out2.push({ cell: [m[0], m[1]], off: true, match: false });
          return;
        }
        var d = ctx2.getImageData(Math.floor(cx), Math.floor(cy), 1, 1).data;
        out2.push({
          cell: [m[0], m[1]], rgb: [d[0], d[1], d[2]],
          match: Math.abs(d[0] - want2[0]) < 16 && Math.abs(d[1] - want2[1]) < 16 &&
                 Math.abs(d[2] - want2[2]) < 16
        });
      });
      return { ready: true, expect: want2, marks: out2, onScreen: out2.filter(function(o){ return !o.off; }).length };
    },
    /* 在房间矩形里均匀取 n×n 个点的 RGB。同一视图下取两次（矢量 / 实机）再比对，
       是「位图真的贴上去了」最直接的证据——比肉眼看截图可靠得多。 */
    roomPixels: function(n){
      var cv3 = $('rm-canvas');
      if (!cv3 || !rmData) return null;
      var ctx3 = cv3.getContext('2d'), dpr3 = rmView.dpr, s3 = rmView.scale;
      n = n || 8;
      var out3 = [];
      for (var iy = 0; iy < n; iy++){
        for (var ix = 0; ix < n; ix++){
          var tx = (ix + 0.5) / n * rmData.w, ty = (iy + 0.5) / n * rmData.h;
          var px = Math.round((rmView.tx + tx * s3) * dpr3);
          var py = Math.round((rmView.ty + ty * s3) * dpr3);
          if (px < 0 || py < 0 || px >= cv3.width || py >= cv3.height){ out3.push(null); continue; }
          var d3 = ctx3.getImageData(px, py, 1, 1).data;
          out3.push([d3[0], d3[1], d3[2]]);
        }
      }
      return out3;
    },
    /* 直接切画法（回归用；界面上的按钮走同一条 rmStyleSet） */
    setRoomStyle: function(s){
      rmStyleSet(s);
      return rmStyle;
    },
    /* 立刻结束淡入并重绘（回归用）。淡入靠 requestAnimationFrame 推进，
       窗口在后台时 Chromium 会节流它——采样像素前必须先把 alpha 拉到 1，
       否则「位图画没画上去」这条断言会拿矢量图当结果，变成噪声测试。 */
    revealLive: function(){
      rmLiveFade = 1;
      drawRoom();
      return true;
    },
    /* 清空 L1 内存缓存（回归用：逼下一次请求走磁盘，验证 L2 的 SLO） */
    clearLiveCache: function(){
      rmLiveCache = {}; rmLiveOrder = []; rmLiveBytes = 0;
      rmHiDrop();
      return true;
    },
    /* 区域数据弹窗里的「房间渲染缓存」一行（回归用：确认入口渲染出来了） */
    cacheBar: function(){
      var el = $('m-room-cache'), btn = $('m-room-clear');
      return { text: el ? el.textContent : '', hasButton: !!btn,
               disabled: !!(btn && btn.disabled) };
    },
    /* 放大到 fit 的 mult 倍（回归用：触发 B 档裁块）。按中心放大，和滚轮一个效果。 */
    zoomRoom: function(mult){
      if (!rmData) return false;
      var k = (mult || 2) * rmView.fit;
      rmView.scale = Math.max(rmView.fit * 0.9, Math.min(rmView.fit * 16, k));
      clampRoomPan();
      drawRoom();
      rmHiSchedule();
      return true;
    },
    /* 悬停徽章：在出口格中心偏一点（避开数字笔画）取像素，确认强调色真的画出来了 */
    roomBadgePixel: function(){
      if (!rmData || rmHoverExit < 0) return { ready: false };
      var link = rmExitLinks[rmHoverExit];
      if (!link || !link.ok) return { ready: false, noCell: true };
      var cv = $('rm-canvas'), ctx = cv.getContext('2d');
      var s = rmView.scale, dpr = rmView.dpr;
      var cx = rmView.tx + (link.x + 0.5) * s, cy = rmView.ty + (link.y + 0.5) * s;
      if (cx < 2 || cy < 2 || cx >= rmView.cw - 2 || cy >= rmView.ch - 2){
        return { ready: false, off: true };
      }
      var R = Math.max(7, Math.min(11, s * 0.55));
      var px = Math.floor((cx + R * 0.7) * dpr), py = Math.floor(cy * dpr);
      var d = ctx.getImageData(px, py, 1, 1).data;
      var hex = (window.getComputedStyle($('rm-stage')).getPropertyValue('--accent') || '').trim();
      var want = [parseInt(hex.substr(1, 2), 16), parseInt(hex.substr(3, 2), 16), parseInt(hex.substr(5, 2), 16)];
      return {
        ready: true, cell: [link.x, link.y], radius: Math.round(R),
        match: Math.abs(d[0] - want[0]) < 12 && Math.abs(d[1] - want[1]) < 12 && Math.abs(d[2] - want[2]) < 12,
        actual: [d[0], d[1], d[2]], expect: want
      };
    },
    /* 随机抽 n 个格子，比对画布像素颜色与 cells 的期望值（空气/非空气） */
    roomSample: function(n){
      if (!rmData || !rmRuns) return { ready: false };
      var cv = $('rm-canvas'), ctx = cv.getContext('2d');
      var w = rmData.w, cells = rmData.cells;
      var s = rmView.scale, dpr = rmView.dpr;
      var cs = window.getComputedStyle($('rm-stage'));
      function rgb(v){
        v = (v || '').trim();
        if (v.charAt(0) !== '#' || v.length < 7) return null;
        return [parseInt(v.substr(1, 2), 16), parseInt(v.substr(3, 2), 16), parseInt(v.substr(5, 2), 16)];
      }
      var air = rgb(cs.getPropertyValue('--rm-air'));
      if (!air) return { ready: false };
      /* 可攀爬墙的格子底色被换过，且可能是管道/十字所在的格子，采样时跳过 */
      var skip = {};
      if (rmMarks){
        (rmMarks.climb || []).forEach(function(p){ skip[p[0] + ',' + p[1]] = 1; });
        (rmMarks.dots || []).forEach(function(p){ skip[p[0] + ',' + p[1]] = 1; });
        (rmMarks.ports || []).forEach(function(p){ skip[p[0] + ',' + p[1]] = 1; });
        (rmMarks.marks || []).forEach(function(m){ skip[m[0] + ',' + m[1]] = 1; });
      }
      var total = 0, hit = 0;
      for (var i = 0; i < n; i++){
        var idx = Math.floor(Math.random() * cells.length);
        var x = idx % w, y = Math.floor(idx / w);
        if (skip[x + ',' + y]) continue;
        var px = rmView.tx + (x + 0.5) * s;
        var py = rmView.ty + (y + 0.5) * s;
        if (px < 1 || py < 1 || px >= rmView.cw - 1 || py >= rmView.ch - 1) continue;
        var d = ctx.getImageData(Math.floor(px * dpr), Math.floor(py * dpr), 1, 1).data;
        var isAir = d[0] === air[0] && d[1] === air[1] && d[2] === air[2];
        total++;
        if (isAir === (cells.charAt(idx) === '0')) hit++;
      }
      return { ready: true, total: total, hit: hit, ratio: total ? hit / total : 0 };
    },
    /* 取第一根竖杆的中点像素，确认真的画出了杆子（而不是只建了数据） */
    roomBeamPixel: function(){
      if (!rmData || !rmMarks || !rmMarks.v.length) return { ready: false };
      var cv = $('rm-canvas'), ctx = cv.getContext('2d');
      var s = rmView.scale, dpr = rmView.dpr, r = rmMarks.v[0];
      var px = rmView.tx + (r.k + 0.5) * s;
      var py = rmView.ty + (r.from + r.len / 2) * s;
      if (px < 2 || py < 2 || px >= rmView.cw - 2 || py >= rmView.ch - 2) return { ready: false, off: true };
      var d = ctx.getImageData(Math.floor(px * dpr), Math.floor(py * dpr), 1, 1).data;
      var hex = (window.getComputedStyle($('rm-stage')).getPropertyValue('--rm-beam') || '').trim();
      var want = [parseInt(hex.substr(1, 2), 16), parseInt(hex.substr(3, 2), 16), parseInt(hex.substr(5, 2), 16)];
      return {
        ready: true, len: r.len, col: r.k,
        match: d[0] === want[0] && d[1] === want[1] && d[2] === want[2],
        actual: [d[0], d[1], d[2]], expect: want
      };
    },
    /* 取第一个管道口周围的小方块，统计落在「管道色」上的像素，确认 T 形画出来了 */
    roomPortPixel: function(){
      if (!rmData || !rmMarks || !rmMarks.ports.length) return { ready: false };
      var cv = $('rm-canvas'), ctx = cv.getContext('2d');
      var s = rmView.scale, dpr = rmView.dpr, p = rmMarks.ports[0];
      var cx = rmView.tx + (p[0] + 0.5) * s;
      var cy = rmView.ty + (p[1] + 0.5) * s;
      var half = Math.ceil(s * 0.55 * dpr);
      var x0 = Math.max(0, Math.floor(cx * dpr) - half);
      var y0 = Math.max(0, Math.floor(cy * dpr) - half);
      var size = Math.min(half * 2, cv.width - x0, cv.height - y0);
      if (size < 4) return { ready: false, off: true };
      var d = ctx.getImageData(x0, y0, size, size).data;
      var hex = (window.getComputedStyle($('rm-stage')).getPropertyValue('--rm-pipe') || '').trim();
      var want = [parseInt(hex.substr(1, 2), 16), parseInt(hex.substr(3, 2), 16), parseInt(hex.substr(5, 2), 16)];
      var hit = 0, i;
      for (i = 0; i < d.length; i += 4){
        if (Math.abs(d[i] - want[0]) + Math.abs(d[i + 1] - want[1]) + Math.abs(d[i + 2] - want[2]) < 60) hit++;
      }
      return { ready: true, hit: hit, want: want, dir: [p[2], p[3]] };
    },
    /* 取指定种类十字所在格的中心区，统计落在该颜色上的像素 */
    roomMarkPixel: function(kind){
      kind = kind || 'exit';
      if (!rmData || !rmMarks) return { ready: false };
      var list = rmMarks.marks.filter(function(m){ return m[2] === kind; });
      if (!list.length) return { ready: false, none: true };
      var cv = $('rm-canvas'), ctx = cv.getContext('2d');
      var s = rmView.scale, dpr = rmView.dpr, m = list[0];
      var cx = rmView.tx + (m[0] + 0.5) * s;
      var cy = rmView.ty + (m[1] + 0.5) * s;
      var half = Math.ceil(s * 0.45 * dpr);
      var x0 = Math.max(0, Math.floor(cx * dpr) - half);
      var y0 = Math.max(0, Math.floor(cy * dpr) - half);
      var size = Math.min(half * 2, cv.width - x0, cv.height - y0);
      if (size < 4) return { ready: false, off: true };
      var d = ctx.getImageData(x0, y0, size, size).data;
      var varName = { exit: '--rm-exit', den: '--rm-den', creature: '--rm-creature' }[kind] || '--rm-exit';
      var hex = (window.getComputedStyle($('rm-stage')).getPropertyValue(varName) || '').trim();
      var want = [parseInt(hex.substr(1, 2), 16), parseInt(hex.substr(3, 2), 16), parseInt(hex.substr(5, 2), 16)];
      var hit = 0, i;
      for (i = 0; i < d.length; i += 4){
        if (Math.abs(d[i] - want[0]) + Math.abs(d[i + 1] - want[1]) + Math.abs(d[i + 2] - want[2]) < 60) hit++;
      }
      return { ready: true, hit: hit, want: want, cell: [m[0], m[1]] };
    },
    /* 房间卡配色：当前主题的生效值 + 用户改过的项 */
    roomPalette: function(){
      var el = document.getElementById('rp-modal');
      return {
        theme: state.theme,
        palette: roomPaletteOf(state.theme),
        custom: state.roomPalette,
        open: !!(el && !el.hidden)
      };
    },
    resetRoomPalette: function(){
      state.roomPalette = { dark: {}, light: {} };
      applyRoomPalette();
      if (rmData) drawRoom();
      saveRoomPalette();
      return true;
    },
    setStrict: function(on){
      state.roomStrict = !!on;
      var b = document.getElementById('reach-mode');
      if (b) b.textContent = '口径：' + (state.roomStrict ? '严格' : '宽松');
      recompute();
      return true;
    },
    /* 直接看某个区域在某角色下的房间集合（不依赖这个区域在不在当前战役里） */
    roomSets: function(code, slugcat, withDetail){
      var rd = regionData(code);
      if (!rd) return { missing: true };
      var sets = regionRoomSets(rd, slugcat || (currentCampaign() || {}).slugcat);
      if (!sets) return { missing: true };
      var out = {
        total: sets.total, roleDrop: sets.roleDropped || 0,
        manualDrop: sets.manualDropped || 0, condDrop: sets.conditionalDropped || 0,
        strict: state.roomStrict !== false,
        names: Object.keys(sets.names)
      };
      /* 庇护所 / 门 / 邻接表体积不小，只在自检脚本明确要的时候才带出来 */
      if (withDetail){
        out.shelters = Object.keys(sets.shelters || {});
        out.gates = Object.keys(sets.gates || {});
        out.nbr = sets.nbr || {};
      }
      return out;
    },
    region: function(code, slugcat){
      var c = window.__rwTest.campaign(slugcat);
      if (!c) return { missing: true };
      var r = (c.regions || []).filter(function(x){
        return String(x.name).toUpperCase() === String(code).toUpperCase();
      })[0];
      if (!r) return { missing: true };
      var cp = r.completion || {};
      return {
        pct: cp.pct == null ? null : Math.round(cp.pct * 10) / 10,
        total: cp.total, visited: cp.visited,
        variant: cp.variant || null, condDrop: cp.conditionalDropped || 0,
        roleDrop: cp.roleDropped || 0, manualDrop: cp.manualDropped || 0,
        strict: state.roomStrict !== false,
        unknown: cp.unknown || 0, layers: cp.layerNames || [],
        unvisited: (cp.unvisited || []).slice(0, 40)
      };
    }
  };

  // 初始聚焦拖拽区
  showDrop();
})();
