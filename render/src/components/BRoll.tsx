import React from 'react';
import {AbsoluteFill, interpolate, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import type {Brand, Layout} from '../types';
import {KineticText} from './KineticText';

/** Full-bleed stock footage, slow push, brand-tinted dark overlay so captions stay readable. */
export const BRoll: React.FC<{props: Record<string, any>; duration: number; brand: Brand; layout: Layout}> = ({props, duration, brand, layout}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, Math.max(duration, 1)], [1.06, 1.14]);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{transform: `scale(${scale})`}}>
        <OffthreadVideo src={staticFile(props.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'saturate(0.7) contrast(1.1)'}} />
      </AbsoluteFill>
      <AbsoluteFill style={{background: `linear-gradient(180deg, ${brand.colors.bg}99 0%, ${brand.colors.bg}55 35%, ${brand.colors.bg}AA 62%, ${brand.colors.bg}EE 100%)`}} />
      <AbsoluteFill style={{background: `${brand.colors.accent}10`, mixBlendMode: 'overlay'}} />
      {props.text ? <KineticText text={props.text} brand={brand} layout={layout} /> : null}
    </AbsoluteFill>
  );
};
