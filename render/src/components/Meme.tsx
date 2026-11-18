import React from 'react';
import {AbsoluteFill, interpolate, spring, useVideoConfig} from 'remotion';
import {EMOJI, MEME, palette} from '../fonts';
import type {Brand, Layout} from '../types';
import {Fire} from './FX';

/* Original meme layouts drawn with emoji + bold meme type (no third-party meme images). */
type Panel = {emoji: string; text: string};
type P = {props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout};

const outline: React.CSSProperties = {fontFamily: MEME, textTransform: 'uppercase', color: '#fff', WebkitTextStroke: '10px #000', paintOrder: 'stroke fill', lineHeight: 1.02, textAlign: 'center'};
const ink: React.CSSProperties = {fontFamily: MEME, textTransform: 'uppercase', color: '#0b0b0b', lineHeight: 1.04};
const fit = (t: string, max: number, min: number) => Math.round(Math.max(min, Math.min(max, max * 14 / Math.max(14, (t || '').length))));

const usePop = (elapsed: number, delay: number, stiff = 240) => {
  const {fps} = useVideoConfig();
  return spring({frame: elapsed - delay, fps, config: {damping: 11, stiffness: stiff, mass: 0.6}});
};

const Emoji: React.FC<{e: string; size: number; style?: React.CSSProperties}> = ({e, size, style}) => (
  <div style={{fontFamily: EMOJI, fontSize: size, lineHeight: 1, filter: 'drop-shadow(0 14px 18px rgba(0,0,0,.45))', ...style}}>{e}</div>
);

