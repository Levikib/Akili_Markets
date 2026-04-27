'use client';
import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { authApi } from '@/lib/api';
import { Trash2, Plus, Eye, EyeOff, CheckCircle } from 'lucide-react';
import { clsx } from 'clsx';

export default function SettingsPage() {
  const [showSecret, setShowSecret] = useState(false);
  const [keyForm, setKeyForm] = useState({ api_key: '', api_secret: '', is_testnet: false, label: 'Main Account' });
  const [keyError, setKeyError] = useState('');
  const [keySuccess, setKeySuccess] = useState('');
  const [riskForm, setRiskForm] = useState({ max_risk_per_trade_pct: '', max_daily_loss_pct: '', paper_balance: '' });

  const { data: keys, refetch: refetchKeys } = useQuery({
    queryKey: ['keys'],
    queryFn: () => authApi.listKeys().then(r => r.data),
  });

  const addKeyMutation = useMutation({
    mutationFn: () => authApi.addKey(keyForm),
    onSuccess: () => {
      setKeySuccess('API key validated and saved successfully');
      setKeyError('');
      setKeyForm({ api_key: '', api_secret: '', is_testnet: false, label: 'Main Account' });
      refetchKeys();
      setTimeout(() => setKeySuccess(''), 4000);
    },
    onError: (e: any) => {
      setKeyError(e.response?.data?.detail || 'Failed to validate API key');
      setKeySuccess('');
    },
  });

  const deleteKeyMutation = useMutation({
    mutationFn: (id: string) => authApi.deleteKey(id),
    onSuccess: () => refetchKeys(),
  });

  const updateSettingsMutation = useMutation({
    mutationFn: () => authApi.updateSettings({
      ...(riskForm.max_risk_per_trade_pct && { max_risk_per_trade_pct: parseFloat(riskForm.max_risk_per_trade_pct) }),
      ...(riskForm.max_daily_loss_pct && { max_daily_loss_pct: parseFloat(riskForm.max_daily_loss_pct) }),
      ...(riskForm.paper_balance && { paper_balance: parseFloat(riskForm.paper_balance) }),
    }),
  });

  return (
    <div className="p-6 space-y-8 min-h-screen max-w-3xl">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="text-xl font-bold font-mono text-cyan-DEFAULT text-glow-cyan">SETTINGS</h1>
        <p className="text-xs text-text-secondary font-mono mt-0.5">API keys · Risk parameters · Account preferences</p>
      </motion.div>

      {/* Exchange API Keys */}
      <section className="cyber-panel rounded-lg p-6 clip-corner space-y-5">
        <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary border-b border-border pb-3">
          Binance API Keys
        </h2>

        {/* Existing keys */}
        {keys && keys.length > 0 && (
          <div className="space-y-2">
            {keys.map((k: any) => (
              <div key={k.id} className="flex items-center justify-between p-3 bg-surface rounded border border-border">
                <div>
                  <p className="text-xs font-mono text-text-primary">{k.label || 'Unnamed'}</p>
                  <p className="text-[10px] font-mono text-text-secondary">{k.api_key_preview} · {k.is_testnet ? 'TESTNET' : 'LIVE'}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    'text-[10px] font-mono px-2 py-0.5 rounded',
                    k.is_active ? 'text-emerald-DEFAULT bg-emerald-dim' : 'text-text-muted bg-surface'
                  )}>
                    {k.is_active ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                  <button
                    onClick={() => deleteKeyMutation.mutate(k.id)}
                    className="p-1.5 text-text-muted hover:text-rose-DEFAULT hover:bg-rose-dim rounded transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add new key form */}
        <div className="space-y-3">
          <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider">Add New Key</p>
          <input
            type="text"
            placeholder="Label (e.g. Main Account)"
            value={keyForm.label}
            onChange={e => setKeyForm({ ...keyForm, label: e.target.value })}
            className="w-full bg-surface border border-border rounded px-4 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT transition-all"
          />
          <input
            type="text"
            placeholder="API Key"
            value={keyForm.api_key}
            onChange={e => setKeyForm({ ...keyForm, api_key: e.target.value })}
            className="w-full bg-surface border border-border rounded px-4 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT transition-all"
          />
          <div className="relative">
            <input
              type={showSecret ? 'text' : 'password'}
              placeholder="Secret Key"
              value={keyForm.api_secret}
              onChange={e => setKeyForm({ ...keyForm, api_secret: e.target.value })}
              className="w-full bg-surface border border-border rounded px-4 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT transition-all pr-10"
            />
            <button
              type="button"
              onClick={() => setShowSecret(!showSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
            >
              {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={keyForm.is_testnet}
              onChange={e => setKeyForm({ ...keyForm, is_testnet: e.target.checked })}
              className="accent-cyan-DEFAULT"
            />
            <span className="text-xs font-mono text-text-secondary">Testnet (paper trading only)</span>
          </label>

          {keyError && (
            <p className="text-rose-DEFAULT text-xs font-mono bg-rose-dim rounded px-3 py-2 border border-rose-DEFAULT/30">⚠ {keyError}</p>
          )}
          {keySuccess && (
            <p className="text-emerald-DEFAULT text-xs font-mono bg-emerald-dim rounded px-3 py-2 border border-emerald-DEFAULT/30 flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5" /> {keySuccess}
            </p>
          )}

          <button
            onClick={() => addKeyMutation.mutate()}
            disabled={addKeyMutation.isPending || !keyForm.api_key || !keyForm.api_secret}
            className="flex items-center gap-2 px-4 py-2.5 bg-cyan-DEFAULT text-[#000008] font-bold font-mono text-xs uppercase tracking-widest rounded clip-corner-sm hover:shadow-cyan-glow transition-all disabled:opacity-50"
          >
            <Plus className="w-3.5 h-3.5" />
            {addKeyMutation.isPending ? 'VALIDATING...' : 'ADD & VALIDATE KEY'}
          </button>
        </div>
      </section>

      {/* Risk Settings */}
      <section className="cyber-panel rounded-lg p-6 clip-corner space-y-4">
        <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-text-primary border-b border-border pb-3">
          Risk Parameters
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
              Max Risk / Trade (%)
            </label>
            <input
              type="number"
              step="0.1"
              min="0.1"
              max="2"
              placeholder="1.5"
              value={riskForm.max_risk_per_trade_pct}
              onChange={e => setRiskForm({ ...riskForm, max_risk_per_trade_pct: e.target.value })}
              className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-amber-DEFAULT transition-all"
            />
            <p className="text-[9px] font-mono text-text-muted mt-1">Hard cap: 2%</p>
          </div>
          <div>
            <label className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
              Max Daily Loss (%)
            </label>
            <input
              type="number"
              step="0.5"
              min="1"
              max="10"
              placeholder="5.0"
              value={riskForm.max_daily_loss_pct}
              onChange={e => setRiskForm({ ...riskForm, max_daily_loss_pct: e.target.value })}
              className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-amber-DEFAULT transition-all"
            />
            <p className="text-[9px] font-mono text-text-muted mt-1">Hard cap: 10%</p>
          </div>
          <div>
            <label className="block text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
              Paper Balance (USDT)
            </label>
            <input
              type="number"
              step="100"
              min="100"
              placeholder="1000"
              value={riskForm.paper_balance}
              onChange={e => setRiskForm({ ...riskForm, paper_balance: e.target.value })}
              className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm font-mono text-text-primary focus:outline-none focus:border-amber-DEFAULT transition-all"
            />
          </div>
        </div>
        <button
          onClick={() => updateSettingsMutation.mutate()}
          disabled={updateSettingsMutation.isPending}
          className="px-4 py-2.5 bg-amber-DEFAULT text-[#000008] font-bold font-mono text-xs uppercase tracking-widest rounded clip-corner-sm transition-all disabled:opacity-50"
        >
          {updateSettingsMutation.isPending ? 'SAVING...' : 'SAVE SETTINGS'}
        </button>
        {updateSettingsMutation.isSuccess && (
          <p className="text-emerald-DEFAULT text-xs font-mono">Settings updated.</p>
        )}
      </section>
    </div>
  );
}
