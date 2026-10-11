"""Vẽ sơ đồ răng FDI dạng SVG cho bản in bệnh án (QWeb → trình duyệt / wkhtmltopdf).

Cùng hình học với sơ đồ trên màn hình (dmag_clinic_workspace/static/src/odontogram/tooth_geometry.js):
mỗi răng có hình mặt bên (thân + chân, nhìn từ phía má/môi) và hình mặt nhai chia 5 mặt.
Hướng vẽ: bác sĩ nhìn đối diện bệnh nhân (bên phải bệnh nhân = bên trái tờ giấy);
hàm trên: phía má ở trên, phía khẩu cái về giữa; hàm dưới: phía lưỡi về giữa, phía má ở dưới;
mặt gần (M) luôn quay về đường giữa.

Chỉ dùng thuộc tính SVG thuần (không CSS biến, không paint-order) để wkhtmltopdf (QtWebKit) hiển thị đúng.
"""
from markupsafe import Markup, escape

PITCH = 50
GUTTER = 10
MIDGAP = 18
CAPTION = 22
SIDE_GAP = 5
NUM_H = 38  # số răng + dòng ký hiệu
BAND = 34

PERMANENT_ROWS = {
    'upper': [[18, 17, 16, 15, 14, 13, 12, 11], [21, 22, 23, 24, 25, 26, 27, 28]],
    'lower': [[48, 47, 46, 45, 44, 43, 42, 41], [31, 32, 33, 34, 35, 36, 37, 38]],
}
PRIMARY_ROWS = {
    'upper': [[55, 54, 53, 52, 51], [61, 62, 63, 64, 65]],
    'lower': [[85, 84, 83, 82, 81], [71, 72, 73, 74, 75]],
}

DIMS = {
    'permanent': {
        'upper': {1: (38, 34, 46, 30), 2: (31, 30, 42, 28), 3: (34, 34, 56, 32), 4: (32, 30, 44, 40),
                  5: (31, 29, 44, 40), 6: (42, 28, 42, 44), 7: (40, 27, 40, 42), 8: (36, 26, 34, 38)},
        'lower': {1: (25, 28, 40, 28), 2: (27, 28, 42, 28), 3: (31, 33, 52, 30), 4: (30, 29, 46, 34),
                  5: (32, 28, 46, 35), 6: (44, 27, 42, 40), 7: (42, 26, 40, 38), 8: (40, 25, 34, 36)},
    },
    'primary': {
        'upper': {1: (32, 26, 34, 28), 2: (27, 24, 32, 26), 3: (30, 27, 38, 30), 4: (35, 23, 30, 36),
                  5: (40, 24, 32, 40)},
        'lower': {1: (23, 23, 30, 26), 2: (25, 23, 32, 26), 3: (27, 25, 36, 28), 4: (36, 22, 30, 34),
                  5: (42, 23, 32, 38)},
    },
}

SURFACE_KEY = [
    ('O / I', 'Mặt nhai / rìa cắn', 'đỉnh răng, chỗ ăn nhai'),
    ('B / F', 'Mặt ngoài', 'phía má / môi – "mặt trước"'),
    ('L / P', 'Mặt trong', 'phía lưỡi / khẩu cái – "mặt sau"'),
    ('M', 'Mặt gần', 'mặt bên hướng về đường giữa'),
    ('D', 'Mặt xa', 'mặt bên hướng ra sau'),
]

FONT = 'Arial, Helvetica, DejaVu Sans, sans-serif'
TOOTH_LINE = '#5E6F88'
REGION_LINE = '#B8C4D4'
ROOT_FILL = '#F3EBDC'
ROOT_LINE = '#A8977C'


def _f(v):
    return f'{round(v * 10) / 10:g}'


def tooth_info(code):
    n = int(code)
    q, pos = divmod(n, 10)
    primary = q >= 5
    upper = q in (1, 2, 5, 6)
    right = q in (1, 4, 5, 8)
    if pos <= 2:
        kind = 'incisor'
    elif pos == 3:
        kind = 'canine'
    elif primary or pos >= 6:
        kind = 'molar'
    else:
        kind = 'premolar'
    w, c, r, d = DIMS['primary' if primary else 'permanent']['upper' if upper else 'lower'][pos]
    roots = 1
    if kind == 'molar':
        roots = 3 if upper else 2
    elif kind == 'premolar' and upper and pos == 4:
        roots = 2
    return {'code': str(code), 'q': q, 'pos': pos, 'primary': primary, 'upper': upper, 'right': right,
            'kind': kind, 'anterior': pos <= 3, 'roots': roots, 'w': w, 'C': c, 'R': r, 'd': d,
            'sx': 1 if right else -1}


