"""AI-03 – Quy tắc an toàn đơn thuốc CỐ ĐỊNH (tại chỗ, không dùng AI).

Các quy tắc ở đây CHẶN / CẢNH BÁO bất kể AI bật hay tắt; AI chỉ giải thích bằng lời dễ hiểu.
Đối chiếu theo tên hoạt chất (INN), tên thương mại và tên tiếng Việt / tiếng Anh thường gặp, bỏ dấu.
"""
import re
import unicodedata

from odoo import _


def norm(text):
    """Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng."""
    text = (text or '').replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', text.lower()).strip()


# Nhóm thuốc: từ khóa nhận diện thuốc (trên tên chung / biệt dược) và từ khóa nhận diện dị ứng trong hồ sơ
FAMILIES = {
    'penicillin': {
        'label': 'nhóm Penicillin (kháng sinh beta-lactam)',
        'drug': ['penicillin', 'penicilin', 'amoxicillin', 'amoxicilin', 'amoxycillin', 'ampicillin', 'ampicilin',
                 'augmentin', 'clavulanic', 'cloxacillin', 'oxacillin', 'klamentin', 'curam', 'sultamicillin'],
        'allergy': ['penicillin', 'penicilin', 'peni', 'amoxicillin', 'amoxicilin', 'amoxi', 'ampicillin',
                    'augmentin', 'beta-lactam', 'betalactam', 'beta lactam'],
    },
    'cephalosporin': {
        'label': 'nhóm Cephalosporin',
        'drug': ['cefalexin', 'cephalexin', 'cefuroxim', 'cefixim', 'cefadroxil', 'cefaclor', 'cefpodoxim',
                 'cefdinir', 'zinnat'],
        'allergy': ['cephalosporin', 'cefalosporin', 'cefalexin', 'cephalexin', 'cefuroxim', 'cefixim', 'cefadroxil'],
    },
    'macrolide': {
        'label': 'nhóm Macrolid',
        'drug': ['erythromycin', 'clarithromycin', 'azithromycin', 'spiramycin', 'roxithromycin', 'rodogyl',
                 'zithromax'],
        'allergy': ['macrolid', 'erythromycin', 'clarithromycin', 'azithromycin', 'spiramycin', 'rodogyl'],
    },
    'nitroimidazole': {
        'label': 'nhóm Nitroimidazol (Metronidazol)',
        'drug': ['metronidazol', 'tinidazol', 'flagyl', 'rodogyl'],
        'allergy': ['metronidazol', 'tinidazol', 'flagyl', 'nitroimidazol'],
    },
    'lincosamide': {
        'label': 'nhóm Lincosamid (Clindamycin)',
        'drug': ['clindamycin', 'lincomycin', 'dalacin'],
        'allergy': ['clindamycin', 'lincomycin', 'dalacin', 'lincosamid'],
    },
    'tetracycline': {
        'label': 'nhóm Tetracyclin',
        'drug': ['tetracyclin', 'doxycyclin', 'minocyclin'],
        'allergy': ['tetracyclin', 'doxycyclin', 'minocyclin'],
    },
    'sulfonamide': {
        'label': 'nhóm Sulfamid',
        'drug': ['sulfamethoxazol', 'cotrimoxazol', 'co-trimoxazol', 'bactrim'],
        'allergy': ['sulfa', 'sulfamid', 'sulfonamid', 'bactrim', 'cotrimoxazol'],
    },
    'nsaid': {
        'label': 'nhóm kháng viêm không steroid (NSAID)',
        'drug': ['ibuprofen', 'meloxicam', 'diclofenac', 'etoricoxib', 'celecoxib', 'naproxen', 'ketorolac',
                 'piroxicam', 'aspirin', 'acetylsalicylic', 'arcoxia', 'mobic', 'voltaren', 'alaxan', 'celebrex',
                 'ketoprofen', 'nimesulid'],
        'allergy': ['nsaid', 'ains', 'khang viem khong steroid', 'aspirin', 'acetylsalicylic', 'ibuprofen',
                    'diclofenac', 'meloxicam', 'etoricoxib', 'celecoxib', 'naproxen', 'ketorolac', 'piroxicam'],
    },
    'paracetamol': {
        'label': 'Paracetamol (Acetaminophen)',
        'drug': ['paracetamol', 'acetaminophen', 'efferalgan', 'panadol', 'hapacol', 'tylenol'],
        'allergy': ['paracetamol', 'acetaminophen', 'efferalgan', 'panadol', 'hapacol'],
    },
    'local_anesthetic': {
        'label': 'thuốc tê tại chỗ (nhóm amid / ester)',
        'drug': ['lidocain', 'xylocain', 'articain', 'mepivacain', 'procain', 'benzocain', 'septocaine',
                 'scandonest'],
        'allergy': ['lidocain', 'xylocain', 'articain', 'mepivacain', 'procain', 'benzocain', 'thuoc te', 'gay te'],
    },
    'chlorhexidine': {
        'label': 'Chlorhexidin',
        'drug': ['chlorhexidin', 'eludril', 'kin gingival'],
        'allergy': ['chlorhexidin'],
    },
    'corticoid': {
        'label': 'nhóm Corticoid',
        'drug': ['prednisolon', 'dexamethason', 'methylprednisolon', 'medrol', 'betamethason', 'hydrocortison'],
        'allergy': ['corticoid', 'prednisolon', 'dexamethason', 'methylprednisolon'],
    },
}

