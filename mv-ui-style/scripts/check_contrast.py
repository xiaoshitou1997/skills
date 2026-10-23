#!/usr/bin/env python3
"""WCAG 对比度校验：校验前景/背景颜色对的对比度是否达标。

用法：check_contrast.py [--min N] <前景> <背景> [<前景> <背景> ...]
颜色格式：#rgb 或 #rrggbb 十六进制；oklch(L C H)，按 CSS Color 4
定义转换到 sRGB。sRGB 色域外的推导值按通道截断并在输出标注。
每对输出对比度与判定；任一对低于阈值时退出码 1；参数缺失或
颜色无法解析时退出码 2 并写 stderr。阈值默认 4.5（WCAG 2.1 AA
正文文字），纯 UI 部件对可用 --min 3。
"""
import math
import re
import sys

USAGE = ('用法: check_contrast.py [--min N] <前景> <背景> '
         '[<前景> <背景> ...]')
HEX6_RE = re.compile(r'#([0-9a-fA-F]{6})\Z')
HEX3_RE = re.compile(r'#([0-9a-fA-F]{3})\Z')
OKLCH_RE = re.compile(
    r'oklch\(\s*(\d(?:\.\d+)?)\s+([+-]?\d(?:\.\d+)?)'
    r'\s+([+-]?\d+(?:\.\d+)?)\s*\)')


def fail(message):
    print('check_contrast: ' + message, file=sys.stderr)
    sys.exit(2)


def decode_srgb(channel):
    """sRGB 编码值转线性值，WCAG 2.1 相对亮度定义的分段函数。"""
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def encode_srgb(channel):
    """线性值转 sRGB 编码值，CSS Color 4 分段函数。"""
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_linear(text):
    body = text[1:]
    if len(body) == 3:
        body = ''.join(ch * 2 for ch in body)
    encoded = [int(body[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [decode_srgb(c) for c in encoded]


def oklch_to_linear(match):
    """OKLCH 转线性 sRGB，矩阵取自 CSS Color 4 规范公式。"""
    lightness = float(match.group(1))
    chroma = float(match.group(2))
    hue = math.radians(float(match.group(3)))
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)
    lms = [
        (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3,
        (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3,
        (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3,
    ]
    return [
        4.0767416621 * lms[0] - 3.3077115913 * lms[1] + 0.2309699292 * lms[2],
        -1.2684380046 * lms[0] + 2.6097574011 * lms[1] - 0.3413193965 * lms[2],
        -0.0041960863 * lms[0] - 0.7034186147 * lms[1] + 1.7076147010 * lms[2],
    ]


def parse_color(text):
    match = HEX6_RE.fullmatch(text) or HEX3_RE.fullmatch(text)
    if match:
        return hex_to_linear(match.group(0)), False
    match = OKLCH_RE.fullmatch(text)
    if match:
        linear = oklch_to_linear(match)
        clipped = any(c < 0.0 or c > 1.0 for c in linear)
        return [min(1.0, max(0.0, c)) for c in linear], clipped
    return None, None


def luminance(linear):
    return (0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2])


def display(linear):
    return '#' + ''.join(
        '%02x' % round(encode_srgb(c) * 255) for c in linear)


def main(argv):
    threshold = 4.5
    args = argv[1:]
    if args and args[0] == '--min':
        if len(args) < 2:
            fail(USAGE)
        try:
            threshold = float(args[1])
        except ValueError:
            fail('--min 阈值需要数字: ' + args[1])
        if threshold <= 0:
            fail('--min 阈值必须为正数')
        args = args[2:]
    pairs = []
    for index in range(0, len(args), 2):
        if index + 1 >= len(args):
            fail(USAGE)
        pairs.append((args[index], args[index + 1]))
    if not pairs:
        fail(USAGE)
    failures = 0
    for foreground_text, background_text in pairs:
        foreground, clipped_fg = parse_color(foreground_text)
        background, clipped_bg = parse_color(background_text)
        if foreground is None:
            fail('无法解析颜色: ' + foreground_text)
        if background is None:
            fail('无法解析颜色: ' + background_text)
        light_fg = luminance(foreground)
        light_bg = luminance(background)
        ratio = ((max(light_fg, light_bg) + 0.05)
                 / (min(light_fg, light_bg) + 0.05))
        passed = ratio >= threshold
        if not passed:
            failures += 1
        note = ' [sRGB色域截断]' if (clipped_fg or clipped_bg) else ''
        verdict = '过' if passed else '不过'
        print('%s %.2f:1 (阈值 %.1f:1) %s on %s%s' % (
            verdict, ratio, threshold,
            display(foreground), display(background), note))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main(sys.argv)
