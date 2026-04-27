"""
Groq-powered trade explanation generator.
Converts raw indicator data into clear, plain-English trade reasoning.
Using llama-3.3-70b-versatile for fast, high-quality explanations.
"""
from typing import Optional
from loguru import logger
from groq import AsyncGroq

from app.core.config import settings
from app.services.analysis.signals import Signal
from app.services.risk.manager import TradeParameters


SYSTEM_PROMPT = """You are the Akili Markets Trader AI explainer. Your job is to explain algorithmic trading decisions in clear, plain English that anyone can understand — no trading jargon without explanation.

When explaining a trade:
1. State what the market is doing (trending, reversing, breaking out, consolidating)
2. Explain why the indicators triggered
3. State the risk clearly: how much is at risk and what the reward target is
4. Give confidence context: why this setup is or isn't high-conviction

Be concise (3-4 sentences max). Be honest about uncertainty. Never hype or guarantee outcomes."""


class TradeExplainer:
    def __init__(self):
        self._client: Optional[AsyncGroq] = None

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    async def explain_trade(self, signal: Signal, params: TradeParameters) -> str:
        try:
            client = self._get_client()
            user_message = f"""
Explain this {signal.strategy_type.upper()} trade signal:

Instrument: {signal.instrument}
Direction: {signal.direction.value}
Confidence: {signal.confidence:.0f}/100
Timeframe: {signal.timeframe}

Key indicators:
{self._format_indicators(signal.indicators)}

Risk details:
- Risk amount: ${params.risk_amount:.2f} ({params.risk_pct}% of account)
- Stop loss: {params.stop_loss:.5f}
- Take profit: {params.take_profit:.5f if params.take_profit else "none set"}
- Risk:Reward = {params.risk_reward_ratio:.1f}:1

System reason: {signal.reason}

Explain this trade in plain English (3-4 sentences max).
"""
            response = await client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=250,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"AI explanation failed: {e}")
            return signal.reason  # fallback to system reason

    def _format_indicators(self, indicators: dict) -> str:
        lines = []
        for k, v in indicators.items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.5f}")
            else:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    async def explain_backtest_result(self, result: dict) -> str:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"""
Summarize this backtest result in plain English (4-5 sentences):

Strategy: {result.get('strategy_name', 'Unknown')}
Instrument: {result.get('instrument')}
Period: {result.get('date_from')} to {result.get('date_to')}

Results:
- Total return: {result.get('total_return_pct', 0):.2f}%
- Win rate: {result.get('win_rate', 0)*100:.1f}%
- Profit factor: {result.get('profit_factor', 0):.2f}
- Sharpe ratio: {result.get('sharpe_ratio', 0):.2f}
- Max drawdown: {result.get('max_drawdown_pct', 0):.2f}%
- Total trades: {result.get('total_trades', 0)}
- Expectancy: ${result.get('expectancy', 0):.2f} per trade

What does this tell us about the strategy's performance? Be honest.
"""
                    }
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Backtest explanation failed: {e}")
            return "Backtest explanation unavailable."


trade_explainer = TradeExplainer()
