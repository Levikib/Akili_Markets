'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  LayoutDashboard, Terminal, BarChart2, FlaskConical,
  Settings, LogOut, Activity, Shield, Zap,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import { clsx } from 'clsx';

const NAV = [
  { href: '/dashboard',             icon: LayoutDashboard, label: 'Dashboard',  color: 'cyan' },
  { href: '/dashboard/terminal',    icon: Terminal,         label: 'Terminal',   color: 'violet' },
  { href: '/dashboard/strategies',  icon: Zap,              label: 'Strategies', color: 'amber' },
  { href: '/dashboard/paper',       icon: FlaskConical,     label: 'Paper',      color: 'emerald' },
  { href: '/dashboard/risk',        icon: Shield,           label: 'Risk',       color: 'rose' },
  { href: '/dashboard/performance', icon: BarChart2,        label: 'Analytics',  color: 'violet' },
  { href: '/dashboard/settings',    icon: Settings,         label: 'Settings',   color: 'cyan' },
];

const COLOR_MAP: Record<string, string> = {
  cyan:    'text-cyan-DEFAULT border-cyan-DEFAULT shadow-cyan-glow',
  violet:  'text-violet-DEFAULT border-violet-DEFAULT shadow-violet-glow',
  emerald: 'text-emerald-DEFAULT border-emerald-DEFAULT shadow-emerald-glow',
  amber:   'text-amber-DEFAULT border-amber-DEFAULT',
  rose:    'text-rose-DEFAULT border-rose-DEFAULT shadow-rose-glow',
};

export default function Sidebar() {
  const pathname = usePathname();
  const router   = useRouter();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <aside className="fixed left-0 top-0 h-screen w-16 lg:w-56 bg-surface border-r border-border flex flex-col z-50">
      {/* Logo */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-cyan-dim border border-cyan-DEFAULT flex items-center justify-center flex-shrink-0">
            <Activity className="w-4 h-4 text-cyan-DEFAULT" />
          </div>
          <div className="hidden lg:block">
            <p className="text-xs font-bold font-mono text-cyan-DEFAULT text-glow-cyan tracking-widest">AKILI</p>
            <p className="text-[10px] text-text-muted font-mono tracking-wider">MARKETS TRADER</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {NAV.map(({ href, icon: Icon, label, color }) => {
          const active = pathname === href || (href !== '/dashboard' && pathname.startsWith(href));
          return (
            <Link key={href} href={href}>
              <motion.div
                whileHover={{ x: 2 }}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded cursor-pointer transition-all duration-150 group',
                  active
                    ? `bg-cyan-dim border-l-2 ${COLOR_MAP[color]}`
                    : 'hover:bg-panel border-l-2 border-transparent text-text-secondary hover:text-text-primary'
                )}
              >
                <Icon className={clsx('w-4 h-4 flex-shrink-0', active && COLOR_MAP[color].split(' ')[0])} />
                <span className="hidden lg:block text-xs font-mono uppercase tracking-wider">{label}</span>
                {active && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="hidden lg:block ml-auto w-1 h-1 rounded-full bg-current"
                  />
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* User + logout */}
      <div className="p-2 border-t border-border space-y-1">
        <div className="px-3 py-2 hidden lg:block">
          <p className="text-xs font-mono text-text-primary truncate">{user?.full_name || '—'}</p>
          <p className={clsx(
            'text-[10px] font-mono uppercase tracking-wider',
            user?.role === 'admin' ? 'text-amber-DEFAULT' : 'text-text-secondary'
          )}>
            {user?.role || 'trader'}
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded text-text-secondary hover:text-rose-DEFAULT hover:bg-rose-dim transition-all duration-150"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          <span className="hidden lg:block text-xs font-mono uppercase tracking-wider">Logout</span>
        </button>
      </div>
    </aside>
  );
}
