import React from 'react';
import {interpolate, spring, useVideoConfig} from 'remotion';
import {MONO} from '../fonts';
import type {Brand, Layout} from '../types';

/** Shared card chrome for code + terminal. `elapsed` = frames since the card first appeared. */
export const Window: React.FC<{brand: Brand; layout: Layout; title: string; elapsed: number; children: React.ReactNode}> = ({
  brand, layout, title, elapsed, children,
}) => {
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const s = spring({frame: elapsed, fps, config: {damping: 16, stiffness: 180}});
  const zoneH = layout.content_bottom - layout.content_top;
  return (
    <div
      style={{
        position: 'absolute', left: 70, right: 70, top: layout.content_top + zoneH * 0.06, maxHeight: zoneH * 0.9,
        background: `${c.surface}F2`, border: `2px solid ${c.accent}33`, borderRadius: 30, overflow: 'hidden',
        boxShadow: `0 40px 90px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.04), 0 0 60px ${c.accent}14`,
        opacity: s, transform: `translateY(${interpolate(s, [0, 1], [60, 0])}px) scale(${interpolate(s, [0, 1], [0.94, 1])})`,
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 14, padding: '24px 30px', borderBottom: '2px solid rgba(255,255,255,.06)'}}>
        {[c.warning, '#F5B83D', c.accent].map((col) => (
          <div key={col} style={{width: 20, height: 20, borderRadius: 10, background: col, opacity: 0.85}} />
        ))}
        <div style={{marginLeft: 16, fontFamily: MONO, fontSize: 28, color: c.muted, letterSpacing: '0.04em'}}>{title}</div>
      </div>
      <div style={{padding: '30px 36px 40px'}}>{children}</div>
    </div>
  );
};

export const Cursor: React.FC<{color: string; frame: number}> = ({color, frame}) => (
  <span style={{display: 'inline-block', width: '0.55em', height: '1.05em', background: color, verticalAlign: 'text-bottom', marginLeft: 2, opacity: Math.floor(frame / 8) % 2 ? 0.15 : 1}} />
);
