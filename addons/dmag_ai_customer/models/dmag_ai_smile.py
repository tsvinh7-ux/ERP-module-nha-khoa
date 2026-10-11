"""AI-19 – Mô phỏng nụ cười (MINH HỌA – không phải cam kết kết quả).

* Giả lập / tại chỗ: xử lý ảnh đơn giản bằng Pillow – ước lượng vùng răng (sáng, ít bão hòa, giữa khung hình), ước tính
  màu răng theo thang kiểu VITA, tạo ảnh "minh họa sau tẩy trắng" + ghép đôi Hiện tại | Minh họa, đóng dấu "MINH HỌA".
* Claude (chế độ thật): AI xem ảnh và mô tả nhận xét thẩm mỹ + các lựa chọn từ BẢNG GIÁ (chỉ văn bản – Claude không tạo ảnh).
Không phải chẩn đoán; bác sĩ thăm khám mới quyết định.
"""
import base64
import io
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

from .text_utils import money

_logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover
    Image = None

# Thang màu tham khảo (sáng → tối) – màu hiển thị gần đúng, chỉ để minh họa
SHADES = [('B1', (246, 240, 226)), ('A1', (240, 230, 208)), ('B2', (236, 224, 196)), ('A2', (230, 214, 182)),
          ('A3', (222, 202, 164)), ('B3', (214, 194, 150)), ('A3.5', (208, 186, 144)), ('A4', (196, 170, 126))]
BANNER = 'MINH HỌA – không phải cam kết kết quả'
SCHEMA = {
    'type': 'object',
    'properties': {
        'observations': {'type': 'array', 'items': {'type': 'string'}},
        'options': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'service': {'type': 'string'}, 'why': {'type': 'string'}},
            'required': ['service', 'why'], 'additionalProperties': False}},
        'caution': {'type': 'string'},
    },
    'required': ['observations', 'options', 'caution'],
    'additionalProperties': False,
}
SYSTEM = (
    'Bạn hỗ trợ tư vấn thẩm mỹ nha khoa. Xem ảnh nụ cười và nêu 3–5 nhận xét THẨM MỸ quan sát được (màu răng, độ đều, '
    'đường cười, khe thưa…) bằng lời trung tính, dễ hiểu. Gợi ý 1–3 lựa chọn CHỈ từ danh sách dịch vụ được cung cấp '
    '(ghi đúng tên dịch vụ), kèm lý do ngắn. Không chẩn đoán bệnh lý, không cam kết kết quả, không nêu giá. '
    'caution: nhắc rằng đây chỉ là minh họa, cần bác sĩ khám trực tiếp.'
)


def _font(size, bold=False):
    for path in ('web/static/fonts/sign/NotoSans-Reg.ttf',):
        try:
            return ImageFont.truetype(file_path(path), size)
        except Exception:  # noqa: BLE001
            pass
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if bold else ''),):
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            pass
    return ImageFont.load_default()


def teeth_mask(img):
    """Mặt nạ vùng răng ước lượng: điểm sáng, ít bão hòa, nằm giữa khung hình."""
    w, h = img.size
    hsv = img.convert('HSV')
    mask = Image.new('L', (w, h), 0)
    src, out = hsv.load(), mask.load()
    x0, x1, y0, y1 = int(w * 0.12), int(w * 0.88), int(h * 0.25), int(h * 0.9)
    for y in range(y0, y1):
        for x in range(x0, x1):
            hue, sat, val = src[x, y]
            if val > 150 and (sat < 35 or (22 <= hue <= 45 and sat < 95)):
                out[x, y] = 255
    mask = mask.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(2))
    return mask


def estimate_shade(img, mask):
    px, m = img.load(), mask.load()
    w, h = img.size
    total, acc = 0, [0, 0, 0]
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if m[x, y] > 128:
                r, g, b = px[x, y]
                acc[0] += r
                acc[1] += g
                acc[2] += b
                total += 1
    if not total:
        return None, 0.0
    mean = tuple(v / total for v in acc)
    best = min(range(len(SHADES)), key=lambda i: sum((mean[k] - SHADES[i][1][k]) ** 2 for k in range(3)))
    coverage = total * 4.0 / (w * h)
    return best, coverage


def whiten(img, mask, strength=0.55):
    """Làm trắng minh họa: giảm ngả vàng, tăng sáng trong vùng mặt nạ."""
    r, g, b = img.split()
    bright = Image.merge('RGB', (r.point(lambda v: min(255, int(v * 1.06 + 8))),
                                 g.point(lambda v: min(255, int(v * 1.08 + 10))),
                                 b.point(lambda v: min(255, int(v * 1.22 + 22)))))
    desat = ImageOps.grayscale(bright).convert('RGB')
    target = Image.blend(bright, desat, 0.35)
    alpha = mask.point(lambda v: int(v * strength))
    return Image.composite(target, img, alpha)


