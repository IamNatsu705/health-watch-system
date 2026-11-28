"""Đặc trưng của một cửa sổ gia tốc cho mô hình phân loại "đang đi bộ hay không".

Cùng một hàm này được dùng khi huấn luyện trên PC (``ml/``) và khi suy luận
trên Pi, nên đặc trưng luôn khớp nhau. Chỉ dùng độ lớn gia tốc và các đại
lượng tương đối (độ lệch, tỷ lệ, chu kỳ) để không phụ thuộc hướng gắn cảm
biến hoặc sai số offset tĩnh giữa các dòng cảm biến (AX3 so với MPU6050).
Thuần Python để chạy được trên Pi không có numpy.
"""

import math

FEATURE_VERSION = "step-features-v1"
FEATURE_NAMES = (
    "m_std",                   # độ lệch chuẩn độ lớn gia tốc (g)
    "m_p90_p10",               # khoảng phân vị 90-10 của độ lớn (g)
    "y_std",                   # độ lệch chuẩn tín hiệu lọc 0,5–3 Hz (g)
    "y_absmean",               # trung bình trị tuyệt đối tín hiệu lọc (g)
    "hf_std",                  # năng lượng thành phần >5 Hz (rung, run tay)
    "lf_std",                  # thay đổi chậm <0,5 Hz (đổi tư thế)
    "acf_step",                # tự tương quan lớn nhất ở chu kỳ bước 0,3–0,8 s
    "acf_step_lag_s",
    "acf_stride",              # tự tương quan lớn nhất ở chu kỳ sải 0,8–1,6 s
    "acf_stride_lag_s",
    "walkband_frac",           # tỷ lệ công suất 1,2–2,6 Hz trên 0,5–4 Hz
    "spec_entropy",            # entropy phổ trong 0,5–4 Hz
    "dom_freq_hz",             # tần số trội trong 0,5–4 Hz
    "n_candidates",            # số đỉnh ứng viên trong cửa sổ
    "cand_interval_cv",        # hệ số biến thiên khoảng cách đỉnh
    "cand_interval_median_s",  # trung vị khoảng cách đỉnh
)
GATE_INPUT_NAMES = FEATURE_NAMES + tuple(f"prev_{name}" for name in FEATURE_NAMES)

_FEATURE_RATE_HZ = 25.0
_DFT_CACHE: dict[tuple[int, float], tuple[list[int], list[list[float]], list[list[float]], list[float]]] = {}


def _mean_std(values) -> tuple[float, float]:
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) * (v - mean) for v in values) / n
    return mean, math.sqrt(max(var, 0.0))


def _percentile(sorted_values, q: float) -> float:
    """Nội suy tuyến tính, giống numpy.percentile mặc định."""
    pos = (len(sorted_values) - 1) * q / 100.0
    low = int(math.floor(pos))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def _best_autocorr(x, den: float, lo: int, hi: int) -> tuple[float, int]:
    best, best_lag = -1.0, lo
    n = len(x)
    for lag in range(lo, min(hi, n - 1) + 1):
        acc = 0.0
        for j in range(n - lag):
            acc += x[j] * x[j + lag]
        value = acc / den
        if value > best:
            best, best_lag = value, lag
    return best, best_lag


def _dft_tables(n: int, rate: float):
    cached = _DFT_CACHE.get((n, rate))
    if cached is None:
        resolution = rate / n
        bins = [k for k in range(1, n // 2 + 1) if 0.5 <= k * resolution <= 4.0]
        cos_rows = [[math.cos(2 * math.pi * k * j / n) for j in range(n)] for k in bins]
        sin_rows = [[math.sin(2 * math.pi * k * j / n) for j in range(n)] for k in bins]
        hann = [0.5 - 0.5 * math.cos(2 * math.pi * j / (n - 1)) for j in range(n)] if n > 1 else [1.0]
        cached = (bins, cos_rows, sin_rows, hann)
        _DFT_CACHE[(n, rate)] = cached
    return cached


def window_features(m, y, hf, lf, candidate_offsets, sample_rate_hz: float) -> list[float]:
    """Tính đặc trưng cho một cửa sổ.

    ``m``: độ lớn gia tốc (g); ``y``: độ lớn đã lọc thông dải 0,5–3 Hz;
    ``hf``: độ lớn lọc thông cao 5 Hz; ``lf``: độ lớn lọc thông thấp 0,5 Hz;
    ``candidate_offsets``: chỉ số (tính từ đầu cửa sổ) của các đỉnh ứng viên.
    """
    if len(m) < 10:
        raise ValueError("Cửa sổ quá ngắn")
    _, m_std = _mean_std(m)
    m_sorted = sorted(m)
    spread = _percentile(m_sorted, 90) - _percentile(m_sorted, 10)
    y_mean, y_std = _mean_std(y)
    y_absmean = sum(abs(v) for v in y) / len(y)
    _, hf_std = _mean_std(hf)
    _, lf_std = _mean_std(lf)

    # Hạ tần số về ~25 Hz: y đã lọc thông thấp 3 Hz nên không bị chồng phổ đáng kể.
    step = max(1, int(round(sample_rate_hz / _FEATURE_RATE_HZ)))
    rate = sample_rate_hz / step
    x = y[::step]
    x_mean = sum(x) / len(x)
    xc = [v - x_mean for v in x]
    den = sum(v * v for v in xc) + 1e-12
    acf_step, lag_step = _best_autocorr(xc, den, int(0.3 * rate), int(0.8 * rate))
    acf_stride, lag_stride = _best_autocorr(xc, den, int(0.8 * rate), int(1.6 * rate))

    bins, cos_rows, sin_rows, hann = _dft_tables(len(xc), rate)
    xw = [v * w for v, w in zip(xc, hann)]
    powers = []
    for cos_row, sin_row in zip(cos_rows, sin_rows):
        re = 0.0
        im = 0.0
        for value, c, s in zip(xw, cos_row, sin_row):
            re += value * c
            im += value * s
        powers.append(re * re + im * im)
    total = sum(powers) + 1e-12
    resolution = rate / len(xc)
    walkband = sum(p for k, p in zip(bins, powers) if 1.2 <= k * resolution <= 2.6) / total
    entropy = 0.0
    for p in powers:
        share = p / total
        entropy -= share * math.log(share + 1e-12)
    dominant = bins[max(range(len(powers)), key=powers.__getitem__)] * resolution if powers else 0.0

    offsets = sorted(candidate_offsets)
    intervals = [(b - a) / sample_rate_hz for a, b in zip(offsets, offsets[1:])]
    if len(intervals) > 1:
        iv_mean, iv_std = _mean_std(intervals)
        cv = iv_std / iv_mean if iv_mean > 0 else 1.0
    else:
        cv = 1.0
    if intervals:
        ordered = sorted(intervals)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    else:
        median = 0.0

    return [
        m_std, spread, y_std, y_absmean, hf_std, lf_std,
        acf_step, lag_step / rate, acf_stride, lag_stride / rate,
        walkband, entropy, dominant,
        float(len(offsets)), cv, median,
    ]
