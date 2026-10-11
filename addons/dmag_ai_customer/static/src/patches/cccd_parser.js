/** @odoo-module **/

/**
 * AI-10 – Đọc chuỗi QR trên CCCD gắn chip (tại trình duyệt, không gửi đi đâu):
 * "<số CCCD>|<số CMND cũ>|<họ tên>|<ngày sinh ddmmyyyy>|<giới tính>|<địa chỉ>|<ngày cấp ddmmyyyy>"
 * Bản Python tương đương: models/cccd.py (dùng cho kiểm thử & kiểm tra trùng hồ sơ).
 */
export const SAMPLE_CCCD_QR =
    "079190001234|025123456|Nguyễn Thị Minh Anh|15081990|Nữ|123 Nguyễn Thị Minh Khai, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh|20042021";

function ddmmyyyy(value) {
    const v = (value || "").trim();
    if (!/^\d{8}$/.test(v)) {
        return false;
    }
    const d = Number(v.slice(0, 2));
    const m = Number(v.slice(2, 4));
    const y = Number(v.slice(4));
    const date = new Date(Date.UTC(y, m - 1, d));
    if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
        return false;
    }
    return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function parseCccdQr(raw) {
    const text = (raw || "").trim().replace(/[\r\n]/g, "");
    const parts = text.split("|").map((p) => p.trim());
    if (parts.length < 6) {
        throw new Error("Không phải mã QR CCCD (cần ít nhất 6 trường, ngăn cách bằng dấu |).");
    }
    const [citizenId, oldIdRaw, name, birth, sex, address] = parts;
    if (!/^\d{12}$/.test(citizenId)) {
        throw new Error("Số CCCD phải gồm 12 chữ số.");
    }
    if (!name) {
        throw new Error("Mã QR thiếu họ tên.");
    }
    const birthdate = ddmmyyyy(birth);
    if (birth && !birthdate) {
        throw new Error("Ngày sinh trong mã QR không hợp lệ (ddmmyyyy).");
    }
    const s = (sex || "").toLowerCase();
    const gender = ["nam", "male", "m"].includes(s) ? "male" : ["nữ", "nu", "female", "f"].includes(s) ? "female" : false;
    return {
        citizen_id: citizenId,
        old_id: /^(\d{9}|\d{12})$/.test(oldIdRaw || "") ? oldIdRaw : "",
        name: name.split(/\s+/).join(" "),
        birthdate,
        gender,
        address: (address || "").split(/\s+/).join(" "),
        issue_date: ddmmyyyy(parts[6] || ""),
    };
}