ANTICOAGULANTS = ['warfarin', 'sintrom', 'acenocoumarol', 'rivaroxaban', 'xarelto', 'apixaban', 'eliquis',
                  'dabigatran', 'pradaxa', 'clopidogrel', 'plavix', 'heparin', 'enoxaparin', 'lovenox', 'aspirin',
                  'aspegic', 'ticagrelor', 'brilinta', 'chong dong', 'chong ket tap tieu cau']
SYSTEMIC_ROUTES = ('oral', 'injection', 'buccal')


def drug_text(drug):
    return norm(' '.join(filter(None, [drug.inn_name, drug.brand_name, drug.name])))


def drug_families(drug):
    text = drug_text(drug)
    return [key for key, fam in FAMILIES.items() if any(word in text for word in fam['drug'])]


def ingredients(drug):
    if not drug.inn_name:
        return []
    return [norm(part) for part in re.split(r'\+|/|,', drug.inn_name) if norm(part)]


def patient_profile(partner):
    """Các dữ kiện an toàn của bệnh nhân (dmag_dental_base)."""
    partner = partner.sudo()
    alerts = partner.patient_alert_ids
    alert_names = [norm(a.name) for a in alerts]
    allergy_text = norm(partner.allergy)
    if any('di ung thuoc te' in a for a in alert_names):
        allergy_text = (allergy_text + ' thuoc te').strip()
    pregnant = bool(partner.is_pregnant) or any('mang thai' in a for a in alert_names)
    meds = norm(partner.current_medication)
    bleeding = any('dong mau' in a or 'chong dong' in a for a in alert_names)
    hypertension = any('huyet ap' in a for a in alert_names)
    generic_allergy_alert = any(a.startswith('di ung thuoc') and 'te' not in a for a in alert_names)
    return {
        'allergy_raw': partner.allergy or '',
        'allergy': allergy_text,
        'pregnant': pregnant,
        'age': partner.age or 0,
        'meds_raw': partner.current_medication or '',
        'anticoagulant': bleeding or any(word in meds for word in ANTICOAGULANTS),
        'anticoagulant_names': [w for w in ANTICOAGULANTS if w in meds],
        'warfarin': any(w in meds for w in ('warfarin', 'sintrom', 'acenocoumarol')),
        'hypertension': hypertension,
        'generic_allergy_alert': generic_allergy_alert,
    }


