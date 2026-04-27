"""
Technical indicators — pure functions operating on numpy arrays.
Every indicator returns both numeric value(s) AND an interpretation string.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IndicatorResult:
    name: str
    value: float
    interpretation: str
    raw: dict = field(default_factory=dict)


@dataclass
class CandleData:
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    volumes: np.ndarray
    epochs: np.ndarray

    @classmethod
    def from_candles(cls, candles: list[dict]) -> "CandleData":
        """Parse Deriv candle format: {open, high, low, close, epoch}"""
        candles = sorted(candles, key=lambda c: c["epoch"])
        return cls(
            opens=np.array([float(c["open"]) for c in candles]),
            highs=np.array([float(c["high"]) for c in candles]),
            lows=np.array([float(c["low"]) for c in candles]),
            closes=np.array([float(c["close"]) for c in candles]),
            volumes=np.array([float(c.get("volume", 1.0)) for c in candles]),
            epochs=np.array([int(c["epoch"]) for c in candles]),
        )

    def __len__(self) -> int:
        return len(self.closes)


# ─── EMA ─────────────────────────────────────────────────────────────────────

def ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average — full array."""
    if len(prices) < period:
        return np.full(len(prices), np.nan)
    result = np.full(len(prices), np.nan)
    k = 2.0 / (period + 1)
    # Seed with SMA
    result[period - 1] = np.mean(prices[:period])
    for i in range(period, len(prices)):
        result[i] = prices[i] * k + result[i - 1] * (1 - k)
    return result


def ema_indicator(data: CandleData, period: int) -> IndicatorResult:
    values = ema(data.closes, period)
    current = values[-1]
    prev = values[-2] if len(values) > 1 else current
    price = data.closes[-1]
    direction = "rising" if current > prev else "falling"
    relation = "above" if price > current else "below"
    return IndicatorResult(
        name=f"EMA{period}",
        value=current,
        interpretation=f"Price is {relation} EMA{period} ({current:.5f}), EMA is {direction}",
        raw={"values": values.tolist(), "current": current, "period": period},
    )


# ─── RSI ─────────────────────────────────────────────────────────────────────

def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    if len(prices) < period + 1:
        return np.full(len(prices), np.nan)
    result = np.full(len(prices), np.nan)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))
    return result


def rsi_indicator(data: CandleData, period: int = 14) -> IndicatorResult:
    values = rsi(data.closes, period)
    current = values[-1]
    if np.isnan(current):
        return IndicatorResult("RSI", float("nan"), "Insufficient data", {})
    if current >= 70:
        zone = "OVERBOUGHT — expect potential reversal or pullback"
    elif current >= 60:
        zone = "BULLISH zone — strong but not extreme"
    elif current >= 40:
        zone = "NEUTRAL zone — no clear bias"
    elif current >= 30:
        zone = "BEARISH zone — weak but not extreme"
    else:
        zone = "OVERSOLD — expect potential bounce or reversal"
    return IndicatorResult(
        name=f"RSI{period}",
        value=current,
        interpretation=f"RSI({period}) = {current:.1f} — {zone}",
        raw={"values": values.tolist(), "current": current, "period": period},
    )


# ─── MACD ────────────────────────────────────────────────────────────────────

def macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(prices, fast)
    slow_ema = ema(prices, slow)
    macd_line = fast_ema - slow_ema
    valid_mask = ~np.isnan(macd_line)
    padded_signal = np.full(len(macd_line), np.nan)
    if valid_mask.sum() >= signal:
        valid_start = np.where(valid_mask)[0][0]
        signal_vals = ema(macd_line[valid_mask], signal)
        signal_start = valid_start + signal - 1
        slots = len(prices) - signal_start
        signal_vals = signal_vals[:slots]  # clip to available space
        padded_signal[signal_start:signal_start + len(signal_vals)] = signal_vals
    histogram = macd_line - padded_signal
    return macd_line, padded_signal, histogram


