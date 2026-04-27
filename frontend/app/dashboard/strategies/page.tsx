'use client';
import { motion } from 'framer-motion';
import { Zap, TrendingUp, BarChart2, Activity } from 'lucide-react';

const STRATEGIES = [
  { name: 'Momentum', description: 'MACD crossover + RSI filter. Rides strong directional moves.', color: 'cyan', icon: TrendingUp, instruments: 'BTCUSDT, ETHUSDT', timeframe: 'M5, M15' },
  { name: 'Mean Reversion', description: 'Bollinger Band squeeze + RSI extremes. Fades overextended moves.', color: 'violet', icon: Activity, instruments: 'BNBUSDT, SOLUSDT', timeframe: 'M15, H1' },
  { name: 'Breakout', description: 'ATR channel break + volume confirmation. Captures trend initiations.', color: 'emerald', icon: BarChart2, instruments: 'BTCUSDT, XRPUSDT', timeframe: 'H1, H4' },
  { name: 'Scalper', description: 'EMA ribbon + momentum bursts. Fast entries on micro structure.', color: 'amber', icon: Zap, instruments: 'BTCUSDT', timeframe: 'M1, M5' },
];

const COLOR: Record<string, string> = {
  cyan:    'border-cyan-DEFAULT/30 text-cyan-DEFAULT bg-cyan-dim',
  violet:  'border-violet-DEFAULT/30 text-violet-DEFAULT bg-violet-dim',
  emerald: 'border-emerald-DEFAULT/30 text-emerald-DEFAULT bg-emerald-dim',
  amber:   'border-amber-DEFAULT/30 text-amber-DEFAULT bg-amber-dim',
};

export default function StrategiesPage() {
  return (
    <div className="p-6 space-y-6 min-h-screen">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="text-xl font-bold font-mono text-amber-DEFAULT">STRATEGIES</h1>
        <p className="text-xs text-text-secondary font-mono mt-0.5">4 active signal generators · All run every 60s on live candle data</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {STRATEGIES.map(({ name, description, color, icon: Icon, instruments, timeframe }, i) => (
          <motion.div
            key={name}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`cyber-panel rounded-lg p-6 clip-corner border ${COLOR[color].split(' ')[0]}`}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded flex items-center justify-center ${COLOR[color].split(' ').slice(2).join(' ')}`}>
                  <Icon className={`w-4 h-4 ${COLOR[color].split(' ')[1]}`} />
                </div>
                <div>
                  <h3 className={`text-sm font-bold font-mono ${COLOR[color].split(' ')[1]}`}>{name.toUpperCase()}</h3>
                  <p className="text-[10px] font-mono text-text-muted">{timeframe}</p>
                </div>
              </div>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${COLOR[color]}`}>ACTIVE</span>
            </div>
            <p className="text-xs text-text-secondary font-mono mb-4">{description}</p>
            <div className="border-t border-border pt-3">
              <p className="text-[10px] font-mono text-text-muted">Instruments: <span className="text-text-secondary">{instruments}</span></p>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="cyber-panel rounded-lg p-4 border border-cyan-DEFAULT/10">
        <p className="text-xs font-mono text-text-secondary">
          <span className="text-cyan-DEFAULT">Risk rules enforced on every signal:</span> 1.5% max risk/trade · 5% daily loss cap · 15% drawdown kill switch · Stop-loss mandatory on all trades
        </p>
      </div>
    </div>
  );
}