def _rounded_poly(points, frac=0.3):
    n = len(points)
    parts = []
    for i, p in enumerate(points):
        prev = points[(i - 1) % n]
        nxt = points[(i + 1) % n]
        a = (p[0] + (prev[0] - p[0]) * frac, p[1] + (prev[1] - p[1]) * frac)
        b = (p[0] + (nxt[0] - p[0]) * frac, p[1] + (nxt[1] - p[1]) * frac)
        parts.append(f"{'M' if i == 0 else 'L'}{_f(a[0])},{_f(a[1])} Q{_f(p[0])},{_f(p[1])} {_f(b[0])},{_f(b[1])}")
    return ' '.join(parts) + ' Z'


def _poly(pts):
    return ' '.join(f'{_f(x)},{_f(y)}' for x, y in pts)


def _occ_points(t, scale=1.0):
    w = t['w'] * scale / 2
    d = t['d'] * scale / 2
    kind = t['kind']
    if kind == 'molar':
        if t['upper']:
            s = w * 0.12
            return [(-w + s, -d), (w + s, -d), (w - s, d), (-w - s, d)]
        return [(-w, -d), (w, -d), (w * 0.94, d), (-w * 0.86, d)]
    if kind == 'premolar':
        if t['upper']:
            return [(-w * 0.8, -d), (w * 0.8, -d), (w, 0), (w * 0.72, d), (-w * 0.72, d), (-w, 0)]
        return [(-w * 0.85, -d), (w * 0.85, -d), (w, -d * 0.1), (w * 0.6, d), (-w * 0.6, d), (-w, -d * 0.1)]
    if kind == 'canine':
        return [(-w, -d * 0.1), (-w * 0.42, -d), (w * 0.42, -d), (w, -d * 0.1), (w * 0.3, d), (-w * 0.3, d)]
    return [(-w, -d * 0.35), (-w * 0.6, -d), (w * 0.6, -d), (w, -d * 0.35), (w * 0.32, d), (-w * 0.32, d)]


def _occ_frac(t):
    return {'molar': 0.3, 'premolar': 0.42}.get(t['kind'], 0.36)


def occlusal_geometry(t):
    outline = _rounded_poly(_occ_points(t), _occ_frac(t))
    W = t['w'] / 2 + 6
    H = t['d'] / 2 + 6
    if t['anterior']:
        ix0, ix1, iy0, iy1 = -t['w'] * 0.24, t['w'] * 0.24, -t['d'] * 0.22, t['d'] * 0.04
        center = _rounded_poly([(ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)], 0.45)
    else:
        inner = _occ_points(t, 0.5)
        xs = [p[0] for p in inner]
        ys = [p[1] for p in inner]
        ix0, ix1, iy0, iy1 = min(xs) * 0.9, max(xs) * 0.9, min(ys), max(ys)
        center = _rounded_poly(inner, _occ_frac(t))
    regions = [
        ('B', _poly([(-W, -H), (W, -H), (ix1, iy0), (ix0, iy0)])),
        ('M', _poly([(W, -H), (W, H), (ix1, iy1), (ix1, iy0)])),
        ('L', _poly([(W, H), (-W, H), (ix0, iy1), (ix1, iy1)])),
        ('D', _poly([(-W, H), (-W, -H), (ix0, iy0), (ix0, iy1)])),
    ]
    return {'outline': outline, 'regions': regions, 'center': center,
            'center_surface': 'I' if t['anterior'] else 'O'}