def macd_indicator(data: CandleData, fast: int = 12, slow: int = 26, signal: int = 9) -> IndicatorResult:
    macd_line, signal_line, histogram = macd(data.closes, fast, slow, signal)
    m = macd_line[-1]
    s = signal_line[-1]
    h = histogram[-1]
    h_prev = histogram[-2] if len(histogram) > 1 else h
    if np.isnan(m) or np.isnan(s):
        return IndicatorResult("MACD", float("nan"), "Insufficient data", {})
    crossover = ""
    if h > 0 and h_prev <= 0:
        crossover = " — BULLISH crossover just occurred"
    elif h < 0 and h_prev >= 0:
        crossover = " — BEARISH crossover just occurred"
    bias = "bullish" if m > s else "bearish"
    return IndicatorResult(
        name="MACD",
        value=h,
        interpretation=f"MACD histogram = {h:.5f} ({bias} bias){crossover}",
        raw={
            "macd": macd_line.tolist(),
            "signal": signal_line.tolist(),
            "histogram": histogram.tolist(),
            "current_macd": m,
            "current_signal": s,
            "current_hist": h,
        },
    )


# ─── Bollinger Bands ─────────────────────────────────────────────────────────

def bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2.0):
    middle = np.full(len(prices), np.nan)
    upper = np.full(len(prices), np.nan)
    lower = np.full(len(prices), np.nan)
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        mid = np.mean(window)
        std = np.std(window, ddof=0)
        middle[i] = mid
        upper[i] = mid + std_dev * std
        lower[i] = mid - std_dev * std
    return upper, middle, lower


def bollinger_indicator(data: CandleData, period: int = 20, std_dev: float = 2.0) -> IndicatorResult:
    upper, middle, lower = bollinger_bands(data.closes, period, std_dev)
    price = data.closes[-1]
    u, m, l = upper[-1], middle[-1], lower[-1]
    if np.isnan(u):
        return IndicatorResult("BB", float("nan"), "Insufficient data", {})
    band_width = (u - l) / m * 100
    if price >= u:
        position = "AT/ABOVE upper band — overbought, mean reversion SELL signal"
    elif price <= l:
        position = "AT/BELOW lower band — oversold, mean reversion BUY signal"
    elif price > m:
        pct = (price - m) / (u - m) * 100
        position = f"{pct:.0f}% through upper half — bullish bias"
    else:
        pct = (m - price) / (m - l) * 100
        position = f"{pct:.0f}% through lower half — bearish bias"
    return IndicatorResult(
        name="BollingerBands",
        value=price,
        interpretation=f"Price {position}. Band width: {band_width:.2f}%",
        raw={
            "upper": u, "middle": m, "lower": l,
            "price": price, "band_width": band_width,
            "upper_arr": upper.tolist(),
            "middle_arr": middle.tolist(),
            "lower_arr": lower.tolist(),
        },
    )


# ─── ATR ─────────────────────────────────────────────────────────────────────

def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    result = np.full(len(closes), np.nan)
    if len(tr) < period:
        return result
    result[period] = np.mean(tr[:period])
    for i in range(period + 1, len(closes)):
        result[i] = (result[i - 1] * (period - 1) + tr[i - 1]) / period
    return result


def atr_indicator(data: CandleData, period: int = 14) -> IndicatorResult:
    values = atr(data.highs, data.lows, data.closes, period)
    current = values[-1]
    avg_20 = np.nanmean(values[-20:]) if len(values) >= 20 else current
    if np.isnan(current):
        return IndicatorResult("ATR", float("nan"), "Insufficient data", {})
    ratio = current / avg_20 if avg_20 > 0 else 1.0
    if ratio > 1.5:
        vol_desc = "HIGH volatility — expanded range, breakout potential"
    elif ratio > 1.2:
        vol_desc = "ABOVE average volatility — active market"
    elif ratio < 0.5:
        vol_desc = "LOW volatility — consolidating, breakout may be imminent"
    elif ratio < 0.8:
        vol_desc = "BELOW average volatility — quiet market"
    else:
        vol_desc = "NORMAL volatility"
    return IndicatorResult(
        name=f"ATR{period}",
        value=current,
        interpretation=f"ATR({period}) = {current:.5f} ({vol_desc})",
        raw={"values": values.tolist(), "current": current, "avg_20": avg_20, "ratio": ratio},
    )


