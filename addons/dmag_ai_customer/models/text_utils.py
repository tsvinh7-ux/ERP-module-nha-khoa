"""Tiện ích xử lý tiếng Việt cho các bộ trả lời giả lập / phân loại tại chỗ (không cần AI)."""
import re
import unicodedata
from datetime import date, timedelta

PHONE_RE = re.compile(r'(?:\+?84|0)(?:[\s.\-]?\d){9}')
TIME_RE = re.compile(r'\b(\d{1,2})\s*(?:h|g|giờ|:)\s*(\d{2})?\b')
DATE_RE = re.compile(r'\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b')
WEEKDAYS = {
    'thu 2': 0, 'thu hai': 0, 't2': 0, 'thu 3': 1, 'thu ba': 1, 't3': 1, 'thu 4': 2, 'thu tu': 2, 't4': 2,
    'thu 5': 3, 'thu nam': 3, 't5': 3, 'thu 6': 4, 'thu sau': 4, 't6': 4, 'thu 7': 5, 'thu bay': 5, 't7': 5,
    'chu nhat': 6, 'cn': 6,
}


def fold(text):
    """Bỏ dấu, chữ thường, gom khoảng trắng: 'Cạo vôi RĂNG' -> 'cao voi rang'."""
    text = (text or '').replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', text.lower()).strip()


def has_any(folded, words):
    """``folded`` đã bỏ dấu; ``words`` có thể có dấu. So khớp theo ranh giới từ."""
    for word in words:
        w = fold(word)
        if re.search(r'(?<![a-z0-9])' + re.escape(w) + r'(?![a-z0-9])', folded):
            return True
    return False


def has_raw(text, words):
    """So khớp có dấu (phân biệt 'tối' / 'tôi', 'sáng' / 'sang')."""
    low = unicodedata.normalize('NFC', (text or '').lower())
    return any(re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', low) for w in words)


def match_words(text, words):
    """Từ khóa nào xuất hiện: có dấu thì khớp chính xác ('hôi' ≠ 'hơi', 'sốt' ≠ 'sót'); cụm dài (≥ 8 ký tự)
    khớp cả khi khách gõ không dấu."""
    folded = fold(text)
    return [w for w in words if has_raw(text, [w]) or (len(fold(w)) >= 8 and has_any(folded, [w]))]


def digits(text):
    return ''.join(ch for ch in (text or '') if ch.isdigit())


def extract_phone(text):
    match = PHONE_RE.search(text or '')
    if not match:
        return False
    num = digits(match.group(0))
    if num.startswith('84'):
        num = '0' + num[2:]
    return num if len(num) == 10 else False


def extract_time(text):
    """'14h', '14:30', '9 giờ', '2h chiều' -> 'HH:MM'."""
    folded = fold(text)
    match = TIME_RE.search(folded.replace('gio', 'giờ'))
    if not match:
        return False
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if hour < 8 and has_raw(text, ['chiều', 'tối']):
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return False
    return '%02d:%02d' % (hour, minute)


def extract_part_of_day(text):
    if has_raw(text, ['sáng']):
        return 'morning'
    if has_raw(text, ['chiều', 'trưa']):
        return 'afternoon'
    if has_raw(text, ['tối']):
        return 'evening'
    return 'any'


def extract_date(text, today):
    """Ngày trong câu tiếng Việt: hôm nay, mai, ngày kia, thứ 7, 15/10…"""
    folded = fold(text)
    if has_any(folded, ['hôm nay', 'chiều nay', 'sáng nay', 'tối nay', 'bây giờ', 'hnay']):
        return today
    if has_any(folded, ['ngày kia', 'ngày mốt']):
        return today + timedelta(days=2)
    if has_raw(text, ['ngày mai', 'sáng mai', 'chiều mai', 'tối mai', 'trưa mai', 'mai nhé']) \
            or re.match(r'^\s*mai\b', (text or '').lower()):
        return today + timedelta(days=1)
    for key, weekday in WEEKDAYS.items():
        if re.search(r'(?<![a-z0-9])' + re.escape(key) + r'(?![a-z0-9])', folded):
            delta = (weekday - today.weekday()) % 7 or 7
            if has_any(folded, ['tuần sau', 'tuần tới']) and delta < 7:
                delta += 7 if delta <= (6 - today.weekday()) else 0
            return today + timedelta(days=delta)
    match = DATE_RE.search(folded)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            found = date(year, month, day)
        except ValueError:
            return False
        if found < today and not match.group(3):
            try:
                found = date(year + 1, month, day)
            except ValueError:
                return False
        return found
    return False


def salutation(partner):
    """Anh / chị / bé theo giới tính và tuổi – dùng cho lời chào."""
    if not partner:
        return 'anh/chị'
    age = partner.age if 'age' in partner._fields else 0
    if age and age < 12:
        return 'bé'
    if partner.gender == 'male':
        return 'anh'
    if partner.gender == 'female':
        return 'chị'
    return 'anh/chị'


def given_name(name):
    parts = (name or '').split()
    return parts[-1] if parts else ''


def money(amount):
    return '{:,.0f}'.format(amount or 0).replace(',', '.') + ' đ'


def warranty_text(months):
    """120 → "bảo hành 120 tháng (10 năm)"; 0 → "không áp dụng bảo hành riêng"."""
    months = int(months or 0)
    if not months:
        return 'không áp dụng bảo hành riêng'
    if months % 12 == 0:
        return 'bảo hành %s tháng (%s năm)' % (months, months // 12)
    return 'bảo hành %s tháng' % months


NUMBER_RE = re.compile(r'\d+(?:[.,]\d+)*')


def numbers_in(text, parts=False):
    """Các con số trong văn bản, chuẩn hóa để so khớp: "1.500.000 đ" → 1500000; "08:00" → 8, 0; "14/10" → 14, 10.

    ``parts=True`` (phía NGUỒN) thêm từng nhóm số ("2.500.000" → 2, 500, 0) để câu trả lời viết "2,5" vẫn bị chặn
    nhưng "08:00" / "8:00" khớp nhau."""
    out = set()
    for raw in NUMBER_RE.findall(text or ''):
        compact = raw.replace('.', '').replace(',', '')
        if compact.isdigit():
            out.add(int(compact))
        if parts:
            for part in re.split(r'[.,]', raw):
                if part.isdigit():
                    out.add(int(part))
    return out
