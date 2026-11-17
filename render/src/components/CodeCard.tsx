import React from 'react';
import {MONO} from '../fonts';
import type {Brand, Layout} from '../types';
import {Cursor, Window} from './Window';

const CHARS_PER_FRAME = 2.4;
const KEYWORDS = /\b(GET|POST|PUT|DELETE|HTTP|if|else|return|def|function|const|let|var|import|from|true|false|null|None|True|False|for|while|curl|sudo|select|from|where|and|or|not)\b/gi;

const colorize = (line: string, brand: Brand): React.ReactNode[] => {
  const c = brand.colors;
  if (/^\s*(#|\/\/|--)/.test(line)) return [<span key="c" style={{color: c.muted}}>{line}</span>];
  const parts: React.ReactNode[] = [];
  const re = /("[^"]*"?|'[^']*'?|\b\d[\d.]*\b|[A-Za-z_][\w-]*:|\b\w+\b|\s+|.)/g;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(line))) {
    const t = m[0];
    let color = c.text;
    if (/^["']/.test(t)) color = '#F5B83D';
    else if (/^\d/.test(t)) color = c.warning;
    else if (/:$/.test(t)) color = c.accent;
    else if (KEYWORDS.test(t)) color = c.accent;
    KEYWORDS.lastIndex = 0;
    parts.push(<span key={k++} style={{color}}>{t}</span>);
  }
  return parts;
};

export const CodeCard: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const lines: string[] = props.lines ?? [];
  const typed = Math.max(0, (elapsed - 6) * CHARS_PER_FRAME);
  const longest = Math.max(...lines.map((l) => l.length), 10);
  const fontSize = Math.max(28, Math.min(48, Math.floor(1750 / longest)));
  let budget = typed;
  let cursorLine = lines.length - 1;
  const shown = lines.map((l, i) => {
    const n = Math.min(l.length, Math.max(0, Math.floor(budget)));
    if (budget < l.length + 1 && cursorLine === lines.length - 1 && budget >= 0) cursorLine = i;
    budget -= l.length + 1;
    return l.slice(0, n);
  });
  const done = budget > 0;
  return (
    <Window brand={brand} layout={layout} title={props.language ?? 'code'} elapsed={elapsed}>
      <div style={{fontFamily: MONO, fontSize, lineHeight: 1.55, whiteSpace: 'pre'}}>
        {shown.map((l, i) => {
          const hl = props.highlight === i + 1 && done;
          return (
            <div key={i} style={{display: 'flex', background: hl ? `${brand.colors.warning}22` : 'transparent', borderLeft: `6px solid ${hl ? brand.colors.warning : 'transparent'}`, paddingLeft: 14, marginLeft: -20}}>
              <span style={{color: `${brand.colors.muted}88`, width: fontSize * 1.6, flexShrink: 0}}>{i + 1}</span>
              <span>{colorize(l, brand)}{i === cursorLine && <Cursor color={brand.colors.accent} frame={elapsed} />}</span>
            </div>
          );
        })}
      </div>
    </Window>
  );
};