# ─── Volume Analysis ─────────────────────────────────────────────────────────

def volume_indicator(data: CandleData, period: int = 20) -> IndicatorResult:
    current_vol = data.volumes[-1]
    avg_vol = np.mean(data.volumes[-period - 1:-1]) if len(data.volumes) > period else np.mean(data.volumes)
    ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
    if ratio >= 2.0:
        desc = f"VOLUME SPIKE — {ratio:.1f}x average (strong confirmation signal)"
    elif ratio >= 1.2:
        desc = f"Above average volume ({ratio:.1f}x) — confirming move"
    elif ratio < 0.5:
        desc = f"Low volume ({ratio:.1f}x average) — weak conviction"
    else:
        desc = f"Normal volume ({ratio:.1f}x average)"
    return IndicatorResult(
        name="Volume",
        value=current_vol,
        interpretation=desc,
        raw={"current": current_vol, "average": avg_vol, "ratio": ratio},
    )


# ─── EMA Ribbon (Scalper) ────────────────────────────────────────────────────

@dataclass
class EMARibbon:
    ema5: float
    ema8: float
    ema13: float
    ema21: float
    ema34: float
    aligned_up: bool
    aligned_down: bool
    fanning_up: bool
    fanning_down: bool
    interpretation: str


def ema_ribbon(data: CandleData) -> EMARibbon:
    periods = [5, 8, 13, 21, 34]
    emas_now = []
    emas_prev = []
    for p in periods:
        arr = ema(data.closes, p)
        emas_now.append(arr[-1])
        emas_prev.append(arr[-2] if len(arr) > 1 else arr[-1])

    e5, e8, e13, e21, e34 = emas_now
    p5, p8, p13, p21, p34 = emas_prev

    aligned_up = e5 > e8 > e13 > e21 > e34
    aligned_down = e5 < e8 < e13 < e21 < e34

    # Fanning: each EMA moving away from the next
    fanning_up = aligned_up and (e5 - e8) > (p5 - p8) and (e8 - e13) > (p8 - p13)
    fanning_down = aligned_down and (e8 - e5) > (p8 - p5) and (e13 - e8) > (p13 - p8)

    if aligned_up and fanning_up:
        interpretation = "EMA ribbon ALIGNED UP and FANNING — strong BUY signal"
    elif aligned_down and fanning_down:
        interpretation = "EMA ribbon ALIGNED DOWN and FANNING — strong SELL signal"
    elif aligned_up:
        interpretation = "EMA ribbon aligned upward — bullish but not accelerating"
    elif aligned_down:
        interpretation = "EMA ribbon aligned downward — bearish but not accelerating"
    else:
        interpretation = "EMA ribbon tangled — no clear directional bias"

    return EMARibbon(
        ema5=e5, ema8=e8, ema13=e13, ema21=e21, ema34=e34,
        aligned_up=aligned_up, aligned_down=aligned_down,
        fanning_up=fanning_up, fanning_down=fanning_down,
        interpretation=interpretation,
    )


# ─── EMA Crossover Detection ─────────────────────────────────────────────────

@dataclass
class EMACross:
    crossed_up: bool
    crossed_down: bool
    fast_value: float
    slow_value: float
    interpretation: str


def ema_crossover(data: CandleData, fast_period: int = 8, slow_period: int = 21) -> EMACross:
    fast = ema(data.closes, fast_period)
    slow = ema(data.closes, slow_period)

    current_diff = fast[-1] - slow[-1]
    prev_diff = fast[-2] - slow[-2] if len(fast) > 1 else current_diff

    crossed_up = current_diff > 0 and prev_diff <= 0
    crossed_down = current_diff < 0 and prev_diff >= 0

    if crossed_up:
        desc = f"EMA{fast_period} crossed ABOVE EMA{slow_period} — BULLISH crossover"
    elif crossed_down:
        desc = f"EMA{fast_period} crossed BELOW EMA{slow_period} — BEARISH crossover"
    elif current_diff > 0:
        desc = f"EMA{fast_period} above EMA{slow_period} — bullish alignment"
    else:
        desc = f"EMA{fast_period} below EMA{slow_period} — bearish alignment"

    return EMACross(
        crossed_up=crossed_up,
        crossed_down=crossed_down,
        fast_value=fast[-1],
        slow_value=slow[-1],
        interpretation=desc,
    )


