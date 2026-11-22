
'use strict';

var PROG_DIV_A='<progDivA>', PROG_DIV_B='<progDivB>';
var MPD_A='<mpdA>', MPD_B='<mpdB>', MPD_C='<mpdC>';
var SV_A='<svA>', SV_B='<svB>', SV_C='<svC>', SV_D='<svD>';
var RG_A='<rgA>', RG_B='<rgB>', RG_C='<rgC>';
var DP_A='<dpA>', DP_B='<dpB>';
var OO_A='<oA>', OO_B='<oB>';
var CO_A='<coA>', CO_B='<coB>';
var WS_A='<wsA>', EG_A='<egA>';
var CA_A='<cA>';
var MW_B='<mwB>', SLOS_A='<slosA>', SLOS_B='<slosB>';

function rwkv(chunk, sep){
  var i = chunk.indexOf(sep);
  if (i < 0) return [chunk, ''];
  return [chunk.slice(0, i), chunk.slice(i + sep.length)];
}
function rwint(v){
  if (v === '' || v == null) return null;
  var n = parseInt(v, 10);
  return isNaN(n) ? null : n;
}
function rwbool(v){ return v !== '' && v !== '0' && v !== 'False' && v !== 'false'; }
function rwclean(a){ return a.filter(function(x){ return x !== '' && x != null; }); }

function rwunescape(s){
  return s.replace(/&(?:#(\d+)|#x([0-9a-fA-F]+)|([a-zA-Z]+));/g, function(m, dec, hex, name){
    try{
      if (dec) return String.fromCodePoint(parseInt(dec, 10));
      if (hex) return String.fromCodePoint(parseInt(hex, 16));
    }catch(e){ return m; }
    switch(name){
      case 'amp': return '&';
      case 'lt': return '<';
      case 'gt': return '>';
      case 'quot': return '"';
      case 'apos': return "'";
      default: return m;
    }
  });
}

function rwParseItems(value){
  if (!value) return [];
  var recs = value.indexOf(RG_C) >= 0 ? value.split(RG_C) : [value];
  var out = [];
  for (var i = 0; i < recs.length; i++){
    var toks = recs[i].split(OO_A);
    if (!toks.length || toks[0].indexOf('ID.') !== 0) continue;
    var id = toks[0].split(OO_B)[0];
    var type = toks[1] || '';
    var room = '', x = null, y = null, z = null;
    if (toks.length > 2){
      var pos = toks[2];
      var m = pos.match(/^(.*?)\.(-?\d+(?:\.\d+)?)\.(-?\d+(?:\.\d+)?)\.(-?\d+(?:\.\d+)?)$/);
      if (m){ room = m[1]; x = parseFloat(m[2]); y = parseFloat(m[3]); z = parseFloat(m[4]); }
      else room = pos;
    }
    var extras = toks.slice(3).map(function(t){ return t.split(OO_B)[0]; }).filter(Boolean);
    if (type) out.push({ id:id, type:type, room:room, x:x, y:y, z:z, extras:extras });
  }
  return out;
}

function rwParseRegion(value){
  var raw = {};
  value.split(RG_A).forEach(function(chunk){
    var kv = rwkv(chunk, RG_B);
    if (kv[0]) raw[kv[0]] = kv[1];
  });
  var rooms = (raw['ROOMSVISITED'] || '').split(',').filter(Boolean);
  var objects = rwParseItems(raw['OBJECTS'] || '');
  var objTypes = {};
  var pearlRooms = {};
  objects.forEach(function(o){
    objTypes[o.type] = (objTypes[o.type] || 0) + 1;
    /* 珍珠有十几种类型（DataPearl / BigGoldenPearl / BudPearl …），统一算珍珠 */
    if (o.type && o.type.indexOf('Pearl') >= 0 && o.room){
      var k = String(o.room).toUpperCase();
      pearlRooms[k] = (pearlRooms[k] || 0) + 1;
    }
  });
  var population = (raw['POPULATION'] || '').split(RG_C).filter(Boolean);
  var consumed = (raw['CONSUMEDITEMS'] || '').split(RG_C).filter(Boolean);
  var swarm = 0;
  (raw['SWARMROOMS'] || '').split(',').forEach(function(p){ if (p.indexOf(':') > 0) swarm++; });
  return {
    name: raw['REGIONNAME'] || '',
    lastCycle: rwint(raw['LASTCYCLEUPDATED'] || ''),
    roomsVisited: rooms.length,
    roomList: rooms,
    roomsSample: rooms.slice(0, 12),
    objects: objects.length,
    objectTypes: objTypes,
    pearlRooms: Object.keys(pearlRooms),
    pearlTotal: Object.keys(pearlRooms).reduce(function(a, k){ return a + pearlRooms[k]; }, 0),
    population: population.length,
    consumed: consumed.length,
    swarmRooms: swarm,
    lineages: (raw['LINEAGES'] || '').split(',').filter(Boolean).length
  };
}

