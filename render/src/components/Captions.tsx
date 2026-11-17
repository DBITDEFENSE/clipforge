import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {DISPLAY} from '../fonts';
import type {Brand, Caption, Layout} from '../types';

/** Word-by-word captions: 1-3 words at a time, active word highlighted, inside the safe caption band. */
export const Captions: React.FC<{captions: Caption[]; brand: Brand; layout: Layout}> = ({captions, brand, layout}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cap = captions.find((c) => frame >= c.start_frame && frame < c.end_frame);
  if (!cap) return null;
  const local = frame - cap.start_frame;
  const pop = spring({frame: local, fps, config: {damping: 13, stiffness: 260, mass: 0.5}});
  const chars = cap.words.reduce((n, w) => n + w.text.length + 1, 0);
  const size = chars > 16 ? 76 : 88;
  return (
    <div
      style={{
        position: 'absolute', left: 80, right: 80, top: layout.caption_top, height: layout.caption_bottom - layout.caption_top,
        display: 'flex', flexWrap: 'wrap', alignContent: 'center', justifyContent: 'center', gap: '6px 34px',
        transform: `scale(${interpolate(pop, [0, 1], [0.86, 1])})`,
      }}
    >
      {cap.words.map((w, i) => {
        const active = frame >= w.start_frame && frame < w.end_frame;
        const spoken = frame >= w.start_frame;
        return (
          <span
            key={i}
            style={{
              fontFamily: DISPLAY, fontWeight: 900, fontSize: size, lineHeight: 1.05, textTransform: 'uppercase', letterSpacing: '-0.01em',
              color: active ? brand.colors.accent : brand.colors.text,
              opacity: spoken ? 1 : 0.55,
              WebkitTextStroke: '10px #000', paintOrder: 'stroke fill',
              textShadow: '0 8px 24px rgba(0,0,0,.7)',
              transform: active ? 'scale(1.05)' : 'none', transformOrigin: '50% 60%', display: 'inline-block',
            }}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
};