# ─── Consolidation Detection (for Breakout) ──────────────────────────────────

@dataclass
class ConsolidationResult:
    is_consolidating: bool
    current_atr: float
    avg_atr: float
    range_high: float
    range_low: float
    interpretation: str


def detect_consolidation(data: CandleData, atr_period: int = 14, lookback: int = 20) -> ConsolidationResult:
    atr_arr = atr(data.highs, data.lows, data.closes, atr_period)
    current_atr_val = atr_arr[-1]
    avg_atr = np.nanmean(atr_arr[-lookback - 1:-1])
    is_consolidating = current_atr_val < 0.5 * avg_atr

    recent_highs = data.highs[-lookback:]
    recent_lows = data.lows[-lookback:]
    range_high = float(np.max(recent_highs))
    range_low = float(np.min(recent_lows))

    if is_consolidating:
        desc = f"CONSOLIDATING — ATR {current_atr_val:.5f} is {current_atr_val/avg_atr:.1%} of 20-period average. Range: {range_low:.5f}–{range_high:.5f}"
    else:
        desc = f"Not consolidating — ATR {current_atr_val:.5f} is {current_atr_val/avg_atr:.1%} of average (need <50%)"

    return ConsolidationResult(
        is_consolidating=is_consolidating,
        current_atr=current_atr_val,
        avg_atr=avg_atr,
        range_high=range_high,
        range_low=range_low,
        interpretation=desc,
    )


# ─── Full Indicator Suite ────────────────────────────────────────────────────

def compute_all_indicators(data: CandleData) -> dict:
    """Compute all indicators at once and return as dict for JSON serialization."""
    rsi_res = rsi_indicator(data)
    macd_res = macd_indicator(data)
    bb_res = bollinger_indicator(data)
    atr_res = atr_indicator(data)
    vol_res = volume_indicator(data)
    ema8_res = ema_indicator(data, 8)
    ema21_res = ema_indicator(data, 21)
    cross = ema_crossover(data, 8, 21)
    ribbon = ema_ribbon(data)
    consol = detect_consolidation(data)

    return {
        "rsi": {"value": rsi_res.value, "interpretation": rsi_res.interpretation},
        "macd": {"value": macd_res.value, "interpretation": macd_res.interpretation, "raw": macd_res.raw},
        "bollinger": {"value": bb_res.value, "interpretation": bb_res.interpretation, "raw": bb_res.raw},
        "atr": {"value": atr_res.value, "interpretation": atr_res.interpretation},
        "volume": {"value": vol_res.value, "ratio": vol_res.raw["ratio"], "interpretation": vol_res.interpretation},
        "ema8": {"value": ema8_res.value, "interpretation": ema8_res.interpretation},
        "ema21": {"value": ema21_res.value, "interpretation": ema21_res.interpretation},
        "ema_cross": {
            "crossed_up": cross.crossed_up,
            "crossed_down": cross.crossed_down,
            "interpretation": cross.interpretation,
        },
        "ribbon": {
            "aligned_up": ribbon.aligned_up,
            "aligned_down": ribbon.aligned_down,
            "fanning_up": ribbon.fanning_up,
            "fanning_down": ribbon.fanning_down,
            "ema5": ribbon.ema5,
            "ema8": ribbon.ema8,
            "ema13": ribbon.ema13,
            "ema21": ribbon.ema21,
            "ema34": ribbon.ema34,
            "interpretation": ribbon.interpretation,
        },
        "consolidation": {
            "is_consolidating": consol.is_consolidating,
            "current_atr": consol.current_atr,
            "avg_atr": consol.avg_atr,
            "range_high": consol.range_high,
            "range_low": consol.range_low,
            "interpretation": consol.interpretation,
        },
        "price": float(data.closes[-1]),
    }
