import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {palette} from '../fonts';
import type {Brand} from '../types';

/** Two drifting color fields (cyan + pink) over a deep base, a faint moving grid, film grain, vignette. */
export const Background: React.FC<{brand: Brand}> = ({brand}) => {
  const frame = useCurrentFrame();
  const c = palette(brand.colors);
  const shift = (frame * 0.6) % 90;
  const ax = 22 + 10 * Math.sin(frame / 70), ay = 26 + 6 * Math.cos(frame / 90);
  const bx = 78 + 10 * Math.cos(frame / 80), by = 64 + 8 * Math.sin(frame / 60);
  return (
    <AbsoluteFill style={{background: `linear-gradient(180deg, ${c.bg} 0%, #0B0D16 55%, ${c.bg} 100%)`}}>
      <AbsoluteFill style={{background: `radial-gradient(ellipse 55% 30% at ${ax}% ${ay}%, ${c.accent}26, transparent 70%)`}} />
      <AbsoluteFill style={{background: `radial-gradient(ellipse 55% 32% at ${bx}% ${by}%, ${c.accent2}22, transparent 70%)`}} />
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${c.accent}0F 2px, transparent 2px), linear-gradient(90deg, ${c.accent}0F 2px, transparent 2px)`,
          backgroundSize: '90px 90px',
          backgroundPosition: `0 ${shift}px`,
          maskImage: 'radial-gradient(ellipse 70% 55% at 50% 40%, black 30%, transparent 100%)',
        }}
      />
      <AbsoluteFill style={{opacity: 0.07, mixBlendMode: 'overlay', backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' seed='${frame % 8}'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`}} />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 85% 70% at 50% 45%, transparent 55%, rgba(0,0,0,.7) 100%)'}} />
    </AbsoluteFill>
  );
};