def compose(before, after, shade_now, shade_after, clinic=''):
    w, h = before.size
    pad, head, foot = 24, 70, 120
    canvas = Image.new('RGB', (w * 2 + pad * 3, h + head + foot + pad), (244, 247, 251))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, canvas.width, 52], fill=(17, 52, 106))
    draw.text((pad, 13), BANNER, fill=(255, 255, 255), font=_font(24, True))
    if clinic:
        f = _font(16)
        tw = draw.textlength(clinic, font=f)
        draw.text((canvas.width - pad - tw, 18), clinic, fill=(200, 220, 245), font=f)
    canvas.paste(before, (pad, head))
    canvas.paste(after, (pad * 2 + w, head))
    label_font = _font(18, True)
    labels = [('Hiện tại%s' % (' (~%s)' % SHADES[shade_now][0] if shade_now is not None else ''), pad),
              ('Minh họa sau tẩy trắng%s' % (' (~%s)' % SHADES[shade_after][0] if shade_after is not None else ''), pad * 2 + w)]
    for text, x in labels:
        draw.rounded_rectangle([x + 10, head + 10, x + 20 + draw.textlength(text, font=label_font), head + 40], 8,
                               fill=(255, 255, 255))
        draw.text((x + 15, head + 12), text, fill=(17, 52, 106), font=label_font)
    # đóng dấu chéo "MINH HỌA" trên ảnh minh họa
    stamp = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    sfont = _font(max(28, w // 9), True)
    sd.text((w * 0.12, h * 0.42), 'MINH HỌA', fill=(255, 255, 255, 70), font=sfont)
    stamp = stamp.rotate(18, resample=Image.BICUBIC)
    canvas.paste(stamp, (pad * 2 + w, head), stamp)
    # thang màu
    y = head + h + 22
    draw.text((pad, y), 'Thang màu tham khảo (sáng → tối):', fill=(27, 42, 61), font=_font(16))
    sw = min(70, (canvas.width - pad * 2 - 300) // len(SHADES))
    for i, (name, color) in enumerate(SHADES):
        x = pad + 300 + i * (sw + 6)
        outline = (229, 72, 77) if i == shade_now else (18, 165, 148) if i == shade_after else (200, 210, 222)
        draw.rounded_rectangle([x, y - 4, x + sw, y + 40], 6, fill=color, outline=outline, width=3 if outline != (200, 210, 222) else 1)
        draw.text((x + 6, y + 44), name, fill=(80, 90, 110), font=_font(14))
    draw.text((pad, y + 30), '■ đỏ: ước tính hiện tại   ■ xanh: minh họa', fill=(107, 122, 144), font=_font(14))
    return canvas


def simulate_smile(image_bytes, clinic=''):
    if Image is None:
        raise UserError(_('Máy chủ thiếu thư viện Pillow.'))
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert('RGB')
    except Exception as e:  # noqa: BLE001
        raise UserError(_('Không đọc được ảnh (%s).', e)) from e
    img.thumbnail((640, 640))
    mask = teeth_mask(img)
    shade_now, coverage = estimate_shade(img, mask)
    after = whiten(img, mask)
    shade_after = estimate_shade(after, mask)[0]
    if shade_now is not None and shade_after is not None and shade_after >= shade_now:
        shade_after = max(0, shade_now - 2)
    canvas = compose(img, after, shade_now, shade_after, clinic)
    buf = io.BytesIO()
    canvas.save(buf, format='JPEG', quality=86)
    small = io.BytesIO()
    img.save(small, format='JPEG', quality=85)
    return {'composite': buf.getvalue(), 'resized': small.getvalue(), 'shade_now': shade_now, 'shade_after': shade_after,
            'coverage': coverage}


class DmagAiSmile(models.Model):
    _name = 'dmag.ai.smile'
    _description = 'Mô phỏng nụ cười – minh họa (AI-19)'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    patient_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 domain=[('is_patient', '=', True)])
    source = fields.Selection([('consult', 'Tư vấn tại phòng khám'), ('portal', 'Bệnh nhân tự tải lên')], default='consult')
    image_before = fields.Image('Ảnh nụ cười', max_width=1280, max_height=1280, required=True)
    image_result = fields.Image('Ảnh minh họa (ghép đôi)', readonly=True)
    shade_now = fields.Char('Màu ước tính hiện tại', readonly=True)
    shade_after = fields.Char('Màu minh họa', readonly=True)
    observations = fields.Text('Nhận xét thẩm mỹ', readonly=True)
    options = fields.Text('Lựa chọn tham khảo (theo bảng giá)', readonly=True)
    caution = fields.Char('Lưu ý', readonly=True, default=BANNER)
    mode = fields.Char('Chế độ', readonly=True)
    estimated_cost_vnd = fields.Float('Chi phí nếu chạy thật (đ)', digits=(12, 0), readonly=True)
    cost_vnd = fields.Float('Chi phí AI (đ)', digits=(12, 0), readonly=True)
    state = fields.Selection([('draft', 'Chưa xử lý'), ('done', 'Đã tạo minh họa')], default='draft')

    @api.depends('patient_id')
    def _compute_name(self):
        for rec in self:
            rec.name = _('Nụ cười – %s', rec.patient_id.name or '')

    @api.model
    def _aesthetic_services(self):
        return self.env['product.product'].sudo().search([
            ('is_dental_service', '=', True),
            ('dental_category', 'in', ('cosmetic', 'orthodontic', 'prosthodontic', 'hygiene'))], limit=40)

    def action_generate(self):
        for rec in self:
            sim = simulate_smile(base64.b64decode(rec.image_before), rec.company_id.name)
            services = rec._aesthetic_services()
            shade_now = SHADES[sim['shade_now']][0] if sim['shade_now'] is not None else False
            shade_after = SHADES[sim['shade_after']][0] if sim['shade_after'] is not None else False

            def pick(*words):
                return services.filtered(lambda p: any(w in p.name.lower() for w in words))[:1]

            local_obs, local_opts = [], []
            if sim['coverage'] < 0.01:
                local_obs.append('Chưa nhận diện rõ vùng răng trong ảnh – nên chụp chính diện, cười lộ răng, đủ sáng.')
            else:
                local_obs.append('Màu răng ước tính khoảng %s trên thang tham khảo%s.'
                                 % (shade_now, ' (hơi ngả vàng)' if sim['shade_now'] and sim['shade_now'] >= 3 else ''))
                local_obs.append('Ảnh minh họa giả định làm sáng khoảng 2 bậc màu (≈ %s) – mức thực tế tùy men răng.' % shade_after)
            local_obs.append('Độ đều, khớp cắn, nướu và tình trạng sâu răng cần bác sĩ khám trực tiếp.')
            for words, why in ((('tẩy trắng',), 'Làm sáng màu răng tự nhiên, không mài răng.'),
                               (('cạo vôi', 'lấy cao', 'vệ sinh'), 'Làm sạch mảng bám trước khi làm thẩm mỹ.'),
                               (('veneer', 'dán sứ'), 'Cải thiện màu & hình dáng nhóm răng cửa (cần bác sĩ thứ hai duyệt chỉ định).'),
                               (('khay trong', 'chỉnh nha', 'niềng'), 'Nếu răng lệch / thưa – cần khám & chụp phim để đánh giá.')):
                product = pick(*words)
                if product:
                    local_opts.append({'service': product.name, 'why': why, 'price': product.lst_price})
            simulated = {'observations': local_obs, 'options': [{'service': o['service'], 'why': o['why']} for o in local_opts],
                         'caution': 'Đây chỉ là ảnh minh họa, không phải cam kết kết quả; bác sĩ cần thăm khám trực tiếp.'}
            catalog = '\n'.join('- %s' % p.name for p in services)
            user = [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                             'data': base64.b64encode(sim['resized']).decode()}},
                {'type': 'text', 'text': 'Danh sách dịch vụ thẩm mỹ của phòng khám:\n%s\nMàu ước tính bằng xử lý ảnh: %s.'
                                         % (catalog, shade_now or 'không rõ')},
            ]
            res = self.env['dmag.ai'].run('AI-19', SYSTEM, user, schema=SCHEMA, record=rec, patient=rec.patient_id,
                                          simulate=lambda: {'data': simulated, 'text': ''})
            data = res.get('data') or simulated
            prices = {p.name.lower(): p.lst_price for p in services}
            option_lines = []
            for opt in data.get('options') or []:
                price = prices.get((opt.get('service') or '').lower())
                option_lines.append('• %s%s – %s' % (opt.get('service'), (' (giá niêm yết %s)' % money(price)) if price else '',
                                                     opt.get('why')))
            rec.write({
                'image_result': base64.b64encode(sim['composite']),
                'shade_now': shade_now, 'shade_after': shade_after,
                'observations': '\n'.join('• %s' % o for o in data.get('observations') or []),
                'options': '\n'.join(option_lines) or False,
                'caution': data.get('caution') or BANNER,
                'mode': 'Giả lập (xử lý ảnh tại chỗ)' if res.get('simulated') else 'Claude (nhận xét) + xử lý ảnh tại chỗ',
                'estimated_cost_vnd': res.get('estimated_cost_vnd') or 0, 'cost_vnd': res.get('cost_vnd') or 0,
                'state': 'done',
            })
        return True
