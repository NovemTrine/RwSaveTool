"""区域地图布局（从 demo `region_map/` 搬入工具的核心部分）。

只保留「算」的部分：装配 → 判边 → 拼接 → 力松弛 → 平移 → 门圈 → 连线分级 → 缩略游程。
不含任何绘制 / 导出 / 命令行：画由前端 SVG 负责，导出走浏览器。

对外两个入口：
  - `build_rooms(rooms, opts)`：**工具主路径**。`rooms` 由 `adapter` 用工具自己的
    数据层装配好（region_data JSON + room_geo 的地形），本函数只管排版。
  - `build_region_layout(region_json, ...)`：**对拍路径**。吃一个 JSON 路径，内部走
    demo 自带解析器，用来验证「搬过来的算法与 demo 逐位一致」。
"""
from __future__ import annotations

from . import anno, colors, config, doorrule, engine_zq, fx, layout as layout_mod, model, thumbnail

__all__ = ["build_rooms", "build_region_layout", "load_region", "campaign_names",
           "config", "doorrule", "model", "anno", "colors"]

DEFAULT_OPTS = layout_mod.DEFAULTS


def load_region(region_json, index_json=None, campaign=None):
    return model.load_region(region_json, index_json, campaign=campaign)


def campaign_names(region_json):
    return model.campaign_names(region_json)


def _run_engine(rooms, p):
    """按 `engine` 选引擎；zq 出异常就退回 legacy 并在 stats 里记一笔。

    退而不崩是必须的：布局是所有下游（SVG / 导出 / 审计）的唯一入口，
    一个区域的几何把整张图弄崩，比排得丑严重得多。
    """
    engine = str(p.get("engine") or "legacy").lower()
    if engine != "zq":
        res = layout_mod.build(rooms, p)
    else:
        try:
            res = engine_zq.build(rooms, p)
        except Exception as exc:                   # noqa: BLE001 - 兜底
            res = layout_mod.build(rooms, p)
            res.setdefault("stats", {})["engine"] = "legacy"
            res["stats"]["engine_fallback"] = str(exc)
    return res


def _finish(result, region, p, code, prepare):
    if prepare:
        # 不翻行：房间格的行序**就是**原图行序（用实机渲染图逐格比对过：
        # 「图顶=文件行 0」相关 0.78/0.67，「图顶=文件末行」只有 0.33/0.27）。
        thumbnail.prepare(result["nodes"], p["solidify"], p["density"], False)
    result["params"] = p
    # 特效层（W4-fx）：水 / 酸液 / 沙 / 腐化，挂在 node["fx"] 上。
    # 放在 `prepare` 之后：缩略图要先知道房间的有效尺寸，特效只跟房间自身尺寸有关，
    # 两边互不影响，但先 prepare 的好处是失败时（尺寸异常）能直接跳过这间。
    fx.attach(result["nodes"],
              str(p.get("campaign") or region.get("campaign") or ""), p)
    # 标注层（W4 / №2）：**只剩子区域名与颜色**，挂在 node["anno"] = {sub, sc} 上。
    # 房间类型图标 / 物件 / 业力门三类已连渲染代码一起删掉（V1.18）。
    # 依赖 `Room.tags`（model 读世界文件）与房间自己的 `_settings.txt`，跟布局无关，
    # 所以放最后；`opts.anno` 里逐项开关，全关时一个字段都不加。
    try:
        anno.attach(result["nodes"], region, p.get("anno") if isinstance(p.get("anno"), dict) else None)
    except Exception:                             # noqa: BLE001 - 标注不该拖垮布局
        pass
    # 区域配色（V1.15 №0/№4）：调色板提取的可通行色 + `corlor` 派生的背景结构色，
    # 主体一组、每个子区域一组。挂到 `colors` 上，`svg` 按房间所在子区域下发 CSS 变量。
    try:
        result["colors"] = colors.cached(
            (code or region.get("code") or "").upper(),
            region.get("rooms") if isinstance(region.get("rooms"), list) else
            [n["room"] for n in result["nodes"] if n.get("room")],
            region)
    except Exception as exc:                      # noqa: BLE001 - 取色失败就用兜底色
        result.setdefault("stats", {})["colors_error"] = str(exc)
    result["region"] = {
        "code": (code or region.get("code") or "").upper(),
        "name": region.get("name"),
        "displayName": region.get("displayName") or "",
        "nameZh": region.get("nameZh") or "",
        "rooms": len(region["rooms"]),
        "gates": region.get("gates"),
        "missing": region.get("missing") or [],
        "campaign": region.get("campaign") or "",
        "replaced": region.get("replaced") or [],
        "hidden": region.get("hidden") or [],
        "variant_rooms": region.get("variant_rooms") or [],
        "layers": region.get("layers") or [],
    }
    return result


def build_rooms(rooms, opts=None, region=None, code="", prepare=True):
    """工具主路径：`rooms` 已经装配好，这里只排版。

    `region` 只是透传给调用方看的元信息（房间数 / 缺失清单 / 战役），不参与计算。
    """
    p = config.defaults()
    p.update(opts or {})
    result = _run_engine(rooms, p)
    return _finish(result, region or {}, p, code, prepare)


def build_region_layout(region_json, code=None, opts=None, prepare=True,
                        index_json=None, campaign=None):
    """对拍路径：与 demo 完全相同的入口（含 demo 自带 txt 解析）。"""
    p = config.defaults()
    p.update(opts or {})
    if campaign and not p.get("campaign"):
        p["campaign"] = campaign
    camp = p.get("campaign") or None
    region = model.load_region(region_json, index_json, campaign=camp)
    result = _run_engine(region["rooms"], p)
    return _finish(result, region, p, code, prepare)
