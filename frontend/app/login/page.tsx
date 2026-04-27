'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/store/auth';

export default function LoginPage() {
  const router = useRouter();
  const { setTokens, setUser } = useAuthStore();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [form, setForm] = useState({ email: '', password: '', full_name: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = mode === 'login'
        ? await authApi.login({ email: form.email, password: form.password })
        : await authApi.register(form);

      setTokens(res.data.access_token, res.data.refresh_token);
      const me = await authApi.me();
      setUser(me.data);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-void bg-grid flex items-center justify-center p-4 relative overflow-hidden">
      {/* Ambient glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cyan/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet/5 rounded-full blur-3xl pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <motion.div
            initial={{ scale: 0.8 }}
            animate={{ scale: 1 }}
            transition={{ duration: 0.5, type: 'spring' }}
          >
            <h1 className="text-3xl font-bold text-cyan-DEFAULT text-glow-cyan font-mono tracking-widest">
              AKILI
            </h1>
            <p className="text-text-secondary text-xs tracking-[0.4em] mt-1 uppercase">
              Markets Trader
            </p>
            <div className="mt-3 h-px w-32 mx-auto bg-gradient-to-r from-transparent via-cyan-DEFAULT to-transparent" />
          </motion.div>
        </div>

        {/* Panel */}
        <div className="cyber-panel-cyan rounded-lg p-8 clip-corner">
          {/* Tab toggle */}
          <div className="flex gap-1 mb-6 bg-[#0a0a14] rounded p-1">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(''); }}
                style={mode === m ? { background: '#00d4ff', color: '#000008' } : {}}
                className={`flex-1 py-2 text-xs font-mono uppercase tracking-widest rounded transition-all duration-200 font-bold ${
                  mode === m ? '' : 'text-[#64748b] hover:text-[#e2e8f0]'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="block text-xs text-text-secondary font-mono mb-1 uppercase tracking-wider">
                  Full Name
                </label>
                <input
                  type="text"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="w-full bg-surface border border-border rounded px-4 py-3 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT focus:shadow-cyan-glow transition-all"
                  placeholder="John Doe"
                  required
                />
              </div>
            )}

            <div>
              <label className="block text-xs text-text-secondary font-mono mb-1 uppercase tracking-wider">
                Email
              </label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full bg-surface border border-border rounded px-4 py-3 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT focus:shadow-cyan-glow transition-all"
                placeholder="trader@akili.io"
                required
              />
            </div>

            <div>
              <label className="block text-xs text-text-secondary font-mono mb-1 uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full bg-surface border border-border rounded px-4 py-3 text-sm font-mono text-text-primary focus:outline-none focus:border-cyan-DEFAULT focus:shadow-cyan-glow transition-all"
                placeholder="••••••••"
                required
                minLength={8}
              />
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-rose-DEFAULT text-xs font-mono bg-rose-dim rounded px-3 py-2 border border-rose-DEFAULT border-opacity-30"
              >
                ⚠ {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{ background: '#00d4ff', color: '#000008' }}
              className="w-full py-3 font-bold font-mono text-sm uppercase tracking-widest rounded transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading ? 'AUTHENTICATING...' : mode === 'login' ? 'ENTER SYSTEM' : 'CREATE ACCOUNT'}
            </button>
          </form>
        </div>

        <p className="text-center text-text-muted text-xs font-mono mt-6 tracking-wider">
          SYSTEMATIC · DISCIPLINED · TRANSPARENT
        </p>
      </motion.div>
    </div>
  );
}
