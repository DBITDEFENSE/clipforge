import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Brand} from '../types';

export const Background: React.FC<{brand: Brand}> = ({brand}) => {
  const frame = useCurrentFrame();
  const c = brand.colors;
  const shift = (frame * 0.6) % 90;
  return (
    <AbsoluteFill style={{background: c.bg}}>
      {/* slow-moving grid, barely there */}
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${c.accent}0D 2px, transparent 2px), linear-gradient(90deg, ${c.accent}0D 2px, transparent 2px)`,
          backgroundSize: '90px 90px',
          backgroundPosition: `0 ${shift}px`,
          maskImage: 'radial-gradient(ellipse 70% 55% at 50% 40%, black 30%, transparent 100%)',
        }}
      />
      {/* accent glow behind the content zone */}
      <AbsoluteFill style={{background: `radial-gradient(ellipse 60% 30% at 50% 36%, ${c.accent}1F, transparent 70%)`}} />
      {/* vignette */}
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 85% 70% at 50% 45%, transparent 55%, rgba(0,0,0,.65) 100%)'}} />
    </AbsoluteFill>
  );
};
