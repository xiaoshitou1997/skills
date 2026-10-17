"""End-to-end OOXML figure CLI tests, with original stdlib-only Office fixtures."""

import posixpath
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "mv-document-figure-production" / "scripts" / "office_figures.py"
EMU = 914400
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
for prefix in ("w", "wp", "a", "pic", "p", "r"):
    ET.register_namespace(prefix, NS[prefix])
ET.register_namespace("", NS["rel"])


def q(prefix, local):
    return f"{{{NS[prefix]}}}{local}"


def element(prefix, local, **attrs):
    return ET.Element(q(prefix, local), attrs)


def child(parent, prefix, local, **attrs):
    return ET.SubElement(parent, q(prefix, local), attrs)


def xml(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def png(width, height, rgb):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\0" + bytes(rgb) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def relationships(*entries):
    root = element("rel", "Relationships")
    for rel_id, kind, target in entries:
        child(root, "rel", "Relationship", Id=rel_id,
              Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/" + kind,
              Target=target)
    # Relationship parts conventionally use the default namespace.
    return xml(root)


def types(default_types, overrides):
    root = element("ct", "Types")
    for extension, content_type in default_types.items():
        child(root, "ct", "Default", Extension=extension, ContentType=content_type)
    for part, content_type in overrides.items():
        child(root, "ct", "Override", PartName="/" + part, ContentType=content_type)
    return xml(root)


def write_package(path, parts):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for part, data in parts.items():
            archive.writestr(part, data)


def word_picture(drawing_id, rel_id, width=2 * EMU, height=EMU, cropped=False):
    # Mirrors the markup Word and docx-js emit: zero effectExtent, empty srcRect.
    run = element("w", "r")
    drawing = child(run, "w", "drawing")
    inline = child(drawing, "wp", "inline", distT="0", distB="0", distL="0", distR="0")
    child(inline, "wp", "extent", cx=str(width), cy=str(height))
    child(inline, "wp", "effectExtent", l="0", t="0", r="0", b="0")
    child(inline, "wp", "docPr", id=str(drawing_id), name=f"Picture {drawing_id}")
    frame = child(inline, "wp", "cNvGraphicFramePr")
    child(frame, "a", "graphicFrameLocks", noChangeAspect="1")
    graphic = child(inline, "a", "graphic")
    graphic_data = child(graphic, "a", "graphicData", uri=NS["pic"])
    picture = child(graphic_data, "pic", "pic")
    nv = child(picture, "pic", "nvPicPr")
    child(nv, "pic", "cNvPr", id="0", name="shared.png")
    child(nv, "pic", "cNvPicPr")
    fill = child(picture, "pic", "blipFill")
    child(fill, "a", "blip", cstate="none", **{q("r", "embed"): rel_id})
    if cropped:
        child(fill, "a", "srcRect", l="10000", t="10000")
    else:
        child(fill, "a", "srcRect")
    stretch = child(fill, "a", "stretch")
    child(stretch, "a", "fillRect")
    shape = child(picture, "pic", "spPr", bwMode="auto")
    xfrm = child(shape, "a", "xfrm")
    child(xfrm, "a", "off", x="0", y="0")
    child(xfrm, "a", "ext", cx=str(width), cy=str(height))
    geometry = child(shape, "a", "prstGeom", prst="rect")
    child(geometry, "a", "avLst")
    return run


def make_docx(path, markers=("[[FIGURE:one]]",), shared=False, cropped=False):
    document = element("w", "document")
    body = child(document, "w", "body")
    for marker in markers:
        paragraph = child(body, "w", "p")
        text = child(child(paragraph, "w", "r"), "w", "t")
        text.text = marker
    if shared:
        for drawing_id in (7, 8):
            child(body, "w", "p").append(word_picture(drawing_id, "rId2"))
    if cropped:
        child(body, "w", "p").append(word_picture(7, "rId2", cropped=True))
    child(body, "w", "sectPr")
    defaults = {"rels": "application/vnd.openxmlformats-package.relationships+xml",
                "xml": "application/xml", "png": "image/png"}
    parts = {
        "[Content_Types].xml": types(defaults, {"word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"}),
        "_rels/.rels": relationships(("rId1", "officeDocument", "word/document.xml")),
        "word/document.xml": xml(document),
        "word/_rels/document.xml.rels": relationships(("rId2", "image", "media/shared.png")) if (shared or cropped) else relationships(),
    }
    if shared or cropped:
        parts["word/media/shared.png"] = png(2, 1, (200, 10, 10))
    write_package(path, parts)


def shape_tree():
    tree = element("p", "spTree")
    nv = child(tree, "p", "nvGrpSpPr")
    child(nv, "p", "cNvPr", id="1", name="")
    child(nv, "p", "cNvGrpSpPr")
    child(nv, "p", "nvPr")
    xfrm = child(child(tree, "p", "grpSpPr"), "a", "xfrm")
    for tag in ("off", "ext", "chOff", "chExt"):
        child(xfrm, "a", tag, **({"x": "0", "y": "0"} if "off" in tag.lower() else {"cx": "0", "cy": "0"}))
    return tree


def slide_picture(shape_id, name, rel_id, x=EMU, y=EMU, width=4 * EMU, height=2 * EMU):
    picture = element("p", "pic")
    nv = child(picture, "p", "nvPicPr")
    child(nv, "p", "cNvPr", id=str(shape_id), name=name)
    locks = child(nv, "p", "cNvPicPr")
    child(locks, "a", "picLocks", noChangeAspect="1")
    child(nv, "p", "nvPr")
    fill = child(picture, "p", "blipFill")
    child(fill, "a", "blip", **{q("r", "embed"): rel_id})
    child(child(fill, "a", "stretch"), "a", "fillRect")
    shape = child(picture, "p", "spPr")
    xfrm = child(shape, "a", "xfrm")
    child(xfrm, "a", "off", x=str(x), y=str(y))
    child(xfrm, "a", "ext", cx=str(width), cy=str(height))
    child(child(shape, "a", "prstGeom", prst="rect"), "a", "avLst")
    return picture


def theme():
    root = element("a", "theme", name="Fixture Theme")
    elements = child(root, "a", "themeElements")
    colors = child(elements, "a", "clrScheme", name="Fixture")
    for name, value in (("dk1", "000000"), ("lt1", "FFFFFF"), ("dk2", "222222"), ("lt2", "EEEEEE"),
                        ("accent1", "4472C4"), ("accent2", "ED7D31"), ("accent3", "A5A5A5"),
                        ("accent4", "FFC000"), ("accent5", "5B9BD5"), ("accent6", "70AD47"),
                        ("hlink", "0563C1"), ("folHlink", "954F72")):
        child(child(colors, "a", name), "a", "srgbClr", val=value)
    fonts = child(elements, "a", "fontScheme", name="Fixture")
    for name in ("majorFont", "minorFont"):
        font = child(fonts, "a", name)
        child(font, "a", "latin", typeface="Arial")
        child(font, "a", "ea", typeface="")
        child(font, "a", "cs", typeface="")
    formats = child(elements, "a", "fmtScheme", name="Fixture")
    fills = child(formats, "a", "fillStyleLst")
    lines = child(formats, "a", "lnStyleLst")
    effects = child(formats, "a", "effectStyleLst")
    backgrounds = child(formats, "a", "bgFillStyleLst")
    for _ in range(3):
        child(child(fills, "a", "solidFill"), "a", "schemeClr", val="accent1")
        line = child(lines, "a", "ln", w="9525")
        child(child(line, "a", "solidFill"), "a", "schemeClr", val="accent1")
        child(line, "a", "prstDash", val="solid")
        child(child(effects, "a", "effectStyle"), "a", "effectLst")
        child(child(backgrounds, "a", "solidFill"), "a", "schemeClr", val="lt1")
    return xml(root)


def make_pptx(path, shared=False):
    presentation = element("p", "presentation")
    masters = child(presentation, "p", "sldMasterIdLst")
    child(masters, "p", "sldMasterId", id="2147483648", **{q("r", "id"): "rId1"})
    slides = child(presentation, "p", "sldIdLst")
    for n in (1, 2):
        child(slides, "p", "sldId", id=str(255 + n), **{q("r", "id"): f"rId{n + 1}"})
    child(presentation, "p", "sldSz", cx=str(10 * EMU), cy=str(6 * EMU), type="screen4x3")
    child(presentation, "p", "notesSz", cx=str(6 * EMU), cy=str(8 * EMU))

    master = element("p", "sldMaster")
    child(master, "p", "cSld").append(shape_tree())
    child(master, "p", "clrMap", accent1="accent1", accent2="accent2", accent3="accent3",
          accent4="accent4", accent5="accent5", accent6="accent6", bg1="lt1", bg2="lt2",
          tx1="dk1", tx2="dk2", hlink="hlink", folHlink="folHlink")
    child(child(master, "p", "sldLayoutIdLst"), "p", "sldLayoutId", id="2147483649", **{q("r", "id"): "rId1"})
    layout = element("p", "sldLayout", type="blank", preserve="1")
    child(layout, "p", "cSld").append(shape_tree())
    child(child(layout, "p", "clrMapOvr"), "a", "masterClrMapping")

    parts = {
        "[Content_Types].xml": types(
            {"rels": "application/vnd.openxmlformats-package.relationships+xml", "xml": "application/xml", "png": "image/png"},
            {"ppt/presentation.xml": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
             "ppt/slideMasters/slideMaster1.xml": "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
             "ppt/slideLayouts/slideLayout1.xml": "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
             "ppt/theme/theme1.xml": "application/vnd.openxmlformats-officedocument.theme+xml",
             **{f"ppt/slides/slide{n}.xml": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml" for n in (1, 2)}}),
        "_rels/.rels": relationships(("rId1", "officeDocument", "ppt/presentation.xml")),
        "ppt/presentation.xml": xml(presentation),
        "ppt/_rels/presentation.xml.rels": relationships(("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                                                      ("rId2", "slide", "slides/slide1.xml"),
                                                      ("rId3", "slide", "slides/slide2.xml")),
        "ppt/slideMasters/slideMaster1.xml": xml(master),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": relationships(("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                                                                    ("rId2", "theme", "../theme/theme1.xml")),
        "ppt/slideLayouts/slideLayout1.xml": xml(layout),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": relationships(("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")),
        "ppt/theme/theme1.xml": theme(),
    }
    for n in (1, 2):
        slide = element("p", "sld")
        tree = shape_tree()
        if shared and n == 1:
            tree.append(slide_picture(7, "target", "rId2"))
            tree.append(slide_picture(8, "untouched", "rId2", x=5 * EMU))
        child(slide, "p", "cSld").append(tree)
        child(child(slide, "p", "clrMapOvr"), "a", "masterClrMapping")
        part = f"ppt/slides/slide{n}.xml"
        parts[part] = xml(slide)
        rel_entries = [("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")]
        if shared and n == 1:
            rel_entries.append(("rId2", "image", "../media/shared.png"))
        parts[f"ppt/slides/_rels/slide{n}.xml.rels"] = relationships(*rel_entries)
    if shared:
        parts["ppt/media/shared.png"] = png(2, 1, (200, 10, 10))
    write_package(path, parts)


def validate_package(path):
    """Check every internal relationship and the content type of each inserted image."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP member"
        assert archive.testzip() is None
        content_types = ET.fromstring(archive.read("[Content_Types].xml"))
        png_default = [node for node in content_types.findall("ct:Default", NS)
                       if node.get("Extension") == "png" and node.get("ContentType") == "image/png"]
        assert png_default, "PNG content type missing"
        for rels_path in (name for name in names if name.endswith(".rels")):
            if rels_path == "_rels/.rels":
                base = ""
            else:
                folder, filename = posixpath.split(rels_path)
                base = posixpath.dirname(folder)
                assert filename.endswith(".rels")
            for rel in ET.fromstring(archive.read(rels_path)):
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "").split("#", 1)[0]
                resolved = posixpath.normpath(posixpath.join(base, target.lstrip("/"))) if not target.startswith("/") else target.lstrip("/")
                assert resolved in names, f"{rels_path}: missing {resolved}"
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                ET.fromstring(archive.read(name))


def image_for(archive, xml_part, rel_id):
    folder, filename = posixpath.split(xml_part)
    rels_path = posixpath.join(folder, "_rels", filename + ".rels")
    matches = [rel for rel in ET.fromstring(archive.read(rels_path)) if rel.get("Id") == rel_id]
    assert len(matches) == 1
    assert matches[0].get("Type", "").endswith("/image")
    target = matches[0].get("Target")
    assert not target.startswith("/")
    return archive.read(posixpath.normpath(posixpath.join(folder, target)))


def word_drawings(archive):
    root = ET.fromstring(archive.read("word/document.xml"))
    result = {}
    for inline in root.findall(".//wp:inline", NS):
        doc_pr = inline.find("wp:docPr", NS)
        blip = inline.find(".//a:blip", NS)
        extent = inline.find("wp:extent", NS)
        result[int(doc_pr.get("id"))] = (blip.get(q("r", "embed")), int(extent.get("cx")), int(extent.get("cy")))
    return root, result


def slide_pictures(archive, number=1):
    part = f"ppt/slides/slide{number}.xml"
    root = ET.fromstring(archive.read(part))
    result = {}
    for picture in root.findall(".//p:pic", NS):
        prop = picture.find("p:nvPicPr/p:cNvPr", NS)
        blip = picture.find("p:blipFill/a:blip", NS)
        off = picture.find("p:spPr/a:xfrm/a:off", NS)
        ext = picture.find("p:spPr/a:xfrm/a:ext", NS)
        result[int(prop.get("id"))] = (prop.get("name"), blip.get(q("r", "embed")),
                                        tuple(int(off.get(k)) for k in ("x", "y")) +
                                        tuple(int(ext.get(k)) for k in ("cx", "cy")))
    return result


class OfficeFigureCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.wide = self.base / "wide.png"
        self.tall = self.base / "tall.png"
        self.wide.write_bytes(png(2, 1, (10, 160, 20)))
        self.tall.write_bytes(png(1, 2, (30, 40, 220)))

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)],
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_docx_insert_list_and_reopen(self):
        source, output = self.base / "source.docx", self.base / "output.docx"
        make_docx(source)
        self.cli("docx", "insert", source, output, "--after", "[[FIGURE:one]]", "--png", self.wide, "--width", "4")
        validate_package(output)
        with zipfile.ZipFile(output) as archive:
            root, drawings = word_drawings(archive)
            self.assertEqual(len(drawings), 1)
            drawing_id, (rel_id, width, height) = next(iter(drawings.items()))
            self.assertAlmostEqual(width, 4 * EMU, delta=2)
            self.assertAlmostEqual(height, 2 * EMU, delta=2)
            self.assertEqual(image_for(archive, "word/document.xml", rel_id), self.wide.read_bytes())
            paragraphs = root.findall("w:body/w:p", NS)
            anchor_index = next(i for i, paragraph in enumerate(paragraphs)
                                if "[[FIGURE:one]]" in "".join(t.text or "" for t in paragraph.findall(".//w:t", NS)))
            self.assertIsNotNone(paragraphs[anchor_index + 1].find(".//wp:inline", NS))
        self.assertIn(str(drawing_id), self.cli("docx", "list", output).stdout)

    def test_docx_replace_does_not_change_another_drawing_sharing_media(self):
        source, output = self.base / "shared.docx", self.base / "replaced.docx"
        make_docx(source, shared=True)
        listing = self.cli("docx", "list", source).stdout
        self.assertIn("7", listing)
        self.assertIn("8", listing)
        self.cli("docx", "replace", source, output, "--drawing-id", "7", "--png", self.tall)
        validate_package(output)
        with zipfile.ZipFile(output) as archive:
            _, drawings = word_drawings(archive)
            self.assertEqual(set(drawings), {7, 8})
            self.assertEqual(image_for(archive, "word/document.xml", drawings[7][0]), self.tall.read_bytes())
            self.assertEqual(image_for(archive, "word/document.xml", drawings[8][0]), png(2, 1, (200, 10, 10)))
            self.assertEqual(drawings[7][1], 2 * EMU)
            self.assertAlmostEqual(drawings[7][2], 4 * EMU, delta=2)
            self.assertEqual(drawings[8][1:], (2 * EMU, EMU))

    def test_docx_rejects_ambiguous_marker_missing_id_and_unsafe_outputs(self):
        source, output = self.base / "source.docx", self.base / "new.docx"
        make_docx(source, markers=("same", "same"))
        self.cli("docx", "insert", source, output, "--after", "same", "--png", self.wide, "--width", "2", success=False)
        self.assertFalse(output.exists())
        self.cli("docx", "replace", source, output, "--drawing-id", "77", "--png", self.wide, success=False)
        self.assertFalse(output.exists())
        before = source.read_bytes()
        self.cli("docx", "insert", source, source, "--after", "same", "--png", self.wide, "--width", "2", success=False)
        self.assertEqual(source.read_bytes(), before)
        output.write_bytes(b"keep this output")
        self.cli("docx", "insert", source, output, "--after", "same", "--png", self.wide, "--width", "2", success=False)
        self.assertEqual(output.read_bytes(), b"keep this output")

    def test_docx_rejects_real_crop_but_accepts_docx_js_markup(self):
        source, output = self.base / "cropped.docx", self.base / "new.docx"
        make_docx(source, cropped=True)
        result = self.cli("docx", "replace", source, output, "--drawing-id", "7", "--png", self.tall,
                          success=False)
        self.assertIn("cropped", result.stderr)
        self.assertFalse(output.exists())

    def test_docx_rejects_duplicate_zip_member(self):
        source, output = self.base / "duplicated.docx", self.base / "new.docx"
        make_docx(source)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(source, "a") as archive:
                archive.writestr("word/document.xml", archive.read("word/document.xml"))
        self.cli("docx", "insert", source, output, "--after", "[[FIGURE:one]]", "--png", self.wide,
                 "--width", "2", success=False)
        self.assertFalse(output.exists())

    def test_pptx_insert_on_multiple_slides_and_list(self):
        source, first, output = (self.base / name for name in ("source.pptx", "first.pptx", "output.pptx"))
        make_pptx(source)
        self.cli("pptx", "insert", source, first, "--slide", "1", "--png", self.wide,
                 "--left", "1", "--top", "1", "--width", "4", "--height", "4", "--name", "wide")
        self.cli("pptx", "insert", first, output, "--slide", "2", "--png", self.tall,
                 "--left", "3", "--top", "0.5", "--width", "3", "--height", "3", "--name", "tall")
        validate_package(output)
        with zipfile.ZipFile(output) as archive:
            for number, label, data, area, ratio in (
                (1, "wide", self.wide.read_bytes(), (1, 1, 4, 4), 2),
                (2, "tall", self.tall.read_bytes(), (3, .5, 3, 3), .5),
            ):
                pictures = slide_pictures(archive, number)
                self.assertEqual(len(pictures), 1)
                _, (name, rel_id, (x, y, width, height)) = next(iter(pictures.items()))
                self.assertEqual(name, label)
                self.assertEqual(image_for(archive, f"ppt/slides/slide{number}.xml", rel_id), data)
                left, top, box_width, box_height = (v * EMU for v in area)
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                self.assertAlmostEqual(width / height, ratio, delta=.00001)
                self.assertAlmostEqual(x + width / 2, left + box_width / 2, delta=2)
                self.assertAlmostEqual(y + height / 2, top + box_height / 2, delta=2)
                self.assertLessEqual(x + width, left + box_width + 2)
                self.assertLessEqual(y + height, top + box_height + 2)
        listing = self.cli("pptx", "list", output).stdout
        self.assertIn("wide", listing)
        self.assertIn("tall", listing)

    def test_pptx_replace_by_id_preserves_other_shape_with_shared_media(self):
        source, output = self.base / "shared.pptx", self.base / "by-id.pptx"
        make_pptx(source, shared=True)
        listing = self.cli("pptx", "list", source).stdout
        self.assertIn("target", listing)
        self.assertIn("untouched", listing)
        self.cli("pptx", "replace", source, output, "--slide", "1", "--shape-id", "7", "--png", self.tall)
        validate_package(output)
        with zipfile.ZipFile(output) as archive:
            pictures = slide_pictures(archive)
            self.assertEqual(set(pictures), {7, 8})
            self.assertEqual(image_for(archive, "ppt/slides/slide1.xml", pictures[7][1]), self.tall.read_bytes())
            self.assertEqual(image_for(archive, "ppt/slides/slide1.xml", pictures[8][1]), png(2, 1, (200, 10, 10)))
            x, y, width, height = pictures[7][2]
            self.assertAlmostEqual(width / height, .5, delta=.00001)
            self.assertAlmostEqual(x + width / 2, 3 * EMU, delta=2)
            self.assertAlmostEqual(y + height / 2, 2 * EMU, delta=2)
            self.assertEqual(pictures[8][2], (5 * EMU, EMU, 4 * EMU, 2 * EMU))
            self.assertFalse(slide_pictures(archive, 2))

    def test_pptx_replace_by_name_and_reject_invalid_targets(self):
        source, output = self.base / "shared.pptx", self.base / "by-name.pptx"
        make_pptx(source, shared=True)
        self.cli("pptx", "replace", source, output, "--slide", "1", "--shape-name", "target", "--png", self.tall)
        validate_package(output)
        with zipfile.ZipFile(output) as archive:
            pictures = slide_pictures(archive)
            self.assertEqual(image_for(archive, "ppt/slides/slide1.xml", pictures[7][1]), self.tall.read_bytes())
            self.assertEqual(image_for(archive, "ppt/slides/slide1.xml", pictures[8][1]), png(2, 1, (200, 10, 10)))
        missing = self.base / "missing.pptx"
        self.cli("pptx", "replace", source, missing, "--slide", "2", "--shape-id", "7", "--png", self.wide,
                 success=False)
        self.assertFalse(missing.exists())
        self.cli("pptx", "insert", source, missing, "--slide", "3", "--png", self.wide,
                 "--left", "1", "--top", "1", "--width", "2", "--height", "2", success=False)
        self.assertFalse(missing.exists())
        before = source.read_bytes()
        self.cli("pptx", "replace", source, source, "--slide", "1", "--shape-id", "7", "--png", self.wide,
                 success=False)
        self.assertEqual(source.read_bytes(), before)
        self.cli("pptx", "replace", source, output, "--slide", "1", "--shape-id", "7", "--png", self.wide,
                 success=False)
        validate_package(output)

    def test_pptx_rejects_duplicate_zip_member(self):
        source, output = self.base / "duplicated.pptx", self.base / "new.pptx"
        make_pptx(source)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(source, "a") as archive:
                archive.writestr("ppt/slides/slide1.xml", archive.read("ppt/slides/slide1.xml"))
        self.cli("pptx", "insert", source, output, "--slide", "1", "--png", self.wide,
                 "--left", "1", "--top", "1", "--width", "2", "--height", "2", success=False)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
