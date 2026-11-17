import React from 'react';
import {Easing, interpolate, spring, useVideoConfig} from 'remotion';
import {DISPLAY, MONO} from '../fonts';
import type {Brand, Layout} from '../types';

export const CVEScoreCard: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const score = typeof props.cvss === 'number' ? Math.max(0, Math.min(10, props.cvss)) : null;
  const sev = String(props.severity || (score === null ? '' : score >= 9 ? 'CRITICAL' : score >= 7 ? 'HIGH' : score >= 4 ? 'MEDIUM' : 'LOW')).toUpperCase();
  const hot = sev === 'CRITICAL' || sev === 'HIGH';
  const col = hot ? c.warning : c.accent;
  const s = spring({frame: elapsed, fps, config: {damping: 15, stiffness: 180}});
  const fill = interpolate(elapsed, [8, 34], [0, (score ?? 0) / 10], {easing: Easing.out(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const shown = (fill * 10).toFixed(1);
  const zoneH = layout.content_bottom - layout.content_top;
  return (
    <div style={{
      position: 'absolute', left: 80, right: 80, top: layout.content_top + zoneH * 0.1, padding: '46px 50px', borderRadius: 32,
      background: `${c.surface}F2`, border: `3px solid ${col}66`, boxShadow: `0 40px 90px rgba(0,0,0,.6), 0 0 80px ${col}22`,
      opacity: s, transform: `translateY(${interpolate(s, [0, 1], [50, 0])}px)`,
    }}>
      <div style={{fontFamily: MONO, fontWeight: 700, fontSize: 30, letterSpacing: '0.14em', color: c.muted}}>VULNERABILITY</div>
      <div style={{fontFamily: MONO, fontWeight: 700, fontSize: 70, color: c.text, marginTop: 10, letterSpacing: '-0.01em'}}>{props.cve_id}</div>
      {props.product ? <div style={{fontFamily: DISPLAY, fontWeight: 800, fontSize: 44, color: c.muted, marginTop: 6}}>{props.product}</div> : null}
      {score !== null && (
        <div style={{marginTop: 44}}>
          <div style={{display: 'flex', alignItems: 'baseline', justifyContent: 'space-between'}}>
            <span style={{fontFamily: MONO, fontSize: 30, letterSpacing: '0.12em', color: c.muted}}>CVSS</span>
            <span style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: 150, lineHeight: 1, color: col, textShadow: `0 0 50px ${col}66`, fontVariantNumeric: 'tabular-nums'}}>{shown}</span>
          </div>
          <div style={{height: 22, borderRadius: 11, background: 'rgba(255,255,255,.08)', marginTop: 18, overflow: 'hidden'}}>
            <div style={{height: '100%', width: `${fill * 100}%`, borderRadius: 11, background: `linear-gradient(90deg, ${c.accent}, ${col})`, boxShadow: `0 0 24px ${col}`}} />
          </div>
        </div>
      )}
      {sev && (
        <div style={{display: 'inline-block', marginTop: 34, fontFamily: MONO, fontWeight: 700, fontSize: 36, letterSpacing: '0.1em', color: hot ? c.bg : c.bg, background: col, padding: '10px 24px', borderRadius: 10, opacity: interpolate(elapsed, [30, 38], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
          {sev}
        </div>
      )}
    </div>
  );
};
