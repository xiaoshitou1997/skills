#!/usr/bin/env python3
"""layout_gen.py — 声明式 spec 到自包含 HTML/SVG 的确定性布局生成器。

结构类图的坐标不由人手摆：spec（JSON）进，成品 HTML 出，同 spec 必同输出。
内置布局规则（与 mv-diagram-drafter 的图例与标注约定一致）：
  坐标取 4px 网格；节点默认 168×64；行距=行内间距=64；每行居中、行内等距；
  正交走线（直落 / L / 同源总线 / 双机交叉双通道）；线段只走行间隙，不穿节点框；
  文字超宽断言失败，不缩字硬塞；分区框=成员包围盒外扩 24。

用法：
  python3 layout_gen.py <spec.json> <out.html>
  python3 layout_gen.py --help

spec 两种模板（顶层字段区分）：

1) 分层/组网图：
{
  "title": "生产环境物理组网图",
  "rows": [
    {"style": "core", "band": true, "label": "业务服务层",
     "nodes": [{"id": "order", "name": "订单服务", "sub": "交易 / 履约", "w": 168}]}
  ],
  "zones": [
    {"name": "服务器区",
     "members": [{"id": "srv1", "name": "应用服务器", "sub": "应用服务",
                   "style": "srv", "w": 168, "align": "acc-1"}]}
  ],
  "links": [{"from": "gw", "to": "order", "kind": "L", "label": "路由"}]
}
  rows.style ∈ isp|fw|core|acc|srv|office；band=true 时该行画底板并带 label
  （分层架构/安全域）；"legend": false 关闭图例（band 自解释时用，图例文案
  本身是网络语义）；zones 可选，成员用 align 对齐到某节点同列；
  links.kind ∈ straight|L|cross|dashh：straight 轴对齐直落（目标框须含
  源中轴），L 直角折线（仅同行目标改走面向边直连，被中间节点挡住走行
  下方绕行通道；跨行不限上下方向），同源同间隙多条 L 自动合并为总线，
  cross 用于双机互备交叉对
  （上下双通道），dashh 同行相邻虚线；label 可选，直连与 L 支持标注；
  L 链路可设 "bus": false 保留独立走线（如物理线缆）。
  表达层通道（图面语法见 references/visual-grammar.md）：节点 shape ∈
  box|db|cloud（方框=组件、圆柱=存储、云=外部网络），ghost=true 虚框半透明
  （逻辑存在/未激活）；行 role 覆盖该行样式在图例里的名称；链路 tone 引用
  顶层 "link-tones" 声明（通道名→green|blue|purple|orange，线色=承载通道，
  引用未声明的通道名即失败）；"line-legend": {"solid": ..., "dash": ...}
  覆盖实/虚线图例文案；图例按实际用量生成，未动用的通道不进图例。
  容器嵌套：zone 成员或站点域成员可以是 {"kind": "group", "name": ...,
  "members": [...]} 递归容器（限 3 层，标题超宽断言失败），成员左→右
  排布；含 group 的 zone 成员不支持 align。
  样式声明制：顶层 "styles": {"名": [填充色, 边线色, 图例名]} 声明自定义
  样式（机制同 link-tones，与内置六样式并存，重名即失败），节点 style
  引用未声明的样式名即失败。
  双站点镜像：顶层 "region" = {"name": 大区名, "sites": [主站, 镜像站]}。
  sites[0] 必须完整声明 domains（域结构同 zone），sites[1] 只允许
  name/role/style/ghost，引擎深拷贝 sites[0] 结构派生镜像站点（叶子 id
  加 "-b" 后缀，style 给出时整站覆盖，ghost: true 整站虚框=逻辑存在/
  未激活）；region 与 zones 互斥，rows 仍必备；链路直接引用 "-b" 节点
  即可连到镜像站。region 图的对称链路只写一份：from/to 都不带 "-b" 的
  链路自动派生镜像链路（rows 节点无镜像则该端保持），跨站链路（任一端
  带 "-b"）不派生，"mirror": false 显式关闭派生，派生结果与手写链路
  重复（会画双线）即失败。

2) 时序图：
{
  "template": "sequence",
  "title": "下单支付时序",
  "lanes": [{"id": "c", "name": "客户端"}],
  "messages": [{"from": "c", "to": "s", "text": "提交订单", "dash": false}]
}
  from==to 为自消息；dash=true 为返回/异步虚线。
"""
import copy
import json
import sys
from pathlib import Path

W, H = 168, 64
GAP = 64
MARGIN = 64
TOP = 88
BAND_HEAD, BAND_FOOT = 36, 20
ZONE_PAD, ZONE_HEAD, INNER_H = 24, 36, 56
# 容器嵌套与大区：底部留白加深一档，给同排绕行通道留出净空（24+12*idx）
SITE_PAD_BOT = 48
REGION_HEAD, REGION_PAD_BOT = 44, 60
DOMAIN_GAP, SITE_SEP = 32, 64
LINK_COLOR = "#334155"
ARRIVAL_STEP = 24
CHANNEL_STEP = 12
STYLES = {
    "isp":    ("#EEF2FF", "#6366F1", "互联网出口"),
    "fw":     ("#FEE2E2", "#B91C1C", "防火墙"),
    "core":   ("#ECFDF5", "#047857", "核心交换"),
    "acc":    ("#EFF6FF", "#2563EB", "接入交换"),
    "srv":    ("#FAF5FF", "#7C3AED", "服务器"),
    "office": ("#F8FAFC", "#475569", "办公终端"),
}
STYLE_EXTRAS = {}


