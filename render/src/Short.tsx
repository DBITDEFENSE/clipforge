import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Background} from './components/Background';
import {BRoll} from './components/BRoll';
import {CVEScoreCard} from './components/CVEScoreCard';
import {DiagramFlow} from './components/DiagramFlow';
import {LowerThird} from './components/LowerThird';
import {Captions} from './components/Captions';
import {CodeCard} from './components/CodeCard';
import {HeadlineCard} from './components/HeadlineCard';
import {KineticText} from './components/KineticText';
import {Motion} from './components/Motion';
import {StatCard} from './components/StatCard';
import {TerminalCard} from './components/TerminalCard';
import {Alarm, EmojiRain, Fire, Glitch, Shake, Sticker} from './components/FX';
import {Popups} from './components/Popups';
import {Reaction} from './components/Reaction';
import {MONO, palette} from './fonts';
import type {Shot, ShotsDoc} from './types';

const ShotView: React.FC<{shot: Shot; doc: ShotsDoc}> = ({shot, doc}) => {
  const frame = useCurrentFrame(); // local to this shot's Sequence
  const {brand, layout} = doc;
  // cards keep animating across sub-shots of the same beat
  const elapsed = frame + shot.start_frame - (shot.props.anim_start_frame ?? shot.start_frame);
  const common = {props: shot.props, elapsed, brand, layout};
  let body: React.ReactNode = null;
  switch (shot.type) {
    case 'kinetic': body = <KineticText text={shot.props.text} brand={brand} layout={layout} />; break;
    case 'code': body = <CodeCard {...common} />; break;
    case 'terminal': body = <TerminalCard {...common} />; break;
    case 'headline': body = <HeadlineCard {...common} />; break;
    case 'stat': body = <StatCard {...common} />; break;
    case 'diagram': body = <DiagramFlow {...common} />; break;
    case 'cve': body = <CVEScoreCard {...common} />; break;
    case 'reaction': body = <Reaction {...common} />; break;
    case 'popups': body = <Popups {...common} />; break;
    case 'broll': body = <BRoll props={shot.props} duration={shot.end_frame - shot.start_frame} brand={brand} layout={layout} />; break;
  }
  const lower = shot.props.lower;
  const fx: string = shot.props.fx ?? 'none';
  const emoji: string = shot.props.emoji ?? '';
  let moved: React.ReactNode = <Motion motion={shot.type === 'broll' ? 'none' : shot.motion} duration={shot.end_frame - shot.start_frame}>{body}</Motion>;
  if (fx === 'glitch') moved = <Glitch>{moved}</Glitch>;
  if (fx === 'shake') moved = <Shake>{moved}</Shake>;
  const side = parseInt(shot.id.replace(/\D/g, '') || '0', 10) % 2 ? 'left' : 'right';
  return (
    <>
      {fx === 'fire' ? <Fire brand={brand} /> : null}
      {fx === 'emoji_rain' ? <EmojiRain emoji={emoji} /> : null}
      {moved}
      {fx === 'alarm' ? <Alarm brand={brand} layout={layout} text={shot.props.alert_text} /> : null}
      {emoji && shot.type !== 'reaction' && fx !== 'emoji_rain' && !lower?.title ? <Sticker emoji={emoji} layout={layout} side={side} /> : null}
      {lower?.title ? <LowerThird title={lower.title} sub={lower.sub} brand={brand} layout={layout} /> : null}
      {shot.props.sfx_src ? <Audio src={staticFile(shot.props.sfx_src)} volume={shot.props.sfx_volume ?? 0.4} /> : null}
    </>
  );
};

const Chrome: React.FC<{doc: ShotsDoc}> = ({doc}) => {
  const frame = useCurrentFrame();
  const c = doc.brand.colors;
  const y = doc.layout.caption_bottom + 34;
  return (
    <>
      <div style={{position: 'absolute', left: 90, right: 90, top: y, height: 6, borderRadius: 3, background: 'rgba(255,255,255,.08)'}}>
        <div style={{height: '100%', width: `${(frame / doc.duration_frames) * 100}%`, borderRadius: 3, background: `linear-gradient(90deg, ${palette(c).accent}, ${palette(c).accent2})`}} />
      </div>
      {doc.brand.handle ? (
        <div style={{position: 'absolute', left: 0, right: 0, top: y + 22, textAlign: 'center', fontFamily: MONO, fontSize: 24, letterSpacing: '0.12em', color: `${c.muted}AA`}}>
          {doc.brand.handle}
        </div>
      ) : null}
    </>
  );
};

export const Short: React.FC<ShotsDoc> = (doc) => (
  <AbsoluteFill>
    <Background brand={doc.brand} />
    {doc.shots.map((s) => (
      <Sequence key={s.id} from={s.start_frame} durationInFrames={s.end_frame - s.start_frame} premountFor={10}>
        <ShotView shot={s} doc={doc} />
      </Sequence>
    ))}
    <Captions captions={doc.captions} brand={doc.brand} layout={doc.layout} />
    <Chrome doc={doc} />
    {doc.audio ? <Audio src={staticFile(doc.audio)} /> : null}
  </AbsoluteFill>
);
