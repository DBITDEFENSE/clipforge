import React from 'react';
import {interpolate, spring, useVideoConfig} from 'remotion';
import {EMOJI, MEME, palette, parseAccent} from '../fonts';
import type {Brand, Layout} from '../types';

/** Meme-format beat: optional top line ("NOBODY:", "POV:"), giant emoji with a comic burst, punchline at the bottom. */
export const Reaction: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = palette(brand.colors);
  const top = layout.content_top;
  const h = layout.content_bottom - layout.content_top;
  const slam = spring({frame: elapsed - 2, fps, config: {damping: 8, stiffness: 260, mass: 0.7}});
  const txt = spring({frame: elapsed - 7, fps, config: {damping: 14, stiffness: 200}});
  const kick = spring({frame: elapsed, fps, config: {damping: 14, stiffness: 220}});
  const tokens = parseAccent(props.text ?? '');
  const chars = tokens.reduce((n, t) => n + t.text.length + 1, 0);
  const size = Math.round(Math.max(84, Math.min(130, 160 - chars * 2.6)));
  const meme: React.CSSProperties = {fontFamily: MEME, textTransform: 'uppercase', color: '#fff', WebkitTextStroke: '12px #000', paintOrder: 'stroke fill', letterSpacing: '0.01em', textAlign: 'center', lineHeight: 1.02};
  const emojiSize = props.kicker ? 330 : 380;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top, height: h}}>
      {/* comic burst */}
      <div style={{
        position: 'absolute', left: 540 - 520, top: h * 0.46 - 520, width: 1040, height: 1040, borderRadius: '50%',
        background: `repeating-conic-gradient(from ${elapsed * 1.5}deg, ${c.accent2}55 0deg 7deg, transparent 7deg 18deg)`,
        maskImage: 'radial-gradient(circle, black 18%, transparent 68%)', WebkitMaskImage: 'radial-gradient(circle, black 18%, transparent 68%)',
        opacity: interpolate(slam, [0, 1], [0, 1]), transform: `scale(${interpolate(slam, [0, 1], [0.4, 1])})`,
      }} />
      {props.kicker ? (
        <div style={{...meme, position: 'absolute', left: 60, right: 60, top: 10, fontSize: 92, opacity: kick, transform: `translateY(${interpolate(kick, [0, 1], [-40, 0])}px)`}}>
          {props.kicker}
        </div>
      ) : null}
      <div style={{
        position: 'absolute', left: 0, right: 0, top: h * 0.46 - emojiSize * 0.6, textAlign: 'center', fontFamily: EMOJI, fontSize: emojiSize, lineHeight: 1.2,
        transform: `scale(${interpolate(slam, [0, 1], [3.2, 1])}) rotate(${interpolate(slam, [0, 1], [-25, 0]) + Math.sin(elapsed * 0.22) * 5}deg)`,
        opacity: interpolate(slam, [0, 0.15], [0, 1], {extrapolateRight: 'clamp'}), filter: 'drop-shadow(0 30px 40px rgba(0,0,0,.6))',
      }}>
        {props.emoji || '😳'}
      </div>
      {tokens.length ? (
        <div style={{position: 'absolute', left: 50, right: 50, bottom: 0, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `0 ${size * 0.24}px`, opacity: txt, transform: `scale(${interpolate(txt, [0, 1], [1.3, 1])})`}}>
          {tokens.map((t, i) => (
            <span key={i} style={{...meme, fontSize: size, color: t.accent ? c.highlight : '#fff'}}>{t.text}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
};