def _crown_path(t):
    w, C, kind = t['w'], t['C'], t['kind']
    h = w / 2
    neck = h * (0.78 if kind == 'molar' else 0.7 if kind == 'incisor' else 0.66)
    bulge = C * 0.32
    if kind == 'molar':
        start = C * 0.2
        k = 2 if t['primary'] else 3
        step = w * 0.86 / k
        x0 = -w * 0.43
        top = f'M{_f(-h)},{_f(C * 0.2)} Q{_f(-h)},{_f(C * 0.06)} {_f(x0)},{_f(C * 0.08)}'
        for i in range(k):
            xa = x0 + step * i
            xb = xa + step
            top += f' Q{_f((xa + xb) / 2)},{_f(-C * 0.1)} {_f(xb)},{_f(C * 0.08)}'
        top += f' Q{_f(h)},{_f(C * 0.06)} {_f(h)},{_f(C * 0.2)}'
    elif kind == 'premolar':
        start = C * 0.26
        top = (f'M{_f(-h)},{_f(C * 0.26)} C{_f(-h * 0.72)},{_f(C * 0.1)} {_f(-h * 0.32)},{_f(-C * 0.01)} 0,{_f(-C * 0.01)}'
               f' C{_f(h * 0.32)},{_f(-C * 0.01)} {_f(h * 0.72)},{_f(C * 0.1)} {_f(h)},{_f(C * 0.26)}')
    elif kind == 'canine':
        start = C * 0.3
        top = (f'M{_f(-h)},{_f(C * 0.3)} C{_f(-h * 0.62)},{_f(C * 0.2)} {_f(-h * 0.26)},{_f(C * 0.02)} {_f(-h * 0.04)},{_f(-C * 0.03)}'
               f' C{_f(h * 0.18)},{_f(C * 0.02)} {_f(h * 0.6)},{_f(C * 0.14)} {_f(h)},{_f(C * 0.26)}')
    else:
        start = C * 0.14
        top = (f'M{_f(-h)},{_f(C * 0.14)} Q{_f(-h * 0.96)},{_f(C * 0.01)} {_f(-h * 0.7)},{_f(C * 0.01)}'
               f' L{_f(h * 0.82)},0 Q{_f(h)},0 {_f(h)},{_f(C * 0.1)}')
    return (f'{top} C{_f(h * 1.04)},{_f(bulge + C * 0.1)} {_f(neck * 1.08)},{_f(C * 0.82)} {_f(neck)},{_f(C)}'
            f' L{_f(-neck)},{_f(C)} C{_f(-neck * 1.08)},{_f(C * 0.82)} {_f(-h * 1.04)},{_f(bulge + C * 0.1)} {_f(-h)},{_f(start)} Z')


