"""Toán dự báo thuần Python (không cần numpy / statsmodels) – dùng cho AI-16.

* ``holt_winters``: san bằng hàm mũ ba tham số (mức · xu hướng · mùa vụ cộng tính), chọn tham số bằng lưới
  tối thiểu tổng bình phương sai số dự báo một bước; mùa vụ = chu kỳ tuần làm việc (6 ngày, thứ Hai – thứ Bảy).
  Thiếu dữ liệu (< 2 chu kỳ) → Holt (mức + xu hướng); quá ngắn → trung bình.
* ``weekday_profile``: mùa vụ theo THỨ trong tuần (phòng khám mở 7 ngày, Chủ nhật đông nhất) – chênh lệch cộng tính
  của từng thứ so với trung bình, co về 0 khi ít mẫu; gắn theo thứ thật nên ngày nghỉ lễ không làm lệch pha.
* ``norm_cdf`` / ``Z80``: khoảng tin cậy 80 % theo phân phối chuẩn.
Các hàm đều tất định (cùng đầu vào → cùng kết quả) để kiểm thử được.
"""
import math

Z80 = 1.2816


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def stdev(values):
    values = list(values)
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def quantile(values, q):
    values = sorted(values)
    if not values:
        return 0.0
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _hw_run(series, season, alpha, beta, gamma):
    """Chạy Holt-Winters cộng tính; trả (sse, level, trend, seasonals, residuals)."""
    n = len(series)
    if season and n >= 2 * season:
        first = mean(series[:season])
        second = mean(series[season:2 * season])
        level = first
        trend = (second - first) / season
        seasonals = [series[i] - first for i in range(season)]
    else:
        season = 0
        level = series[0]
        trend = (series[1] - series[0]) if n > 1 else 0.0
        seasonals = []
    sse = 0.0
    residuals = []
    start = 1
    for t in range(start, n):
        s = seasonals[t % season] if season else 0.0
        forecast = level + trend + s
        err = series[t] - forecast
        residuals.append(err)
        sse += err * err
        prev_level = level
        level = alpha * (series[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        if season:
            seasonals[t % season] = gamma * (series[t] - level) + (1 - gamma) * s
    return sse, level, trend, seasonals, residuals, season


def holt_winters(series, horizon, season=6, damped=0.9):
    """Dự báo ``horizon`` bước. Trả dict: forecast (list), sigma (độ lệch chuẩn sai số 1 bước), params, method.

    Xu hướng được "hãm" (damped trend, phi = ``damped``) để không ngoại suy quá đà khi dữ liệu ngắn.
    """
    series = [float(v) for v in series]
    n = len(series)
    if n == 0:
        return {'forecast': [0.0] * horizon, 'sigma': 0.0, 'method': 'none', 'params': {}}
    if n < 4:
        m = mean(series)
        return {'forecast': [m] * horizon, 'sigma': stdev(series), 'method': 'mean', 'params': {}}
    grid = [0.1, 0.2, 0.3, 0.5, 0.7]
    beta_grid = [0.0, 0.05, 0.1, 0.2]
    use_season = season if n >= 2 * season else 0
    gamma_grid = [0.05, 0.1, 0.3] if use_season else [0.0]
    best = None
    for alpha in grid:
        for beta in beta_grid:
            for gamma in gamma_grid:
                res = _hw_run(series, use_season, alpha, beta, gamma)
                if best is None or res[0] < best[0] - 1e-9:
                    best = res + ((alpha, beta, gamma),)
    sse, level, trend, seasonals, residuals, season_used, params = best
    forecast = []
    damp_sum = 0.0
    for h in range(1, horizon + 1):
        damp_sum += damped ** h
        s = seasonals[(n - 1 + h) % season_used] if season_used else 0.0
        forecast.append(max(0.0, level + damp_sum * trend + s))
    sigma = math.sqrt(sse / max(1, len(residuals))) if residuals else 0.0
    return {
        'forecast': forecast, 'sigma': sigma,
        'method': 'holt_winters' if season_used else 'holt',
        'params': {'alpha': params[0], 'beta': params[1], 'gamma': params[2], 'season': season_used, 'phi': damped},
    }


def robust_z(value, values):
    """Điểm z bền vững (median / MAD) – ít bị chính điểm bất thường kéo lệch."""
    values = list(values)
    if len(values) < 3:
        return 0.0
    med = quantile(values, 0.5)
    mad = quantile([abs(v - med) for v in values], 0.5) * 1.4826
    if mad <= 1e-9:
        sd = stdev(values)
        if sd > 1e-9:
            return (value - mean(values)) / sd
        # mọi giá trị so sánh bằng nhau (vd. đồng nghiệp đều 0): độ lệch tính theo đơn vị của chính dữ liệu
        return float(value - med)
    return (value - med) / mad


def iqr_fence(values, k=1.5):
    """Ngưỡng trên Q3 + k × IQR (Tukey)."""
    q1, q3 = quantile(values, 0.25), quantile(values, 0.75)
    return q3 + k * (q3 - q1), q1, q3


def split_spikes(series, k=3.0):
    """Tách ca lớn bất thường (implant, chỉnh nha trọn gói…) khỏi chuỗi ngày.

    Trả (chuỗi đã chặn trần, tốc độ phần vượt trần / ngày, phương sai phần vượt / ngày, trần). Mô hình hóa chuỗi đã
    chặn bằng Holt-Winters rồi cộng lại kỳ vọng phần ca lớn → giữ đúng trung bình mà không để vài ngày đột biến
    làm lệch mức / xu hướng / mùa vụ.
    """
    values = [float(v) for v in series]
    positive = [v for v in values if v > 0]
    if len(positive) < 8:
        return values, 0.0, 0.0, None
    cap, _q1, _q3 = iqr_fence(positive, k)
    excess = [max(0.0, v - cap) for v in values]
    capped = [min(v, cap) for v in values]
    n = len(values)
    rate = sum(excess) / n
    var = sum(e * e for e in excess) / n - rate * rate
    return capped, rate, max(0.0, var), cap


def weekday_profile(days, values, shrink=2.0):
    """Mùa vụ theo thứ: {thứ (0 = Thứ Hai): (chênh lệch cộng tính, chỉ số nhân, số mẫu)}.

    Chênh lệch = (TB của thứ − TB chung) × n / (n + ``shrink``) – thứ ít mẫu bị co về 0 để không khuếch đại nhiễu.
    """
    values = [float(v) for v in values]
    if not values:
        return {}
    # trung vị (bền với ca lớn đột biến như implant / chỉnh nha trọn gói)
    overall = quantile(values, 0.5) or mean(values)
    by_wd = {}
    for day, value in zip(days, values):
        by_wd.setdefault(day.weekday(), []).append(value)
    out = {}
    for wd, vals in by_wd.items():
        n = len(vals)
        diff = (quantile(vals, 0.5) - overall) * n / (n + shrink)
        out[wd] = (diff, ((overall + diff) / overall) if overall else 1.0, n)
    return out
