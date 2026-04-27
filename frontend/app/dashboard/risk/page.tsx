'use client';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Shield, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '@/lib/api';

export default function RiskPage() {
  const { data: risk } = useQuery({
    queryKey: ['risk'],
    queryFn: () => api.get('/risk/status').then(r => r.data),
    refetchInterval: 10000,
  });

  const rules = [
    { label: 'Max Risk / Trade', value: '1.5%', cap: '2.0%', status: 'enforced' },
    { label: 'Daily Loss Cap', value: `${risk?.daily_loss_pct?.toFixed(1) ?? '0.0'}%`, cap: '5.0%', status: (risk?.daily_loss_pct ?? 0) > 3 ? 'warning' : 'ok' },
    { label: 'Max Drawdown Kill Switch', value: `${risk?.drawdown_pct?.toFixed(1) ?? '0.0'}%`, cap: '15.0%', status: (risk?.drawdown_pct ?? 0) > 10 ? 'warning' : 'ok' },
    { label: 'Stop-Loss on Every Trade', value: 'Mandatory', cap: '—', status: 'enforced' },
    { label: 'Leverage', value: '1x', cap: '1x max', status: 'enforced' },
    { label: 'Simultaneous Positions', value: `${risk?.open_positions ?? 0}`, cap: '5 max', status: 'ok' },
  ];

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
        <Shield className="w-5 h-5 text-rose-DEFAULT" />
        <div>
          <h1 className="text-xl font-bold font-mono text-rose-DEFAULT text-glow-rose">RISK MANAGEMENT</h1>
          <p className="text-xs text-text-secondary font-mono mt-0.5">Hard-coded rules · Cannot be disabled · Enforced on every signal</p>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {rules.map(({ label, value, cap, status }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className={clsx(
              'cyber-panel rounded-lg p-5 clip-corner border',
              status === 'warning' ? 'border-amber-DEFAULT/40' :
              status === 'enforced' ? 'border-rose-DEFAULT/20' : 'border-border'
            )}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">{label}</p>
                <p className={clsx(
                  'text-lg font-bold font-mono',
                  status === 'warning' ? 'text-amber-DEFAULT' :
                  status === 'enforced' ? 'text-rose-DEFAULT' : 'text-text-primary'
                )}>{value}</p>
                <p className="text-[10px] font-mono text-text-muted mt-1">Cap: {cap}</p>
              </div>
              {status === 'warning'
                ? <AlertTriangle className="w-4 h-4 text-amber-DEFAULT" />
                : <Shield className="w-4 h-4 text-text-muted" />
              }
            </div>
          </motion.div>
        ))}
      </div>

      <div className="cyber-panel rounded-lg p-5 border border-rose-DEFAULT/20">
        <p className="text-xs font-mono text-text-secondary leading-relaxed">
          <span className="text-rose-DEFAULT font-bold">HARD RULES — </span>
          These limits are enforced in the backend Risk Manager and cannot be overridden from the UI.
          Any signal that would violate a rule is rejected before order placement.
          The 15% drawdown kill switch immediately cancels all open orders and closes all positions.
        </p>
      </div>
    </div>
  );
}