def _root_geometry(t):
    w, C, R, kind, roots = t['w'], t['C'], t['R'], t['kind'], t['roots']
    h = w / 2
    neck = h * (0.78 if kind == 'molar' else 0.7 if kind == 'incisor' else 0.66)
    apex_y = C + R
    tilt = -w * 0.06
    canals, apexes, back = [], [], ''
    if roots == 1:
        ax = tilt
        path = (f'M{_f(-neck)},{_f(C - 1)} C{_f(-neck * 0.95)},{_f(C + R * 0.45)} {_f(ax - neck * 0.32)},{_f(apex_y - 4)} {_f(ax)},{_f(apex_y)}'
                f' C{_f(ax + neck * 0.32)},{_f(apex_y - 4)} {_f(neck * 0.95)},{_f(C + R * 0.45)} {_f(neck)},{_f(C - 1)} Z')
        canals.append(f'M0,{_f(C * 0.55)} Q{_f(tilt * 0.3)},{_f(C + R * 0.5)} {_f(ax)},{_f(apex_y - 3)}')
        apexes.append((ax, apex_y))
    else:
        spread = 1.25 if t['primary'] else 0.55 if kind == 'premolar' else 1.0
        fur_y = C + R * (0.55 if kind == 'premolar' else 0.18 if t['primary'] else 0.3)
        rw = neck * (0.6 if kind == 'premolar' else 0.62)
        dx = -neck * 0.55 * spread + tilt
        mx = neck * 0.55 * spread + tilt * 0.5
        d_apex = apex_y - (0 if kind == 'premolar' else 3)
        path = (f'M{_f(-neck)},{_f(C - 1)}'
                f' C{_f(-neck * 1.02)},{_f(C + R * 0.35)} {_f(dx - rw * 0.5)},{_f(d_apex - R * 0.25)} {_f(dx)},{_f(d_apex)}'
                f' C{_f(dx + rw * 0.45)},{_f(d_apex - R * 0.2)} {_f(-rw * 0.25)},{_f(fur_y + 4)} 0,{_f(fur_y)}'
                f' C{_f(rw * 0.25)},{_f(fur_y + 4)} {_f(mx - rw * 0.45)},{_f(apex_y - R * 0.2)} {_f(mx)},{_f(apex_y)}'
                f' C{_f(mx + rw * 0.5)},{_f(apex_y - R * 0.25)} {_f(neck * 1.02)},{_f(C + R * 0.35)} {_f(neck)},{_f(C - 1)} Z')
        canals.append(f'M{_f(-neck * 0.25)},{_f(C * 0.6)} Q{_f(dx * 0.7)},{_f(fur_y)} {_f(dx)},{_f(d_apex - 3)}')
        canals.append(f'M{_f(neck * 0.25)},{_f(C * 0.6)} Q{_f(mx * 0.7)},{_f(fur_y)} {_f(mx)},{_f(apex_y - 3)}')
        apexes += [(dx, d_apex), (mx, apex_y)]
        if roots == 3:
            px = tilt * 0.3
            p_apex = apex_y + 3
            back = (f'M{_f(-neck * 0.5)},{_f(C)} C{_f(-neck * 0.5)},{_f(C + R * 0.5)} {_f(px - 5)},{_f(p_apex - 3)} {_f(px)},{_f(p_apex)}'
                    f' C{_f(px + 5)},{_f(p_apex - 3)} {_f(neck * 0.5)},{_f(C + R * 0.5)} {_f(neck * 0.5)},{_f(C)} Z')
            canals.append(f'M0,{_f(C * 0.6)} L{_f(px)},{_f(p_apex - 4)}')
            apexes.append((px, p_apex))
    pulp = (f'M{_f(-neck * 0.42)},{_f(C * 0.92)} Q{_f(-neck * 0.5)},{_f(C * 0.42)} {_f(-neck * 0.18)},{_f(C * 0.38)}'
            f' L{_f(neck * 0.18)},{_f(C * 0.38)} Q{_f(neck * 0.5)},{_f(C * 0.42)} {_f(neck * 0.42)},{_f(C * 0.92)} Z')
    return {'path': path, 'back': back, 'canals': canals, 'apexes': apexes, 'pulp': pulp, 'neck': neck}


def _side_regions(t):
    w, C = t['w'], t['C']
    W = w / 2 + 4
    ix = w * 0.27
    iy = C * (0.2 if t['anterior'] else 0.27)
    b = C + 2
    return [
        ('I' if t['anterior'] else 'O', _poly([(-W, -6), (W, -6), (ix, iy), (-ix, iy)])),
        ('M', _poly([(W, -6), (W, b), (ix, b), (ix, iy)])),
        ('D', _poly([(-W, -6), (-ix, iy), (-ix, b), (-W, b)])),
        ('B', _poly([(-ix, iy), (ix, iy), (ix, b), (-ix, b)])),
    ]


def _implant(t):
    iw = max(7, t['w'] * 0.22)
    C, R = t['C'], t['R']
    body = (f'M{_f(-iw / 2)},{_f(C + 1)} L{_f(iw / 2)},{_f(C + 1)} L{_f(iw * 0.38)},{_f(C + R * 0.86)}'
            f' Q0,{_f(C + R * 0.98)} {_f(-iw * 0.38)},{_f(C + R * 0.86)} Z')
    threads = []
    for k in (0.18, 0.32, 0.46, 0.6, 0.74):
        y = C + R * k
        half = iw / 2 - k * iw * 0.14 + 2
        threads.append(f'M{_f(-half)},{_f(y)} L{_f(half)},{_f(y + 2.5)}')
    return body, threads