def check_lines(env, partner, lines, max_days=30, weight=0.0):
    """Kiểm tra danh sách dòng thuốc.

    :param lines: [{'drug_id': int, 'days': int, 'dose_per_time':..., 'times_per_day':...}]
    :return: list of {'level': 'block'|'warn'|'info', 'code', 'drug', 'title', 'message'}
    """
    Drug = env['dmag.drug'].sudo()
    profile = patient_profile(partner) if partner else patient_profile(env['res.partner'])
    findings = []

    def add(level, code, drug, title, message):
        findings.append({'level': level, 'code': code, 'drug': drug.name if drug else '', 'title': title,
                         'message': message})

    seen_ingredients = {}
    nsaid_lines = []
    allergy = profile['allergy']
    allergy_tokens = set(re.findall(r'[a-z][a-z\-]{3,}', allergy))
    for line in lines or []:
        drug = Drug.browse(int(line.get('drug_id') or 0)).exists()
        if not drug:
            continue
        families = drug_families(drug)
        # 1. Dị ứng (CHẶN)
        hit = None
        for key in families:
            if any(word in allergy for word in FAMILIES[key]['allergy']):
                hit = FAMILIES[key]['label']
                break
        if not hit:
            for ing in ingredients(drug):
                head = ing.split(' ')[0]
                if len(head) >= 5 and any(tok.startswith(head[:6]) or head.startswith(tok[:6])
                                          for tok in allergy_tokens if len(tok) >= 5):
                    hit = drug.inn_name
                    break
        if hit:
            add('block', 'allergy', drug, _('Dị ứng thuốc'),
                _('Bệnh nhân có tiền sử dị ứng "%(allergy)s" – %(drug)s thuộc %(family)s. Không kê, chọn thuốc khác.',
                  allergy=profile['allergy_raw'] or _('thuốc tê (cảnh báo y khoa)'), drug=drug.name, family=hit))
        elif 'cephalosporin' in families and any(w in allergy for w in FAMILIES['penicillin']['allergy']):
            add('warn', 'cross_allergy', drug, _('Dị ứng chéo'),
                _('Bệnh nhân dị ứng nhóm Penicillin – %s (Cephalosporin) có nguy cơ dị ứng chéo. Cân nhắc thuốc khác '
                  'hoặc theo dõi sát.', drug.name))
        elif profile['generic_allergy_alert'] and not profile['allergy_raw']:
            add('warn', 'allergy_unknown', drug, _('Dị ứng chưa rõ thuốc'),
                _('Hồ sơ có cảnh báo "Dị ứng thuốc" nhưng chưa ghi tên thuốc – hỏi lại bệnh nhân trước khi kê %s.',
                  drug.name))
        # 2. NSAID + chống đông / aspirin
        if 'nsaid' in families:
            nsaid_lines.append(drug)
            if profile['anticoagulant']:
                add('warn', 'nsaid_anticoagulant', drug, _('Nguy cơ chảy máu'),
                    _('%(drug)s (NSAID) dùng cùng thuốc chống đông / chống kết tập tiểu cầu%(meds)s làm tăng nguy cơ '
                      'chảy máu, nhất là sau nhổ răng. Ưu tiên Paracetamol.',
                      drug=drug.name,
                      meds=(' (%s)' % ', '.join(profile['anticoagulant_names'])) if profile['anticoagulant_names'] else ''))
            elif profile['hypertension']:
                add('info', 'nsaid_hypertension', drug, _('Tăng huyết áp'),
                    _('NSAID có thể làm tăng huyết áp – dùng ngắn ngày, liều thấp nhất có hiệu quả.'))
        if 'nitroimidazole' in families and profile['warfarin']:
            add('warn', 'metronidazole_warfarin', drug, _('Tương tác thuốc'),
                _('Metronidazol làm tăng tác dụng chống đông của Warfarin / Acenocoumarol (tăng INR) – tránh phối hợp '
                  'hoặc báo bác sĩ điều trị chống đông.'))
        # 3. Thai kỳ
        if profile['pregnant']:
            if 'tetracycline' in families:
                add('block', 'pregnancy_contra', drug, _('Chống chỉ định khi mang thai'),
                    _('%s (nhóm Tetracyclin) chống chỉ định cho phụ nữ mang thai (ảnh hưởng răng, xương thai nhi).',
                      drug.name))
            elif 'nsaid' in families:
                add('warn', 'pregnancy_nsaid', drug, _('Phụ nữ mang thai'),
                    _('Tránh NSAID khi mang thai, đặc biệt 3 tháng cuối (nguy cơ đóng sớm ống động mạch). Ưu tiên '
                      'Paracetamol.'))
            elif 'nitroimidazole' in families:
                add('warn', 'pregnancy_metronidazole', drug, _('Phụ nữ mang thai'),
                    _('Hạn chế Metronidazol trong 3 tháng đầu thai kỳ – cân nhắc lợi ích / nguy cơ.'))
            elif 'corticoid' in families:
                add('warn', 'pregnancy_corticoid', drug, _('Phụ nữ mang thai'),
                    _('Corticoid toàn thân khi mang thai chỉ dùng khi thật cần thiết, liều thấp, ngắn ngày.'))
            else:
                add('info', 'pregnancy_check', drug, _('Phụ nữ mang thai'),
                    _('Kiểm tra mức độ an toàn thai kỳ của %s trước khi kê.', drug.name))
        # 4. Trẻ em dưới 12 tuổi
        age = profile['age']
        if partner and partner.birthdate and age < 12:
            if 'tetracycline' in families and age < 8:
                add('block', 'child_tetracycline', drug, _('Trẻ dưới 8 tuổi'),
                    _('%s gây đổi màu răng vĩnh viễn ở trẻ dưới 8 tuổi – không kê.', drug.name))
            elif 'nsaid' in families and any(w in drug_text(drug) for w in ('aspirin', 'acetylsalicylic')):
                add('warn', 'child_aspirin', drug, _('Trẻ em – Aspirin'),
                    _('Không dùng Aspirin cho trẻ em (nguy cơ hội chứng Reye).'))
            elif 'chlorhexidine' in families and age < 6:
                add('warn', 'child_mouthwash', drug, _('Trẻ dưới 6 tuổi'),
                    _('Trẻ dưới 6 tuổi dễ nuốt nước súc miệng – cân nhắc dạng gel hoặc bôi bằng gạc.'))
            elif drug.route in SYSTEMIC_ROUTES:
                add('warn', 'child_dose', drug, _('Liều trẻ em (%s tuổi)', age),
                    _('%(drug)s: tính liều theo cân nặng (mg/kg)%(w)s, không dùng liều người lớn.',
                      drug=drug.name,
                      w=(_(' – cân nặng %s kg', weight) if weight else _(' – chưa có cân nặng của trẻ'))))
        # 5. Trùng hoạt chất
        for ing in ingredients(drug):
            if ing in seen_ingredients and seen_ingredients[ing] != drug.id:
                add('warn', 'duplicate', drug, _('Trùng hoạt chất'),
                    _('Hoạt chất "%(ing)s" có ở 2 thuốc trong đơn (%(drug)s) – nguy cơ quá liều.',
                      ing=ing, drug=drug.name))
            seen_ingredients.setdefault(ing, drug.id)
        # 6. Số ngày
        days = int(line.get('days') or 0)
        if days > max_days:
            add('block', 'max_days', drug, _('Vượt số ngày tối đa'),
                _('%(drug)s kê %(days)s ngày – tối đa %(max)s ngày/đơn (TT 26/2025).', drug=drug.name, days=days,
                  max=max_days))
        if drug.is_narcotic or drug.is_psychotropic:
            add('info', 'controlled', drug, _('Thuốc kiểm soát đặc biệt'),
                _('%s là thuốc gây nghiện / hướng thần – phải kê đơn "N"/"H" đúng quy định.', drug.name))
    if len(nsaid_lines) >= 2:
        add('warn', 'duplicate_nsaid', nsaid_lines[1], _('Trùng nhóm NSAID'),
            _('Đơn có %s thuốc nhóm NSAID (%s) – không phối hợp 2 NSAID.',
              len(nsaid_lines), ', '.join(d.name for d in nsaid_lines)))
    order = {'block': 0, 'warn': 1, 'info': 2}
    findings.sort(key=lambda f: order[f['level']])
    return findings
