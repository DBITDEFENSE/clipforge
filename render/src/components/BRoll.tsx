import React from 'react';
import {AbsoluteFill, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {MONO} from '../fonts';
import type {Brand, Layout} from '../types';
import {KineticText} from './KineticText';

/** Source footage: the clip comes pre-composed by footage.cut() for this layout: 1080 x canvas_h (the gameplay panel
 *  stays visible below it), source frame at fg_y..fg_y+fg_h inside the content zone. Light grade, credit chip on the
 *  frame, and `offset` (seconds) so later cuts of the same clip beat continue where the previous cut left off. */
const SourceClip: React.FC<{props: Record<string, any>; duration: number; brand: Brand; layout: Layout}> = ({props, duration, brand, layout}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const c = brand.colors;
  const canvas = props.canvas_h || layout.gameplay_top || height;
  const fgY = props.fg_y ?? layout.content_top;
  const scale = interpolate(frame, [0, Math.max(duration, 1)], [1.0, 1.03]);
  const chip = interpolate(frame, [0, 6], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: canvas, overflow: 'hidden'}}>
        <div style={{width: '100%', height: '100%', transform: `scale(${scale})`}}>
          <OffthreadVideo src={staticFile(props.src)} muted startFrom={Math.round((props.offset || 0) * fps)}
            style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </div>
        <AbsoluteFill style={{background: `linear-gradient(180deg, ${c.bg}66 0%, transparent 16%, transparent 64%, ${c.bg}CC 82%, ${c.bg}EE 100%)`}} />
      </div>
      {props.credit ? (
        <div style={{position: 'absolute', left: 40, top: fgY + 18, opacity: chip, display: 'flex', alignItems: 'center', gap: 12,
          background: `${c.bg}CC`, border: `1px solid ${c.accent}66`, borderRadius: 10, padding: '8px 16px',
          fontFamily: MONO, fontSize: 26, color: c.text, letterSpacing: '0.02em'}}>
          <span style={{width: 12, height: 12, borderRadius: 6, background: c.warning, boxShadow: `0 0 10px ${c.warning}`}} />
          {props.restyled ? 'RESTYLED CLIP' : 'CLIP'} · via {props.credit}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Full-bleed stock / AI footage, slow push, brand-tinted dark overlay so captions stay readable. */
export const BRoll: React.FC<{props: Record<string, any>; duration: number; brand: Brand; layout: Layout}> = ({props, duration, brand, layout}) => {
  const frame = useCurrentFrame();
  if (props.source) return <SourceClip props={props} duration={duration} brand={brand} layout={layout} />;
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