def tooth_visual(entries):
    """entries: list of dict(color, symbol, code, layer, surfaces) cũ → mới."""
    v = {'surfaces': {}, 'plan': {}, 'missing': None, 'crown': None, 'bridge': None, 'implant': None,
         'canal': None, 'pulp': None, 'apex': None, 'residual': None, 'calculus': None, 'unerupted': None,
         'mobility': None}
    for e in entries:
        st = {'color': e['color'], 'planned': e['layer'] == 'planned'}
        sym, code = e['symbol'], e['code']
        if sym == 'fill':
            target = v['plan'] if st['planned'] else v['surfaces']
            for s in (e['surfaces'] or ['M', 'D', 'O', 'I', 'B', 'L']):
                target[s] = st
        elif sym == 'cross':
            v['missing'] = st
        elif sym == 'ring':
            if code == 'mobility':
                v['mobility'] = st
            else:
                v['crown'] = st
                if code == 'bridge':
                    v['bridge'] = st
        elif sym == 'implant':
            v['implant'] = st
        elif sym == 'root':
            key = {'periapical': 'apex', 'pulpitis': 'pulp', 'residual_root': 'residual'}.get(code, 'canal')
            v[key] = st
        elif sym == 'dash':
            v['unerupted' if code in ('impacted', 'unerupted') else 'calculus'] = st
    if v['missing'] and not v['missing']['planned']:
        v['surfaces'], v['plan'] = {}, {}
        if not v['implant']:
            v['crown'] = None
    return v


class _Svg:
    def __init__(self, uid):
        self.uid = uid
        self.parts = []
        self.hatches = set()

    def add(self, s):
        self.parts.append(s)

    def paint(self, st, fallback='#FFFFFF'):
        if not st:
            return fallback
        if st['planned']:
            self.hatches.add(st['color'])
            return f"url(#{self.hatch_id(st['color'])})"
        return st['color']

    def hatch_id(self, color):
        return f"{self.uid}h{''.join(ch for ch in color if ch.isalnum())}"

    def defs(self):
        out = []
        for c in sorted(self.hatches):
            out.append(f'<pattern id="{self.hatch_id(c)}" width="5" height="5" patternUnits="userSpaceOnUse" '
                       f'patternTransform="rotate(45)"><rect width="2.2" height="5" fill="{escape(c)}"/></pattern>')
        return '<defs>' + ''.join(out) + '</defs>'


