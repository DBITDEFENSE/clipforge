import React from 'react';
import {Composition, Still} from 'remotion';
import {Cover} from './Cover';
import {Short} from './Short';
import {SAMPLE_BRAND, SAMPLE_DOC} from './sample';
import type {CoverProps, ShotsDoc} from './types';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition<any, ShotsDoc>
      id="Short"
      component={Short}
      defaultProps={SAMPLE_DOC}
      fps={30}
      width={1080}
      height={1920}
      durationInFrames={SAMPLE_DOC.duration_frames}
      calculateMetadata={({props}) => ({durationInFrames: props.duration_frames, fps: props.fps, width: props.width, height: props.height})}
    />
    <Still<any, CoverProps>
      id="Cover"
      component={Cover}
      width={1080}
      height={1920}
      defaultProps={{title: 'Your VPN was the *front door*', kicker: 'CVE-2025-0001 · CVSS 9.8', brand: SAMPLE_BRAND}}
    />
  </>
);
