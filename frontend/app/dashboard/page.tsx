'use client';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  TrendingUp, TrendingDown, Activity,
  Zap, Shield, AlertTriangle, CheckCircle,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { tradingApi, healthApi } from '@/lib/api';
import StatCard from '@/components/ui/StatCard';
import LiveTicker from '@/components/ui/LiveTicker';
import { clsx } from 'clsx';

export default function DashboardPage() {
  const { user } = useAuthStore();

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => healthApi.check().then(r => r.data),
    refetchInterval: 10000,
  });

  const { data: perf } = useQuery({
    queryKey: ['performance'],
    queryFn: () => tradingApi.performance().then(r => r.data),
    refetchInterval: 30000,
  });

  const { data: openTrades } = useQuery({
    queryKey: ['openTrades'],
    queryFn: () => tradingApi.openTrades().then(r => r.data),
    refetchInterval: 5000,
  });

  const { data: trades } = useQuery({
    queryKey: ['trades'],
    queryFn: () => tradingApi.trades({ limit: 10 }).then(r => r.data),
    refetchInterval: 15000,
  });

  const totalPnl    = perf?.total_pnl ?? 0;
  const winRate     = perf?.win_rate ?? 0;
  const totalTrades = perf?.total_trades ?? 0;
  const openCount   = openTrades?.length ?? 0;

  return (
    <div className="p-6 space-y-6 min-h-screen">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-xl font-bold font-mono text-text-primary">
            Welcome back, <span className="text-cyan-DEFAULT text-glow-cyan">{user?.full_name?.split(' ')[0] || 'Trader'}</span>
          </h1>
          <p className="text-xs text-text-secondary font-mono mt-0.5">
            {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </p>
        </div>

        {/* System status */}
        <div className="flex items-center gap-2">
          <div className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded border text-xs font-mono',
            health?.binance_connected
              ? 'border-emerald-DEFAULT/30 text-emerald-DEFAULT bg-emerald-dim'
              : 'border-rose-DEFAULT/30 text-rose-DEFAULT bg-rose-dim'
          )}>
            <span className={clsx(
              'w-1.5 h-1.5 rounded-full',
              health?.binance_connected ? 'bg-emerald-DEFAULT animate-pulse' : 'bg-rose-DEFAULT'
            )} />
            {health?.binance_connected ? 'BINANCE LIVE' : 'DISCONNECTED'}
          </div>
          <div className="px-3 py-1.5 rounded border border-amber-DEFAULT/30 text-amber-DEFAULT bg-amber-dim text-xs font-mono">
            PAPER MODE
          </div>
        </div>
      </motion.div>

      {/* Live market ticker */}
      <div>
        <p className="text-[10px] font-mono text-text-muted uppercase tracking-widest mb-2">Live Markets</p>
        <LiveTicker />
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total P&L"
          value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`}
          sub="All time paper"
          color={totalPnl >= 0 ? 'emerald' : 'rose'}
          icon={totalPnl >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          index={0}
        />
        <StatCard
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          sub={`${totalTrades} total trades`}
          color="cyan"
          icon={<Activity className="w-3.5 h-3.5" />}
          index={1}
        />
        <StatCard
          label="Open Trades"
          value={openCount}
          sub="Active positions"
          color="violet"
          icon={<Zap className="w-3.5 h-3.5" />}
          index={2}
        />
        <StatCard
          label="Daily Risk Used"
          value={`${perf?.daily_risk_used?.toFixed(1) ?? '0.0'}%`}
          sub="5% cap"
          color={(perf?.daily_risk_used ?? 0) > 3 ? 'rose' : 'amber'}
          icon={<Shield className="w-3.5 h-3.5" />}
          index={3}
        />
      </div>

      {/* Recent trades + open positions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Open positions */}
        <div className="cyber-panel rounded-lg p-5 clip-corner">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary">Open Positions</h2>
            <span className="text-[10px] font-mono text-violet-DEFAULT bg-violet-dim px-2 py-0.5 rounded">
              {openCount} active
            </span>
          </div>
          {openCount === 0 ? (
            <div className="text-center py-8">
              <p className="text-text-muted text-xs font-mono">No open positions</p>
              <p className="text-text-muted text-[10px] font-mono mt-1">Scanner running every 60s</p>
            </div>
          ) : (
            <div className="space-y-2">
              {openTrades?.slice(0, 5).map((t: any) => (
                <div key={t.id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div>
                    <p className="text-xs font-mono text-text-primary">{t.instrument}</p>
                    <p className={clsx(
                      'text-[10px] font-mono',
                      t.direction === 'long' ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
                    )}>
                      {t.direction?.toUpperCase()} · ${t.entry_price?.toFixed(2)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={clsx(
                      'text-xs font-mono font-bold',
                      (t.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
                    )}>
                      {(t.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${(t.unrealized_pnl ?? 0).toFixed(2)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent trades */}
        <div className="cyber-panel rounded-lg p-5 clip-corner">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary">Recent Trades</h2>
          </div>
          {!trades || trades.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-text-muted text-xs font-mono">No trades yet</p>
              <p className="text-text-muted text-[10px] font-mono mt-1">Strategies are scanning the market</p>
            </div>
          ) : (
            <div className="space-y-2">
              {trades?.slice(0, 8).map((t: any) => (
                <div key={t.id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div className="flex items-center gap-2">
                    {t.pnl >= 0
                      ? <CheckCircle className="w-3 h-3 text-emerald-DEFAULT flex-shrink-0" />
                      : <AlertTriangle className="w-3 h-3 text-rose-DEFAULT flex-shrink-0" />
                    }
                    <div>
                      <p className="text-xs font-mono text-text-primary">{t.instrument}</p>
                      <p className="text-[10px] font-mono text-text-secondary">{t.strategy}</p>
                    </div>
                  </div>
                  <p className={clsx(
                    'text-xs font-mono font-bold',
                    t.pnl >= 0 ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
                  )}>
                    {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Strategy scanner status */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="cyber-panel rounded-lg p-4 border border-cyan-DEFAULT/10"
      >
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-cyan-DEFAULT animate-pulse" />
          <p className="text-xs font-mono text-text-secondary">
            Strategy scanner active · Scanning <span className="text-cyan-DEFAULT">BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT</span> every 60s ·{' '}
            <span className="text-amber-DEFAULT">PAPER MODE</span> — live trading requires qualification
          </p>
        </div>
      </motion.div>
    </div>
  );
}
