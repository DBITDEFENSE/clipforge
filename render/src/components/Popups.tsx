import React from 'react';
import {interpolate, spring, useVideoConfig} from 'remotion';
import {DISPLAY, MONO, palette} from '../fonts';
import type {Brand, Layout} from '../types';

/** Alert windows cascading in one after another ("ACCESS GRANTED", "$6.3B WITHDRAWN"...). Original UI, not any real OS. */
export const Popups: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = palette(brand.colors);
  const msgs: string[] = (props.lines ?? []).slice(0, 5);
  const title: string = props.title || 'ALERT';
  const zoneH = layout.content_bottom - layout.content_top;
  const step = 6;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      {msgs.map((m, i) => {
        const s = spring({frame: elapsed - i * step, fps, config: {damping: 11, stiffness: 260, mass: 0.6}});
        if (elapsed < i * step) return null;
        const last = i === msgs.length - 1;
        const x = 70 + ((i * 53) % 130) - (i % 2 ? 30 : 0);
        const y = layout.content_top + 30 + i * (zoneH - 360) / Math.max(msgs.length - 1, 1);
        const rot = ((i * 37) % 9) - 4;
        const danger = last || /denied|fail|breach|stolen|compromis|critical|drained|withdrawn|hack/i.test(m);
        const head = danger ? c.warning : c.accent;
        return (
          <div key={i} style={{
            position: 'absolute', left: x, top: y, width: 860, borderRadius: 22, overflow: 'hidden', background: `${c.surface}F7`,
            border: `3px solid ${head}`, boxShadow: `0 30px 70px rgba(0,0,0,.7), 0 0 50px ${head}44`,
            transform: `scale(${interpolate(s, [0, 1], [0.5, 1])}) rotate(${rot}deg)`, opacity: interpolate(s, [0, 0.3], [0, 1], {extrapolateRight: 'clamp'}),
          }}>
            <div style={{display: 'flex', alignItems: 'center', gap: 14, padding: '14px 22px', background: head}}>
              <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 28, color: c.bg, letterSpacing: '0.08em', flex: 1}}>{title.toUpperCase()}</span>
              <span style={{fontFamily: MONO, fontWeight: 700, fontSize: 30, color: c.bg}}>✕</span>
            </div>
            <div style={{display: 'flex', alignItems: 'center', gap: 24, padding: '28px 30px'}}>
              <div style={{width: 76, height: 76, flex: 'none', borderRadius: 38, background: `${head}22`, border: `4px solid ${head}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: DISPLAY, fontWeight: 900, fontSize: 52, color: head}}>!</div>
              <div style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: 54, lineHeight: 1.05, textTransform: 'uppercase', color: c.text}}>{m}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