function rwParseCommunities(value){
  if (!value) return [];
  var out = [];
  var parts = value.split(CO_A);
  for (var i = 1; i < parts.length; i++){
    var kv = rwkv(parts[i], CO_B);
    if (!kv[0]) continue;
    var values = {};
    kv[1].split('|').forEach(function(pair){
      var j = pair.indexOf(':');
      if (j > 0){
        var f = parseFloat(pair.slice(j + 1));
        if (!isNaN(f)) values[pair.slice(0, j)] = f;
      }
    });
    out.push({ name: kv[0], values: values });
  }
  return out;
}

function rwParsePassages(value){
  if (!value) return [];
  var out = [];
  value.split(WS_A).forEach(function(chunk){
    var t = chunk.split(EG_A);
    if (!t[0]) return;
    out.push({
      name: t[0],
      earned: t.length > 1 && rwbool(t[1]),
      progress: rwclean(t.slice(2))
    });
  });
  return out;
}

function rwParseProgression(line){
  var p = {
    currentSlugcat:'', shelters:{}, levelTokens:[], sandboxTokens:[], classTokens:[],
    safariTokens:[], playedArenas:[], lore:[], broadcasts:[], campaignTimes:{}, raw:{}
  };
  var body = line.indexOf(PROG_DIV_B) >= 0 ? line.slice(line.indexOf(PROG_DIV_B) + PROG_DIV_B.length) : line;
  body.split(MPD_A).forEach(function(chunk){
    var kv = rwkv(chunk, MPD_B);
    var name = kv[0], value = kv[1];
    if (!name) return;
    switch(name){
      case 'CURRENTSLUGCAT': p.currentSlugcat = value; break;
      case 'SHELTERLIST': {
        var sub = value.split(MPD_B);
        var region = sub[0];
        var rooms = sub.length > 1 ? rwclean(sub.slice(1).join(MPD_C).split(MPD_C)) : [];
        if (region) p.shelters[region] = rooms;
        break;
      }
      case 'LEVELTOKENS': p.levelTokens = rwclean(value.split(',')); break;
      case 'SANDBOXTOKENS': p.sandboxTokens = rwclean(value.split(',')); break;
      case 'CLASSTOKENS': p.classTokens = rwclean(value.split(',')); break;
      case 'SAFARITOKENS': p.safariTokens = rwclean(value.split(',')); break;
      case 'PLAYEDARENAS': p.playedArenas = rwclean(value.split(MPD_C)); break;
      case 'LORE': p.lore = rwclean(value.split(',')); break;
      case 'BROADCASTS': p.broadcasts = rwclean(value.split(',')); break;
      case 'CAMPAIGNTIME': {
        var s = value.split(MPD_B);
        if (s.length){
          var nums = [];
          for (var k = 1; k < s.length; k++){ var n = rwint(s[k]); if (n !== null) nums.push(n); }
          p.campaignTimes[s[0]] = nums;
        }
        break;
      }
      default: p.raw[name] = value;
    }
  });
  return p;
}

