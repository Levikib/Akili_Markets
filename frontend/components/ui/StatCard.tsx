'use client';
import { motion } from 'framer-motion';
import { clsx } from 'clsx';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: 'cyan' | 'emerald' | 'rose' | 'violet' | 'amber';
  icon?: React.ReactNode;
  index?: number;
}

const COLOR = {
  cyan:    { text: 'text-cyan-DEFAULT',    border: 'border-cyan-DEFAULT/30',    bg: 'bg-cyan-dim',    glow: 'shadow-cyan-glow' },
  emerald: { text: 'text-emerald-DEFAULT', border: 'border-emerald-DEFAULT/30', bg: 'bg-emerald-dim', glow: 'shadow-emerald-glow' },
  rose:    { text: 'text-rose-DEFAULT',    border: 'border-rose-DEFAULT/30',    bg: 'bg-rose-dim',    glow: 'shadow-rose-glow' },
  violet:  { text: 'text-violet-DEFAULT',  border: 'border-violet-DEFAULT/30',  bg: 'bg-violet-dim',  glow: 'shadow-violet-glow' },
  amber:   { text: 'text-amber-DEFAULT',   border: 'border-amber-DEFAULT/30',   bg: 'bg-amber-dim',   glow: '' },
};

export default function StatCard({ label, value, sub, color = 'cyan', icon, index = 0 }: StatCardProps) {
  const c = COLOR[color];
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
      className={clsx('cyber-panel rounded-lg p-5 clip-corner border', c.border)}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-[10px] font-mono text-text-secondary uppercase tracking-widest">{label}</p>
        {icon && (
          <div className={clsx('w-7 h-7 rounded flex items-center justify-center', c.bg)}>
            <span className={c.text}>{icon}</span>
          </div>
        )}
      </div>
      <p className={clsx('text-2xl font-bold font-mono', c.text)}>{value}</p>
      {sub && <p className="text-[10px] text-text-secondary font-mono mt-1">{sub}</p>}
    </motion.div>
  );
}