def style_entry(name):
    """内置样式或 spec "styles" 声明（[填充色, 边线色, 图例名]），都没有即失败。"""
    if name in STYLES:
        return STYLES[name]
    if name in STYLE_EXTRAS:
        return STYLE_EXTRAS[name]
    fail(f"未声明节点样式: {name}")
LANE_MIN_W, LANE_GAP, MSG_PITCH = 128, 64, 52
TONES = {"green": "#16A34A", "blue": "#0284C7", "purple": "#9333EA", "orange": "#EA580C"}
CLOUD_D = ("M 32 96 C 12 96 4 74 20 62 C 10 40 34 24 54 34 C 58 12 92 6 104 24 "
           "C 118 6 152 12 154 34 C 178 30 196 50 184 68 C 200 82 188 102 168 98 "
           "C 160 112 132 112 124 100 C 108 112 76 110 70 98 C 58 108 38 106 32 96 Z")


def cloud_svg(x, y, w, h, fill, stroke, dash, opacity):
    return (f'<path d="{CLOUD_D}" transform="translate({x} {y}) '
            f'scale({w / 200:.4g} {h / 120:.4g})" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1.5" vector-effect="non-scaling-stroke"'
            f'{dash}{opacity}/>')


def fail(msg):
    raise SystemExit(f"layout_gen: {msg}")


def text_w(s, size):
    return sum(size if ord(c) > 0x2E7F else size * 0.6 for c in s)


def cx(n):
    return n["x"] + n["w"] // 2


def bot(n):
    return n["y"] + n["h"]