function rwParseCampaign(line, warnings){
  var chunks = line.split(SV_A);
  var raw = {};
  var slugcat = '';
  for (var idx = 0; idx < chunks.length; idx++){
    var kv = rwkv(chunks[idx], SV_B);
    if (idx === 0){
      if (kv[0].indexOf('SAV STATE NUMBER') >= 0) slugcat = kv[1];
      continue;
    }
    if (kv[0]){
      if (!raw[kv[0]]) raw[kv[0]] = [];
      raw[kv[0]].push(kv[1]);
    }
  }
  if (!slugcat){
    var m = line.match(/SAV STATE NUMBER<svB>([^<]+)/);
    slugcat = m ? m[1] : '';
  }
  if (!slugcat){ warnings.push('跳过一条无法识别角色名的 SAVE STATE'); return null; }

  function one(f){ return (raw[f] && raw[f][0]) || ''; }

  var c = {
    slugcat: slugcat,
    seed: one('SEED'), version: one('VERSION'), initVersion: one('INITVERSION'),
    worldVersion: one('WORLDVERSION'), denPos: one('DENPOS'), lastDenPos: one('LASTVDENPOS'),
    cycle: rwint(one('CYCLENUM')), food: rwint(one('FOOD')), nextId: rwint(one('NEXTID')),
    hasGlow: Object.prototype.hasOwnProperty.call(raw, 'HASTHEGLOW'), hasMark: false,
    karma: null, karmaCap: null, karmaRaw: null, karmaCapRaw: null, reinforced: false,
    deaths: null, survives: null, quits: null, deathTime: null,
    totalFood: rwint(one('TOTFOOD')), totalTime: rwint(one('TOTTIME')),
    currVerCycles: rwint(one('CURRVERCYCLES')), forcePups: rwint(one('FORCEPUPS')),
    regions: [], communities: [], passages: [], kills: {}, ghosts: {},
    swallowedItems: rwParseItems(one('SWALLOWEDITEMS')),
    heldItems: rwParseItems(one('PLAYERGRASPS')),
    significantPearls: [], friends: 0
  };

  (raw['REGIONSTATE'] || []).forEach(function(v){
    var r = rwParseRegion(v);
    if (r.name) c.regions.push(r);
  });

  if (raw['COMMUNITIES']) c.communities = rwParseCommunities(one('COMMUNITIES'));

  var dp = {};
  if (raw['DEATHPERSISTENTSAVEDATA']){
    one('DEATHPERSISTENTSAVEDATA').split(DP_A).forEach(function(chunk){
      var kv = rwkv(chunk, DP_B);
      if (kv[0]) dp[kv[0]] = kv[1];
    });
  }
  /* 业力：存档里是 0 基（0 级 ~ 9 级），界面按游戏内习惯显示 1 ~ 10。
     证据：新开战役存档写 KARMA=0 / KARMACAP=4，而游戏里默认「业力 1 / 上限 5」。 */
  c.karmaRaw = rwint(dp['KARMA'] || '');
  c.karmaCapRaw = rwint(dp['KARMACAP'] || '');
  c.karma = (c.karmaRaw == null) ? null : Math.max(1, Math.min(10, c.karmaRaw + 1));
  c.karmaCap = (c.karmaCapRaw == null) ? null : Math.max(1, Math.min(10, c.karmaCapRaw + 1));
  c.reinforced = rwbool(dp['REINFORCEDKARMA'] || '');
  c.hasMark = Object.prototype.hasOwnProperty.call(dp, 'HASTHEMARK');
  c.deaths = rwint(dp['DEATHS'] || '');
  c.survives = rwint(dp['SURVIVES'] || '');
  c.quits = rwint(dp['QUITS'] || '');
  c.deathTime = rwint(dp['DEATHTIME'] || '');
  if (dp['WINSTATE']) c.passages = rwParsePassages(dp['WINSTATE']);

  (dp['GHOSTS'] || '').split(',').forEach(function(pair){
    var j = pair.indexOf(':');
    if (j > 0){ var n = rwint(pair.slice(j + 1)); if (n !== null) c.ghosts[pair.slice(0, j)] = n; }
  });

  if (raw['KILLS']){
    one('KILLS').split(SV_C).forEach(function(chunk){
      var j = chunk.indexOf(SV_D);
      if (j > 0){
        var name = chunk.slice(0, j);
        var n = rwint(chunk.slice(j + SV_D.length));
        if (name && n !== null) c.kills[name] = n;
      }
    });
  }

  if (raw['MISCWORLDSAVEDATA']){
    var mw = one('MISCWORLDSAVEDATA');
    var mb = mw.indexOf(MW_B) >= 0 ? mw.slice(mw.indexOf(MW_B) + MW_B.length) : mw;
    var map = {};
    mb.split(SLOS_A).forEach(function(chunk){
      var kv = rwkv(chunk, SLOS_B);
      if (kv[0]) map[kv[0]] = kv[1];
    });
    c.significantPearls = rwclean((map['significantPearls'] || '').split(',').map(function(s){ return s.trim(); }));
  }

  if (raw['FRIENDS']){
    var f = one('FRIENDS');
    c.friends = (f.match(/SlugNPC/g) || []).length;
  }

  return c;
}

