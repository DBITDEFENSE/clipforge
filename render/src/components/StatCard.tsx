import React from 'react';
import {Easing, interpolate, spring, useVideoConfig} from 'remotion';
import {DISPLAY} from '../fonts';
import type {Brand, Layout} from '../types';

/** Splits "$4.2M" -> {prefix:"$", num:4.2, decimals:1, suffix:"M", commas:false} so it can count up. */
const parse = (v: string) => {
  const m = String(v).match(/^([^\d]*)([\d,]*\.?\d+)(.*)$/);
  if (!m) return null;
  const raw = m[2];
  return {prefix: m[1], num: parseFloat(raw.replace(/,/g, '')), decimals: (raw.split('.')[1] ?? '').length, suffix: m[3], commas: raw.includes(',')};
};

export const StatCard: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const p = parse(props.value ?? '');
  const t = interpolate(elapsed, [2, 26], [0, 1], {easing: Easing.out(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  let text = String(props.value ?? '');
  if (p) {
    const n = p.num * t;
    const fixed = n.toFixed(p.decimals);
    const body = p.commas ? Number(fixed).toLocaleString('en-US', {minimumFractionDigits: p.decimals, maximumFractionDigits: p.decimals}) : fixed;
    text = `${p.prefix}${body}${p.suffix}`;
  }
  const s = spring({frame: elapsed, fps, config: {damping: 12, stiffness: 160}});
  const size = Math.max(200, Math.min(330, 1500 / Math.max(String(props.value).length, 3)));
  return (
    <div style={{position: 'absolute', left: 60, right: 60, top: layout.content_top, height: layout.content_bottom - layout.content_top, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'}}>
      <div style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: size, lineHeight: 1, color: c.accent, letterSpacing: '-0.04em', textShadow: `0 0 60px ${c.accent}55`, transform: `scale(${interpolate(s, [0, 1], [0.7, 1])})`, fontVariantNumeric: 'tabular-nums'}}>
        {text}
      </div>
      <div style={{marginTop: 28, fontFamily: DISPLAY, fontWeight: 800, fontSize: 64, textTransform: 'uppercase', letterSpacing: '0.02em', color: c.text, textAlign: 'center', opacity: interpolate(elapsed, [10, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
        {props.label}
      </div>
    </div>
  );
};