def _text(x, y, s, size=10, weight='normal', fill='#5B6B82', anchor='middle'):
    return (f'<text x="{_f(x)}" y="{_f(y)}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


def _draw_tooth(svg, t, cx, side_base, map_y, num_y, marks_y, v, marks):
    code = t['code']
    upper = t['upper']
    side_tf = f"translate({_f(cx)},{_f(side_base)}) scale({t['sx']},{-1 if upper else 1})"
    map_tf = f"translate({_f(cx)},{_f(map_y)}) scale({t['sx']},{1 if upper else -1})"
    ghost = (v['missing'] and not v['missing']['planned']) or v['unerupted']
    op = ' opacity="0.38"' if ghost else ''
    root = _root_geometry(t)
    crown = _crown_path(t)
    # --- mặt bên
    g = [f'<g transform="{side_tf}"{op}>']
    if v['implant']:
        body, threads = _implant(t)
        g.append(f'<path d="{root["path"]}" fill="none" stroke="#C9BDA6" stroke-width="0.9" stroke-dasharray="2.5 2"/>')
        g.append(f'<path d="{body}" fill="{svg.paint(v["implant"])}" stroke="{v["implant"]["color"]}" stroke-width="1"/>')
        g += [f'<path d="{th}" stroke="{v["implant"]["color"]}" stroke-width="1.5"/>' for th in threads]
    else:
        if root['back']:
            g.append(f'<path d="{root["back"]}" fill="#E9DFCB" stroke="{ROOT_LINE}" stroke-width="0.8"/>')
        rf = svg.paint(v['residual'], ROOT_FILL) if v['residual'] else ROOT_FILL
        rs = v['residual']['color'] if v['residual'] else ROOT_LINE
        g.append(f'<path d="{root["path"]}" fill="{rf}" stroke="{rs}" stroke-width="1"/>')
        endo = v['canal'] or v['pulp'] or v['apex']
        if endo:
            if v['pulp']:
                g.append(f'<path d="{root["pulp"]}" fill="{v["pulp"]["color"]}" opacity="0.85"/>')
            dash = ' stroke-dasharray="3 2.5"' if endo['planned'] else ''
            sw = 3 if v['canal'] else 1.8
            g += [f'<path d="{c}" fill="none" stroke="{endo["color"]}" stroke-width="{sw}" stroke-linecap="round"{dash}/>'
                  for c in root['canals']]
            if v['apex']:
                g += [f'<circle cx="{_f(x)}" cy="{_f(y)}" r="5" fill="{v["apex"]["color"]}" fill-opacity="0.25" '
                      f'stroke="{v["apex"]["color"]}" stroke-width="1.5"/>' for x, y in root['apexes']]
    clip = f'{svg.uid}s{code}'
    g.append(f'<clipPath id="{clip}"><path d="{crown}"/></clipPath>')
    if v['residual']:
        g.append(f'<path d="{crown}" fill="none" stroke="#A9B4C4" stroke-width="1" stroke-dasharray="3 2.5"/>')
    else:
        g.append(f'<g clip-path="url(#{clip})">')
        for surf, pts in _side_regions(t):
            g.append(f'<polygon points="{pts}" fill="{svg.paint(v["surfaces"].get(surf))}" stroke="{REGION_LINE}" stroke-width="1"/>')
            if surf in v['plan']:
                g.append(f'<polygon points="{pts}" fill="{svg.paint(v["plan"][surf])}" stroke="none"/>')
        if v['crown']:
            g.append(f'<path d="{crown}" fill="{svg.paint(v["crown"], v["crown"]["color"])}" fill-opacity="0.3"/>')
        g.append('</g>')
        cs = v['crown']
        stroke = (f'stroke="{cs["color"]}" stroke-width="2.6"' + (' stroke-dasharray="4 2.5"' if cs['planned'] else '')) \
            if cs else f'stroke="{TOOTH_LINE}" stroke-width="1.1"'
        g.append(f'<path d="{crown}" fill="none" {stroke}/>')
    if v['calculus']:
        g.append(f'<line x1="{_f(-root["neck"] - 2)}" x2="{_f(root["neck"] + 2)}" y1="{_f(t["C"] + 1)}" y2="{_f(t["C"] + 1)}" '
                 f'stroke="{v["calculus"]["color"]}" stroke-width="3.5" stroke-dasharray="3 2"/>')
    g.append('</g>')
    # --- mặt nhai
    occ = occlusal_geometry(t)
    oclip = f'{svg.uid}o{code}'
    g.append(f'<g transform="{map_tf}"{op}><clipPath id="{oclip}"><path d="{occ["outline"]}"/></clipPath>')
    g.append(f'<g clip-path="url(#{oclip})">')
    for surf, pts in occ['regions']:
        g.append(f'<polygon points="{pts}" fill="{svg.paint(v["surfaces"].get(surf))}" stroke="{REGION_LINE}" stroke-width="1"/>')
        if surf in v['plan']:
            g.append(f'<polygon points="{pts}" fill="{svg.paint(v["plan"][surf])}" stroke="none"/>')
    g.append('</g>')
    cs_ = occ['center_surface']
    g.append(f'<path d="{occ["center"]}" fill="{svg.paint(v["surfaces"].get(cs_))}" stroke="{REGION_LINE}" stroke-width="1"/>')
    if cs_ in v['plan']:
        g.append(f'<path d="{occ["center"]}" fill="{svg.paint(v["plan"][cs_])}" stroke="none"/>')
    cs = v['crown']
    stroke = (f'stroke="{cs["color"]}" stroke-width="3"' + (' stroke-dasharray="4 2.5"' if cs['planned'] else '')) \
        if cs else f'stroke="{TOOTH_LINE}" stroke-width="1.2"'
    g.append(f'<path d="{occ["outline"]}" fill="none" {stroke}/></g>')
    # --- ký hiệu không lật
    side_h = t['C'] + t['R'] + (3 if t['roots'] == 3 else 0)
    crown_mid = side_base - t['C'] / 2 if upper else side_base + t['C'] / 2
    root_mid = side_base - t['C'] - t['R'] * 0.45 if upper else side_base + t['C'] + t['R'] * 0.45
    if v['bridge']:
        g.append(f'<rect x="{_f(cx - 25)}" y="{_f(crown_mid - 2.5)}" width="50" height="5" rx="2" fill="{svg.paint(v["bridge"], v["bridge"]["color"])}"/>')
    if v['mobility']:
        m = v['mobility']['color']
        g.append(f'<path d="M{_f(cx - 12)},{_f(root_mid)} l5,-4 m-5,4 l5,4 M{_f(cx - 12)},{_f(root_mid)} L{_f(cx + 12)},{_f(root_mid)} '
                 f'l-5,-4 m5,4 l-5,4" fill="none" stroke="{m}" stroke-width="2.2" stroke-linecap="round"/>')
    if v['missing']:
        top = side_base - side_h if upper else map_y - t['d'] / 2 - 2
        bottom = map_y + t['d'] / 2 + 2 if upper else side_base + side_h
        dash = ' stroke-dasharray="7 5"' if v['missing']['planned'] else ''
        col = v['missing']['color']
        g.append(f'<line x1="{_f(cx - 17)}" y1="{_f(top)}" x2="{_f(cx + 17)}" y2="{_f(bottom)}" stroke="{col}" stroke-width="3.2" stroke-linecap="round"{dash}/>')
        g.append(f'<line x1="{_f(cx + 17)}" y1="{_f(top)}" x2="{_f(cx - 17)}" y2="{_f(bottom)}" stroke="{col}" stroke-width="3.2" stroke-linecap="round"{dash}/>')
    # --- số răng + ký hiệu chú giải
    has = bool(marks)
    g.append(f'<rect x="{_f(cx - 15)}" y="{_f(num_y - 9.5)}" width="30" height="19" rx="9.5" fill="#FFFFFF" '
             f'stroke="{"#11346A" if has else "#C9D3E0"}" stroke-width="{1.4 if has else 1}"/>')
    g.append(_text(cx, num_y + 4.5, code, 12, 'bold', '#11346A' if has else '#5B6B82'))
    if marks:
        spans = ''.join(f'<tspan fill="{escape(m["color"])}">{escape(m["text"])}</tspan> ' for m in marks)
        g.append(f'<text x="{_f(cx)}" y="{_f(marks_y)}" font-family="{FONT}" font-size="9" font-weight="bold" '
                 f'text-anchor="middle">{spans.strip()}</text>')
    svg.add(''.join(g))


def render_chart_svg(by_tooth, marks_by_tooth, include_primary=True, uid='emrodo'):
    """by_tooth: {code: [entry dict]}; marks_by_tooth: {code: [{'text','color'}]}. Trả về Markup SVG."""
    sets = [('Răng vĩnh viễn', PERMANENT_ROWS)]
    if include_primary:
        sets.append(('Răng sữa', PRIMARY_ROWS))
    width = GUTTER * 2 + 16 * PITCH + MIDGAP
    mid = width / 2
    svg = _Svg(uid)
    y = 0
    for title, rows in sets:
        n = len(rows['upper'][0])
        span_l = mid - MIDGAP / 2 - n * PITCH
        span_r = mid + MIDGAP / 2 + n * PITCH
        q_l = mid - MIDGAP / 2 - n * PITCH / 2
        q_r = mid + MIDGAP / 2 + n * PITCH / 2
        infos = [tooth_info(c) for c in rows['upper'][0] + rows['lower'][0]]
        side_h = max(i['C'] + i['R'] + (3 if i['roots'] == 3 else 0) for i in infos) + 4
        map_h = max(i['d'] for i in infos) + 6
        if len(sets) > 1:
            svg.add(_text(span_l, y + 13, title.upper(), 10.5, 'bold', '#11346A', 'start'))
            y += 18
        cap_top = y + 15
        upper_base = y + CAPTION + side_h
        upper_map = upper_base + SIDE_GAP + map_h / 2
        upper_num = upper_base + SIDE_GAP + map_h + 11
        band_top = upper_base + SIDE_GAP + map_h + NUM_H
        band_mid = band_top + BAND / 2
        lower_num = band_top + BAND + NUM_H - 11
        lower_map_top = band_top + BAND + NUM_H
        lower_map = lower_map_top + map_h / 2
        lower_base = lower_map_top + map_h + SIDE_GAP
        bottom = lower_base + side_h
        cap_bottom = bottom + 15
        narrow = n < 8
        for x in (q_l, q_r):
            svg.add(_text(x, cap_top, '▲ Phía má / môi · mặt ngoài (B)', 11, 'bold', '#8C9AAF'))
            svg.add(_text(x, cap_bottom, '▼ Phía má / môi · mặt ngoài (B)', 11, 'bold', '#8C9AAF'))
        svg.add(f'<rect x="{_f(span_l)}" y="{_f(band_top + 2)}" width="{_f(span_r - span_l)}" height="{BAND - 4}" rx="9" fill="#F1F4F9"/>')
        svg.add(f'<line x1="{_f(span_l + 8)}" x2="{_f(span_r - 8)}" y1="{_f(band_mid)}" y2="{_f(band_mid)}" stroke="#C9D4E2" stroke-width="1"/>')
        for x, anchor in ((span_l + 10, 'start'), (span_r - 10, 'end')):
            svg.add(_text(x, band_mid - 4, 'HÀM TRÊN', 10, 'bold', '#11346A', anchor))
            svg.add(_text(x, band_mid + 12, 'HÀM DƯỚI', 10, 'bold', '#11346A', anchor))
        pal = '▲ khẩu cái (L/P)' if narrow else '▲ phía khẩu cái · mặt trong (L/P)'
        lin = '▼ lưỡi (L)' if narrow else '▼ phía lưỡi · mặt trong (L)'
        for x in (mid - MIDGAP / 2 - (n * PITCH - 70) / 2, mid + MIDGAP / 2 + (n * PITCH - 70) / 2):
            svg.add(_text(x, band_mid - 4, pal, 10.5))
            svg.add(_text(x, band_mid + 12, lin, 10.5))
        svg.add(f'<line x1="{_f(mid)}" x2="{_f(mid)}" y1="{_f(cap_top + 4)}" y2="{_f(cap_bottom - 12)}" '
                f'stroke="#AFBDD0" stroke-width="1.2" stroke-dasharray="3 4"/>')
        for arch in ('upper', 'lower'):
            for code in rows[arch][0] + rows[arch][1]:
                t = tooth_info(code)
                idx = t['pos'] - 1
                cx = mid - MIDGAP / 2 - PITCH / 2 - idx * PITCH if t['right'] else mid + MIDGAP / 2 + PITCH / 2 + idx * PITCH
                up = arch == 'upper'
                num_y = upper_num if up else lower_num
                marks_y = num_y + 21 if up else num_y - 14
                v = tooth_visual(by_tooth.get(str(code), []))
                _draw_tooth(svg, t, cx, upper_base if up else lower_base, upper_map if up else lower_map,
                            num_y, marks_y, v, marks_by_tooth.get(str(code), []))
        y = cap_bottom + 12
    height = y
    body = ''.join(svg.parts)
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" width="100%" '
        f'style="display:block; width:100%; height:auto;" preserveAspectRatio="xMidYMin meet">{svg.defs()}{body}</svg>'
    )


