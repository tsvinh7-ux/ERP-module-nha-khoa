#!/bin/bash
# Lần chạy đầu: tạo CSDL demo, cài module demo (tự kéo toàn bộ module nha khoa + sinh dữ liệu mẫu ~3–5 phút),
# chuyển giao diện sang tiếng Việt, múi giờ Việt Nam. Các lần sau: chỉ khởi động Odoo.
set -e
DB="${DMAG_DB:-dmag_demo}"
CONF=/etc/odoo/odoo.conf
export PGPASSWORD="$PASSWORD"

until pg_isready -h "$HOST" -U "$USER" -q; do sleep 1; done

if ! psql -h "$HOST" -U "$USER" -d postgres -tAc "select 1 from pg_database where datname='$DB'" | grep -q 1; then
  echo "=== DMAG: khởi tạo CSDL demo '$DB' (lần đầu, mất khoảng 3–5 phút) ==="
  MODULES=dmag_dental_demo
  if [ -d /mnt/okr-addons/okr_scale ]; then MODULES="$MODULES,dmag_okr_dental"; fi
  odoo -c "$CONF" -d "$DB" -i "$MODULES" --without-demo=all --load-language=vi_VN --stop-after-init
  echo "=== DMAG: tiếng Việt + múi giờ Việt Nam cho mọi người dùng ==="
  odoo shell -c "$CONF" -d "$DB" --no-http <<'PY'
env['res.lang']._activate_lang('vi_VN')
env['res.users'].with_context(active_test=False).search([]).write({'lang': 'vi_VN', 'tz': 'Asia/Ho_Chi_Minh'})
env['res.partner'].search([('lang', '!=', 'vi_VN')]).write({'lang': 'vi_VN'})
env['ir.default'].set('res.partner', 'lang', 'vi_VN')
env.cr.commit()
PY
  echo "=== DMAG: sẵn sàng tại http://localhost:${DMAG_PORT:-8069} ==="
fi

exec odoo -c "$CONF" -d "$DB"
