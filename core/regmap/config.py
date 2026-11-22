"""全部可调参数，集中在这一份里。

命令行、demo 页面、以后接进工具，都只读这里——不再有第二处默认值，也不会出现
「调了 demo、出图和 demo 不一样」。每一项都写了「调大/调小会发生什么」，因为参数
没有绝对值，只有取舍。

`kind` 决定 demo 里用什么控件：
  - `range`（默认）：滑块
  - `choice`：下拉框，值必须是 `options[].v`
  - `text`：文本框（`campaign` 例外，demo 会换成下拉框）
"""
from __future__ import annotations

# group 只影响 demo 面板的分栏
PARAMS = [
    {
        "key": "scale_exp", "group": "尺寸",
        "default": 0.75, "min": 0.35, "max": 1.0, "step": 0.01,
        "label": "尺寸压缩指数",
        "desc": "显示尺寸 = 格数 ^ 指数。1.0 是真实比例，大房间会把小房间挤到看不见；"
                "0.75 把最大/中位面积倍数从 29.5 压到 12.7；越小越平均、但小房间越糊。",
    },
    {
        "key": "min_side", "group": "尺寸",
        "default": 2.0, "min": 0.5, "max": 8.0, "step": 0.1,
        "label": "最小边长",
        "desc": "压缩后的下限，防止极窄房间退化成一条线。调大后小房间更好点中，但失真。",
    },
    {
        "key": "gap", "group": "间距",
        "default": 6.0, "min": 0.0, "max": 12.0, "step": 0.1,
        "label": "相邻房间细缝",
        "desc": "有门相通的房间之间留的空隙（单位≈1 格），**同时也是拖动房间的滑动余量**。"
                "1.2 太挤，门对不齐又挪不动，只能靠绕线；6.0 让缝更整齐、穿房更少、能挪的边更多，"
                "代价是整图面积约 +36%（UW）。",
    },
    {
        "key": "repel", "group": "间距",
        "default": 2.6, "min": 1.0, "max": 8.0, "step": 0.1,
        "label": "非相邻隔开倍率",
        "desc": "没有门相通的房间之间的空隙 = 细缝 × 这个值。调大更「用力隔开」，但整图会散。",
    },
    {
        "key": "component_gap", "group": "间距",
        "default": 6.0, "min": 0.0, "max": 24.0, "step": 0.5,
        "label": "连通块间距（×细缝）",
        "desc": "互不相连的几片房间（飞地）之间的空隙。调小整图更紧凑，调大能看出「这是另一片区域」。",
    },
    {
        "key": "parking_gap", "group": "间距",
        "default": 6.0, "min": 0.0, "max": 24.0, "step": 0.5,
        "label": "孤立房间停车场距离（×细缝）",
        "desc": "完全没有出口的房间被统一摆在主块右侧，这是它们与主块的距离。",
    },
    {
        "key": "spring_k", "group": "力学",
        "default": 0.34, "min": 0.0, "max": 1.0, "step": 0.01,
        "label": "贴合弹簧刚度",
        "desc": "把房间拉回「贴边 + 门对齐」的力度。调大更紧、更贴；过大时会和分离打架、残余重叠。",
    },
    {
        "key": "corner_k", "group": "力学",
        "default": 0.1, "min": 0.0, "max": 0.5, "step": 0.01,
        "label": "斜向边弱弹簧",
        "desc": "地图上真斜向的对子（图上是拐角虚线）拉近的力度。0 = 完全不拉（旧行为，"
                "拐角线可能隔很远）；0.1 只让它们别飘太远，不足以把整块拉歪。",
    },
    {
        "key": "align_tol", "group": "对齐",
        "default": 2.0, "min": 0.0, "max": 12.0, "step": 0.1,
        "label": "门对齐容差",
        "desc": "两个通道口沿边错开多少以内算「已经对齐」。调大后更多边直接连实线，"
                "但会容忍明显的错位（门点看着歪）；调小则逼着房间去挪。",
    },
    {
        "key": "slide_max", "group": "对齐",
        "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05,
        "label": "平移上界（×边长）",
        "desc": "为了对齐通道口，最多把房间沿共享边挪多远的比例。0.5 保证两间房仍有"
                "一半边长对着，不会挪成斜对角；0 = 关掉平移（退回「只会绕线」的旧行为）。",
    },
    {
        "key": "slide_rounds", "group": "对齐",
        "default": 3, "min": 0, "max": 8, "step": 1,
        "label": "平移轮数",
        "desc": "挪一轮会影响别的边的对齐，所以要重算再挪。3 轮足够收敛；0 = 关掉平移。",
    },
    {
        "key": "loose_tol", "group": "连线",
        "default": 2.4, "min": 0.0, "max": 16.0, "step": 0.1,
        "label": "「贴住」的额外容差",
        "desc": "缝 ≤ gap + 这个值、门又对齐，才算贴住、直接连实线。**是相对 gap 的余量**，"
                "不是绝对值——gap 放大到 6 时若还写死 3，全库每条边都会被判成「没贴住」。",
    },
    {
        "key": "route_margin", "group": "连线",
        "default": 0.3, "min": 0.0, "max": 3.0, "step": 0.05,
        "label": "折线离墙距离",
        "desc": "绕行折线与房间边界保持的最小间隙。0 会贴着墙画（易与边框重叠）；太大窄缝就过不去了。",
    },
    {
        "key": "door_clear", "group": "门圈",
        "default": 2.5, "min": 0.0, "max": 8.0, "step": 0.1,
        "label": "门圈进深",
        "desc": "每扇门外侧要留出的空地深度。门正对着别的房间时，线出不去、房间也挪不动——"
                "这条力会把挡路的房间推出去。0 = 关掉门圈。",
    },
    {
        "key": "door_half", "group": "门圈",
        "default": 0.8, "min": 0.0, "max": 8.0, "step": 0.1,
        "label": "门圈半宽",
        "desc": "门外侧那块空地的半宽（沿墙方向）。太窄容易从旁边漏过，太宽会把邻房推得很远。",
    },
    {
        "key": "sep_alpha", "group": "力学",
        "default": 0.55, "min": 0.1, "max": 1.0, "step": 0.01,
        "label": "每次推开比例",
        "desc": "发现重叠时一次推掉重叠量的比例。调大收敛快但会把弹簧压死；调小更柔和但要多迭代。",
    },
    {
        "key": "sep_iters", "group": "力学",
        "default": 200, "min": 0, "max": 800, "step": 10,
        "label": "预分离轮数",
        "desc": "先只做「推开」的轮数，把 BFS 阶段撞在一起的分支解开。",
    },
    {
        "key": "fit_rounds", "group": "力学",
        "default": 170, "min": 0, "max": 800, "step": 10,
        "label": "贴合轮数",
        "desc": "弹簧 + 分离交替的轮数。调大更贴合，代价是布局时间线性增加。",
    },
    {
        "key": "engine", "group": "引擎", "kind": "choice",
        "default": "zq",
        "options": [
            {"v": "legacy", "t": "legacy：出口方向约束 + 硬贴合（现状）"},
            {"v": "zq", "t": "zq：门对齐 → 力松弛 → 去重叠 → 分量拼装"},
        ],
        "label": "排布引擎",
        "desc": "legacy 由「门属于哪条边」决定房间位置，规整区很好、大区会拉歪；"
                "zq 走参考实现的四段式（门对齐 → 力松弛 → 去重叠 → 分量拼装）。"
                "2026-11-21 W2 全量对拍：92 区 quad 中位 82.7 → 92.2，重叠 0，最慢 0.98 s，"
                "所以默认改成 zq；legacy 留作回退。",
    },
    {
        "key": "door_side", "group": "判边", "kind": "choice",
        "default": "auto",
        "options": [
            {"v": "auto", "t": "自动：通道 → 有效区 → 贴边 → 摄像机"},
            {"v": "channel", "t": "只用通道（对象 3）"},
            {"v": "effective", "t": "只用有效区边界"},
            {"v": "edge", "t": "只用贴边（旧规则）"},
            {"v": "camera", "t": "只用摄像机位移"},
        ],
        "label": "门属于哪条边（证据链）",
        "desc": "auto 依次尝试：门格所在通道段的走向 → 实心行/列包围盒的最近边 → 贴边 → 摄像机。"
                "旧规则（贴边≤1 → 摄像机）在主人给的 8 扇标尺门上只中 3 扇。",
    },
    {
        "key": "edge_tol", "group": "判边",
        "default": 2, "min": 0, "max": 3, "step": 1,
        "label": "贴边容差（格）",
        "desc": "「正好贴边」的容差。从 1 提到 2：UW_A01 的门 (53,34) 距上边 2 格，"
                "被 1 卡掉后掉进摄像机分支，误判成右。",
    },
    {
        "key": "corner_tol", "group": "判边",
        "default": 5, "min": 0, "max": 8, "step": 1,
        "label": "转角双记录范围（格）",
        "desc": "门到两条边都 ≤ 此值时，两条边都记下来（primary/secondary），布局可以二选一。"
                "调到 0 = 只记一条边；调太大会让正门也被当成转角。",
    },
    {
        "key": "dir_source", "group": "判边", "kind": "choice",
        "default": "map",
        "options": [
            {"v": "map", "t": "尽量用游戏地图矩形（默认）"},
            {"v": "auto", "t": "自动：门给候选，地图在候选里挑"},
            {"v": "door", "t": "只用门（物理位置）"},
        ],
        "label": "布局朝向以谁为准",
        "desc": "map = 有地图矩形就按它摆（UW 相邻对主轴一致 95.9%，auto 79.6%）；"
                "地图缺失时退回门的判定。auto = 门给候选边、地图只在候选里挑，"
                "门与地图矛盾就标 warn；door = 完全不看地图。",
    },
    {
        "key": "map_check", "group": "判边",
        "default": 1, "min": 0, "max": 1, "step": 1,
        "label": "用地图矩形交叉验（1=开）",
        "desc": "门与地图矛盾、且地图方位不在候选边里的边，标成 warn：图上画虚线、布局降权。"
                "关掉就完全不看地图矩形。",
    },
    {
        "key": "diag_ratio", "group": "判边",
        "default": 0.6, "min": 0.3, "max": 1.0, "step": 0.05,
        "label": "斜向判定阈值",
        "desc": "地图上两间房的位移 min(|dx|,|dy|)/max(|dx|,|dy|) ≥ 此值就算「真斜向」："
                "不强行贴边，改用拐角虚线连接。调大 = 更少被判斜向。",
    },
    {
        "key": "link_mode", "group": "画法",
        "default": 2, "min": 0, "max": 2, "step": 1,
        "label": "连线（0=无 1=全实线 2=实线+虚线）",
        "desc": "2 = 正常贴合实线；warn（门与地图矛盾）与 corner（真斜向）画虚线。",
    },
    {
        "key": "solidify", "group": "画法",
        "default": 0.34, "min": 0.05, "max": 0.95, "step": 0.01,
        "label": "缩略图实心阈值",
        "desc": "一个缩略格盖住的源格里有这么大比例是实心，就判成岩壁。调低墙更粗更明显；"
                "调高只剩大块地形，细平台和杆子会消失。",
    },
    {
        "key": "density", "group": "画法",
        "default": 2, "min": 1, "max": 4, "step": 1,
        "label": "缩略密度（格/单位）",
        "desc": "每个显示单位铺几格缩略图。调高更细腻但数据量大，1 会明显锯齿。",
    },
    {
        "key": "invert", "group": "画法",
        "default": 1, "min": 0, "max": 1, "step": 1,
        "label": "亮的是可通行区（1=是）",
        "desc": "1 = 空气亮、岩壁暗（像游戏内地图）；0 = 岩壁亮、空气暗。",
    },
    {
        "key": "y_render_flip", "group": "画法",
        "default": 0, "min": 0, "max": 1, "step": 1,
        "label": "整图上下镜像（仅绘制）",
        "desc": "只翻最后一层画布，用于和旧图对照。不碰判边、不碰缩略图行序"
                "（房间本身已与原图同向：格行 0 = 图顶）。",
    },
    {
        "key": "y_axis", "group": "坐标", "kind": "choice",
        "default": 1,
        "options": [
            {"v": 1, "t": "y=0 是顶边（与图片/地图一致，默认）"},
            {"v": 0, "t": "反过来（旧解释，仅对照）"},
        ],
        "label": "房间格的 y 索引方向（只影响判边）",
        "desc": "2026-11-20 用实机渲染图逐格比对：房间格第 0 行**就是**图片最上一行"
                "（相关 0.78 / 0.67；反过来只有 0.33 / 0.27）。所以绘制**不翻**行，"
                "缩略图与原图同向。这个开关只决定判边时「y 小算上边还是下边」，"
                "默认 1 = y 小是上边；改成 0 会把上下判反，只用于对照。",
    },
    {
        "key": "order_fix", "group": "顺序",
        "default": 1, "min": 0, "max": 1, "step": 1,
        "label": "地图序修复",
        "desc": "1 = 布局算完后按游戏地图的上下左右序做一次最小位移投影（V1.15 方案 A）；0 = 关闭。"
                "门证据在竖轴上只有 57% 的边拿得出、其中 23.7% 还是错的，这一步专门兜那些"
                "「两份门证词互相印证却一起错」的情况。真值默认取 map_image 图标矩形"
                "（就是玩家看的那张图），另一套世界坐标可用 order_truth 切。",
    },
    {
        "key": "order_min_dy", "group": "顺序",
        "default": 8.0, "min": 0.0, "max": 40.0, "step": 0.5,
        "label": "地图序最小高差",
        "desc": "地图中心高差小于这个值的边不参与修复（分不清上下就不硬分）。默认 8 格 ≈ 一个房间高度。",
    },
    {
        "key": "order_rounds", "group": "顺序",
        "default": 8, "min": 1, "max": 40, "step": 1,
        "label": "地图序迭代轮数",
        "desc": "推动会引出新的违反（链式让位），所以要迭代到收敛；一般 2–3 轮就干净，8 是上限保险。",
    },
    {
        "key": "campaign", "group": "战役", "kind": "text",
        "default": "",
        "label": "战役（空 = 主线）",
        "desc": "填 rivulet / saint / artificer… 时按区域 JSON 的 variants 表替换房间"
                "（RIV 等后缀件顶替主图房间，被隐藏的房间不进图）。工具侧直接传现有 slugcat。",
    },
]

