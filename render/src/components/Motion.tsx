import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Motion as MotionType} from '../types';

/** Camera-style motion for a whole shot + a quick flash on the cut so every change reads as a cut. */
export const Motion: React.FC<{motion: MotionType; duration: number; children: React.ReactNode}> = ({motion, duration, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  let transform = 'none';
  if (motion === 'pop') {
    const s = spring({frame, fps, config: {damping: 14, stiffness: 220, mass: 0.6}});
    transform = `scale(${interpolate(s, [0, 1], [1.12, 1])})`;
  } else if (motion === 'punch_in') {
    const s = interpolate(frame, [0, Math.max(duration, 2)], [1.0, 1.08], {easing: Easing.out(Easing.cubic), extrapolateRight: 'clamp'});
    transform = `scale(${s})`;
  } else if (motion === 'drift') {
    const y = interpolate(frame, [0, Math.max(duration, 2)], [24, -24], {extrapolateRight: 'clamp'});
    transform = `translateY(${y}px) scale(1.03)`;
  }
  const flash = interpolate(frame, [0, 3], [0.18, 0], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{transform, transformOrigin: '50% 38%'}}>{children}</AbsoluteFill>
      <AbsoluteFill style={{background: '#fff', opacity: flash, pointerEvents: 'none'}} />
    </AbsoluteFill>
  );
};
