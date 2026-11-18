import React from 'react';
import {AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {EMOJI, MONO, palette} from '../fonts';
import type {Brand, Layout} from '../types';

/* All effects are procedural (CSS + deterministic noise): original, no stock assets. `frame` is local to the shot. */

const n1 = (f: number, seed: number) => Math.sin(f * 0.91 + seed * 12.9898) * 0.5 + Math.sin(f * 2.13 + seed * 78.233) * 0.3 + Math.sin(f * 4.7 + seed * 3.1) * 0.2;

/** Flames along the bottom of the frame + rising embers + heat glow. Sits BEHIND the shot content. */
export const Fire: React.FC<{brand: Brand}> = ({brand}) => {
  const frame = useCurrentFrame();
  const c = palette(brand.colors);
  const intro = interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'});
  const tongues = Array.from({length: 16}, (_, i) => i);
  const embers = Array.from({length: 26}, (_, i) => i);
  return (
    <AbsoluteFill style={{opacity: intro, pointerEvents: 'none'}}>
      <AbsoluteFill style={{background: `radial-gradient(ellipse 100% 60% at 50% 105%, ${c.fire}99, ${c.warning}40 45%, transparent 78%)`}} />
      <AbsoluteFill style={{filter: 'blur(14px)', mixBlendMode: 'screen'}}>
        {tongues.map((i) => {
          const x = (i / (tongues.length - 1)) * 1180 - 50;
          const h = 820 + 300 * n1(frame * 0.35, i) + 160 * Math.sin(frame * 0.5 + i);
          const w = 200 + 50 * n1(frame * 0.2, i + 40);
          const sway = 18 * n1(frame * 0.3, i + 7);
          return (
            <div key={i} style={{
              position: 'absolute', left: x - w / 2 + sway, bottom: -80, width: w, height: h * intro,
              borderRadius: '50% 50% 45% 45% / 70% 70% 30% 30%',
              background: `radial-gradient(ellipse 50% 60% at 50% 80%, #FFF3B0 0%, #FFC83D 22%, ${c.fire} 48%, ${c.warning}AA 70%, transparent 82%)`,
              opacity: 0.85,
            }} />
          );
        })}
      </AbsoluteFill>
      {embers.map((i) => {
        const speed = 7 + random(`es${i}`) * 9;
        const life = 1920 / speed;
        const t = ((frame + random(`eo${i}`) * life) % life) / life;
        const x = random(`ex${i}`) * 1080 + 60 * Math.sin(frame * 0.08 + i);
        const y = 1920 - t * 1500;
        const size = 6 + random(`ez${i}`) * 10;
        return <div key={i} style={{position: 'absolute', left: x, top: y, width: size, height: size, borderRadius: size, background: i % 3 ? '#FFC83D' : c.fire, boxShadow: `0 0 ${size * 2}px ${c.fire}`, opacity: (1 - t) * 0.9}} />;
      })}
    </AbsoluteFill>
  );
};

/** Red pulsing edges, sweeping siren beams, and a scrolling ALERT strip under the platform's top UI. */
export const Alarm: React.FC<{brand: Brand; layout: Layout; text?: string}> = ({brand, layout, text}) => {
  const frame = useCurrentFrame();
  const c = palette(brand.colors);
  const pulse = 0.5 + 0.5 * Math.sin(frame * 0.42);
  const label = `⚠ ${(text || 'SECURITY ALERT').toUpperCase()} `;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill style={{boxShadow: `inset 0 0 ${70 + 90 * pulse}px ${c.warning}${pulse > 0.5 ? 'AA' : '55'}`}} />
      <AbsoluteFill style={{background: `conic-gradient(from ${frame * 9}deg at 50% -8%, transparent 0deg, ${c.warning}30 18deg, transparent 40deg, transparent 180deg, ${c.warning}30 198deg, transparent 220deg)`, mixBlendMode: 'screen'}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: layout.content_top - 66, height: 54, overflow: 'hidden', background: c.warning, transform: 'rotate(-2deg) scaleX(1.1)', boxShadow: `0 0 40px ${c.warning}AA`}}>
        <div style={{whiteSpace: 'nowrap', fontFamily: MONO, fontWeight: 700, fontSize: 34, lineHeight: '54px', color: '#fff', letterSpacing: '0.1em', transform: `translateX(${-((frame * 9) % 700)}px)`}}>
          {label.repeat(12)}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Emoji falling across the frame (money, skulls, fire...). In front of content but light enough to read through. */
export const EmojiRain: React.FC<{emoji: string}> = ({emoji}) => {
  const frame = useCurrentFrame();
  const chars = Array.from(emoji || '💸').filter((ch) => ch.trim() && ch !== '️');
  const set = chars.length ? chars : ['💸'];
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {Array.from({length: 14}, (_, i) => {
        const speed = 22 + random(`rs${i}`) * 20;
        const delay = random(`rd${i}`) * 20;
        const y = -160 + (frame - delay) * speed;
        if (y < -160) return null;
        const x = random(`rx${i}`) * 1000 + 20 * Math.sin(frame * 0.15 + i);
        const size = 90 + random(`rz${i}`) * 80;
        const rot = (random(`rr${i}`) - 0.5) * 60 + frame * (random(`rw${i}`) - 0.5) * 8;
        return <div key={i} style={{position: 'absolute', left: x, top: y, fontFamily: EMOJI, fontSize: size, lineHeight: 1, transform: `rotate(${rot}deg)`, opacity: 0.92, filter: 'drop-shadow(0 10px 18px rgba(0,0,0,.5))'}}>{set[i % set.length]}</div>;
      })}
    </AbsoluteFill>
  );
};

