import React from 'react';
import {MONO} from '../fonts';
import type {Brand, Layout} from '../types';
import {Cursor, Window} from './Window';

const CMD_CPF = 1.8; // command typing speed, chars/frame
const OUT_GAP = 3; // frames between output lines
const ALERT = /(critical|alert|denied|failed|exploit|malicious|vulnerable|compromised|error|cve-\d)/i;

export const TerminalCard: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const c = brand.colors;
  const lines: string[] = props.lines ?? [];
  // schedule: each line gets a start frame; commands take time to type, outputs pop in
  let t = 6;
  const sched = lines.map((l) => {
    const isCmd = l.startsWith('$ ');
    const start = t;
    const body = isCmd ? l.slice(2) : l;
    t += isCmd ? Math.ceil(body.length / CMD_CPF) + 8 : OUT_GAP;
    return {isCmd, body, start};
  });
  const longest = Math.max(...lines.map((l) => l.length), 10);
  const fontSize = Math.max(28, Math.min(44, Math.floor(1700 / longest)));
  const active = sched.filter((s) => elapsed >= s.start);
  return (
    <Window brand={brand} layout={layout} title="terminal — soc" elapsed={elapsed}>
      <div style={{fontFamily: MONO, fontSize, lineHeight: 1.6, whiteSpace: 'pre-wrap', overflowWrap: 'break-word'}}>
        {active.map((s, i) => {
          const last = i === active.length - 1;
          if (s.isCmd) {
            const n = Math.min(s.body.length, Math.floor((elapsed - s.start) * CMD_CPF));
            return (
              <div key={i}>
                <span style={{color: c.accent, fontWeight: 700}}>$ </span>
                <span style={{color: c.text}}>{s.body.slice(0, n)}</span>
                {last && <Cursor color={c.accent} frame={elapsed} />}
              </div>
            );
          }
          return (
            <div key={i} style={{color: ALERT.test(s.body) ? c.warning : c.muted}}>
              {s.body}
              {last && <Cursor color={c.accent} frame={elapsed} />}
            </div>
          );
        })}
      </div>
    </Window>
  );
};
