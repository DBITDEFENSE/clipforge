import type {Brand, ShotsDoc} from './types';

// Studio preview only; real renders get props from clipforge (shots.json).
export const SAMPLE_BRAND: Brand = {
  name: 'DBIT Defense',
  handle: '@dbitdefense',
  colors: {bg: '#0A0B0D', surface: '#14161A', text: '#F2F4F7', muted: '#8A93A0', accent: '#00E0FF', warning: '#FF4D3D'},
  fonts: {display: 'Archivo', mono: 'JetBrains Mono'},
};

export const SAMPLE_DOC: ShotsDoc = {
  version: 1,
  short_id: 'sample',
  title: 'Sample',
  fps: 30,
  width: 1080,
  height: 1920,
  duration_frames: 300,
  audio: '',
  layout: {content_top: 250, content_bottom: 1130, caption_top: 1170, caption_bottom: 1440},
  brand: SAMPLE_BRAND,
  shots: [
    {id: 's00', type: 'kinetic', beat: 'hook', start_frame: 0, end_frame: 40, motion: 'pop', props: {text: 'Front door *open*'}},
    {id: 's01', type: 'headline', beat: 'what', start_frame: 40, end_frame: 120, motion: 'punch_in', props: {headline: 'VPN zero-day under active attack', kicker: 'CVE-2025-0001 · CVSS 9.8', anim_start_frame: 40}},
    {id: 's02', type: 'code', beat: 'how', start_frame: 120, end_frame: 210, motion: 'drift', props: {language: 'http', lines: ['GET /api/session HTTP/1.1', 'Host: vpn.corp.example', 'X-Auth-Verified: true', '', '# server skips the login check', '200 OK'], highlight: 3, anim_start_frame: 120}},
    {id: 's03', type: 'stat', beat: 'why', start_frame: 210, end_frame: 260, motion: 'pop', props: {value: '40,000', label: 'devices exposed', anim_start_frame: 210}},
    {id: 's04', type: 'terminal', beat: 'punch', start_frame: 260, end_frame: 300, motion: 'punch_in', props: {lines: ['$ grep X-Auth-Verified access.log | wc -l', '1337', 'ALERT: header abuse detected'], anim_start_frame: 260}},
  ],
  captions: [
    {start_frame: 0, end_frame: 20, words: [{text: 'Your', start_frame: 0, end_frame: 8}, {text: 'VPN', start_frame: 8, end_frame: 20}]},
    {start_frame: 20, end_frame: 40, words: [{text: 'was', start_frame: 20, end_frame: 26}, {text: 'the', start_frame: 26, end_frame: 30}, {text: 'door', start_frame: 30, end_frame: 40}]},
  ],
};