/** Big emoji sticker slapped onto the corner of the content zone (white sticker outline, overshoot, wobble). */
export const Sticker: React.FC<{emoji: string; layout: Layout; side: 'left' | 'right'}> = ({emoji, layout, side}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - 3, fps, config: {damping: 9, stiffness: 240, mass: 0.6}});
  const wob = Math.sin(frame * 0.25) * 4;
  const rot = (side === 'right' ? 14 : -14) + wob;
  return (
    <div style={{
      position: 'absolute', [side]: 40, top: layout.content_top - 40, fontFamily: EMOJI, fontSize: 210, lineHeight: 1,
      transform: `scale(${interpolate(s, [0, 1], [2.6, 1])}) rotate(${rot}deg)`, opacity: interpolate(s, [0, 0.2], [0, 1], {extrapolateRight: 'clamp'}),
      filter: 'drop-shadow(0 0 0 #fff) drop-shadow(5px 0 0 #fff) drop-shadow(-5px 0 0 #fff) drop-shadow(0 5px 0 #fff) drop-shadow(0 -5px 0 #fff) drop-shadow(0 18px 24px rgba(0,0,0,.55))',
    } as React.CSSProperties}>
      {emoji}
    </div>
  );
};

/** Camera shake: hard on the cut, settling to a subtle tremor. Wraps the shot. */
export const Shake: React.FC<{children: React.ReactNode; strength?: number}> = ({children, strength = 1}) => {
  const frame = useCurrentFrame();
  const amp = strength * (4 + 26 * Math.exp(-frame / 6));
  const x = n1(frame * 2.3, 1) * amp;
  const y = n1(frame * 2.7, 2) * amp;
  const r = n1(frame * 1.9, 3) * amp * 0.06;
  return <AbsoluteFill style={{transform: `translate(${x}px, ${y}px) rotate(${r}deg)`}}>{children}</AbsoluteFill>;
};

/** RGB split + horizontal slice tearing on the cut and in short random bursts. Wraps the shot. */
export const Glitch: React.FC<{children: React.ReactNode}> = ({children}) => {
  const frame = useCurrentFrame();
  const burst = frame < 7 || random(`g${Math.floor(frame / 3)}`) < 0.16;
  if (!burst) return <AbsoluteFill>{children}</AbsoluteFill>;
  const off = 10 + random(`go${frame}`) * 18;
  const slices = Array.from({length: 5}, (_, i) => {
    const top = random(`gt${frame}-${i}`) * 90;
    return {top, h: 3 + random(`gh${frame}-${i}`) * 9, dx: (random(`gx${frame}-${i}`) - 0.5) * 120};
  });
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{filter: `drop-shadow(${-off}px 0 0 rgba(255,45,135,.85)) drop-shadow(${off}px 0 0 rgba(0,229,255,.85))`}}>{children}</AbsoluteFill>
      {slices.map((s, i) => (
        <AbsoluteFill key={i} style={{clipPath: `inset(${s.top}% 0 ${Math.max(0, 100 - s.top - s.h)}% 0)`, transform: `translateX(${s.dx}px)`}}>{children}</AbsoluteFill>
      ))}
      <AbsoluteFill style={{background: 'repeating-linear-gradient(0deg, rgba(255,255,255,.06) 0 2px, transparent 2px 6px)'}} />
    </AbsoluteFill>
  );
};
