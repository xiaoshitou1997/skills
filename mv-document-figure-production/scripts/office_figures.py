#!/usr/bin/env python3
"""List, insert and replace PNG pictures in existing DOCX/PPTX packages."""

import argparse
import copy
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import posixpath
import struct
import sys
import tempfile
import zipfile
import zlib
from xml.dom import Node, minidom


W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
IMAGE_REL = R + '/image'
SLIDE_REL = R + '/slide'
EMU = 914400
MAX_PART = 64 * 1024 * 1024
MAX_PACKAGE = 512 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
MAX_PIXELS = 64_000_000
MAX_RASTER = 256 * 1024 * 1024


class FigureError(ValueError):
    """A document or selector cannot be safely edited."""


def fail(message):
    raise FigureError(message)


def children(element, namespace=None, local=None):
    return [child for child in element.childNodes if child.nodeType == Node.ELEMENT_NODE
            and (namespace is None or child.namespaceURI == namespace)
            and (local is None or child.localName == local)]


def one(element, namespace, local, required=True):
    matches = children(element, namespace, local)
    if len(matches) != 1:
        if required or matches:
            fail(f'expected one {local} element, found {len(matches)}')
        return None
    return matches[0]


def descendants(element, namespace, local):
    return element.getElementsByTagNameNS(namespace, local)


def required_attr(element, name):
    value = element.getAttribute(name)
    if not value:
        fail(f'missing {name} on {element.tagName}')
    return value


def positive_int(value, label):
    try:
        number = int(value)
    except (ValueError, TypeError):
        fail(f'invalid {label}: {value}')
    if number <= 0:
        fail(f'{label} must be positive')
    return number


def nonnegative_int(value, label):
    try:
        number = int(value)
    except (ValueError, TypeError):
        fail(f'invalid {label}: {value}')
    if number < 0:
        fail(f'{label} must not be negative')
    return number


def inches(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        fail(f'invalid inch value: {value}')
    if not amount.is_finite() or amount < 0 or amount * EMU > 2**31 - 1:
        fail(f'inch value outside supported range: {value}')
    return int(amount * EMU + Decimal('0.5'))


def element(document, namespace, name, attrs=None):
    prefix = {W: 'w', WP: 'wp', A: 'a', PIC: 'pic', P: 'p', R: 'r'}[namespace]
    item = document.createElementNS(namespace, prefix + ':' + name)
    for key, value in (attrs or {}).items():
        item.setAttribute(key, str(value))
    return item


def append(parent, namespace, name, attrs=None):
    item = element(parent.ownerDocument, namespace, name, attrs)
    parent.appendChild(item)
    return item


def declare(root, bindings):
    for prefix, namespace in bindings.items():
        key = 'xmlns:' + prefix
        existing = root.getAttribute(key)
        if existing and existing != namespace:
            fail(f'incompatible {key} namespace')
        if not existing:
            root.setAttribute(key, namespace)


def check_ignorable(document, name):
    """minidom preserves prefixes; require all MC prefix references to remain bound."""
    for node in [document.documentElement, *document.getElementsByTagName('*')]:
        if not node.hasAttributes():
            continue
        for local in ('Ignorable', 'MustUnderstand', 'PreserveElements',
                      'PreserveAttributes', 'ProcessContent'):
            value = node.getAttributeNS(MC, local)
            if not value:
                continue
            for token in value.split():
                prefix = token.split(':', 1)[0]
                cursor = node
                while cursor.nodeType == Node.ELEMENT_NODE and not cursor.hasAttribute('xmlns:' + prefix):
                    cursor = cursor.parentNode
                if cursor.nodeType != Node.ELEMENT_NODE or not cursor.getAttribute('xmlns:' + prefix):
                    fail(f'unbound mc:{local} prefix {prefix!r} in {name}')


def xml(data, name):
    if len(data) > MAX_XML:
        fail(f'XML part is too large: {name}')
    if b'<!doctype' in data.lower() or b'<!entity' in data.lower():
        fail(f'DTD/entity declaration is unsupported: {name}')
    try:
        document = minidom.parseString(data)
    except Exception as exc:
        fail(f'malformed XML in {name}: {exc}')
    if document.doctype is not None:
        fail(f'DTD is unsupported: {name}')
    check_ignorable(document, name)
    return document


def png_dimensions(data):
    if len(data) < 57 or data[:8] != b'\x89PNG\r\n\x1a\n':
        fail('PNG signature or length is invalid')
    offset = 8
    dimensions = None
    has_idat = False
    has_iend = False
    decoder = zlib.decompressobj()
    decoded_bytes = 0
    while offset + 12 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            fail('truncated PNG chunk')
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        expected = struct.unpack_from('>I', data, offset + 8 + size)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != expected:
            fail('invalid PNG chunk checksum')
        if dimensions is None:
            if kind != b'IHDR' or size != 13:
                fail('invalid PNG IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (width < 1 or height < 1 or width * height > MAX_PIXELS
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)
                    or (color, depth) not in {(0, 1), (0, 2), (0, 4), (0, 8), (0, 16),
                                              (2, 8), (2, 16), (3, 1), (3, 2), (3, 4), (3, 8),
                                              (4, 8), (4, 16), (6, 8), (6, 16)}):
                fail('unsupported PNG dimensions or IHDR format')
            dimensions = (width, height)
        elif kind == b'IHDR':
            fail('duplicate PNG IHDR')
        if kind == b'IDAT':
            has_idat = True
            try:
                output = decoder.decompress(payload, MAX_RASTER - decoded_bytes + 1)
                decoded_bytes += len(output)
                if decoded_bytes > MAX_RASTER or decoder.unconsumed_tail or decoder.unused_data:
                    fail('PNG decompressed image exceeds size limit or contains trailing data')
            except zlib.error as exc:
                fail(f'invalid compressed PNG image: {exc}')
        if kind == b'IEND':
            if size or not has_idat or end != len(data) or not decoder.eof:
                fail('invalid PNG ending')
            has_iend = True
            break
        offset = end
    if not has_iend:
        fail('PNG is missing IEND')
    return dimensions


