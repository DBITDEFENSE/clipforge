import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {DISPLAY, palette, parseAccent} from '../fonts';
import type {Brand, Layout} from '../types';

export const KineticText: React.FC<{text: string; brand: Brand; layout: Layout}> = ({text, brand, layout}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const tokens = parseAccent(text);
  const chars = tokens.reduce((n, t) => n + t.text.length + 1, 0);
  const size = Math.round(Math.max(96, Math.min(168, 190 - chars * 3.2)));
  return (
    <div
      style={{
        position: 'absolute', left: 90, right: 90, top: layout.content_top, height: layout.content_bottom - layout.content_top,
        display: 'flex', flexWrap: 'wrap', alignContent: 'center', justifyContent: 'center', gap: `${size * 0.08}px ${size * 0.26}px`,
      }}
    >
      {tokens.map((t, i) => {
        const s = spring({frame: frame - i * 3, fps, config: {damping: 13, stiffness: 200, mass: 0.7}});
        const y = interpolate(s, [0, 1], [size * 0.5, 0]);
        return (
          <span
            key={i}
            style={{
              fontFamily: DISPLAY, fontWeight: 900, fontSize: size, lineHeight: 0.98, textTransform: 'uppercase', letterSpacing: '-0.02em',
              color: brand.colors.text,
              textShadow: t.accent ? 'none' : '0 6px 30px rgba(0,0,0,.6)',
              ...(t.accent ? {background: palette(brand.colors).accent2, padding: `0 ${size * 0.12}px`, borderRadius: size * 0.1, boxShadow: `0 0 50px ${palette(brand.colors).accent2}77`} : {}),
              opacity: s, transform: `translateY(${y}px) scale(${interpolate(s, [0, 1], [0.82, 1])}) rotate(${t.accent ? (i % 2 ? 2 : -2) : 0}deg)`, display: 'inline-block',
            }}
          >
            {t.text}
          </span>
        );
      })}
    </div>
  );
};
