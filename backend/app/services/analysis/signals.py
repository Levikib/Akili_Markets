"""
Signal generator — takes CandleData + indicator output → Signal objects.
Each strategy's logic lives here as a pure function.
Signals carry confidence (0-100) and a plain-English reason string.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import numpy as np
from loguru import logger

from app.services.analysis.indicators import (
    CandleData, rsi, ema, ema_crossover, ema_ribbon,
    bollinger_bands, atr, volume_indicator, detect_consolidation,
    compute_all_indicators
)
from app.models.trading import TradeDirection


@dataclass
class Signal:
    direction: TradeDirection
    confidence: float       # 0-100
    reason: str             # plain English for UI/logs/AI
    strategy_type: str
    instrument: str
    timeframe: str
    indicators: dict
    suggested_stop_loss: Optional[float] = None
    suggested_take_profit: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.confidence = max(0.0, min(100.0, self.confidence))


NO_SIGNAL = None


# ─── Strategy 1: Akili Momentum ──────────────────────────────────────────────

def generate_momentum_signal(
    data: CandleData,
    instrument: str,
    timeframe: str,
    confidence_threshold: float = 60.0,
) -> Optional[Signal]:
    """
    EMA 8/21 crossover + RSI 40-70 filter (BUY) / 30-60 (SELL) + volume > 1.2x avg.
    """
    if len(data) < 35:
        return NO_SIGNAL

    cross = ema_crossover(data, fast_period=8, slow_period=21)
    rsi_arr = rsi(data.closes, period=14)
    rsi_val = rsi_arr[-1]
    vol = volume_indicator(data, period=20)

    if np.isnan(rsi_val):
        return NO_SIGNAL

    vol_ratio = vol.raw["ratio"]
    vol_confirmed = vol_ratio >= 1.2

    if cross.crossed_up and 40 <= rsi_val <= 70 and vol_confirmed:
        confidence = _momentum_confidence(rsi_val, vol_ratio, cross.crossed_up)
        atr_arr = atr(data.highs, data.lows, data.closes, 14)
        atr_val = atr_arr[-1]
        price = data.closes[-1]
        sl = price - 1.5 * atr_val
        tp = price + 2.5 * atr_val
        reason = (
            f"MOMENTUM BUY: EMA8 ({cross.fast_value:.5f}) crossed above EMA21 ({cross.slow_value:.5f}). "
            f"RSI {rsi_val:.1f} in bullish zone (40-70). "
            f"Volume {vol_ratio:.1f}x average confirming the move. "
            f"Stop loss at {sl:.5f}, target at {tp:.5f}."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.BUY,
            confidence=confidence,
            reason=reason,
            strategy_type="momentum",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "ema8": cross.fast_value, "ema21": cross.slow_value,
                "rsi": rsi_val, "volume_ratio": vol_ratio, "atr": float(atr_val),
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    if cross.crossed_down and 30 <= rsi_val <= 60 and vol_confirmed:
        confidence = _momentum_confidence(rsi_val, vol_ratio, cross.crossed_up)
        atr_arr = atr(data.highs, data.lows, data.closes, 14)
        atr_val = atr_arr[-1]
        price = data.closes[-1]
        sl = price + 1.5 * atr_val
        tp = price - 2.5 * atr_val
        reason = (
            f"MOMENTUM SELL: EMA8 ({cross.fast_value:.5f}) crossed below EMA21 ({cross.slow_value:.5f}). "
            f"RSI {rsi_val:.1f} in bearish zone (30-60). "
            f"Volume {vol_ratio:.1f}x average confirming the move. "
            f"Stop loss at {sl:.5f}, target at {tp:.5f}."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.SELL,
            confidence=confidence,
            reason=reason,
            strategy_type="momentum",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "ema8": cross.fast_value, "ema21": cross.slow_value,
                "rsi": rsi_val, "volume_ratio": vol_ratio, "atr": float(atr_val),
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    return NO_SIGNAL


def _momentum_confidence(rsi_val: float, vol_ratio: float, is_buy: bool) -> float:
    base = 55.0
    # RSI in ideal zone gives more confidence
    if is_buy:
        rsi_bonus = 15.0 if 50 <= rsi_val <= 65 else 5.0
    else:
        rsi_bonus = 15.0 if 35 <= rsi_val <= 50 else 5.0
    # Volume multiplier bonus
    vol_bonus = min(15.0, (vol_ratio - 1.2) * 10)
    return base + rsi_bonus + vol_bonus


# ─── Strategy 2: Akili Mean Reversion ────────────────────────────────────────

def generate_mean_reversion_signal(
    data: CandleData,
    instrument: str,
    timeframe: str,
    confidence_threshold: float = 65.0,
) -> Optional[Signal]:
    """
    Price at BB bands + RSI confirmation (<30 for BUY, >70 for SELL).
    """
    if len(data) < 25:
        return NO_SIGNAL

    upper, middle, lower = bollinger_bands(data.closes, period=20, std_dev=2.0)
    rsi_arr = rsi(data.closes, period=14)
    price = data.closes[-1]
    rsi_val = rsi_arr[-1]

    if np.isnan(lower[-1]) or np.isnan(rsi_val):
        return NO_SIGNAL

    atr_arr = atr(data.highs, data.lows, data.closes, 14)
    atr_val = atr_arr[-1]

    # BUY: price at/below lower band + RSI oversold
    if price <= lower[-1] and rsi_val < 30:
        penetration = (lower[-1] - price) / atr_val if atr_val > 0 else 0
        confidence = 65.0 + min(20.0, penetration * 10) + min(10.0, (30 - rsi_val))
        sl = price - 1.0 * atr_val
        tp = float(middle[-1])  # target: return to middle band
        reason = (
            f"MEAN REVERSION BUY: Price ({price:.5f}) at/below lower Bollinger Band ({lower[-1]:.5f}). "
            f"RSI {rsi_val:.1f} confirms oversold condition (<30). "
            f"Target: return to middle band ({tp:.5f}). "
            f"Stop loss: {sl:.5f}."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.BUY,
            confidence=confidence,
            reason=reason,
            strategy_type="mean_reversion",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "price": price, "bb_lower": float(lower[-1]),
                "bb_middle": float(middle[-1]), "bb_upper": float(upper[-1]),
                "rsi": rsi_val, "atr": float(atr_val),
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    # SELL: price at/above upper band + RSI overbought
    if price >= upper[-1] and rsi_val > 70:
        penetration = (price - upper[-1]) / atr_val if atr_val > 0 else 0
        confidence = 65.0 + min(20.0, penetration * 10) + min(10.0, rsi_val - 70)
        sl = price + 1.0 * atr_val
        tp = float(middle[-1])
        reason = (
            f"MEAN REVERSION SELL: Price ({price:.5f}) at/above upper Bollinger Band ({upper[-1]:.5f}). "
            f"RSI {rsi_val:.1f} confirms overbought condition (>70). "
            f"Target: return to middle band ({tp:.5f}). "
            f"Stop loss: {sl:.5f}."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.SELL,
            confidence=confidence,
            reason=reason,
            strategy_type="mean_reversion",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "price": price, "bb_lower": float(lower[-1]),
                "bb_middle": float(middle[-1]), "bb_upper": float(upper[-1]),
                "rsi": rsi_val, "atr": float(atr_val),
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    return NO_SIGNAL


# ─── Strategy 3: Akili Breakout ───────────────────────────────────────────────

def generate_breakout_signal(
    data: CandleData,
    instrument: str,
    timeframe: str,
    confidence_threshold: float = 70.0,
) -> Optional[Signal]:
    """
    ATR consolidation detected → breakout when price moves >1.5x ATR beyond range.
    Volume spike >2x average required.
    """
    if len(data) < 40:
        return NO_SIGNAL

    consol = detect_consolidation(data, atr_period=14, lookback=20)
    if not consol.is_consolidating:
        return NO_SIGNAL

    vol = volume_indicator(data, period=20)
    vol_ratio = vol.raw["ratio"]
    if vol_ratio < 2.0:
        return NO_SIGNAL

    price = data.closes[-1]
    prev_price = data.closes[-2]
    breakout_dist = 1.5 * consol.current_atr

    # Upside breakout
    if price > consol.range_high + breakout_dist and price > prev_price:
        atr_val = consol.current_atr
        sl = consol.range_high - 1.5 * atr_val
        tp = price + 2.0 * (price - sl)
        rr = (tp - price) / (price - sl) if price > sl else 0
        confidence = 70.0 + min(20.0, (vol_ratio - 2.0) * 5) + min(10.0, rr * 2)
        reason = (
            f"BREAKOUT BUY: Price ({price:.5f}) broke above consolidation range high "
            f"({consol.range_high:.5f}) by {(price - consol.range_high):.5f}. "
            f"Volume spike: {vol_ratio:.1f}x average (need 2x). "
            f"ATR during consolidation: {atr_val:.5f}. "
            f"Stop loss: {sl:.5f}, target: {tp:.5f} (R:R {rr:.1f}:1)."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.BUY,
            confidence=confidence,
            reason=reason,
            strategy_type="breakout",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "price": price, "range_high": consol.range_high, "range_low": consol.range_low,
                "atr": atr_val, "volume_ratio": vol_ratio,
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    # Downside breakout
    if price < consol.range_low - breakout_dist and price < prev_price:
        atr_val = consol.current_atr
        sl = consol.range_low + 1.5 * atr_val
        tp = price - 2.0 * (sl - price)
        rr = (price - tp) / (sl - price) if sl > price else 0
        confidence = 70.0 + min(20.0, (vol_ratio - 2.0) * 5) + min(10.0, rr * 2)
        reason = (
            f"BREAKOUT SELL: Price ({price:.5f}) broke below consolidation range low "
            f"({consol.range_low:.5f}) by {(consol.range_low - price):.5f}. "
            f"Volume spike: {vol_ratio:.1f}x average (need 2x). "
            f"ATR during consolidation: {atr_val:.5f}. "
            f"Stop loss: {sl:.5f}, target: {tp:.5f} (R:R {rr:.1f}:1)."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.SELL,
            confidence=confidence,
            reason=reason,
            strategy_type="breakout",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "price": price, "range_high": consol.range_high, "range_low": consol.range_low,
                "atr": atr_val, "volume_ratio": vol_ratio,
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    return NO_SIGNAL


# ─── Strategy 4: Akili Scalper ────────────────────────────────────────────────

def generate_scalper_signal(
    data: CandleData,
    instrument: str,
    timeframe: str,
    confidence_threshold: float = 75.0,
) -> Optional[Signal]:
    """
    5-EMA ribbon (5, 8, 13, 21, 34) all aligned and fanning in one direction.
    Very tight SL (0.5x ATR). R:R minimum 1:1.
    """
    if len(data) < 40:
        return NO_SIGNAL

    ribbon = ema_ribbon(data)
    atr_arr = atr(data.highs, data.lows, data.closes, 14)
    atr_val = atr_arr[-1]
    price = data.closes[-1]

    if ribbon.aligned_up and ribbon.fanning_up:
        sl = price - 0.5 * atr_val
        tp = price + 0.5 * atr_val  # 1:1 minimum
        confidence = 75.0 + (10.0 if ribbon.fanning_up else 0.0)
        reason = (
            f"SCALPER BUY: All 5 EMAs aligned upward and fanning. "
            f"EMA5={ribbon.ema5:.5f} > EMA8={ribbon.ema8:.5f} > EMA13={ribbon.ema13:.5f} > "
            f"EMA21={ribbon.ema21:.5f} > EMA34={ribbon.ema34:.5f}. "
            f"Tight SL at {sl:.5f} (0.5x ATR), target {tp:.5f} (1:1 R:R)."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.BUY,
            confidence=confidence,
            reason=reason,
            strategy_type="scalper",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "ema5": ribbon.ema5, "ema8": ribbon.ema8, "ema13": ribbon.ema13,
                "ema21": ribbon.ema21, "ema34": ribbon.ema34,
                "atr": float(atr_val), "fanning": ribbon.fanning_up,
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    if ribbon.aligned_down and ribbon.fanning_down:
        sl = price + 0.5 * atr_val
        tp = price - 0.5 * atr_val
        confidence = 75.0 + (10.0 if ribbon.fanning_down else 0.0)
        reason = (
            f"SCALPER SELL: All 5 EMAs aligned downward and fanning. "
            f"EMA5={ribbon.ema5:.5f} < EMA8={ribbon.ema8:.5f} < EMA13={ribbon.ema13:.5f} < "
            f"EMA21={ribbon.ema21:.5f} < EMA34={ribbon.ema34:.5f}. "
            f"Tight SL at {sl:.5f} (0.5x ATR), target {tp:.5f} (1:1 R:R)."
        )
        if confidence < confidence_threshold:
            return NO_SIGNAL
        return Signal(
            direction=TradeDirection.SELL,
            confidence=confidence,
            reason=reason,
            strategy_type="scalper",
            instrument=instrument,
            timeframe=timeframe,
            indicators={
                "ema5": ribbon.ema5, "ema8": ribbon.ema8, "ema13": ribbon.ema13,
                "ema21": ribbon.ema21, "ema34": ribbon.ema34,
                "atr": float(atr_val), "fanning": ribbon.fanning_down,
            },
            suggested_stop_loss=sl,
            suggested_take_profit=tp,
        )

    return NO_SIGNAL


# ─── Signal Dispatcher ────────────────────────────────────────────────────────

STRATEGY_GENERATORS = {
    "momentum": generate_momentum_signal,
    "mean_reversion": generate_mean_reversion_signal,
    "breakout": generate_breakout_signal,
    "scalper": generate_scalper_signal,
}


def generate_signal(
    strategy_type: str,
    data: CandleData,
    instrument: str,
    timeframe: str,
    confidence_threshold: float = 60.0,
) -> Optional[Signal]:
    generator = STRATEGY_GENERATORS.get(strategy_type)
    if not generator:
        logger.warning(f"Unknown strategy type: {strategy_type}")
        return None
    try:
        return generator(data, instrument, timeframe, confidence_threshold)
    except Exception as e:
        logger.error(f"Signal generation error [{strategy_type}@{instrument}]: {e}")
        return None
