// Mirrors clipforge/shots.schema.json (validated in Python before every render).
export type Motion = 'pop' | 'punch_in' | 'drift' | 'none';
export type ShotType = 'kinetic' | 'code' | 'terminal' | 'headline' | 'stat';

export interface Brand {
  name: string;
  handle?: string;
  colors: {bg: string; surface: string; text: string; muted: string; accent: string; warning: string};
  fonts: {display: string; mono: string};
}

export interface Shot {
  id: string;
  type: ShotType;
  beat: 'hook' | 'what' | 'how' | 'why' | 'punch';
  start_frame: number;
  end_frame: number;
  motion: Motion;
  props: Record<string, any>;
}

export interface CaptionWord {text: string; start_frame: number; end_frame: number}
export interface Caption {start_frame: number; end_frame: number; words: CaptionWord[]}

export interface Layout {content_top: number; content_bottom: number; caption_top: number; caption_bottom: number}

export interface ShotsDoc {
  version: 1;
  short_id: string;
  title: string;
  fps: number;
  width: number;
  height: number;
  duration_frames: number;
  audio: string;
  layout: Layout;
  brand: Brand;
  shots: Shot[];
  captions: Caption[];
  [key: string]: unknown;
}

export interface CoverProps {
  title: string;
  kicker: string;
  brand: Brand;
  [key: string]: unknown;
}
