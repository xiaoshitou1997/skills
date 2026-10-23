"""layout_gen.py 的离线用例：确定性、断言、走线规则。"""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_script = ROOT / "mv-diagram-drafter" / "scripts" / "layout_gen.py"
_spec = importlib.util.spec_from_file_location("layout_gen", _script)
layout_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout_gen)


def topology_spec(links):
    return {
        "title": "测试图",
        "rows": [
            {"style": "core", "nodes": [{"id": "s", "name": "源节点", "sub": ""}]},
            {"style": "srv", "nodes": [
                {"id": "a", "name": "节点 A", "sub": ""},
                {"id": "b", "name": "节点 B", "sub": ""},
                {"id": "c", "name": "节点 C", "sub": ""}]},
        ],
        "links": links,
    }


class LayoutGenTest(unittest.TestCase):
    def test_deterministic_same_spec_same_output(self):
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"}])
        self.assertEqual(layout_gen.generate(spec), layout_gen.generate(spec))

    def test_text_overflow_fails(self):
        spec = topology_spec([])
        spec["rows"][0]["nodes"][0]["name"] = "这是一个远远超出节点框宽度的名称"
        with self.assertRaises(AssertionError):
            layout_gen.generate(spec)

    def test_same_row_adjacent_link_draws_facing_edge_direct(self):
        # 同一行内相邻节点 a->b：面向边直连，水平段在行中线上。
        html = layout_gen.generate(topology_spec(
            [{"from": "a", "to": "b", "kind": "L", "label": "读写"}]))
        self.assertIn("M 232 248 H 296", html)

    def test_same_row_blocked_link_detours_below_row(self):
        # 同一行内 a->c 被中间节点 b 挡住：绕行通道在行下方 bot+24，不穿节点。
        html = layout_gen.generate(topology_spec(
            [{"from": "a", "to": "c", "kind": "L", "label": "备份"}]))
        self.assertIn("M 148 280 V 304 H 612 V 280", html)

    def test_same_source_links_merge_into_bus(self):
        # 同源多条 L 合并总线：源底只出一根主干，水平段覆盖目标范围。
        spec = topology_spec([
            {"from": "s", "to": "a", "kind": "L"},
            {"from": "s", "to": "b", "kind": "L"},
            {"from": "s", "to": "c", "kind": "L"}])
        html = layout_gen.generate(spec)
        self.assertEqual(html.count("M 380 152 V"), 1, "源底主干应只有一根")
        self.assertIn("M 148 184 H 612", html)

    def test_canvas_expands_to_fit_legend(self):
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"}])
        html = layout_gen.generate(spec)
        self.assertIn('width="', html)
        svg_width = int(html.split('<svg', 1)[1].split('width="', 1)[1].split('"', 1)[0])
        self.assertGreaterEqual(svg_width, layout_gen.topology_legend_min_width(spec) + 128)

    def test_bus_false_keeps_same_source_links_independent(self):
        # 物理链缆不代表共享介质；显式关闭总线合并后每条线独立走线。
        spec = topology_spec([
            {"from": "s", "to": "a", "kind": "L", "bus": False},
            {"from": "s", "to": "b", "kind": "L", "bus": False},
            {"from": "s", "to": "c", "kind": "L", "bus": False}])
        html = layout_gen.generate(spec)
        self.assertEqual(html.count('<path d="M '), 3)
        self.assertNotIn("M 380 184 H 612", html)

    def test_straight_requires_target_coverage(self):
        spec = topology_spec([{"from": "a", "to": "c", "kind": "straight"}])
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_sequence_template_geometry(self):
        spec = {
            "template": "sequence",
            "title": "时序",
            "lanes": [{"id": "c", "name": "客户端"}, {"id": "s", "name": "服务端"}],
            "messages": [{"from": "c", "to": "s", "text": "请求"},
                         {"from": "c", "to": "c", "text": "自检"}],
        }
        html = layout_gen.generate(spec)
        self.assertIn('x1="128" y1="180" x2="320"', html)
        self.assertIn("M 128 226 h 36 v 22 h -28", html)


    def test_tone_undeclared_fails(self):
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L", "tone": "互联网"}])
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_tone_colors_links_and_legend(self):
        # tone 色入链路；图例收录 tone 名；line-legend 覆盖实线文案。
        spec = topology_spec([
            {"from": "s", "to": "b", "kind": "straight"},
            {"from": "s", "to": "a", "kind": "L", "tone": "互联网"}])
        spec["link-tones"] = {"互联网": "green"}
        spec["line-legend"] = {"solid": "实线 = 域内链路"}
        html = layout_gen.generate(spec)
        self.assertEqual(html.count('stroke="#16A34A"'), 2)  # 1 条路径 + 1 图例
        self.assertIn("互联网", html)
        self.assertIn("实线 = 域内链路", html)

    def test_row_role_overrides_legend_label(self):
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"}])
        spec["rows"][0]["role"] = "接入骨干"
        html = layout_gen.generate(spec)
        self.assertIn("接入骨干", html)
        self.assertNotIn("核心交换", html)

    def test_upward_link_draws_full_orthogonal_path(self):
        # 上行链路（目标在上方行）必须画完整双折线，不允许悬空水平线。
        spec = topology_spec([{"from": "a", "to": "s", "kind": "L"}])
        html = layout_gen.generate(spec)
        self.assertIn("M 178 280 V 184 H 380 V 88", html)

    def test_node_shapes_and_ghost(self):
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"}])
        spec["rows"][1]["nodes"][1]["shape"] = "db"
        spec["rows"][1]["nodes"][2]["shape"] = "cloud"
        spec["rows"][0]["nodes"][0]["ghost"] = True
        html = layout_gen.generate(spec)
        self.assertIn("<ellipse", html)                    # db 圆柱
        self.assertIn("translate(", html)                  # cloud 云朵
        self.assertIn('stroke-dasharray="6 4"', html)      # ghost 虚框
        self.assertIn('fill-opacity="0.55"', html)

    def _grp(self, name, *members):
        return {"kind": "group", "name": name, "members": list(members)}

    def _leaf(self, i):
        return {"id": f"n{i}", "name": f"节点{i}", "style": "srv"}

    def test_nested_group_geometry(self):
        # group 容器框 = 子成员包围盒 + ZONE_PAD/ZONE_HEAD；子成员落在框内。
        grp = self._grp("一组", self._leaf(1), self._leaf(2))
        nodes = {}
        kids, boxes, w, h = layout_gen.layout_members([grp], 0, 0, 0, nodes)
        g = boxes[0]
        self.assertEqual((g["w"], g["h"]), (2 * 168 + 64 + 48, 36 + 56 + 24))
        self.assertEqual((w, h), (g["w"], g["h"]))
        self.assertEqual(sorted(nodes), ["n1", "n2"])
        for k in kids:
            self.assertGreaterEqual(k["x"], g["x"])
            self.assertLessEqual(k["x"] + k["w"], g["x"] + g["w"])
            self.assertGreaterEqual(k["y"], g["y"])
            self.assertLessEqual(k["y"] + k["h"], g["y"] + g["h"])

    def test_group_depth_limit(self):
        deep = self._grp("一层", self._grp("二层", self._grp("三层", self._leaf(1))))
        layout_gen.layout_members([deep], 0, 0, 0, {})      # 3 层放行
        with self.assertRaises(SystemExit):
            layout_gen.layout_members([self._grp("四层", deep)], 0, 0, 0, {})

    def test_group_title_overflow_fails(self):
        grp = self._grp("一个远远超出容器标题宽度上限的分组名称", self._leaf(1))
        with self.assertRaises(AssertionError):
            layout_gen.layout_members([grp], 0, 0, 0, {})

    def test_group_zone_rejects_align(self):
        spec = topology_spec([])
        spec["zones"] = [{"name": "区", "members": [
            self._grp("组", self._leaf(1)),
            {"id": "x", "name": "节点", "style": "srv", "align": "s"}]}]
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_mirror_site_derivation(self):
        # 镜像站点：叶子 id 加 -b、同构组件同一水平线、twin.style 整站覆盖。
        region = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "应用域", "members": [{"id": "app", "name": "应用", "style": "srv"}]}]},
            {"name": "站点乙", "role": "备用站点", "style": "office"}]}
        nodes = {}
        r = layout_gen.layout_region(region, 0, 0, nodes)
        self.assertIn("app-b", nodes)
        self.assertEqual(nodes["app"]["y"], nodes["app-b"]["y"])
        self.assertEqual(nodes["app-b"]["style"], "office")
        self.assertEqual(r["legend"], {"srv": "服务器", "office": "备用站点"})

    def test_twin_rejects_other_fields(self):
        region = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "域", "members": [{"id": "a", "name": "应用", "style": "srv"}]}]},
            {"name": "站点乙", "domains": []}]}
        with self.assertRaises(SystemExit):
            layout_gen.layout_region(region, 0, 0, {})

    def test_region_and_zones_mutex(self):
        spec = topology_spec([])
        spec["zones"] = [{"name": "区", "members": [
            {"id": "x", "name": "节点", "style": "srv", "align": "s"}]}]
        spec["region"] = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "域", "members": [{"id": "a", "name": "应用", "style": "srv"}]}]}]}
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_cross_site_sync_detours_below_sites(self):
        # 镜像站间同步链路：绕行通道落在站点框下方、大区框内部，不穿节点。
        spec = topology_spec([])
        spec["region"] = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "数据域", "members": [
                    {"id": "db", "name": "数据库", "style": "srv"},
                    {"id": "cache", "name": "缓存", "style": "srv"}]}]},
            {"name": "站点乙", "style": "office"}]}
        spec["links"] = [{"from": "db", "to": "db-b", "kind": "L"}]
        region_top = 88 + 2 * (64 + 64)              # TOP + 两行(H+GAP) → rows_bottom + GAP
        site_bot = region_top + 44 + 36 + (36 + 56 + 24) + 48   # +REGION_HEAD+ZONE_HEAD+域高+SITE_PAD_BOT
        ch = site_bot + 24
        html = layout_gen.generate(spec)
        self.assertIn(f"V {ch} H", html)

    def test_region_generation_registers_mirror_links(self):
        # 对称链路只写 s→app：派生出 s→app-b 连通镜像站（缺派生直接 KeyError）。
        spec = topology_spec([{"from": "s", "to": "app", "kind": "L"}])
        spec["region"] = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "域", "members": [{"id": "app", "name": "应用", "style": "srv"}]}]},
            {"name": "站点乙", "style": "office"}]}
        html = layout_gen.generate(spec)
        self.assertEqual(html.count("应用"), 2)

    def test_expand_mirror_links_rules(self):
        # rows 节点无镜像则该端保持；带 -b 的跨站链路不派生；mirror:false 关闭。
        nodes = {"lb": {}, "lb-b": {}, "waf": {}, "waf-b": {}, "db": {}, "db-b": {}}
        links = [{"from": "lb", "to": "waf", "kind": "L"},
                 {"from": "db", "to": "db-b", "kind": "L"},
                 {"from": "lb", "to": "waf", "kind": "L", "mirror": False}]
        out = layout_gen.expand_mirror_links(links, nodes)
        self.assertEqual([(l["from"], l["to"]) for l in out],
                         [("lb", "waf"), ("db", "db-b"), ("lb", "waf"),
                          ("lb-b", "waf-b")])

    def test_mirror_link_double_write_fails(self):
        # 手写对称链 + 自动派生会画双线，必须失败。
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"},
                              {"from": "s", "to": "a-b", "kind": "L"}])
        spec["region"] = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "域", "members": [{"id": "a", "name": "应用", "style": "srv"}]}]},
            {"name": "站点乙", "style": "office"}]}
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_mirror_ghost_site(self):
        # twin ghost: true 整站虚框（备用=逻辑存在/未激活），主站不受染。
        region = {"name": "大区", "sites": [
            {"name": "站点甲", "domains": [
                {"name": "域", "members": [{"id": "a", "name": "应用", "style": "srv"}]}]},
            {"name": "站点乙", "style": "office", "ghost": True}]}
        nodes = {}
        layout_gen.layout_region(region, 0, 0, nodes)
        self.assertFalse(nodes["a"].get("ghost"))
        self.assertTrue(nodes["a-b"]["ghost"])

    def test_custom_style_declaration(self):
        # spec "styles" 声明制：色对生效、图例用声明名。
        spec = topology_spec([{"from": "s", "to": "a", "kind": "L"}])
        spec["styles"] = {"standby": ["#DCFCE7", "#15803D", "备用站点"]}
        spec["rows"][1]["style"] = "standby"
        html = layout_gen.generate(spec)
        self.assertIn('fill="#DCFCE7"', html)
        self.assertIn("备用站点", html)

    def test_custom_style_conflict_fails(self):
        spec = topology_spec([])
        spec["styles"] = {"core": ["#FFFFFF", "#000000", "重名"]}
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)

    def test_undeclared_style_fails(self):
        spec = topology_spec([])
        spec["rows"][1]["style"] = "没声明的样式"
        with self.assertRaises(SystemExit):
            layout_gen.generate(spec)


if __name__ == "__main__":
    unittest.main()
