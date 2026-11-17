import React from 'react';
import {interpolate, spring, useVideoConfig} from 'remotion';
import {DISPLAY, MONO} from '../fonts';
import type {Brand, Layout} from '../types';

/** 2-4 nodes stacked top-to-bottom with arrows; a packet travels the path; danger node in warning color. */
export const DiagramFlow: React.FC<{props: Record<string, any>; elapsed: number; brand: Brand; layout: Layout}> = ({props, elapsed, brand, layout}) => {
  const {fps} = useVideoConfig();
  const c = brand.colors;
  const nodes: string[] = props.nodes ?? [];
  const n = nodes.length;
  const top = layout.content_top + 20;
  const h = layout.content_bottom - layout.content_top - 40 - (props.lower?.title ? 190 : 0); // leave room for a lower third
  const boxH = Math.min(150, h / (n * 1.55));
  const gap = (h - boxH * n) / Math.max(n - 1, 1);
  const centers = nodes.map((_, i) => top + i * (boxH + gap) + boxH / 2);
  const perNode = 9;
  const travelStart = n * perNode;
  const travel = interpolate(elapsed, [travelStart, travelStart + 26], [0, n - 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const seg = Math.min(Math.floor(travel), n - 2);
  const packetY = centers[seg] + (centers[seg + 1] - centers[seg]) * (travel - seg);
  const reached = (i: number) => travel >= i - 0.02 && elapsed >= travelStart;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      {centers.slice(0, -1).map((y, i) => {
        const grow = interpolate(elapsed, [(i + 1) * perNode - 4, (i + 1) * perNode + 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const y0 = y + boxH / 2 + 10;
        const len = (centers[i + 1] - boxH / 2 - 10 - y0) * grow;
        return (
          <div key={i}>
            <div style={{position: 'absolute', left: 538, top: y0, width: 4, height: len, background: `repeating-linear-gradient(${c.accent} 0 14px, transparent 14px 26px)`, backgroundPosition: `0 ${elapsed * 2}px`, opacity: 0.8}} />
            {grow >= 1 && <div style={{position: 'absolute', left: 522, top: y0 + len - 18, width: 0, height: 0, borderLeft: '18px solid transparent', borderRight: '18px solid transparent', borderTop: `22px solid ${c.accent}`}} />}
          </div>
        );
      })}
      {nodes.map((label, i) => {
        const s = spring({frame: elapsed - i * perNode, fps, config: {damping: 14, stiffness: 190}});
        const danger = props.danger === i;
        const col = danger ? c.warning : c.accent;
        const lit = danger && reached(i);
        return (
          <div key={i} style={{
            position: 'absolute', left: 150, right: 150, top: centers[i] - boxH / 2, height: boxH, borderRadius: 26,
            background: lit ? `${c.warning}26` : `${c.surface}F0`, border: `3px solid ${col}${danger ? 'FF' : '88'}`,
            boxShadow: lit ? `0 0 70px ${c.warning}88` : `0 0 30px ${col}22`, display: 'flex', alignItems: 'center', justifyContent: 'center',
            opacity: s, transform: `scale(${interpolate(s, [0, 1], [0.8, 1])})`,
          }}>
            <span style={{fontFamily: DISPLAY, fontWeight: 900, fontSize: Math.min(76, boxH * 0.48), textTransform: 'uppercase', color: danger ? c.warning : c.text, letterSpacing: '-0.01em'}}>{label}</span>
          </div>
        );
      })}
      {elapsed >= travelStart && n >= 2 && (
        <div style={{position: 'absolute', left: 540 - 22, top: packetY - 22, width: 44, height: 44, borderRadius: 22, background: c.accent, boxShadow: `0 0 40px ${c.accent}`}} />
      )}
      {props.label && elapsed >= travelStart && (
        <div style={{position: 'absolute', left: 540 + 44, top: packetY - 22, fontFamily: MONO, fontWeight: 700, fontSize: 32, color: c.accent, background: `${c.bg}CC`, padding: '4px 12px', borderRadius: 8, whiteSpace: 'nowrap'}}>
          {props.label}
        </div>
      )}
    </div>
  );
};
