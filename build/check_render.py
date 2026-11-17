#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""房间实机渲染内核（core/room_render.py）的 CLI 回归。

用法：
    python build/check_render.py --room CC_A03
    python build/check_render.py --room CC_A03 --room GW_B08 --out build/_shots/render
    python build/check_render.py --room CC_S05 --px 8 --sky none

它做三件事：
    1. 出一张 PNG（可选 --out 目录），文件名 `<CODE>_<ROOM>_<px>px_<sky>.png`；
    2. 打印元信息（设置链、调色板、摄像机、雾量）与耗时分解；
    3. 断言若干不变量（尺寸、像素占比、天空色、透明档 alpha），失败即非零退出。

⚠️ 与 RainworldRoomRender 的 `render_room.py` 的逐像素比对**不在这里**：
   那份实现需要 numpy，本机装不上。本脚本只保证「能出图、参数对得上、统计量合理」。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core import paths, region_store, room_geo, room_render  # noqa: E402


def _median(values: list) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[len(values) // 2]


def content_checks(room: str, code: str, sky: str, water: bool, res: dict) -> list[str]:
    """内容级断言：空洞填充取的是周边色、水按水面高度整幅笼罩。

    这两条是 §19 / §20 两个缺陷的直接护栏——以前只断言「画没画」，所以
    「颜色全错但确实画了」也能过。
    """
    fails: list[str] = []
    region = region_store.get_region(code)
    if not region:
        return fails
    path, _ = room_geo.find_file(region, room, None)
    if not path:
        return fails
    geo = room_geo.load(path)
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    cams = room_render._parse_cameras(lines)
    canvas, _ = room_render._stitch(path, geo, cams)
    cw, chh = canvas.w, canvas.h
    covered = canvas.covered
    w, h, ch, buf = room_render.decode_png_bytes(res["png"])
    px = res["pxPerTile"]
    sx_map, sy_map = room_render._sample_maps(cw, chh, px)

    # ---- 1. 空洞区：颜色必须贴近同行最近的已覆盖像素 ----
    if sky == "fill" and res.get("meta", {}).get("voidPixels"):
        devs: list[int] = []
        step = max(1, w // 150)
        for oy in range(0, h, step):
            row_src = sy_map[oy] * cw
            for ox in range(0, w, step):
                if covered[row_src + sx_map[ox]]:
                    continue
                ref = None
                for d in range(1, 13):
                    for xx in (ox - d, ox + d):
                        if 0 <= xx < w and covered[sy_map[oy] * cw + sx_map[xx]]:
                            o = (oy * w + xx) * ch
                            ref = (buf[o], buf[o + 1], buf[o + 2])
                            break
                    if ref is not None:
                        break
                if ref is None:
                    continue
                o = (oy * w + ox) * ch
                devs.append(max(abs(buf[o + k] - ref[k]) for k in range(3)))
        med = _median(devs)
        if devs and med > 48:
            fails.append("%s：空洞填色离周边太远（中位差 %.0f/255，样本 %d）" % (room, med, len(devs)))
        if devs:
            print("  空洞校验：%d 个采样点，离最近已覆盖像素的中位差 %.0f/255，最大 %d" % (
                len(devs), med, max(devs)))

    # ---- 2. 水：统一「整幅半透明笼罩」，只看水面高度，不看 cells ----
    #
    # 2026-11-18 02:23 起，所有房间的水都按 `SL_F01` 那一套画（`WaterFront` 不再
    # 影响结果）。所以这里校验的**不是**「水有没有落在空气格上」，而是三条观感/
    # 几何性质的硬指标：
    #   ① 水面以上**不许**被水改到（以前 `cells` 索引转置就是在这里翻车的）；
    #   ② 水面以下**必须**被水改到（以前 `R<=1` 那条把天空全排除，等于没画）；
    #   ③ 水面上沿必须是**水平**的（逐列找最上面的改动像素，落差只允许波幅那么多）。
    if water and res.get("meta", {}).get("waterLevel", -1) >= 0:
        dry = room_render.render(region, room, px_per_tile=px,
                                 sky=sky, water=False, use_cache=False, use_disk=False)
        if dry.get("ok"):
            w2, h2, ch2, buf2 = room_render.decode_png_bytes(dry["png"])
            if (w2, h2) == (w, h):
                surf_row = chh - (10.0 + res["meta"]["waterLevel"] * 20.0)
                # 水面不是绝对平的一条线：`_water()` 会按 `WaveAmplitude` 上下摆
                # ±(amp*0.15)，amp = 1 + 39*w。容差跟着它走，否则有波的房间会误报
                # （SL_F01 的 amp≈19 → 摆 ±2.9 px，正好越过写死的 3 px）。
                roots = room_render.asset_roots(region, None)
                wave = room_render.Settings(roots, code, None, path).wave_amplitude
                tol = int(39.0 * wave * 0.15 + 0.999) + 2
                above_changed = 0
                below_total = below_changed = 0
                tops: dict[int, int] = {}
                step_y = max(1, h // 200)
                step_x = max(1, w // 200)
                for oy in range(0, h, step_y):
                    sy = sy_map[oy]
                    for ox in range(0, w, step_x):
                        sx = sx_map[ox]
                        if not covered[sy * cw + sx]:
                            continue
                        o = (oy * w + ox) * ch
                        changed = buf[o:o + 3] != buf2[o:o + 3]
                        if sy < surf_row - tol:
                            if changed:
                                above_changed += 1
                        elif sy > surf_row + tol:
                            below_total += 1
                            if changed:
                                below_changed += 1
                                tops.setdefault(ox, oy)
                if above_changed > 2:
                    fails.append("%s：水面以上被水改到 %d 个采样点（水画高了）"
                                 % (room, above_changed))
                if below_total and below_changed < below_total * 0.9:
                    fails.append("%s：水面以下只有 %d/%d 个采样点被水改到（水几乎没画）"
                                 % (room, below_changed, below_total))
                if len(tops) >= 8:
                    spread = max(tops.values()) - min(tops.values())
                    if spread > tol:
                        fails.append("%s：水面上沿不水平，落差 %d px（容差 %d）"
                                     % (room, spread, tol))
                    print("  水面校验：以上改动 %d 点，以下改动 %d/%d 点，上沿落差 %d px（容差 %d）"
                          % (above_changed, below_changed, below_total, spread, tol))
                else:
                    print("  水面校验：以上改动 %d 点，以下改动 %d/%d 点（上沿样本不足）"
                          % (above_changed, below_changed, below_total))
    return fails


_crop_checked = False


def crop_checks(room: str, code: str, sky: str, water: bool, res: dict) -> list[str]:
    """B 档护栏：视口裁块必须与整图**同位置逐像素一致**。

    这是整个裁剪方案的唯一不变量——前端就是把裁块按 tile 坐标叠在整图上，
    错一个像素就会看到一条接缝。所以直接比像素，不给容差。
    （`_crop_checked` 让一组回归里只跑一次：整图那侧本来就有现成的。）
    """
    global _crop_checked
    fails: list[str] = []
    if _crop_checked or not res.get("ok"):
        return fails
    meta = res.get("meta") or {}
    w_tiles, h_tiles = (meta.get("size") or [0, 0])[:2]
    if w_tiles < 20 or h_tiles < 12:
        return fails
    _crop_checked = True
    px = res["pxPerTile"]
    # 中间开一块 20×12 格：既避开房间边缘的空洞带，又一定落在摄像机里
    tx0 = (w_tiles - 20) // 2
    ty0 = (h_tiles - 12) // 2
    rect = (tx0, ty0, tx0 + 20, ty0 + 12)
    region = region_store.get_region(code)
    crop = room_render.render(region, room, px_per_tile=px, sky=sky, water=water,
                              use_cache=False, use_disk=False, crop=rect)
    if not crop.get("ok"):
        fails.append("%s：裁块渲染失败（%s）" % (room, crop.get("error")))
        return fails
    wf, hf, chf, bf = room_render.decode_png_bytes(res["png"])
    wc, hc, chc, bc = room_render.decode_png_bytes(crop["png"])
    if (wc, hc) != ((rect[2] - rect[0]) * px, (rect[3] - rect[1]) * px):
        fails.append("%s：裁块尺寸 %dx%d 与 %d×%d 格 ×%d px 不符"
                     % (room, wc, hc, rect[2] - rect[0], rect[3] - rect[1], px))
        return fails
    ox, oy = rect[0] * px, rect[1] * px
    bad = 0
    for y in range(hc):
        for x in range(wc):
            o = (y * wc + x) * chc
            p = ((y + oy) * wf + (x + ox)) * chf
            if bc[o:o + 3] != bf[p:p + 3]:
                bad += 1
    if bad:
        fails.append("%s：裁块与整图有 %d/%d 个像素不一致（叠加会看到接缝）"
                     % (room, bad, wc * hc))
    print("  裁块校验：%d×%d tile @ %d px，%d/%d 像素与整图一致"
          % (rect[2] - rect[0], rect[3] - rect[1], crop.get("pxPerTile"), wc * hc - bad, wc * hc))
    return fails


# ---------------------------------------------------------------------------
# 极简 PNG 统计（复用内核的解码，避免再引依赖）
# ---------------------------------------------------------------------------
def stats(png_bytes: bytes) -> dict:
    w, h, ch, buf = room_render.decode_png_bytes(png_bytes)
    n = w * h
    opaque = 0
    total = [0, 0, 0]
    hist = [0] * 256
    for i in range(n):
        a = buf[i * ch + 3] if ch == 4 else 255
        if a == 0:
            continue
        opaque += 1
        j = i * ch
        total[0] += buf[j]
        total[1] += buf[j + 1]
        total[2] += buf[j + 2]
        hist[buf[j]] += 1
    if not opaque:
        return {"w": w, "h": h, "opaque": 0.0}
    acc = 0
    p99 = 0
    for v in range(256):
        acc += hist[v]
        if acc >= opaque * 0.99:
            p99 = v
            break
    return {
        "w": w,
        "h": h,
        "opaque": round(opaque / n * 100, 1),
        "mean": [round(t / opaque, 1) for t in total],
        "p99": p99,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", action="append", required=True, help="房间名，可重复")
    ap.add_argument("--code", default=None, help="区域代码；默认由房间名前缀推")
    ap.add_argument("--out", default="", help="输出目录；留空则只统计不落盘")
    ap.add_argument("--px", type=int, default=room_render.PX_PER_TILE, help="每 tile 像素数")
    ap.add_argument("--fit", type=int, default=0, help="输出宽度上限（0=不限制，按 --px 全尺寸出图）")
    ap.add_argument("--sky", default="fill", choices=("fill", "none"))
    ap.add_argument("--slugcat", default=None)
    ap.add_argument("--no-water", action="store_true")
    args = ap.parse_args()

    if args.out:
        os.makedirs(args.out, exist_ok=True)

    failures: list[str] = []
    for room in args.room:
        code = (args.code or room.split("_")[0]).upper()
        region = region_store.get_region(code)
        if not region:
            failures.append("%s：区域 %s 没有导入数据" % (room, code))
            continue

        # 冷启动计时（不吃缓存），再跑一次看热路径
        cold = room_render.render(region, room, slugcat=args.slugcat, px_per_tile=args.px,
                                  sky=args.sky, water=not args.no_water, use_cache=False,
                                  fit_width=args.fit, use_disk=False)
        if not cold.get("ok"):
            failures.append("%s：%s %s" % (room, cold.get("error"), cold.get("detail") or ""))
            print("[FAIL] %s -> %s %s" % (room, cold.get("error"), cold.get("detail") or ""))
            continue

        warm = room_render.render(region, room, slugcat=args.slugcat, px_per_tile=args.px,
                                  sky=args.sky, water=not args.no_water, fit_width=args.fit)
        st = stats(cold["png"])
        meta = cold["meta"]

        print("=" * 72)
        print("%s  %dx%d tile  ->  %dx%d px  (%.1f px/tile)" % (
            cold["room"], meta["size"][0], meta["size"][1],
            cold["width"], cold["height"], cold["pxPerTile"]))
        print("  摄像机 %d 个 %s  缺纹理 %s" % (
            len(meta["cameras"]), meta["cameras"], meta["missingTextures"] or "无"))
        print("  设置：%s" % (os.path.basename(meta["settings"]) if meta["settings"] else "（无，用区域默认模板）"))
        print("  模板链 %d 层  Template=%s" % (meta["templateLayers"], meta["template"]))
        print("  调色板 palette%s  fade=%s@%s  EffectColorA/B=%s/%s" % (
            meta["palette"], meta["fadePalette"], meta["fades"],
            meta["effectColorA"], meta["effectColorB"]))
        print("  light=%.0f  grime=%s  clouds=%s  fog=%.3f  effects=%s" % (
            meta["light"], meta["grime"], meta["clouds"], meta["fog"], meta["effects"] or "无"))
        print("  水：level=%s front=%s" % (meta["waterLevel"], meta["waterFront"]))
        print("  天空色 pal[7,0]=%s" % meta["skyColor"])
        print("  耗时 冷 %.0f ms / 热 %.1f ms   PNG %d KB" % (
            cold["ms"], warm["ms"], round(cold["bytes"] / 1024)))
        print("  统计 %s" % json.dumps(st, ensure_ascii=False))

        # ---- 不变量 ----
        if cold["width"] != meta["size"][0] * cold["pxPerTile"]:
            failures.append("%s：输出宽度不等于 W×pxPerTile" % room)
        if cold["height"] != meta["size"][1] * cold["pxPerTile"]:
            failures.append("%s：输出高度不等于 H×pxPerTile" % room)
        if st["opaque"] <= 0:
            failures.append("%s：整张图全透明" % room)
        if args.sky == "fill" and st["opaque"] < 99.9:
            failures.append("%s：填色档却有 %.1f%% 透明像素" % (room, 100 - st["opaque"]))
        if args.sky == "none" and st["opaque"] >= 100:
            failures.append("%s：透明档却是全不透明" % room)
        if not meta["settings"]:
            print("  [注意] 这间房没有 _settings.txt，已走区域默认模板（这是必须支持的降级路径）")

        # ---- 内容级断言（§19 / §20 的护栏）----
        failures.extend(content_checks(room, code, args.sky, not args.no_water, cold))
        # ---- B 档护栏：裁块与整图同位置逐像素一致（一组里只跑一次）----
        failures.extend(crop_checks(room, code, args.sky, not args.no_water, cold))

        if args.out:
            name = "%s_%s_%dx%dpx_%s.png" % (code, cold["room"].replace(" ", "_"),
                                             cold["width"], cold["pxPerTile"], args.sky)
            path = os.path.join(args.out, name)
            with open(path, "wb") as fh:
                fh.write(cold["png"])
            meta_path = os.path.join(args.out, os.path.splitext(name)[0] + ".json")
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump({k: v for k, v in cold.items() if k != "png"}, fh,
                          ensure_ascii=False, indent=2)
            print("  -> %s" % path)

    print("=" * 72)
    if failures:
        for item in failures:
            print("[FAIL] %s" % item)
        return 1
    print("RENDER OK  (%d 间房)" % len(args.room))
    return 0


if __name__ == "__main__":
    sys.exit(main())
