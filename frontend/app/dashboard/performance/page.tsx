'use client';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { tradingApi } from '@/lib/api';
import { BarChart2 } from 'lucide-react';
import { clsx } from 'clsx';

export default function PerformancePage() {
  const { data: perf } = useQuery({
    queryKey: ['performance'],
    queryFn: () => tradingApi.performance().then(r => r.data),
    refetchInterval: 30000,
  });

  const stats = [
    { label: 'Total P&L',        value: `${(perf?.total_pnl ?? 0) >= 0 ? '+' : ''}$${(perf?.total_pnl ?? 0).toFixed(2)}`,   color: (perf?.total_pnl ?? 0) >= 0 ? 'emerald' : 'rose' },
    { label: 'Win Rate',         value: `${(perf?.win_rate ?? 0).toFixed(1)}%`,          color: 'cyan' },
    { label: 'Total Trades',     value: perf?.total_trades ?? 0,                          color: 'violet' },
    { label: 'Winning Trades',   value: perf?.winning_trades ?? 0,                        color: 'emerald' },
    { label: 'Losing Trades',    value: perf?.losing_trades ?? 0,                         color: 'rose' },
    { label: 'Avg Win',          value: `$${(perf?.avg_win ?? 0).toFixed(2)}`,            color: 'emerald' },
    { label: 'Avg Loss',         value: `$${(perf?.avg_loss ?? 0).toFixed(2)}`,           color: 'rose' },
    { label: 'Profit Factor',    value: (perf?.profit_factor ?? 0).toFixed(2),            color: 'cyan' },
    { label: 'Max Drawdown',     value: `${(perf?.max_drawdown_pct ?? 0).toFixed(1)}%`,  color: 'amber' },
    { label: 'Sharpe Ratio',     value: (perf?.sharpe_ratio ?? 0).toFixed(2),            color: 'violet' },
  ];

  const colorMap: Record<string, string> = {
    cyan:    'text-cyan-DEFAULT',
    violet:  'text-violet-DEFAULT',
    emerald: 'text-emerald-DEFAULT',
    rose:    'text-rose-DEFAULT',
    amber:   'text-amber-DEFAULT',
  };

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
        <BarChart2 className="w-5 h-5 text-violet-DEFAULT" />
        <div>
          <h1 className="text-xl font-bold font-mono text-violet-DEFAULT text-glow-violet">ANALYTICS</h1>
          <p className="text-xs text-text-secondary font-mono mt-0.5">Performance metrics · All paper trades</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {stats.map(({ label, value, color }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            className="cyber-panel rounded-lg p-4 clip-corner"
          >
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">{label}</p>
            <p className={clsx('text-lg font-bold font-mono', colorMap[color])}>{value}</p>
          </motion.div>
        ))}
      </div>

      {/* Strategy breakdown placeholder */}
      <div className="cyber-panel rounded-lg p-6 clip-corner">
        <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary mb-4">Strategy Breakdown</h2>
        {!perf?.by_strategy || Object.keys(perf.by_strategy).length === 0 ? (
          <p className="text-text-muted text-xs font-mono text-center py-8">No strategy data yet — trades will populate this</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(perf.by_strategy).map(([strategy, data]: [string, any]) => (
              <div key={strategy} className="flex items-center justify-between p-3 bg-surface rounded border border-border">
                <p className="text-xs font-mono text-text-primary font-bold">{strategy}</p>
                <div className="flex gap-6 text-xs font-mono">
                  <span className="text-text-secondary">{data.total} trades</span>
                  <span className="text-cyan-DEFAULT">{data.win_rate?.toFixed(1)}% WR</span>
                  <span className={data.pnl >= 0 ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'}>
                    {data.pnl >= 0 ? '+' : ''}${data.pnl?.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
