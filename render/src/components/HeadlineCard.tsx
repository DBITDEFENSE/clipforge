import React from 'react';
import {interpolate, spring, useVideoConfig} from 'remotion';
import {DISPLAY, MONO} from '../fonts';
import type {Brand, Layout} from '../types';

export const HeadlineCard: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const words: string[] = String(props.headline ?? '').split(/\s+/).filter(Boolean);
  const kick = spring({frame: elapsed, fps, config: {damping: 15, stiffness: 200}});
  const rule = interpolate(elapsed, [4, 18], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const chars = words.join(' ').length;
  const size = Math.round(Math.max(84, Math.min(124, 150 - chars * 1.6)));
  return (
    <div style={{position: 'absolute', left: 90, right: 90, top: layout.content_top, height: layout.content_bottom - layout.content_top, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 34}}>
      {props.kicker ? (
        <div style={{alignSelf: 'flex-start', fontFamily: MONO, fontWeight: 700, fontSize: 34, letterSpacing: '0.06em', color: c.bg, background: c.warning, padding: '10px 22px', borderRadius: 10, transform: `translateX(${interpolate(kick, [0, 1], [-80, 0])}px)`, opacity: kick}}>
          {String(props.kicker).toUpperCase()}
        </div>
      ) : null}
      <div style={{height: 6, width: `${rule * 100}%`, background: c.accent, borderRadius: 3, boxShadow: `0 0 24px ${c.accent}`}} />
      <div style={{display: 'flex', flexWrap: 'wrap', gap: `0 ${size * 0.24}px`}}>
        {words.map((w, i) => {
          const s = spring({frame: elapsed - 6 - i * 2, fps, config: {damping: 14, stiffness: 190}});
          return (
            <span key={i} style={{fontFamily: DISPLAY, fontWeight: 800, fontSize: size, lineHeight: 1.04, color: c.text, letterSpacing: '-0.02em', opacity: s, transform: `translateY(${interpolate(s, [0, 1], [40, 0])}px)`, display: 'inline-block'}}>
              {w}
            </span>
          );
        })}
      </div>
    </div>
  );
};