function readEnvelope(raw){
  var warnings = [];
  var keys = [], values = {}, chosen = '';
  var ki = raw.indexOf('</Keys>');
  if (ki >= 0){
    var keysBlock = raw.slice(0, ki);
    var keyRe = /<anyType[^>]*i:type="x:string"[^>]*>([\s\S]*?)<\/anyType>/g;
    var m;
    while ((m = keyRe.exec(keysBlock)) !== null) keys.push(m[1].trim());

    var rest = raw.slice(ki + 7);
    var valsBlock = rest;
    var vm = rest.match(/<Values[^>]*>([\s\S]*?)<\/Values>/);
    if (vm) valsBlock = vm[1];
    var vals = [];
    var valRe = /<anyType[^>]*i:type="x:string"[^>]*>([\s\S]*?)<\/anyType>/g;
    while ((m = valRe.exec(valsBlock)) !== null) vals.push(m[1]);

    for (var i = 0; i < keys.length; i++) values[keys[i]] = vals[i] || '';
    if (values['save'] && values['save'].length >= 32) chosen = 'save';
    else if (values['save__Backup'] && values['save__Backup'].length >= 32){
      chosen = 'save__Backup';
      warnings.push('save 段为空或过短，已改用 save__Backup');
    } else {
      var best = '', bestLen = -1;
      Object.keys(values).forEach(function(k){ if (values[k].length > bestLen){ best = k; bestLen = values[k].length; } });
      chosen = best;
      if (chosen) warnings.push('未找到可用的 save 段，已改用最长的存档段 ' + chosen);
    }
  } else {
    chosen = '(plain)';
    values['(plain)'] = raw.trim();
    warnings.push('未检测到 XML 信封，已按纯文本存档处理');
  }

  var sz = values[chosen] || '';
  var checksum = '';
  var cm = sz.match(/^[0-9a-fA-F]{32}/);
  var payload = cm ? sz.slice(32) : sz;
  if (cm) checksum = cm[0];
  else if (sz) warnings.push('存档串开头不是合法 MD5，可能缺少校验和');

  return {
    keys: keys,
    chosen: chosen,
    checksum: checksum,
    saveStringLength: sz.length,
    payload: rwunescape(payload),
    warnings: warnings
  };
}

function parseSave(raw, onProgress){
  var prog = onProgress || function(){};
  prog('解包存档', 5, '定位 XML 信封');
  if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);

  var env = readEnvelope(raw);
  prog('解包存档', 12, '还原明文数据');
  var payload = env.payload;
  var warnings = env.warnings.slice();
  if (!payload) throw new Error('存档内容为空，无法解析。');
  if (payload.indexOf('MISCPROG') < 0 && payload.indexOf('SAVE STATE') < 0){
    throw new Error('未找到 MISCPROG / SAVE STATE 数据段，这可能不是雨世界存档。');
  }

  var lines = payload.split(PROG_DIV_A);
  prog('解析数据段', 18, '共 ' + lines.length + ' 段');

  var campaigns = [];
  var progression = null;
  var maps = {};
  var mapEntries = 0, mapThumbs = 0;
  var total = lines.length || 1;

  for (var i = 0; i < lines.length; i++){
    var line = lines[i];
    if (line.indexOf('MISCPROG') === 0){
      progression = rwParseProgression(line);
    } else if (line.indexOf('SAVE STATE') === 0){
      var c = rwParseCampaign(line, warnings);
      if (c) campaigns.push(c);
    } else if (line.indexOf('MAP_') === 0){
      var parts = line.slice(4).split(PROG_DIV_B);
      mapEntries++;
      if (parts[0]){
        if (!maps[parts[0]]) maps[parts[0]] = 0;
        if (parts[1]) maps[parts[0]]++;
        if (parts[2] && parts[2].indexOf('iVBOR') === 0) mapThumbs++;
      }
    }
    if (i % 4 === 0 || i === lines.length - 1){
      prog('解析数据段', 18 + Math.round((i + 1) / total * 64), '已处理 ' + (i + 1) + ' / ' + total);
    }
  }

  if (!progression){
    progression = { currentSlugcat:'', shelters:{}, levelTokens:[], sandboxTokens:[], classTokens:[],
      safariTokens:[], playedArenas:[], lore:[], broadcasts:[], campaignTimes:{}, raw:{} };
  }
  if (!campaigns.length) throw new Error('未找到任何角色战役（SAVE STATE），存档可能不完整。');

  prog('整理结果', 92, '生成结构化数据');

  return {
    meta: {
      chosen: env.chosen,
      keys: env.keys,
      checksum: env.checksum,
      saveStringLength: env.saveStringLength,
      payloadLength: payload.length,
      proglineCount: lines.length,
      campaignCount: campaigns.length,
      mapEntries: mapEntries,
      mapThumbnails: mapThumbs,
      maps: maps
    },
    progression: progression,
    campaigns: campaigns,
    warnings: warnings
  };
}
