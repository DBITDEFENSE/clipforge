import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {DISPLAY, MONO} from '../fonts';
import type {Brand, Layout} from '../types';

export const LowerThird: React.FC<{title: string; sub?: string; brand: Brand; layout: Layout}> = ({title, sub, brand, layout}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const s = spring({frame: frame - 4, fps, config: {damping: 16, stiffness: 200}});
  return (
    <div style={{position: 'absolute', left: 90, top: layout.content_bottom - 150, display: 'flex', gap: 18, alignItems: 'stretch', opacity: s, transform: `translateX(${interpolate(s, [0, 1], [-60, 0])}px)`}}>
      <div style={{width: 8, borderRadius: 4, background: c.accent, boxShadow: `0 0 20px ${c.accent}`}} />
      <div style={{background: `${c.bg}D9`, padding: '12px 22px', borderRadius: 12, border: '1px solid rgba(255,255,255,.08)'}}>
        <div style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: 46, color: c.text, textTransform: 'uppercase', letterSpacing: '-0.01em', lineHeight: 1.05}}>{title}</div>
        {sub ? <div style={{fontFamily: MONO, fontSize: 26, color: c.muted, marginTop: 4}}>{sub}</div> : null}
      </div>
    </div>
  );
};
