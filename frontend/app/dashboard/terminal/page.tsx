'use client';
import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery, useMutation } from '@tanstack/react-query';
import { tradingApi } from '@/lib/api';
import { clsx } from 'clsx';
import { X } from 'lucide-react';

export default function TerminalPage() {
  const [_selectedTrade, setSelectedTrade] = useState<any>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const { data: openTrades, refetch: refetchOpen } = useQuery({
    queryKey: ['openTrades'],
    queryFn: () => tradingApi.openTrades().then(r => r.data),
    refetchInterval: 5000,
  });

  const { data: trades } = useQuery({
    queryKey: ['trades', 'all'],
    queryFn: () => tradingApi.trades({ limit: 50 }).then(r => r.data),
    refetchInterval: 10000,
  });

  const closeMutation = useMutation({
    mutationFn: (id: string) => tradingApi.closeTrade(id),
    onSuccess: () => { refetchOpen(); setSelectedTrade(null); },
  });

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="text-xl font-bold font-mono text-violet-DEFAULT text-glow-violet">TRADING TERMINAL</h1>
        <p className="text-xs text-text-secondary font-mono mt-0.5">Live positions · Trade history · Manual controls</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Open positions */}
        <div className="lg:col-span-2 cyber-panel rounded-lg p-5 clip-corner">
          <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-violet-DEFAULT mb-4">
            Open Positions <span className="text-text-muted ml-2">({openTrades?.length ?? 0})</span>
          </h2>

          {!openTrades || openTrades.length === 0 ? (
            <div className="text-center py-12 border border-dashed border-border rounded">
              <p className="text-text-muted text-xs font-mono">No open positions</p>
              <p className="text-text-muted text-[10px] font-mono mt-1">Strategy scanner running every 60s</p>
            </div>
          ) : (
            <div className="space-y-2">
              {/* Header row */}
              <div className="grid grid-cols-6 gap-2 px-3 py-1">
                {['Instrument', 'Direction', 'Entry', 'SL', 'TP', 'Action'].map(h => (
                  <p key={h} className="text-[10px] font-mono text-text-muted uppercase">{h}</p>
                ))}
              </div>
              {openTrades.map((t: any) => (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="grid grid-cols-6 gap-2 items-center px-3 py-3 bg-surface rounded border border-border hover:border-violet-DEFAULT/30 transition-all"
                >
                  <p className="text-xs font-mono text-text-primary font-bold">{t.instrument}</p>
                  <p className={clsx(
                    'text-xs font-mono font-bold',
                    t.direction === 'long' ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
                  )}>
                    {t.direction?.toUpperCase()}
                  </p>
                  <p className="text-xs font-mono text-text-primary">${t.entry_price?.toFixed(2)}</p>
                  <p className="text-xs font-mono text-rose-DEFAULT">${t.stop_loss?.toFixed(2)}</p>
                  <p className="text-xs font-mono text-emerald-DEFAULT">${t.take_profit?.toFixed(2)}</p>
                  <button
                    onClick={() => closeMutation.mutate(t.id)}
                    disabled={closeMutation.isPending}
                    className="flex items-center gap-1 px-2 py-1 bg-rose-dim border border-rose-DEFAULT/30 rounded text-rose-DEFAULT text-[10px] font-mono hover:bg-rose-DEFAULT hover:text-[#000008] transition-all"
                  >
                    <X className="w-3 h-3" /> CLOSE
                  </button>
                </motion.div>
              ))}
            </div>
          )}
        </div>

        {/* Trade log */}
        <div className="cyber-panel rounded-lg p-5 clip-corner overflow-hidden">
          <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary mb-4">Trade Log</h2>
          <div ref={logRef} className="space-y-1 max-h-96 overflow-y-auto">
            {!trades || trades.length === 0 ? (
              <p className="text-text-muted text-xs font-mono text-center py-8">No trades logged yet</p>
            ) : (
              trades.map((t: any) => (
                <div key={t.id} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
                  <div>
                    <p className="text-[10px] font-mono text-text-primary">{t.instrument} · {t.strategy}</p>
                    <p className="text-[9px] font-mono text-text-muted">{new Date(t.created_at).toLocaleTimeString()}</p>
                  </div>
                  <p className={clsx(
                    'text-[10px] font-mono font-bold',
                    (t.pnl ?? 0) >= 0 ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
                  )}>
                    {(t.pnl ?? 0) >= 0 ? '+' : ''}${(t.pnl ?? 0).toFixed(2)}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
