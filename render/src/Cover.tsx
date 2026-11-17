import React from 'react';
import {AbsoluteFill} from 'remotion';
import {Background} from './components/Background';
import {DISPLAY, MONO, parseAccent} from './fonts';
import type {CoverProps} from './types';

export const Cover: React.FC<CoverProps> = ({title, kicker, brand}) => {
  const c = brand.colors;
  const tokens = parseAccent(title);
  if (!tokens.some((t) => t.accent) && tokens.length) tokens[tokens.length - 1].accent = true;
  const chars = tokens.reduce((n, t) => n + t.text.length + 1, 0);
  const size = Math.round(Math.max(120, Math.min(200, 250 - chars * 4)));
  return (
    <AbsoluteFill>
      <Background brand={brand} />
      <AbsoluteFill style={{padding: '0 90px', justifyContent: 'center', alignItems: 'flex-start', gap: 40, paddingBottom: 220}}>
        {kicker ? (
          <div style={{fontFamily: MONO, fontWeight: 700, fontSize: 40, letterSpacing: '0.08em', color: c.bg, background: c.warning, padding: '12px 26px', borderRadius: 12}}>
            {kicker.toUpperCase()}
          </div>
        ) : null}
        <div style={{display: 'flex', flexWrap: 'wrap', gap: `0 ${size * 0.24}px`}}>
          {tokens.map((t, i) => (
            <span key={i} style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: size, lineHeight: 0.96, textTransform: 'uppercase', letterSpacing: '-0.03em', color: t.accent ? c.accent : c.text, textShadow: t.accent ? `0 0 50px ${c.accent}66` : '0 8px 30px rgba(0,0,0,.6)'}}>
              {t.text}
            </span>
          ))}
        </div>
        <div style={{height: 8, width: 220, background: c.accent, borderRadius: 4, boxShadow: `0 0 30px ${c.accent}`}} />
        {brand.handle ? <div style={{fontFamily: MONO, fontSize: 34, color: c.muted, letterSpacing: '0.12em'}}>{brand.handle}</div> : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
