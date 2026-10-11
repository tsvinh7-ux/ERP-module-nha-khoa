"""Sinh 2 ảnh phim toàn cảnh (panorama) TỔNG HỢP để demo AI-06.

Ảnh vẽ hoàn toàn bằng mã (Pillow) – không phải phim của bệnh nhân thật, không lấy từ nguồn ngoài,
nên không vướng bản quyền / dữ liệu cá nhân (giấy phép như module: LGPL-3).
Chạy lại:  python3 scripts/generate_xray_samples.py   (cần Pillow)
Kết quả: static/img/xray_sample_1.png, xray_sample_2.png và static/img/xray_samples.json (vị trí tổn thương
đã vẽ, dùng làm kết quả mẫu cho chế độ giả lập).
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1400, 700
CX = W / 2
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'static', 'img')
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# Chiều rộng răng (px) theo vị trí 1..8 tính từ đường giữa
WIDTHS = {1: 50, 2: 46, 3: 54, 4: 56, 5: 56, 6: 76, 7: 72, 8: 66}
CROWN_H = {1: 72, 2: 66, 3: 74, 4: 66, 5: 64, 6: 66, 7: 62, 8: 58}
ROOT_H = {1: 118, 2: 108, 3: 140, 4: 112, 5: 112, 6: 104, 7: 98, 8: 86}
ROOTS = {1: 1, 2: 1, 3: 1, 4: 2, 5: 1, 6: 2, 7: 2, 8: 2}
GAP = 6


def occlusal_y(x):
    """Đường cắn dạng "nụ cười" của phim panorama."""
    return 360 - 105 * ((x - CX) / 560) ** 2


def layout():
    """Tọa độ tâm x của từng răng FDI (người xem nhìn: bên phải bệnh nhân ở bên trái ảnh)."""
    pos = {}
    for upper in (True, False):
        right_q, left_q = (1, 2) if upper else (4, 3)
        x = CX - GAP / 2
        for p in range(1, 9):  # bên phải bệnh nhân → trái ảnh
            w = WIDTHS[p]
            pos[f'{right_q}{p}'] = (x - w / 2, w)
            x -= w + GAP
        x = CX + GAP / 2
        for p in range(1, 9):
            w = WIDTHS[p]
            pos[f'{left_q}{p}'] = (x + w / 2, w)
            x += w + GAP
    return pos


def tooth_polys(code, cx, w, tilt=0.0, drop=0.0):
    """Đa giác thân răng + chân răng (tọa độ ảnh)."""
    p = int(code[1])
    upper = code[0] in '12'
    sign = -1 if upper else 1
    yo = occlusal_y(cx) + sign * 4 + drop
    ch, rh = CROWN_H[p], ROOT_H[p]
    if not upper:
        ch, rh = ch - 4, rh + 10
    half = w / 2
    neck = yo + sign * ch
    crown = [(cx - half * 0.88, yo), (cx + half * 0.88, yo), (cx + half, yo + sign * ch * 0.55),
             (cx + half * 0.86, neck), (cx - half * 0.86, neck), (cx - half, yo + sign * ch * 0.55)]
    roots = []
    n = ROOTS[p]
    for i in range(n):
        if n == 1:
            rx0, rx1 = cx - half * 0.62, cx + half * 0.62
            apex = cx
        else:
            seg = (half * 1.7) / n
            rx0 = cx - half * 0.85 + i * seg + 2
            rx1 = rx0 + seg - 4
            apex = (rx0 + rx1) / 2 + (-6 if i == 0 else 6)
        roots.append([(rx0, neck), (rx1, neck), (apex + 4, neck + sign * rh), (apex - 4, neck + sign * rh)])

    def rot(pt):
        if not tilt:
            return pt
        ox, oy = cx, neck
        a = math.radians(tilt)
        dx, dy = pt[0] - ox, pt[1] - oy
        return (ox + dx * math.cos(a) - dy * math.sin(a), oy + dx * math.sin(a) + dy * math.cos(a))

    crown = [rot(pt) for pt in crown]
    roots = [[rot(pt) for pt in r] for r in roots]
    apex_pts = [((r[2][0] + r[3][0]) / 2, (r[2][1] + r[3][1]) / 2) for r in roots]
    return crown, roots, yo, neck, apex_pts


def bbox(points, pad=8):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [max(0, min(xs) - pad), max(0, min(ys) - pad), min(W, max(xs) + pad), min(H, max(ys) + pad)]


def norm(box):
    x0, y0, x1, y1 = box
    return {'x': round(x0 / W, 4), 'y': round(y0 / H, 4), 'w': round((x1 - x0) / W, 4), 'h': round((y1 - y0) / H, 4)}


def render(key, spec):
    random.seed(key)
    img = Image.new('L', (W, H), 8)
    d = ImageDraw.Draw(img)
    # Hộp sọ / xương hàm (mờ)
    d.ellipse([60, -260, W - 60, 470], fill=34)
    d.ellipse([120, 120, W - 120, 690], fill=48)        # xương hàm dưới
    d.ellipse([260, 250, W - 260, 640], fill=40)
    d.rectangle([0, 0, 70, H], fill=22)
    d.rectangle([W - 70, 0, W, H], fill=22)
    d.ellipse([300, 110, 600, 250], fill=20)            # xoang hàm trên
    d.ellipse([800, 110, 1100, 250], fill=20)
    d.ellipse([650, 70, 750, 200], fill=16)             # hốc mũi
    d.rectangle([20, 380, 110, 690], fill=60)           # cột sống (bóng)
    d.rectangle([W - 110, 380, W - 20, 690], fill=60)
    img = img.filter(ImageFilter.GaussianBlur(28))
    d = ImageDraw.Draw(img)
    d.arc([150, 40, W - 150, 660], 20, 160, fill=78, width=16)     # bờ dưới xương hàm dưới
    d.arc([230, 190, W - 230, 520], 200, 340, fill=58, width=10)   # khẩu cái cứng
    # Xương ổ răng (sáng hơn nền) bao quanh chân răng
    xs = list(range(160, W - 159, 20))
    upper_band = [(x, occlusal_y(x) - 40) for x in xs] + [(x, occlusal_y(x) - 215) for x in reversed(xs)]
    lower_band = [(x, occlusal_y(x) + 40) for x in xs] + [(x, occlusal_y(x) + 235) for x in reversed(xs)]
    d.polygon(upper_band, fill=88)
    d.polygon(lower_band, fill=96)
    img = img.filter(ImageFilter.GaussianBlur(10))
    d = ImageDraw.Draw(img)

    pos = layout()
    findings = []
    for f in spec['findings']:
        if f['kind'] == 'bone_loss':
            cx, w = pos[f['tooth']]
            _c, _r, yo, neck, _a = tooth_polys(f['tooth'], cx, w)
            d.rectangle([cx - w * 1.7, yo, cx + w * 0.7, neck + 46], fill=40)
    img = img.filter(ImageFilter.GaussianBlur(6))
    d = ImageDraw.Draw(img)
    for code, (cx, w) in pos.items():
        if code in spec.get('missing', ()):
            continue
        tilt = spec.get('tilt', {}).get(code, 0)
        drop = spec.get('drop', {}).get(code, 0)
        crown, roots, yo, neck, apices = tooth_polys(code, cx, w, tilt, drop)
        for r in roots:
            d.polygon(r, fill=168)
        d.polygon(crown, fill=205)
        # men răng sáng hơn ở mặt nhai
        upper = code[0] in '12'
        cap = [crown[0], crown[1], crown[2], crown[5]]
        d.polygon(cap, fill=228)
        # buồng tủy + ống tủy (tối)
        sign = -1 if upper else 1
        mid_y = (yo + neck) / 2
        d.ellipse([cx - w * 0.16, mid_y - 10, cx + w * 0.16, mid_y + 10 + sign * 10], fill=150)
        for r in roots:
            top = ((r[0][0] + r[1][0]) / 2, neck)
            apex = ((r[2][0] + r[3][0]) / 2, (r[2][1] + r[3][1]) / 2)
            canal_fill = 252 if code in spec.get('root_canal', ()) else 112
            d.line([top, apex], fill=canal_fill, width=5 if canal_fill > 200 else 3)
        if code in spec.get('crown', ()):
            d.polygon(crown, outline=255, fill=244)
        if code in spec.get('filling', ()):
            fy = yo + sign * 6
            d.ellipse([cx - w * 0.3, fy - 9, cx + w * 0.3, fy + 9 + sign * 6], fill=255)
    img = img.filter(ImageFilter.GaussianBlur(3.2))
    d = ImageDraw.Draw(img)

    # Tổn thương (vẽ sau khi làm mờ để còn rõ, rồi làm mờ nhẹ lại)
    overlay = Image.new('L', (W, H), 0)
    od = ImageDraw.Draw(overlay)
    for f in spec['findings']:
        code = f['tooth']
        cx, w = pos[code]
        crown, roots, yo, neck, apices = tooth_polys(code, cx, w, spec.get('tilt', {}).get(code, 0),
                                                     spec.get('drop', {}).get(code, 0))
        upper = code[0] in '12'
        sign = -1 if upper else 1
        kind = f['kind']
        if kind == 'caries':
            # Mặt gần (M) hướng về đường giữa: phải ảnh với cung 1/4, trái ảnh với cung 2/3
            off = 0 if f.get('side', 'O') == 'O' else (w * 0.28 if code[0] in '14' else -w * 0.28)
            sx, sy = cx + off, yo + sign * 16
            r = f.get('size', 11)
            d.ellipse([sx - r, sy - r * 0.8, sx + r, sy + r * 0.8], fill=88)
            d.ellipse([sx - r * 0.5, sy - r * 0.3, sx + r * 0.7, sy + r * 1.1], fill=100)
            box = [sx - r - 10, sy - r - 10, sx + r + 10, sy + r + 10]
        elif kind == 'periapical':
            ax, ay = apices[-1]
            r = 22
            d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=66)
            d.ellipse([ax - r * 0.6, ay - r * 0.6, ax + r * 0.6, ay + r * 0.6], fill=56)
            box = [ax - r - 10, ay - r - 10, ax + r + 10, ay + r + 10]
        elif kind == 'bone_loss':
            box = bbox(crown + [pt for rr in roots for pt in rr[:2]], pad=6)
            pass  # đã vẽ trước khi vẽ răng (mào xương hạ thấp)
        else:  # vùng cả răng: mất răng, mão, trám, ngầm, chữa tủy, nứt
            pts = crown + [pt for rr in roots for pt in rr]
            if code in spec.get('missing', ()):
                pts = crown
            box = bbox(pts, pad=6)
            if kind == 'fracture':
                d.line([(cx - 4, yo + sign * 4), (cx + 6, neck + sign * 30)], fill=60, width=3)
        findings.append(dict(f, box=norm(box)))
    del od

    img = img.filter(ImageFilter.GaussianBlur(1.6))
    # nhiễu hạt
    noise = Image.effect_noise((W, H), 18)
    img = Image.blend(img, noise, 0.08)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_B, 18)
    small = ImageFont.truetype(FONT, 15)
    d.text((24, 16), 'R', font=ImageFont.truetype(FONT_B, 34), fill=235)
    d.text((W - 48, 16), 'L', font=ImageFont.truetype(FONT_B, 34), fill=235)
    d.text((86, 18), 'DMAG · ẢNH TỔNG HỢP MINH HỌA – KHÔNG PHẢI PHIM BỆNH NHÂN THẬT', font=font, fill=225)
    d.text((86, 44), spec['title'], font=small, fill=200)
    rgb = img.convert('RGB')
    path = os.path.join(OUT, f'{key}.png')
    rgb.save(path, optimize=True)
    return findings


SAMPLES = {
    'xray_sample_1': {
        'title': 'Mẫu 1 · sâu răng 36, 46 · mất 16 · mão 21 · trám 37 · răng khôn 38 mọc lệch',
        'missing': ['16'], 'crown': ['21'], 'filling': ['37'],
        'tilt': {'38': -28}, 'drop': {'38': 26},
        'findings': [
            {'tooth': '36', 'kind': 'caries', 'side': 'O', 'size': 12, 'condition_code': 'caries', 'confidence': 0.86,
             'finding': 'Vùng thấu quang mặt nhai, nghi sâu ngà', 'surfaces': ['O']},
            {'tooth': '46', 'kind': 'caries', 'side': 'M', 'size': 13, 'condition_code': 'caries', 'confidence': 0.81,
             'finding': 'Thấu quang mặt gần – nhai, sát buồng tủy, nghi sâu ngà sâu', 'surfaces': ['M', 'O']},
            {'tooth': '16', 'kind': 'missing', 'condition_code': 'missing', 'confidence': 0.95,
             'finding': 'Mất răng, xương ổ răng tiêu nhẹ theo chiều đứng', 'surfaces': []},
            {'tooth': '21', 'kind': 'crown', 'condition_code': 'crown', 'confidence': 0.92,
             'finding': 'Phục hình mão cản quang toàn bộ thân răng', 'surfaces': []},
            {'tooth': '37', 'kind': 'filling', 'condition_code': 'filling', 'confidence': 0.9,
             'finding': 'Miếng trám cản quang mặt nhai, sát khít', 'surfaces': ['O']},
            {'tooth': '38', 'kind': 'impacted', 'condition_code': 'impacted', 'confidence': 0.77,
             'finding': 'Răng khôn nghiêng gần ~30°, ngầm một phần dưới xương', 'surfaces': []},
        ],
    },
    'xray_sample_2': {
        'title': 'Mẫu 2 · 46 đã chữa tủy + tổn thương quanh chóp · mất 26 · nứt 36 · 38 ngầm · tiêu xương 31–41',
        'missing': ['26'], 'root_canal': ['46'], 'crown': [],
        'tilt': {'38': -42}, 'drop': {'38': 40},
        'findings': [
            {'tooth': '46', 'kind': 'root_canal', 'condition_code': 'root_canal', 'confidence': 0.9,
             'finding': 'Ống tủy đã trám bít cản quang', 'surfaces': []},
            {'tooth': '46', 'kind': 'periapical', 'condition_code': 'periapical', 'confidence': 0.68,
             'finding': 'Vùng thấu quang quanh chóp chân xa ~4 mm, nghi viêm quanh cuống mạn', 'surfaces': []},
            {'tooth': '36', 'kind': 'fracture', 'condition_code': 'fracture', 'confidence': 0.55,
             'finding': 'Đường thấu quang mảnh dọc thân răng, nghi nứt – cần khám lâm sàng xác nhận', 'surfaces': []},
            {'tooth': '26', 'kind': 'missing', 'condition_code': 'missing', 'confidence': 0.94,
             'finding': 'Mất răng, xoang hàm hạ thấp sát sống hàm', 'surfaces': []},
            {'tooth': '38', 'kind': 'impacted', 'condition_code': 'impacted', 'confidence': 0.83,
             'finding': 'Răng khôn ngầm nghiêng gần ~45°, sát ống thần kinh răng dưới', 'surfaces': []},
            {'tooth': '31', 'kind': 'bone_loss', 'condition_code': 'mobility', 'confidence': 0.58,
             'finding': 'Tiêu xương ngang vùng răng cửa dưới ~1/3 chân răng', 'surfaces': []},
        ],
    },
}


def main():
    meta = {}
    for key, spec in SAMPLES.items():
        findings = render(key, spec)
        for f in findings:
            f.pop('kind', None)
            f.pop('side', None)
            f.pop('size', None)
        meta[key] = {'title': spec['title'], 'file': f'{key}.png', 'findings': findings}
    with open(os.path.join(OUT, 'xray_samples.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
