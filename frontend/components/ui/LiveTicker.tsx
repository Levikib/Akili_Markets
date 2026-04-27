'use client';
import { useEffect, useState } from 'react';
// framer-motion imported for future animations
import { clsx } from 'clsx';

interface TickerItem {
  symbol: string;
  price: number;
  change: number;
}

const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT'];

export default function LiveTicker() {
  const [tickers, setTickers] = useState<Record<string, TickerItem>>({});

  useEffect(() => {
    const streams = SYMBOLS.map(s => `${s.toLowerCase()}@miniTicker`).join('/');
    const ws = new WebSocket(`wss://fstream.binance.com/stream?streams=${streams}`);

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      const d = msg.data;
      if (!d) return;
      const symbol = d.s;
      const price  = parseFloat(d.c);
      const open   = parseFloat(d.o);
      const change = ((price - open) / open) * 100;
      setTickers(prev => ({ ...prev, [symbol]: { symbol, price, change } }));
    };

    return () => ws.close();
  }, []);

  return (
    <div className="flex gap-4 overflow-x-auto pb-1 scrollbar-hide">
      {SYMBOLS.map((sym) => {
        const t = tickers[sym];
        const up = t ? t.change >= 0 : null;
        return (
          <div key={sym} className="flex-shrink-0 cyber-panel rounded px-4 py-3 min-w-[140px]">
            <p className="text-[10px] font-mono text-text-secondary mb-1">{sym.replace('USDT', '/USDT')}</p>
            <p className="text-sm font-bold font-mono text-text-primary">
              {t ? `$${t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
            </p>
            <p className={clsx(
              'text-[10px] font-mono mt-0.5',
              up === null ? 'text-text-muted' : up ? 'text-emerald-DEFAULT' : 'text-rose-DEFAULT'
            )}>
              {t ? `${up ? '+' : ''}${t.change.toFixed(2)}%` : '—'}
            </p>
          </div>
        );
      })}
    </div>
  );
}
