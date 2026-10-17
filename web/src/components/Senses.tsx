import { useEffect, useState } from 'react';
import { useArgus } from '../lib/store';
import type { Source } from '../lib/types';
import { EyeGlyph } from './Ornament';

export default function Senses() {
  const sensors = useArgus(s => s.sensors);
  const activity = useArgus(s => s.senseAt);
  const source = useArgus(s => s.source);
  const conn = useArgus(s => s.conn);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [activity]);
  const names = source === 'replay' ? Object.keys(activity) : sensors === null ? [] : [...sensors, 'files'];
  return <section className="senses" aria-label={source === 'replay' ? 'Simulated senses' : 'Connected senses'}>
    <span className="label">SENSES</span>
    {names.length === 0 && <span className="senses-wait">awaiting core</span>}
    {[...new Set(names)].map(name => {
      const mapped = (name === 'browser_tab' ? 'browser' : name) as Source;
      const lit = (conn === 'live' || conn === 'replay') && now - (activity[mapped] ?? 0) < 2000;
      return <span key={name} className={`sense ${lit ? 'lit' : ''}`} title={`${mapped}: ${lit ? 'active' : 'idle'}`}>
        <EyeGlyph size={17} lit={lit} /> {mapped.toUpperCase()}
      </span>;
    })}
  </section>;
}