def render_key_svg(uid='emrkey'):
    """Răng mẫu 16 nhìn từ mặt nhai, ghi nhãn 5 mặt – cho phần chú giải bản in."""
    t = tooth_info(16)
    occ = occlusal_geometry(t)
    parts = [f'<clipPath id="{uid}c"><path d="{occ["outline"]}"/></clipPath><g clip-path="url(#{uid}c)">']
    parts += [f'<polygon points="{pts}" fill="#FFFFFF" stroke="{REGION_LINE}" stroke-width="1"/>' for _s, pts in occ['regions']]
    parts.append(f'</g><path d="{occ["center"]}" fill="#F6F8FB" stroke="{REGION_LINE}" stroke-width="1"/>')
    parts.append(f'<path d="{occ["outline"]}" fill="none" stroke="{TOOTH_LINE}" stroke-width="1.3"/>')
    for x, y, s in ((1, -13, 'B'), (-1, 20, 'P'), (-16, 3.5, 'D'), (17, 3.5, 'M'), (0, 3.5, 'O')):
        parts.append(_text(x, y, s, 9, 'bold', '#11346A'))
    parts.append(_text(0, -30, '▲ má', 7))
    parts.append(_text(0, 37, '▼ khẩu cái', 7))
    return Markup(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-36 -42 72 84" width="78" height="91">{"".join(parts)}</svg>')