def read_png(path):
    try:
        if Path(path).stat().st_size > MAX_PART:
            fail('PNG exceeds size limit')
        data = Path(path).read_bytes()
    except OSError as exc:
        fail(f'cannot read PNG: {exc}')
    return data, png_dimensions(data)


def part_path(name):
    if (not name or '\\' in name or '\x00' in name or name.startswith('/')
            or ':' in name or any(piece in ('', '.', '..') for piece in name.split('/'))):
        fail(f'unsafe ZIP path: {name}')
    return name


class Package:
    def __init__(self, path):
        self.path = path
        self.parts = {}
        self.info = {}
        try:
            with zipfile.ZipFile(path) as archive:
                if len(archive.infolist()) > 10000:
                    fail('too many ZIP entries')
                total = 0
                seen = set()
                for item in archive.infolist():
                    name = item.filename
                    part_path(name[:-1] if name.endswith('/') else name)
                    key = name.casefold()
                    if key in seen:
                        fail(f'duplicate ZIP entry: {name}')
                    seen.add(key)
                    if (item.flag_bits & 1 or (item.create_system == 3
                            and (item.external_attr >> 16) & 0o170000 == 0o120000)):
                        fail(f'encrypted or symbolic link ZIP entry: {name}')
                    if item.is_dir():
                        continue
                    total += item.file_size
                    if item.file_size > MAX_PART or total > MAX_PACKAGE:
                        fail('ZIP uncompressed size limit exceeded')
                    self.parts[name] = archive.read(item)
                    self.info[name] = item
                if archive.testzip() is not None:
                    fail('ZIP checksum failed')
        except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
            fail(f'invalid Office ZIP: {exc}')
        for name, data in self.parts.items():
            if name.endswith(('.xml', '.rels')):
                xml(data, name)
        self.part('[Content_Types].xml', CT, 'Types')

    def part(self, name, namespace=None, local=None):
        if name not in self.parts:
            fail(f'missing package part: {name}')
        document = xml(self.parts[name], name)
        root = document.documentElement
        if namespace and (root.namespaceURI != namespace or root.localName != local):
            fail(f'unexpected root element in {name}')
        return document

    def save(self, output, updates, image_name, image_data, changed_part, relation_part):
        if image_name in self.parts or image_name in updates:
            fail('new image part already exists')
        fd, temporary = tempfile.mkstemp(prefix='.office-figures-', suffix='.tmp',
                                          dir=str(Path(output).parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w') as archive:
                for name, data in self.parts.items():
                    archive.writestr(copy.copy(self.info[name]), updates.get(name, data))
                for name, data in updates.items():
                    if name not in self.parts:
                        archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr(image_name, image_data, compress_type=zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    fail('output ZIP checksum failed')
                if (archive.read(image_name) != image_data
                        or archive.read(changed_part) != updates[changed_part]
                        or archive.read(relation_part) != updates[relation_part]):
                    fail('output image reference check failed')
            # Linking an already-validated temporary file creates the destination exclusively.
            os.link(temporary, output)
        finally:
            os.unlink(temporary)


def rels_path(source):
    return posixpath.join(posixpath.dirname(source), '_rels', posixpath.basename(source) + '.rels')


def target_path(source, relationship):
    if relationship.getAttribute('TargetMode'):
        fail('external relationship target is unsupported')
    target = required_attr(relationship, 'Target')
    if ('\\' in target or ':' in target or target.startswith('/') or '#' in target
            or '?' in target or any(piece == '..' for piece in target.split('/'))):
        # Relative ../ is legitimate for slides, but it must not escape the package.
        if not (target.startswith('../') and not any(c in target for c in ('\\', ':', '#', '?'))):
            fail(f'unsafe relationship target: {target}')
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
    part_path(normalized)
    return normalized


def relationships(package, source, required=True):
    name = rels_path(source)
    if name not in package.parts:
        if required:
            fail(f'missing relationships: {name}')
        doc = minidom.Document()
        root = doc.createElementNS(REL, 'Relationships')
        root.setAttribute('xmlns', REL)
        doc.appendChild(root)
        return name, doc, {}
    doc = package.part(name, REL, 'Relationships')
    found = {}
    for relation in children(doc.documentElement, REL, 'Relationship'):
        identifier = required_attr(relation, 'Id')
        if identifier in found:
            fail(f'duplicate relationship ID: {identifier}')
        found[identifier] = relation
    return name, doc, found


def relation_target(package, source, identifier, kind):
    _, _, rels = relationships(package, source)
    relation = rels.get(identifier)
    if relation is None or relation.getAttribute('Type') != kind:
        fail(f'missing {kind.rsplit("/", 1)[-1]} relationship: {identifier}')
    target = target_path(source, relation)
    if target not in package.parts:
        fail(f'missing relationship target: {target}')
    return target


def add_image_relationship(package, source, image_name):
    path, document, existing = relationships(package, source, required=False)
    number = 1
    while f'rId{number}' in existing:
        number += 1
    identifier = f'rId{number}'
    relationship = document.createElementNS(REL, 'Relationship')
    relationship.setAttribute('Id', identifier)
    relationship.setAttribute('Type', IMAGE_REL)
    relationship.setAttribute('Target', posixpath.relpath(image_name, posixpath.dirname(source)))
    document.documentElement.appendChild(relationship)
    return identifier, path, document.toxml(encoding='utf-8')


def image_part(package, directory):
    number = 1
    while f'{directory}/image{number}.png' in package.parts:
        number += 1
    return f'{directory}/image{number}.png'


def content_types(package):
    document = package.part('[Content_Types].xml', CT, 'Types')
    for item in children(document.documentElement, CT, 'Default'):
        if item.getAttribute('Extension').lower() == 'png':
            if item.getAttribute('ContentType') != 'image/png':
                fail('PNG extension has incompatible content type')
            return {}
    item = document.createElementNS(CT, 'Default')
    item.setAttribute('Extension', 'png')
    item.setAttribute('ContentType', 'image/png')
    document.documentElement.appendChild(item)
    return {'[Content_Types].xml': document.toxml(encoding='utf-8')}


def paragraph_text(paragraph):
    # A caption/anchor is the complete visible text of one paragraph, including split runs.
    result = []
    def visit(node):
        for child in node.childNodes:
            if child.nodeType != Node.ELEMENT_NODE:
                continue
            if child is not paragraph and child.namespaceURI == W and child.localName == 'p':
                continue
            if child.namespaceURI == W and child.localName == 't':
                result.append(''.join(n.data for n in child.childNodes if n.nodeType == Node.TEXT_NODE))
            elif child.namespaceURI == W and child.localName == 'tab':
                result.append('\t')
            elif child.namespaceURI == W and child.localName in ('br', 'cr'):
                result.append('\n')
            else:
                visit(child)
    visit(paragraph)
    return ''.join(result)


def adjacent_text(drawing):
    paragraph = drawing
    while paragraph is not None and not (paragraph.namespaceURI == W and paragraph.localName == 'p'):
        paragraph = paragraph.parentNode
    if paragraph is None:
        return []
    texts = []
    for direction in ('previousSibling', 'nextSibling'):
        node = getattr(paragraph, direction)
        while node is not None and node.nodeType != Node.ELEMENT_NODE:
            node = getattr(node, direction)
        if node is not None and node.namespaceURI == W and node.localName == 'p':
            texts.append(paragraph_text(node))
    return texts


def word_drawings(document):
    return list(descendants(document.documentElement, W, 'drawing'))


def drawing_id(drawing):
    items = descendants(drawing, WP, 'docPr')
    if len(items) != 1:
        fail('Word drawing needs exactly one docPr')
    return required_attr(items[0], 'id')


def picture_blip(container, mode):
    namespace = PIC if mode == 'docx' else P
    pictures = ([container] if container.namespaceURI == namespace
                and container.localName == 'pic' else list(descendants(container, namespace, 'pic')))
    if len(pictures) != 1:
        fail('selected drawing must contain exactly one picture')
    picture = pictures[0]
    fill = one(picture, PIC if mode == 'docx' else P, 'blipFill')
    # An empty <a:srcRect/> is emitted by Word and docx-js without cropping anything.
    crop = children(fill, A, 'srcRect')
    if len(crop) > 1 or (crop and (crop[0].attributes.length or children(crop[0]))):
        fail('cropped image fill is unsupported')
    if children(fill, A, 'tile'):
        fail('tiled image fill is unsupported')
    if len(children(fill)) != (3 if crop else 2):
        fail('unusual image fill is unsupported')
    stretch = one(fill, A, 'stretch')
    if (len(children(stretch)) != 1 or one(stretch, A, 'fillRect') is None
            or children(one(stretch, A, 'fillRect'))
            or one(stretch, A, 'fillRect').attributes.length):
        fail('nonstandard image stretch is unsupported')
    blip = one(fill, A, 'blip')
    if blip.childNodes or blip.hasAttributeNS(R, 'link'):
        fail('linked or modified image blip is unsupported')
    identifier = blip.getAttributeNS(R, 'embed')
    if not identifier:
        fail('embedded image relationship is missing')
    return picture, blip, identifier


def word_geometry(drawing):
    if len(children(drawing)) != 1:
        fail('unsupported Word drawing wrapper')
    inline = one(drawing, WP, 'inline')
    if inline is None:
        fail('anchored Word drawing is unsupported')
    effect = children(inline, WP, 'effectExtent')
    # Word always writes <wp:effectExtent l="0" t="0" r="0" b="0"/> for plain
    # pictures; any nonzero overhang means real effects this tool does not model.
    if len(effect) > 1 or (effect and (children(effect[0])
            or any(effect[0].getAttribute(side) not in ('', '0')
                   for side in ('l', 't', 'r', 'b')))):
        fail('effect-extended Word drawing is unsupported')
    extent = one(inline, WP, 'extent')
    width = positive_int(required_attr(extent, 'cx'), 'Word picture width')
    positive_int(required_attr(extent, 'cy'), 'Word picture height')
    picture, blip, identifier = picture_blip(inline, 'docx')
    shape = one(picture, PIC, 'spPr')
    transform = one(shape, A, 'xfrm', required=False)
    if transform is not None:
        if transform.hasAttributes():
            fail('rotated or flipped Word drawing is unsupported')
        size = one(transform, A, 'ext')
        offset = one(transform, A, 'off', required=False)
        if len(children(transform)) != (2 if offset is not None else 1):
            fail('unusual Word drawing geometry is unsupported')
        if offset is not None:
            nonnegative_int(required_attr(offset, 'x'), 'Word picture offset x')
            nonnegative_int(required_attr(offset, 'y'), 'Word picture offset y')
        positive_int(required_attr(size, 'cx'), 'Word picture width')
        positive_int(required_attr(size, 'cy'), 'Word picture height')
    if len(children(shape)) > (2 if transform is not None else 1):
        fail('unusual Word drawing picture styling is unsupported')
    geometry = one(shape, A, 'prstGeom')
    if geometry.getAttribute('prst') != 'rect':
        fail('nonrectangular Word picture is unsupported')
    return extent, transform, blip, identifier, width


def word_unique_id(package):
    ids = set()
    for name, data in package.parts.items():
        if name.startswith('word/') and name.endswith('.xml'):
            document = xml(data, name)
            for prop in descendants(document.documentElement, WP, 'docPr'):
                value = required_attr(prop, 'id')
                if value in ids:
                    fail(f'duplicate Word drawing ID: {value}')
                ids.add(value)
    number = 1
    while str(number) in ids:
        number += 1
    return number


def word_document(package):
    return package.part('word/document.xml', W, 'document')


def word_list(package):
    document = word_document(package)
    for drawing in word_drawings(document):
        identifier = drawing_id(drawing)
        captions = adjacent_text(drawing)
        try:
            _, _, _, relation, width = word_geometry(drawing)
            image = relation_target(package, 'word/document.xml', relation, IMAGE_REL)
            info = f'image={image} width={width / EMU:.2f}in'
        except FigureError as exc:
            info = f'unsupported={exc}'
        print(f'drawing-id={identifier} {info} adjacent={captions!r}')


def word_insert(package, args, dimensions, image_name, relation):
    document = word_document(package)
    anchors = [para for para in descendants(document.documentElement, W, 'p')
               if paragraph_text(para) == args.after]
    if len(anchors) != 1:
        fail(f'Word anchor must match one exact paragraph; found {len(anchors)}')
    anchor = anchors[0]
    if anchor.parentNode.namespaceURI not in (W,) or anchor.parentNode.localName not in ('body', 'tc'):
        fail('Word anchor lies in unsupported container')
    width = inches(args.width)
    if width < 1:
        fail('Word picture width must be positive')
    height = max(1, round(width * dimensions[1] / dimensions[0]))
    if height > 2**31 - 1:
        fail('Word image height exceeds supported range')
    identifier = word_unique_id(package)
    declare(document.documentElement, {'w': W, 'wp': WP, 'a': A, 'pic': PIC, 'r': R})
    paragraph = element(document, W, 'p')
    drawing = append(append(paragraph, W, 'r'), W, 'drawing')
    inline = append(drawing, WP, 'inline', {'distT': 0, 'distB': 0, 'distL': 0, 'distR': 0})
    append(inline, WP, 'extent', {'cx': width, 'cy': height})
    append(inline, WP, 'docPr', {'id': identifier, 'name': f'Figure {identifier}'})
    graphics = append(inline, A, 'graphic')
    graphic_data = append(graphics, A, 'graphicData', {'uri': PIC})
    picture = append(graphic_data, PIC, 'pic')
    props = append(picture, PIC, 'nvPicPr')
    append(props, PIC, 'cNvPr', {'id': 0, 'name': posixpath.basename(image_name)})
    append(props, PIC, 'cNvPicPr')
    fill = append(picture, PIC, 'blipFill')
    blip = append(fill, A, 'blip')
    blip.setAttributeNS(R, 'r:embed', relation)
    append(append(fill, A, 'stretch'), A, 'fillRect')
    shape = append(picture, PIC, 'spPr')
    append(append(shape, A, 'xfrm'), A, 'ext', {'cx': width, 'cy': height})
    append(append(shape, A, 'prstGeom', {'prst': 'rect'}), A, 'avLst')
    anchor.parentNode.insertBefore(paragraph, anchor.nextSibling)
    return document.toxml(encoding='utf-8'), f'drawing-id={identifier}'


def word_replace(package, args, dimensions, relation):
    document = word_document(package)
    drawings = word_drawings(document)
    if args.drawing_id is not None:
        matches = [item for item in drawings if drawing_id(item) == args.drawing_id]
    else:
        matches = drawings
    if args.caption is not None:
        matches = [item for item in matches if args.caption in adjacent_text(item)]
    if len(matches) != 1:
        fail(f'Word picture selector must match exactly one drawing; found {len(matches)}')
    drawing = matches[0]
    identifier = drawing_id(drawing)
    extent, transform, blip, old_relation, width = word_geometry(drawing)
    relation_target(package, 'word/document.xml', old_relation, IMAGE_REL)
    height = max(1, round(width * dimensions[1] / dimensions[0]))
    if height > 2**31 - 1:
        fail('Word image height exceeds supported range')
    extent.setAttribute('cy', str(height))
    if transform is not None:
        one(transform, A, 'ext').setAttribute('cx', str(width))
        one(transform, A, 'ext').setAttribute('cy', str(height))
    blip.setAttributeNS(R, 'r:embed', relation)
    return document.toxml(encoding='utf-8'), f'drawing-id={identifier}'


def slides(package):
    document = package.part('ppt/presentation.xml', P, 'presentation')
    slide_list = one(document.documentElement, P, 'sldIdLst')
    paths = []
    for slide_id in children(slide_list, P, 'sldId'):
        identifier = slide_id.getAttributeNS(R, 'id')
        if not identifier:
            fail('slide has no relationship ID')
        path = relation_target(package, 'ppt/presentation.xml', identifier, SLIDE_REL)
        if not path.startswith('ppt/slides/') or not path.endswith('.xml'):
            fail(f'unsupported slide target: {path}')
        paths.append(path)
    return paths


def slide_tree(package, path):
    document = package.part(path, P, 'sld')
    common = one(document.documentElement, P, 'cSld')
    tree = one(common, P, 'spTree')
    return document, tree


def shape_property(shape):
    tag = {'pic': 'nvPicPr', 'sp': 'nvSpPr', 'graphicFrame': 'nvGraphicFramePr',
           'cxnSp': 'nvCxnSpPr', 'grpSp': 'nvGrpSpPr'}.get(shape.localName)
    if tag is None:
        fail(f'unsupported PPT shape: {shape.tagName}')
    return one(one(shape, P, tag), P, 'cNvPr')


def slide_shapes(tree):
    return [item for item in descendants(tree, P, 'cNvPr')]


def slide_image_geometry(picture):
    if picture.parentNode.namespaceURI != P or picture.parentNode.localName != 'spTree':
        fail('grouped PowerPoint picture is unsupported')
    if len(children(picture)) != 3:
        fail('unusual PowerPoint picture styling is unsupported')
    _, blip, relation = picture_blip(picture, 'pptx')
    shape = one(picture, P, 'spPr')
    if len(children(shape)) != 2:
        fail('unusual PowerPoint picture geometry is unsupported')
    transform = one(shape, A, 'xfrm')
    if transform.attributes.length or len(children(transform)) != 2:
        fail('rotated or flipped PowerPoint image is unsupported')
    off = one(transform, A, 'off')
    ext = one(transform, A, 'ext')
    x = nonnegative_int(required_attr(off, 'x'), 'picture left')
    y = nonnegative_int(required_attr(off, 'y'), 'picture top')
    width = positive_int(required_attr(ext, 'cx'), 'picture width')
    height = positive_int(required_attr(ext, 'cy'), 'picture height')
    geometry = one(shape, A, 'prstGeom')
    if geometry.getAttribute('prst') != 'rect':
        fail('nonrectangular PowerPoint picture is unsupported')
    return off, ext, blip, relation, (x, y, width, height)


def fit_box(box, dimensions):
    x, y, width, height = box
    pixel_width, pixel_height = dimensions
    if width * pixel_height <= height * pixel_width:
        fitted_width = width
        fitted_height = max(1, round(width * pixel_height / pixel_width))
    else:
        fitted_height = height
        fitted_width = max(1, round(height * pixel_width / pixel_height))
    return (x + (width - fitted_width) // 2, y + (height - fitted_height) // 2,
            fitted_width, fitted_height)


def ppt_list(package):
    for number, path in enumerate(slides(package), 1):
        _, tree = slide_tree(package, path)
        print(f'slide={number} part={path}')
        for shape in children(tree):
            if shape.namespaceURI != P or shape.localName != 'pic':
                continue
            prop = shape_property(shape)
            try:
                _, _, _, relation, box = slide_image_geometry(shape)
                image = relation_target(package, path, relation, IMAGE_REL)
                details = f'image={image} box={tuple(round(v / EMU, 2) for v in box)}in'
            except FigureError as exc:
                details = f'unsupported={exc}'
            print(f'  shape-id={required_attr(prop, "id")} name={prop.getAttribute("name")!r} {details}')


def ppt_insert(package, path, args, dimensions, image_name, relation):
    document, tree = slide_tree(package, path)
    props = slide_shapes(tree)
    ids = {required_attr(item, 'id') for item in props}
    number = 1
    while str(number) in ids:
        number += 1
    if args.name and any(item.getAttribute('name') == args.name for item in props):
        fail('PowerPoint shape name already exists on slide')
    name = args.name or f'Figure {number}'
    left, top, width, height = (inches(value) for value in
                                (args.left, args.top, args.width, args.height))
    if not width or not height:
        fail('PowerPoint image box must have positive width and height')
    x, y, cx, cy = fit_box((left, top, width, height), dimensions)
    declare(document.documentElement, {'p': P, 'a': A, 'r': R})
    picture = append(tree, P, 'pic')
    props = append(picture, P, 'nvPicPr')
    append(props, P, 'cNvPr', {'id': number, 'name': name})
    append(append(props, P, 'cNvPicPr'), A, 'picLocks', {'noChangeAspect': '1'})
    append(props, P, 'nvPr')
    fill = append(picture, P, 'blipFill')
    blip = append(fill, A, 'blip')
    blip.setAttributeNS(R, 'r:embed', relation)
    append(append(fill, A, 'stretch'), A, 'fillRect')
    shape = append(picture, P, 'spPr')
    transform = append(shape, A, 'xfrm')
    append(transform, A, 'off', {'x': x, 'y': y})
    append(transform, A, 'ext', {'cx': cx, 'cy': cy})
    append(append(shape, A, 'prstGeom', {'prst': 'rect'}), A, 'avLst')
    return document.toxml(encoding='utf-8'), f'slide={args.slide} shape-id={number} name={name!r}'


def ppt_replace(package, path, args, dimensions, relation):
    document, tree = slide_tree(package, path)
    props = slide_shapes(tree)
    key = 'id' if args.shape_id is not None else 'name'
    value = args.shape_id if args.shape_id is not None else args.shape_name
    matches = [item for item in props if item.getAttribute(key) == value]
    if len(matches) != 1:
        fail(f'PowerPoint shape selector must match exactly one shape; found {len(matches)}')
    prop = matches[0]
    picture = prop.parentNode.parentNode
    if picture.namespaceURI != P or picture.localName != 'pic':
        fail('selected PowerPoint shape is not a picture')
    off, ext, blip, old_relation, box = slide_image_geometry(picture)
    relation_target(package, path, old_relation, IMAGE_REL)
    x, y, width, height = fit_box(box, dimensions)
    off.setAttribute('x', str(x))
    off.setAttribute('y', str(y))
    ext.setAttribute('cx', str(width))
    ext.setAttribute('cy', str(height))
    blip.setAttributeNS(R, 'r:embed', relation)
    return document.toxml(encoding='utf-8'), (f'slide={args.slide} '
                                                 f'shape-id={required_attr(prop, "id")}')


def output_path(input_path, output):
    source = Path(input_path).resolve(strict=True)
    destination = Path(output)
    if source == destination.resolve() or os.path.lexists(destination):
        fail('output must be a different, nonexistent path')
    if not destination.parent.is_dir():
        fail('output parent directory does not exist')
    return str(destination)


def run(args):
    package = Package(args.input)
    if args.format == 'docx':
        if not {'word/document.xml', '[Content_Types].xml'}.issubset(package.parts):
            fail('input is not a DOCX package')
        if args.action == 'list':
            word_list(package)
            return
        source = 'word/document.xml'
        directory = 'word/media'
    else:
        paths = slides(package)
        if args.action == 'list':
            ppt_list(package)
            return
        if args.slide > len(paths):
            fail(f'slide {args.slide} does not exist')
        source = paths[args.slide - 1]
        if paths.count(source) != 1:
            fail('selected slide part is shared by multiple slide positions')
        directory = 'ppt/media'
    output = output_path(args.input, args.output)
    image_data, dimensions = read_png(args.png)
    image_name = image_part(package, directory)
    relation, rel_path, rel_data = add_image_relationship(package, source, image_name)
    if args.format == 'docx':
        if args.action == 'insert':
            changed, result = word_insert(package, args, dimensions, image_name, relation)
        else:
            changed, result = word_replace(package, args, dimensions, relation)
    elif args.action == 'insert':
        changed, result = ppt_insert(package, source, args, dimensions, image_name, relation)
    else:
        changed, result = ppt_replace(package, source, args, dimensions, relation)
    updates = {source: changed, rel_path: rel_data, **content_types(package)}
    # Ensure the relationship resolves to the unique, newly embedded image before publishing.
    updated = xml(changed, source)
    blips = [item for item in descendants(updated.documentElement, A, 'blip')
             if item.getAttributeNS(R, 'embed') == relation]
    new_relations = [item for item in children(xml(rel_data, rel_path).documentElement,
                                                REL, 'Relationship')
                     if item.getAttribute('Id') == relation]
    if (len(blips) != 1 or len(new_relations) != 1
            or new_relations[0].getAttribute('Type') != IMAGE_REL
            or target_path(source, new_relations[0]) != image_name):
        fail('new image relationship did not resolve uniquely')
    package.save(output, updates, image_name, image_data, source, rel_path)
    print(f'{result} image={image_name} output={output}')


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    formats = root.add_subparsers(dest='format', required=True)
    for kind in ('docx', 'pptx'):
        fmt = formats.add_parser(kind)
        actions = fmt.add_subparsers(dest='action', required=True)
        listing = actions.add_parser('list', help='List picture IDs and adjacent text or shape names')
        listing.add_argument('input')
        for action in ('insert', 'replace'):
            command = actions.add_parser(action)
            command.add_argument('input')
            command.add_argument('output')
            command.add_argument('--png', required=True)
            if kind == 'docx' and action == 'insert':
                command.add_argument('--after', required=True, help='Unique exact paragraph text')
                command.add_argument('--width', required=True, help='Picture width in inches')
            if kind == 'docx' and action == 'replace':
                command.add_argument('--drawing-id', help='Word docPr ID')
                command.add_argument('--caption', help='Unique exact text in an adjacent paragraph')
            if kind == 'pptx':
                command.add_argument('--slide', type=int, required=True, help='One-based slide position')
                if action == 'insert':
                    for name in ('left', 'top', 'width', 'height'):
                        command.add_argument('--' + name, required=True, help='Inches')
                    command.add_argument('--name', help='Unique picture shape name')
                else:
                    selected = command.add_mutually_exclusive_group(required=True)
                    selected.add_argument('--shape-id', help='Slide shape ID')
                    selected.add_argument('--shape-name', help='Unique exact slide shape name')
    return root


def main():
    arguments = parser().parse_args()
    try:
        if (arguments.format == 'docx' and arguments.action == 'replace'
                and arguments.drawing_id is None and arguments.caption is None):
            fail('specify --drawing-id or --caption for Word replacement')
        if (arguments.format == 'pptx' and arguments.action != 'list'
                and arguments.slide < 1):
            fail('slide number must be positive')
        run(arguments)
    except (FigureError, OSError, zipfile.BadZipFile) as exc:
        print(f'office_figures: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