def node_svg(n, big=True):
    fill, stroke, _ = style_entry(n["style"])
    ghost = n.get("ghost", False)
    dash = ' stroke-dasharray="6 4"' if ghost else ""
    opacity = ' fill-opacity="0.55"' if ghost else ""
    shape = n.get("shape", "box")
    if shape == "db":
        ry = 12
        body = (f'<path d="M {n["x"]} {n["y"] + ry} A {n["w"] // 2} {ry} 0 0 1 '
                f'{n["x"] + n["w"]} {n["y"] + ry} L {n["x"] + n["w"]} {n["y"] + n["h"] - ry} '
                f'A {n["w"] // 2} {ry} 0 0 1 {n["x"]} {n["y"] + n["h"] - ry} Z" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}{opacity}/>'
                f'<ellipse cx="{cx(n)}" cy="{n["y"] + ry}" rx="{n["w"] // 2}" ry="{ry}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        name_y, sub_y = n["y"] + n["h"] // 2 + 2, n["y"] + n["h"] // 2 + 22
    elif shape == "cloud":
        body = cloud_svg(n["x"], n["y"], n["w"], n["h"], fill, stroke, dash, opacity)
        name_y, sub_y = n["y"] + int(n["h"] * 0.43), n["y"] + int(n["h"] * 0.43) + 18
    else:
        body = (f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" rx="8" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}{opacity}/>')
        name_y = n["y"] + 28 if big else n["y"] + 24
        sub_y = n["y"] + n["h"] - 16
    name_size = 14 if big else 13
    return (
        body
        + f'<text x="{cx(n)}" y="{name_y}" font-size="{name_size}" font-weight="600" '
        f'fill="#0F172A" text-anchor="middle">{n["name"]}</text>'
        f'<text x="{cx(n)}" y="{sub_y}" font-size="11" fill="#475569" '
        f'text-anchor="middle">{n["sub"]}</text>'
    )


def page(title, w, h, body):
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><style>'
        f'html,body{{margin:0;padding:0}}'
        f'body{{width:{w}px;height:{h}px;background:#FFFFFF;'
        f'font-family:system-ui,"Microsoft YaHei",sans-serif}}'
        f'</style></head><body>{body}</body></html>'
    )


def svg_open(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">')


def title_svg(text, w):
    return (f'<text x="{w // 2}" y="46" font-size="18" font-weight="700" '
            f'fill="#0F172A" text-anchor="middle">{text}</text>')


def legend_svg(items, legend_y):
    widths = []
    for kind, p in items:
        label = p if isinstance(p, str) else p[1]
        widths.append(text_w(label, 12) + (32 if kind in ("line", "dash", "tone") else 20))
    total = sum(widths) + 24 * (len(items) - 1)
    x, out = (legend_w() - total) / 2, []
    for (kind, p), w in zip(items, widths):
        label = p if isinstance(p, str) else p[1]
        if kind == "line":
            out.append(f'<line x1="{x}" y1="{legend_y - 4}" x2="{x + 26}" y2="{legend_y - 4}" '
                       f'stroke="{LINK_COLOR}" stroke-width="1.75"/>')
        elif kind == "dash":
            out.append(f'<line x1="{x}" y1="{legend_y - 4}" x2="{x + 26}" y2="{legend_y - 4}" '
                       f'stroke="{LINK_COLOR}" stroke-width="1.75" stroke-dasharray="5 4"/>')
        elif kind == "tone":
            out.append(f'<line x1="{x}" y1="{legend_y - 4}" x2="{x + 26}" y2="{legend_y - 4}" '
                       f'stroke="{p[0]}" stroke-width="2.25"/>')
        else:
            fill, stroke, _ = style_entry(p[0])
            out.append(f'<rect x="{x}" y="{legend_y - 11}" width="14" height="14" rx="3" '
                       f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        dx = 32 if kind in ("line", "dash", "tone") else 20
        out.append(f'<text x="{x + dx}" y="{legend_y}" font-size="12" fill="#334155">{label}</text>')
        x += w + 24
    return "".join(out)


def legend_w():
    return CANVAS_W[0]


CANVAS_W = [992]


def label_svg(x, y, t, anchor="middle"):
    return (f'<text x="{x}" y="{y}" font-size="11" fill="{LINK_COLOR}" '
            f'text-anchor="{anchor}" style="paint-order:stroke" stroke="#FFFFFF" '
            f'stroke-width="4" stroke-linejoin="round">{t}</text>')


def path_svg(d, dash=False, color=LINK_COLOR):
    extra = ' stroke-dasharray="5 4"' if dash else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.75"{extra}/>'


def topology_legend_min_width(spec):
    if not spec.get("legend", True):
        return 0
    tone_map = spec.get("link-tones", {})
    tone_used = []
    plain_solid = plain_dash = False
    for link in spec["links"]:
        tone = link.get("tone")
        if tone and tone not in tone_used:
            tone_used.append(tone)
        if link.get("kind", "L") == "dashh":
            plain_dash |= not tone
        else:
            plain_solid |= not tone
    items = []
    line_legend = spec.get("line-legend", {})
    if plain_solid:
        items.append(("line", line_legend.get("solid", "实线 = 物理链路")))
    if plain_dash:
        items.append(("dash", line_legend.get("dash", "虚线 = 逻辑/冗余链路")))
    items += [("tone", ("", tone)) for tone in tone_used]
    used_styles = {}
    for row in spec["rows"]:
        used_styles.setdefault(row["style"], row.get("role") or style_entry(row["style"])[2])
    for zone in spec.get("zones", []):
        for member in iter_leaves(zone["members"]):
            used_styles.setdefault(member["style"], style_entry(member["style"])[2])
    region = spec.get("region")
    if region:
        for member in iter_domain_leaves(region["sites"][0]["domains"]):
            used_styles.setdefault(member["style"], style_entry(member["style"])[2])
        for twin in region["sites"][1:]:
            if twin.get("style"):
                used_styles.setdefault(twin["style"],
                                       twin.get("role") or style_entry(twin["style"])[2])
    items += [("sw", (style, label)) for style, label in used_styles.items()]
    if not items:
        return 0
    widths = [text_w(p if isinstance(p, str) else p[1], 12)
              + (32 if kind in ("line", "dash", "tone") else 20)
              for kind, p in items]
    return sum(widths) + 24 * (len(items) - 1)


def box_title_svg(x, y, text, size=12, color="#475569", weight=600, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" style="paint-order:stroke" stroke="#FFFFFF" '
            f'stroke-width="4" stroke-linejoin="round">{text}</text>')


def iter_leaves(members):
    for m in members:
        if m.get("kind") == "group":
            yield from iter_leaves(m["members"])
        else:
            yield m


def iter_domain_leaves(domains):
    """域列表 → 叶子（域对象比成员多一层，成员遍历不适用）。"""
    for dom in domains:
        yield from iter_leaves(dom["members"])


def layout_members(members, x, y, depth, nodes):
    """容器成员左→右排布；group 递归嵌套，限 3 层。

    返回 (叶子框列表, group 框列表, 总宽, 总高)；叶子记 env=祖先容器框，
    供同行绕行通道判定下缘。
    """
    placed, boxes, cur = [], [], x
    for m in members:
        if m.get("kind") == "group":
            nd = depth + 1
            if nd > 3:
                fail(f"容器嵌套超过 3 层: {m['name']}")
            kids, gboxes, kw, kh = layout_members(
                m["members"], cur + ZONE_PAD, y + ZONE_HEAD, nd, nodes)
            gbox = {"name": m["name"], "x": cur, "y": y,
                    "w": kw + 2 * ZONE_PAD, "h": ZONE_HEAD + kh + ZONE_PAD}
            assert text_w(m["name"], 12) <= gbox["w"] - 24, f"容器标题超宽: {m['name']}"
            for lf in kids:
                lf["env"].append(gbox)
            placed += kids
            boxes.append(gbox)
            boxes += gboxes
            step = gbox["w"]
        else:
            w = m.get("w", W)
            assert text_w(m["name"], 13) <= w - 20, f"节点文字超宽: {m['name']}"
            if m.get("shape", "box") not in ("box", "db", "cloud"):
                fail(f"未知节点形状: {m['shape']}")
            placed.append({"x": cur, "y": y, "w": w, "h": INNER_H,
                           "style": m["style"], "name": m["name"], "sub": m.get("sub", ""),
                           "shape": m.get("shape", "box"), "ghost": bool(m.get("ghost")),
                           "env": []})
            nodes[m["id"]] = placed[-1]
            step = w
        cur += step + GAP
    total_w = cur - x - GAP if members else 0
    inner_h = max([b["h"] for b in boxes]
                  + [p["y"] + p["h"] - y for p in placed] + [0])
    return placed, boxes, total_w, inner_h


def group_zone_boxes(spec, zx, zt, nodes):
    """含 group 的 zone 左→右串行排布；量宽与正式布局共用本函数保证一致。"""
    zone_boxes, gboxes = [], []
    for z in spec.get("zones", []):
        if not any(m.get("kind") == "group" for m in z["members"]):
            continue
        for m in z["members"]:
            if m.get("align"):
                fail(f"含 group 的 zone 成员不支持 align: {z['name']}")
        kids, zgb, kw, kh = layout_members(
            z["members"], zx + ZONE_PAD, zt + ZONE_HEAD, 0, nodes)
        box = {"name": z["name"], "x": zx, "y": zt,
               "w": kw + 2 * ZONE_PAD, "h": ZONE_HEAD + kh + ZONE_PAD}
        assert text_w(z["name"], 12) <= box["w"] - 24, f"容器标题超宽: {z['name']}"
        for lf in kids:
            lf["env"].append(box)
        zone_boxes.append(box)
        gboxes += zgb
        zx += box["w"] + GAP
    return zone_boxes, gboxes


def layout_region(region, ox, oy, nodes):
    """大区布局：sites[0] 完整声明 domains，sites[1] 深拷贝派生镜像站点。

    镜像叶子 id 加 "-b" 后缀、twin.style 给出时整站覆盖；站点同序布置，
    对称由构造保证。返回 box/sites/domains/groups/leaves/legend。
    """
    sites_spec = region["sites"]
    if not 1 <= len(sites_spec) <= 2:
        fail("region.sites 支持 1~2 个站点")
    base = sites_spec[0]
    if not base.get("domains"):
        fail("region.sites[0] 缺 domains")
    for lf in iter_domain_leaves(base["domains"]):
        if lf.get("align"):
            fail("region 模式站点域成员不支持 align")
    twin = sites_spec[1] if len(sites_spec) == 2 else None
    if twin:
        for k in twin:
            if k not in ("name", "role", "style", "ghost"):
                fail(f"镜像站点仅允许 name/role/style/ghost 字段: {k}")
    built = [{"name": base["name"], "domains": base["domains"]}]
    if twin:
        mirror = copy.deepcopy(base["domains"])
        for lf in iter_domain_leaves(mirror):
            lf["id"] += "-b"
            if twin.get("style"):
                lf["style"] = twin["style"]
            if twin.get("ghost"):
                lf["ghost"] = True
        built.append({"name": twin["name"], "domains": mirror})
    legend = {}
    for lf in iter_domain_leaves(base["domains"]):
        legend.setdefault(lf["style"], style_entry(lf["style"])[2])
    if twin and twin.get("style"):
        legend.setdefault(twin["style"],
                          twin.get("role") or style_entry(twin["style"])[2])

    site_boxes, domain_boxes, group_boxes, leaves = [], [], [], []
    sx = ox + ZONE_PAD
    for site in built:
        dx, dh = sx + ZONE_PAD, 0
        s_domains, s_groups, s_leaves = [], [], []
        for dom in site["domains"]:
            dom_y = oy + REGION_HEAD + ZONE_HEAD
            kids, dgb, kw, kh = layout_members(
                dom["members"], dx + ZONE_PAD, dom_y + ZONE_HEAD, 0, nodes)
            dbox = {"name": dom["name"], "x": dx, "y": dom_y,
                    "w": kw + 2 * ZONE_PAD, "h": ZONE_HEAD + kh + ZONE_PAD}
            assert text_w(dom["name"], 12) <= dbox["w"] - 24, f"容器标题超宽: {dom['name']}"
            for lf in kids:
                lf["env"].append(dbox)
            s_domains.append(dbox)
            s_groups += dgb
            s_leaves += kids
            dx += dbox["w"] + DOMAIN_GAP
            dh = max(dh, dbox["h"])
        sbox = {"name": site["name"], "x": sx, "y": oy + REGION_HEAD,
                "w": dx - DOMAIN_GAP - sx + ZONE_PAD,
                "h": ZONE_HEAD + dh + SITE_PAD_BOT}
        assert text_w(sbox["name"], 13) <= sbox["w"] - 28, f"站点标题超宽: {sbox['name']}"
        for lf in s_leaves:
            lf["env"].append(sbox)
        site_boxes.append(sbox)
        domain_boxes += s_domains
        group_boxes += s_groups
        leaves += s_leaves
        sx += sbox["w"] + SITE_SEP
    rbox = {"name": region["name"], "x": ox, "y": oy,
            "w": sx - SITE_SEP - ox + ZONE_PAD,
            "h": REGION_HEAD + max(s["h"] for s in site_boxes) + REGION_PAD_BOT}
    assert text_w(rbox["name"], 13) <= rbox["w"] - 32, f"大区标题超宽: {rbox['name']}"
    for lf in leaves:
        lf["env"].append(rbox)
    return {"box": rbox, "sites": site_boxes, "domains": domain_boxes,
            "groups": group_boxes, "leaves": leaves, "legend": legend}


def generate_topology(spec):
    rows = spec["rows"]
    def row_total(items):
        return sum(n.get("w", W) for n in items) + (len(items) - 1) * GAP
    if spec.get("region") and spec.get("zones"):
        fail("region 与 zones 不能同时使用")
    STYLE_EXTRAS.clear()
    for name, entry in (spec.get("styles") or {}).items():
        if name in STYLES:
            fail(f"样式 {name} 与内置样式重名")
        if not (isinstance(entry, list) and len(entry) == 3):
            fail(f"样式声明须为 [填充色, 边线色, 图例名]: {name}")
        STYLE_EXTRAS[name] = tuple(entry)
    content_width = max(row_total(r["nodes"]) for r in rows) + 2 * MARGIN
    region_w = 0
    if spec.get("region"):
        region_w = layout_region(spec["region"], 0, 0, {})["box"]["w"] + MARGIN
    gzone_w = 0
    if any(m.get("kind") == "group" for z in spec.get("zones", []) for m in z["members"]):
        gzb, _ = group_zone_boxes(spec, MARGIN // 2, 0, {})
        gzone_w = max(b["x"] + b["w"] for b in gzb) + MARGIN // 2
    CANVAS_W[0] = int(max(content_width, region_w, gzone_w,
                          topology_legend_min_width(spec) + 2 * MARGIN) + 0.999)
    canvas_w = CANVAS_W[0]

    nodes, bands, y = {}, [], TOP
    for row in rows:
        items, band = row["nodes"], row.get("band", False)
        total = row_total(items)
        x = (canvas_w - total) // 2
        head = BAND_HEAD if band else 0
        if band:
            bands.append({"label": row.get("label", ""), "x": MARGIN // 2, "y": y,
                          "w": canvas_w - MARGIN, "h": head + H + BAND_FOOT})
        for n in items:
            w = n.get("w", W)
            assert text_w(n["name"], 14) <= w - 20, f"节点文字超宽: {n['name']}"
            if n.get("shape", "box") not in ("box", "db", "cloud"):
                fail(f"未知节点形状: {n['shape']}")
            nodes[n["id"]] = {"x": x, "y": y + head, "w": w, "h": H,
                              "style": row["style"], "name": n["name"],
                              "sub": n.get("sub", ""), "shape": n.get("shape", "box"),
                              "ghost": bool(n.get("ghost"))}
            x += w + GAP
        y += head + H + (BAND_FOOT if band else 0) + GAP
    rows_bottom = y - GAP

    zones, zone_boxes, gboxes = [], [], []
    zone_top = rows_bottom + GAP
    for z in spec.get("zones", []):
        if any(m.get("kind") == "group" for m in z["members"]):
            continue
        kids = []
        for m in z["members"]:
            p = nodes[m["align"]]
            w = m.get("w", W)
            assert text_w(m["name"], 13) <= w - 20, f"节点文字超宽: {m['name']}"
            if m.get("shape", "box") not in ("box", "db", "cloud"):
                fail(f"未知节点形状: {m['shape']}")
            kids.append({"x": p["x"], "y": zone_top + ZONE_HEAD, "w": w, "h": INNER_H,
                         "style": m["style"], "name": m["name"], "sub": m.get("sub", ""),
                         "shape": m.get("shape", "box"), "ghost": bool(m.get("ghost")),
                         "env": []})
            nodes[m["id"]] = kids[-1]
        x0 = min(k["x"] for k in kids) - ZONE_PAD
        x1 = max(k["x"] + k["w"] for k in kids) + ZONE_PAD
        zbox = {"name": z["name"], "x": x0, "y": zone_top,
                "w": x1 - x0, "h": ZONE_HEAD + INNER_H + ZONE_PAD}
        for k in kids:
            k["env"].append(zbox)
        zone_boxes.append(zbox)
        zones.append(kids)
    gzb, gboxes = group_zone_boxes(spec, MARGIN // 2, zone_top, nodes)
    zone_boxes += gzb
    region_blocks = None
    if spec.get("region"):
        region_blocks = layout_region(spec["region"], MARGIN // 2, zone_top, nodes)
    used_styles = {}
    for row in rows:
        used_styles.setdefault(row["style"], row.get("role") or style_entry(row["style"])[2])
    for z in spec.get("zones", []):
        for m in iter_leaves(z["members"]):
            used_styles.setdefault(m["style"], style_entry(m["style"])[2])
    if region_blocks:
        for st, lb in region_blocks["legend"].items():
            used_styles.setdefault(st, lb)

    routes, labels = [], []
    l_reqs = []
    detour_count = {}
    tone_map = spec.get("link-tones", {})
    tone_used = []
    plain_solid = plain_dash = False
    raw_links = spec["links"]
    if spec.get("region"):
        raw_links = expand_mirror_links(raw_links, nodes)
    for lk in raw_links:
        s, d = nodes[lk["from"]], nodes[lk["to"]]
        kind = lk.get("kind", "L")
        label = lk.get("label", "")
        color = LINK_COLOR
        tone = lk.get("tone")
        if tone:
            if tone not in tone_map:
                fail(f"tone 未在 link-tones 声明: {tone}")
            if tone_map[tone] not in TONES:
                fail(f"未知 tone 色: {tone_map[tone]}")
            color = TONES[tone_map[tone]]
            if tone not in tone_used:
                tone_used.append(tone)
        if kind == "dashh":
            plain_dash |= not tone
        else:
            plain_solid |= not tone
        if kind == "straight":
            x = cx(s)
            if not (d["x"] <= x <= d["x"] + d["w"]):
                fail(f"straight 目标框不含源中轴: {lk['from']}->{lk['to']}，请改用 L")
            routes.append((path_svg(f"M {x} {bot(s)} V {top(d)}", color=color),))
            if label:
                labels.append(label_svg(x + 8, (bot(s) + top(d)) / 2 + 4, label, "start"))
        elif kind == "dashh":
            yy = s["y"] + s["h"] // 2
            x1, x2 = sorted((s["x"] + s["w"], d["x"]))
            routes.append((path_svg(f"M {x1} {yy} H {x2}", dash=True, color=color),))
            if label:
                labels.append(label_svg((x1 + x2) / 2, yy - 8, label))
        elif kind in ("L", "cross"):
            if s["y"] == d["y"]:
                yy = s["y"] + s["h"] // 2
                a, b = ((s["x"] + s["w"], d["x"]) if cx(d) > cx(s)
                        else (d["x"] + d["w"], s["x"]))
                blocked = any(n is not s and n is not d and n["y"] == s["y"]
                              and n["x"] + n["w"] > min(a, b) and n["x"] < max(a, b)
                              for n in nodes.values())
                if blocked:
                    senv, denv = s.get("env", []), d.get("env", [])
                    shared = {id(b) for b in senv} & {id(b) for b in denv}
                    floor = max([bot(s), bot(d)]
                                + [b["y"] + b["h"] for b in senv + denv
                                   if id(b) not in shared])
                    idx = detour_count.get((s["y"], floor), 0)
                    detour_count[(s["y"], floor)] = idx + 1
                    ch = floor + 24 + 12 * idx
                    routes.append((path_svg(
                        f"M {cx(s)} {bot(s)} V {ch} H {cx(d)} V {bot(d)}", color=color),))
                    if label:
                        labels.append(label_svg((cx(s) + cx(d)) / 2, ch + 16, label))
                else:
                    routes.append((path_svg(f"M {a} {yy} H {b}", color=color),))
                    if label:
                        labels.append(label_svg((a + b) / 2, yy - 8, label))
            else:
                l_reqs.append((s, d, kind, label, color, lk.get("bus", True)))
        else:
            fail(f"未知 kind: {kind}")

    gaps = {}
    for req in l_reqs:
        gaps.setdefault((bot(req[0]), top(req[1])), []).append(req)
    for (gy1, gy2), reqs in sorted(gaps.items()):
        mid = (gy1 + gy2) // 2
        reqs.sort(key=lambda r: (cx(r[1]), cx(r[0])))
        singles, busses = [], []
        for s, d, kind, label, color, merge_bus in reqs:
            if kind == "cross":
                if cx(d) > cx(s):
                    x1, x2, ch = cx(s) + 30, cx(d) - 30, mid - 6
                else:
                    x1, x2, ch = cx(s) - 46, cx(d) + 46, mid + 6
                routes.append((path_svg(f"M {x1} {gy1} V {ch} H {x2} V {gy2}", color=color),))
                if label:
                    labels.append(label_svg((x1 + x2) / 2, ch - 8, label))
            elif merge_bus and lk_group_source(reqs, s) > 1:
                busses.append((s, d, label, color))
            else:
                singles.append((s, d, label, color))
        singles_by_target = {}
        for s, d, _, _ in singles:
            singles_by_target.setdefault(id(d), []).append((s, d))
        bus_groups = {}
        for s, d, label, color in busses:
            bus_groups.setdefault((id(s), color), (s, color, []))[2].append((d, label))
        total_units = len(singles) + len(bus_groups)

        def channel(idx):
            return mid + round((idx - (total_units - 1) / 2) * CHANNEL_STEP)

        for i, (s, d, label, color) in enumerate(singles):
            ch = channel(i)
            sign = 1 if cx(d) > cx(s) else -1
            x1 = cx(s) + 30 * sign
            pair_list = singles_by_target[id(d)]
            k = next(j for j, pair in enumerate(pair_list) if pair[1] is d)
            if abs(k - (len(pair_list) - 1) / 2) * ARRIVAL_STEP > 60:
                fail(f"同一目标扇入过多，端点放不下: ->{d['name']}")
            x2 = cx(d) + round((k - (len(pair_list) - 1) / 2) * ARRIVAL_STEP)
            routes.append((path_svg(f"M {x1} {gy1} V {ch} H {x2} V {gy2}", color=color),))
            if label:
                labels.append(label_svg((x1 + x2) / 2, ch - 8, label))
        ordered_buses = sorted(bus_groups.values(), key=lambda p: cx(p[0]))
        for gi, (s, color, members) in enumerate(ordered_buses):
            ch = channel(len(singles) + gi)
            xs = sorted(cx(t) for t, _ in members)
            trunk_x, x_left, x_right = cx(s), min(cx(s), xs[0]), max(cx(s), xs[-1])
            routes.append((path_svg(f"M {trunk_x} {gy1} V {ch}", color=color),))
            routes.append((path_svg(f"M {x_left} {ch} H {x_right}", color=color),))
            for t, _ in sorted(members, key=lambda m: cx(m[0])):
                routes.append((path_svg(f"M {cx(t)} {ch} V {gy2}", color=color),))
            names = sorted({text for _, text in members if text})
            if names:
                labels.append(label_svg((x_left + x_right) / 2, ch - 8, " / ".join(names)))

    body = [svg_open(canvas_w, 0)]
    for b in bands:
        body.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="10" '
                    f'fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1"/>')
        body.append(f'<text x="{b["x"] + 14}" y="{b["y"] + 22}" font-size="13" '
                    f'font-weight="600" fill="#475569">{b["label"]}</text>')
    box_titles = []
    for z in zone_boxes:
        body.append(f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["w"]}" height="{z["h"]}" rx="10" '
                    f'fill="#F1F5F9" fill-opacity="0.55" stroke="#94A3B8" stroke-width="1" '
                    f'stroke-dasharray="5 4"/>')
        box_titles.append(box_title_svg(z["x"] + 12, z["y"] + 22, z["name"]))
    for g in gboxes:
        body.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="8" '
                    f'fill="none" stroke="#94A3B8" stroke-width="1" stroke-dasharray="5 4"/>')
        box_titles.append(box_title_svg(g["x"] + 12, g["y"] + 22, g["name"]))
    if region_blocks:
        rb = region_blocks["box"]
        body.append(f'<rect x="{rb["x"]}" y="{rb["y"]}" width="{rb["w"]}" height="{rb["h"]}" rx="12" '
                    f'fill="#F8FAFC" stroke="#64748B" stroke-width="1.5"/>')
        box_titles.append(box_title_svg(rb["x"] + rb["w"] // 2, rb["y"] + 26, rb["name"],
                                        13, "#334155", 700, "middle"))
        for sb in region_blocks["sites"]:
            body.append(f'<rect x="{sb["x"]}" y="{sb["y"]}" width="{sb["w"]}" height="{sb["h"]}" rx="10" '
                        f'fill="#FFFFFF" stroke="#94A3B8" stroke-width="1.25"/>')
            box_titles.append(box_title_svg(sb["x"] + 14, sb["y"] + 24, sb["name"], 13, "#334155"))
        for zb in region_blocks["domains"]:
            body.append(f'<rect x="{zb["x"]}" y="{zb["y"]}" width="{zb["w"]}" height="{zb["h"]}" rx="10" '
                        f'fill="#F1F5F9" fill-opacity="0.55" stroke="#94A3B8" stroke-width="1" '
                        f'stroke-dasharray="5 4"/>')
            box_titles.append(box_title_svg(zb["x"] + 12, zb["y"] + 22, zb["name"]))
        for g in region_blocks["groups"]:
            body.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="8" '
                        f'fill="none" stroke="#94A3B8" stroke-width="1" stroke-dasharray="5 4"/>')
            box_titles.append(box_title_svg(g["x"] + 12, g["y"] + 22, g["name"]))
    body += [p[0] for p in routes]
    for row in rows:
        for n in row["nodes"]:
            body.append(node_svg(nodes[n["id"]]))
    for kids in zones:
        for n in kids:
            body.append(node_svg(n, big=False))
    if region_blocks:
        for n in region_blocks["leaves"]:
            body.append(node_svg(n, big=False))
    body += labels
    body += box_titles
    body.append(title_svg(spec["title"], canvas_w))
    bottoms = [b["y"] + b["h"] for b in zone_boxes] + [rows_bottom]
    if region_blocks:
        rb = region_blocks["box"]
        bottoms.append(rb["y"] + rb["h"])
    content_bottom = max(bottoms)
    bottom_no_legend = content_bottom + 40
    if spec.get("legend", True):
        line_legend = spec.get("line-legend", {})
        items = []
        if plain_solid:
            items.append(("line", line_legend.get("solid", "实线 = 物理链路")))
        if plain_dash:
            items.append(("dash", line_legend.get("dash", "虚线 = 逻辑/冗余链路")))
        items += [("tone", (TONES[tone_map[t]], t)) for t in tone_used]
        items += [("sw", (s, used_styles[s])) for s in used_styles]
        if items:
            legend_y = content_bottom + 80
            body.append(legend_svg(items, legend_y))
            canvas_h = legend_y + 20
        else:
            canvas_h = bottom_no_legend
    else:
        canvas_h = bottom_no_legend
    body.append("</svg>")
    body[0] = svg_open(canvas_w, canvas_h)
    return page(spec["title"], canvas_w, canvas_h, "".join(body))


def expand_mirror_links(links, nodes):
    """region 图对称链路只写一份：两端都不带 -b 的链路派生镜像链路。

    mirror: false 显式关闭；有镜像对应的一端换 -b（rows 节点无镜像则保持），
    派生结果与手写链路重复（会画双线）直接失败。
    """
    out = list(links)
    seen = {(lk["from"], lk["to"]) for lk in links}
    for lk in links:
        if lk.get("mirror") is False:
            continue
        f, t = lk["from"], lk["to"]
        if f.endswith("-b") or t.endswith("-b"):
            continue
        derived = dict(lk)
        derived["from"] = f"{f}-b" if f"{f}-b" in nodes else f
        derived["to"] = f"{t}-b" if f"{t}-b" in nodes else t
        if derived["from"] == f and derived["to"] == t:
            continue
        if (derived["from"], derived["to"]) in seen:
            fail(f"镜像链路已手写，会画双线，请删掉手写条或设 mirror:false: "
                 f"{derived['from']}->{derived['to']}")
        out.append(derived)
    return out


def lk_group_source(reqs, s):
    return sum(1 for r in reqs if r[0] is s and r[2] == "L")


def top(n):
    return n["y"]


def generate_sequence(spec):
    lanes = spec["lanes"]
    msgs = spec["messages"]
    ids = {l["id"] for l in lanes}
    for m in msgs:
        if m["from"] not in ids or m["to"] not in ids:
            fail(f"message 引用未知 lane: {m}")
    lane_w = max(LANE_MIN_W, max(text_w(l["name"], 14) + 28 for l in lanes))
    total = len(lanes) * lane_w + (len(lanes) - 1) * LANE_GAP
    canvas_w = total + 2 * MARGIN
    header_y, header_h = TOP, 48
    lane_x = {l["id"]: MARGIN + i * (lane_w + LANE_GAP) for i, l in enumerate(lanes)}
    lane_c = {i: x + lane_w // 2 for i, x in lane_x.items()}
    first_y = header_y + header_h + 44
    bottom = first_y + max(0, len(msgs) - 1) * MSG_PITCH + 44
    canvas_h = bottom + 32

    body = [svg_open(canvas_w, canvas_h)]
    body.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
                'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                '<path d="M 0 0 L 10 5 L 0 10 z" fill="#334155"/></marker></defs>')
    for l in lanes:
        x = lane_x[l["id"]]
        body.append(f'<rect x="{x}" y="{header_y}" width="{lane_w}" height="{header_h}" rx="8" '
                    f'fill="#EEF2FF" stroke="#6366F1" stroke-width="1.5"/>')
        body.append(f'<text x="{x + lane_w // 2}" y="{header_y + 30}" font-size="14" '
                    f'font-weight="600" fill="#0F172A" text-anchor="middle">{l["name"]}</text>')
        body.append(f'<line x1="{x + lane_w // 2}" y1="{header_y + header_h}" '
                    f'x2="{x + lane_w // 2}" y2="{canvas_h - 24}" stroke="#94A3B8" '
                    f'stroke-width="1.25" stroke-dasharray="4 4"/>')
    for i, m in enumerate(msgs):
        yy = first_y + i * MSG_PITCH
        a, b = lane_c[m["from"]], lane_c[m["to"]]
        dash = ' stroke-dasharray="6 4"' if m.get("dash") else ""
        if a == b:
            body.append(f'<path d="M {a} {yy - 6} h 36 v 22 h -28" fill="none" '
                        f'stroke="{LINK_COLOR}" stroke-width="1.75" marker-end="url(#arr)"/>')
            body.append(label_svg(a + 44, yy + 8, m["text"], "start"))
        else:
            body.append(f'<line x1="{a}" y1="{yy}" x2="{b}" y2="{yy}" stroke="{LINK_COLOR}" '
                        f'stroke-width="1.75"{dash} marker-end="url(#arr)"/>')
            body.append(label_svg((a + b) / 2, yy - 8, m["text"]))
    body.append(title_svg(spec["title"], canvas_w))
    body.append("</svg>")
    return page(spec["title"], canvas_w, canvas_h, "".join(body))


def generate(spec):
    if spec.get("template") == "sequence":
        return generate_sequence(spec)
    return generate_topology(spec)


def main():
    if len(sys.argv) != 3 or sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return 2 if len(sys.argv) != 3 else 0
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    html = generate(spec)
    Path(sys.argv[2]).write_text(html, encoding="utf-8")
    print(f"layout_gen: wrote {sys.argv[2]} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
