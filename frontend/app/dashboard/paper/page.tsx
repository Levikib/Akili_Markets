'use client';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { tradingApi } from '@/lib/api';
import { clsx } from 'clsx';
import { FlaskConical } from 'lucide-react';

export default function PaperPage() {
  const { data: perf } = useQuery({
    queryKey: ['performance'],
    queryFn: () => tradingApi.performance().then(r => r.data),
    refetchInterval: 15000,
  });

  const { data: trades } = useQuery({
    queryKey: ['trades', 'paper'],
    queryFn: () => tradingApi.trades({ limit: 100 }).then(r => r.data),
    refetchInterval: 15000,
  });

  const balance   = perf?.paper_balance ?? 1000;
  const totalPnl  = perf?.total_pnl ?? 0;
  const winRate   = perf?.win_rate ?? 0;
  const totalT    = perf?.total_trades ?? 0;

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
        <FlaskConical className="w-5 h-5 text-emerald-DEFAULT" />
        <div>
          <h1 className="text-xl font-bold font-mono text-emerald-DEFAULT text-glow-emerald">PAPER TRADING</h1>
          <p className="text-xs text-text-secondary font-mono mt-0.5">Simulated · No real money · Full strategy validation</p>
        </div>
      </motion.div>

      {/* Balance card */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Paper Balance', value: `$${balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, color: 'emerald' },
          { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`, color: totalPnl >= 0 ? 'emerald' : 'rose' },
          { label: 'Win Rate', value: `${winRate.toFixed(1)}%`, color: 'cyan' },
          { label: 'Total Trades', value: totalT, color: 'violet' },
        ].map(({ label, value, color }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="cyber-panel rounded-lg p-4 clip-corner"
          >
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest mb-2">{label}</p>
            <p className={clsx(
              'text-xl font-bold font-mono',
              color === 'emerald' ? 'text-emerald-DEFAULT' :
              color === 'rose' ? 'text-rose-DEFAULT' :
              color === 'cyan' ? 'text-cyan-DEFAULT' : 'text-violet-DEFAULT'
            )}>{value}</p>
          </motion.div>
        ))}
      </div>

      {/* Trade history table */}
      <div className="cyber-panel rounded-lg p-5 clip-corner">
        <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary mb-4">Trade History</h2>
        {!trades || trades.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-text-muted text-xs font-mono">No paper trades yet</p>
            <p className="text-text-muted text-[10px] font-mono mt-1">Strategies are scanning — trades will appear here</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border">
                  {['Instrument', 'Strategy', 'Direction', 'Entry', 'Exit', 'P&L', 'Status', 'Time'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-text-muted text-[10px] uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t: any) => (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-surface/50 transition-colors">
                    <td className="py-2.5 px-3 text-text-primary font-bold">{t.instrument}</td>
                    <td className="py-2.5 px-3 text-text-secondary">{t.strategy}</td>
                    <td className={clsx('py-2.5 px-3 font-bold', t.direction === 'long' ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT')}>
                      {t.direction?.toUpperCase()}
                    </td>
                    <td className="py-2.5 px-3 text-text-primary">${t.entry_price?.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-text-secondary">{t.exit_price ? `$${t.exit_price.toFixed(2)}` : '—'}</td>
                    <td className={clsx('py-2.5 px-3 font-bold', (t.pnl ?? 0) >= 0 ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT')}>
                      {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={clsx(
                        'px-2 py-0.5 rounded text-[9px]',
                        t.status === 'open' ? 'bg-cyan-dim text-cyan-DEFAULT' :
                        t.status === 'closed_tp' ? 'bg-emerald-dim text-emerald-DEFAULT' :
                        t.status === 'closed_sl' ? 'bg-rose-dim text-rose-DEFAULT' : 'bg-surface text-text-muted'
                      )}>
                        {t.status?.toUpperCase().replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-text-muted text-[10px]">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