BY_KEY = {p["key"]: p for p in PARAMS}

# 只影响重量、不影响观感的内部常量
INTERNAL = {
    "seed": 7,
    # 以下两项有同名公开参数（同值），保留是为了让老调用方还能拿到
    "parking_gap": 6.0,      # 无出口房间与主块的距离（× gap）
    "component_gap": 6.0,    # 连通分量之间的间距（× gap）
    # 门格上的「通道」对象编号：Rain World 房间里 3 = 管道 / 通道口
    "channel_obj": 3,
    # 有效区：一行/列至少这么多实心格，才算「房间真的有内容」
    "solid_min": 2,
    # 通道段少于这么多格就不当作证据（太短的方向不可信）
    "channel_min": 3,
    # warn 边的弹簧权重（正常是 1.0 / 非树 0.45）
    "warn_k": 0.2,
}


def defaults():
    return {p["key"]: p["default"] for p in PARAMS}


def keys():
    return [p["key"] for p in PARAMS]


def _choice_values(spec):
    return [o["v"] for o in spec.get("options") or []]


def coerce(key, value):
    """把字符串转成该参数的正确类型，并夹到声明范围内。"""
    spec = BY_KEY.get(key)
    if not spec:
        raise KeyError("未知参数：%s（可选：%s）" % (key, ", ".join(keys())))
    kind = spec.get("kind", "range")
    if kind == "choice":
        vals = _choice_values(spec)
        raw = str(value).strip()
        for cand in vals:
            if str(cand) == raw:
                return cand
        raise ValueError("%s 只能是 %s，收到 %r"
                         % (key, " / ".join(str(v) for v in vals), value))
    if kind == "text":
        return str(value).strip()
    if isinstance(spec["default"], int):
        num = int(round(float(value)))
    else:
        num = float(value)
    if num < spec["min"]:
        num = spec["min"]
    if num > spec["max"]:
        num = spec["max"]
    return num


def parse_sets(items):
    """`--set gap=2 --set door_side=channel` → {'gap': 2.0, 'door_side': 'channel'}"""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError("--set 需要 key=value：%r" % item)
        k, v = item.split("=", 1)
        out[k.strip()] = coerce(k.strip(), v.strip())
    return out


def describe():
    lines = []
    for p in PARAMS:
        if p.get("kind") == "choice":
            rng = " / ".join(str(v) for v in _choice_values(p))
        elif p.get("kind") == "text":
            rng = "任意字符串"
        else:
            rng = "%s..%s" % (p["min"], p["max"])
        lines.append("%-12s 默认 %-6s %s  %s"
                     % (p["key"], p["default"], rng, p["label"]))
        lines.append("             %s" % p["desc"])
    return "\n".join(lines)