const NopeYep: React.FC<P & {panels: Panel[]}> = ({panels, elapsed, layout, brand}) => {
  const c = palette(brand.colors);
  const h = (layout.content_bottom - layout.content_top - 30) / 2;
  return (
    <div style={{position: 'absolute', left: 50, right: 50, top: layout.content_top + 10}}>
      {panels.slice(0, 2).map((p, i) => {
        const s = usePop(elapsed, i * 16);
        return (
          <div key={i} style={{display: 'flex', height: h, marginBottom: 30, borderRadius: 18, overflow: 'hidden', border: '6px solid #fff', boxShadow: '0 24px 50px rgba(0,0,0,.55)',
            opacity: interpolate(s, [0, 0.2], [0, 1], {extrapolateRight: 'clamp'}), transform: `translateX(${interpolate(s, [0, 1], [i ? 220 : -220, 0])}px)`}}>
            <div style={{width: h, flex: 'none', background: i ? `${c.highlight}33` : `${c.warning}33`, display: 'grid', placeItems: 'center', position: 'relative'}}>
              <Emoji e={p.emoji || (i ? '😎' : '🙅')} size={h * 0.62} />
              <div style={{position: 'absolute', left: 14, top: 10, fontSize: 64, fontFamily: MEME, color: i ? c.highlight : c.warning, WebkitTextStroke: '6px #000', paintOrder: 'stroke fill'}}>{i ? '✓' : '✗'}</div>
            </div>
            <div style={{flex: 1, background: '#fff', display: 'flex', alignItems: 'center', padding: '0 34px'}}>
              <div style={{...ink, fontSize: fit(p.text, 84, 50)}}>{p.text}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const ExpReality: React.FC<P & {panels: Panel[]}> = ({panels, elapsed, layout, brand}) => {
  const c = palette(brand.colors);
  const h = (layout.content_bottom - layout.content_top - 30) / 2;
  return (
    <div style={{position: 'absolute', left: 50, right: 50, top: layout.content_top + 10}}>
      {panels.slice(0, 2).map((p, i) => {
        const s = usePop(elapsed, i * 20, i ? 320 : 220);
        const shake = i && elapsed - 20 < 10 && elapsed > 20 ? Math.sin(elapsed * 3) * 10 : 0;
        return (
          <div key={i} style={{height: h, marginBottom: 30, borderRadius: 18, overflow: 'hidden', border: '6px solid #fff', background: i ? '#1a0b0b' : '#0b1418', boxShadow: '0 24px 50px rgba(0,0,0,.55)',
            transform: `translateX(${shake}px) scale(${interpolate(s, [0, 1], [i ? 1.25 : 0.8, 1])})`, opacity: interpolate(s, [0, 0.2], [0, 1], {extrapolateRight: 'clamp'})}}>
            <div style={{background: i ? c.warning : c.accent, color: '#000', fontFamily: MEME, fontSize: 50, letterSpacing: '0.06em', padding: '6px 24px'}}>{i ? 'REALITY' : 'EXPECTATION'}</div>
            <div style={{display: 'flex', alignItems: 'center', gap: 26, height: h - 76, padding: '0 30px'}}>
              <Emoji e={p.emoji || (i ? '💀' : '😇')} size={h * 0.5} />
              <div style={{...outline, textAlign: 'left', fontSize: fit(p.text, 78, 48)}}>{p.text}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const GalaxyBrain: React.FC<P & {panels: Panel[]}> = ({panels, elapsed, layout, brand}) => {
  const c = palette(brand.colors);
  const rows = panels.slice(0, 4);
  const h = (layout.content_bottom - layout.content_top - 12 * rows.length) / rows.length;
  return (
    <div style={{position: 'absolute', left: 50, right: 50, top: layout.content_top}}>
      {rows.map((p, i) => {
        const s = usePop(elapsed, i * 11);
        const lvl = (i + 1) / rows.length;
        return (
          <div key={i} style={{display: 'flex', height: h, marginBottom: 12, borderRadius: 14, overflow: 'hidden', border: '4px solid #fff', opacity: interpolate(s, [0, 0.25], [0, 1], {extrapolateRight: 'clamp'}), transform: `scale(${interpolate(s, [0, 1], [0.9, 1])})`}}>
            <div style={{flex: 1, background: '#fff', display: 'flex', alignItems: 'center', padding: '0 26px'}}><div style={{...ink, fontSize: fit(p.text, 66, 40)}}>{p.text}</div></div>
            <div style={{width: h * 1.25, flex: 'none', display: 'grid', placeItems: 'center',
              background: `radial-gradient(circle, ${lvl > 0.7 ? '#fff' : c.accent}${Math.round(40 + lvl * 160).toString(16)} 0%, ${c.accent2}${Math.round(lvl * 200).toString(16).padStart(2, '0')} 45%, #05050f 80%)`}}>
              <Emoji e={p.emoji || '🧠'} size={h * (0.45 + lvl * 0.3)} style={{filter: `drop-shadow(0 0 ${lvl * 50}px ${c.accent}) drop-shadow(0 0 ${lvl * 30}px #fff)`}} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

const StarterPack: React.FC<P & {panels: Panel[]}> = ({panels, elapsed, layout, props}) => {
  const tiles = panels.slice(0, 4);
  const zone = layout.content_bottom - layout.content_top;
  const tile = (zone - 150) / 2 - 12;
  return (
    <div style={{position: 'absolute', left: 50, right: 50, top: layout.content_top}}>
      <div style={{background: '#fff', borderRadius: 14, padding: '10px 18px', marginBottom: 16, ...ink, fontSize: fit(`${props.top} starter pack`, 70, 42), textAlign: 'center'}}>{props.top} STARTER PACK</div>
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18}}>
        {tiles.map((p, i) => {
          const s = usePop(elapsed, 6 + i * 6, 300);
          return (
            <div key={i} style={{height: tile, background: '#fff', borderRadius: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
              transform: `rotate(${[-3, 2, 2.5, -2][i]}deg) scale(${interpolate(s, [0, 1], [0.3, 1])})`, opacity: interpolate(s, [0, 0.2], [0, 1], {extrapolateRight: 'clamp'}), boxShadow: '0 18px 36px rgba(0,0,0,.5)'}}>
              <Emoji e={p.emoji} size={tile * 0.48} />
              <div style={{...ink, fontSize: fit(p.text, 46, 30), textAlign: 'center', padding: '0 10px'}}>{p.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const TwoButtons: React.FC<P & {panels: Panel[]}> = ({panels, elapsed, layout, props, brand}) => {
  const c = palette(brand.colors);
  const s = usePop(elapsed, 0);
  const sweat = usePop(elapsed, 14);
  const zone = layout.content_bottom - layout.content_top;
  return (
    <div style={{position: 'absolute', left: 40, right: 40, top: layout.content_top, height: zone}}>
      {props.top ? <div style={{...outline, fontSize: fit(props.top, 84, 54), marginBottom: 20}}>{props.top}</div> : null}
      <div style={{display: 'flex', gap: 26, justifyContent: 'center', transform: `scale(${interpolate(s, [0, 1], [0.6, 1])})`, opacity: s}}>
        {panels.slice(0, 2).map((p, i) => (
          <div key={i} style={{width: 470, height: 250, borderRadius: 40, background: `radial-gradient(ellipse at 50% 30%, #ff6b6b, ${c.warning} 60%, #8a1010)`, border: '7px solid #fff',
            boxShadow: `0 16px 0 #5a0909, 0 30px 50px rgba(0,0,0,.5)`, display: 'grid', placeItems: 'center', padding: 22, transform: `rotate(${i ? 4 : -4}deg)`}}>
            <div style={{...outline, WebkitTextStroke: '8px #000', fontSize: fit(p.text, 62, 38)}}>{p.text}</div>
          </div>
        ))}
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: props.bottom ? 90 : 10, display: 'grid', placeItems: 'center', transform: `scale(${interpolate(sweat, [0, 1], [0.4, 1])}) rotate(${Math.sin(elapsed * 0.5) * 6}deg)`}}>
        <Emoji e={'😰'} size={300} />
      </div>
      {props.bottom ? <div style={{...outline, position: 'absolute', left: 0, right: 0, bottom: 0, fontSize: fit(props.bottom, 76, 48)}}>{props.bottom}</div> : null}
    </div>
  );
};

const Single: React.FC<P> = ({props, elapsed, layout, brand}) => {
  const c = palette(brand.colors);
  const slam = usePop(elapsed, 2, 260);
  const txt = usePop(elapsed, 8);
  const zone = layout.content_bottom - layout.content_top;
  const nobody = props.format === 'nobody';
  return (
    <div style={{position: 'absolute', left: 50, right: 50, top: layout.content_top, height: zone}}>
      {props.format === 'calm_chaos' ? <AbsoluteFill style={{top: -layout.content_top, height: 1920}}><Fire brand={brand} /></AbsoluteFill> : null}
      <div style={{position: 'relative'}}>
        {nobody ? <div style={{...outline, fontSize: 80, color: c.highlight}}>NOBODY:</div> : null}
        {props.top ? <div style={{...outline, fontSize: fit(props.top, 92, 56), marginTop: nobody ? 14 : 0}}>{props.top}</div> : null}
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, top: zone * 0.48 - 190, display: 'grid', placeItems: 'center',
        transform: `scale(${interpolate(slam, [0, 1], [3, 1])}) rotate(${interpolate(slam, [0, 1], [-22, 0]) + Math.sin(elapsed * 0.25) * 4}deg)`, opacity: interpolate(slam, [0, 0.15], [0, 1], {extrapolateRight: 'clamp'})}}>
        <Emoji e={props.emoji || '😳'} size={360} />
      </div>
      {props.bottom ? <div style={{...outline, position: 'absolute', left: 0, right: 0, bottom: 0, fontSize: fit(props.bottom, 100, 60), opacity: txt, transform: `scale(${interpolate(txt, [0, 1], [1.3, 1])})`}}>{props.bottom}</div> : null}
    </div>
  );
};

export const Meme: React.FC<P> = (p) => {
  const panels: Panel[] = p.props.panels ?? [];
  switch (p.props.format) {
    case 'nope_yep': return <NopeYep {...p} panels={panels} />;
    case 'expectation_reality': return <ExpReality {...p} panels={panels} />;
    case 'galaxy_brain': return <GalaxyBrain {...p} panels={panels} />;
    case 'starter_pack': return <StarterPack {...p} panels={panels} />;
    case 'two_buttons': return <TwoButtons {...p} panels={panels} />;
    default: return <Single {...p} />;
  }
};
