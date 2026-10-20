import { createMp4 } from '@/utils/mp4Video';

/** Minimal WebM writer: one video track, millisecond timecodes and keyframe cues. */
interface VideoPacket { bytes: Uint8Array<ArrayBuffer>; timestamp: number; key: boolean }

const uint = (value: number, length = Math.max(1, Math.ceil(Math.log2(value + 1) / 8))) => {
  const bytes = new Uint8Array(length);
  for (let i = length - 1; i >= 0; i -= 1) { bytes[i] = value % 256; value = Math.floor(value / 256); }
  return bytes;
};
const join = (parts: Uint8Array[]): Uint8Array<ArrayBuffer> => {
  const output = new Uint8Array(parts.reduce((n, part) => n + part.length, 0));
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.length; }
  return output;
};
const vint = (value: number) => {
  let length = 1;
  while (value >= 2 ** (7 * length) - 1) length += 1;
  const bytes = uint(value, length);
  bytes[0] |= 1 << (8 - length);
  return bytes;
};
const element = (id: number, data: Uint8Array) => join([uint(id), vint(data.length), data]);
const number = (id: number, value: number) => element(id, uint(value));
const text = (id: number, value: string) => element(id, new TextEncoder().encode(value));
const float = (id: number, value: number) => {
  const bytes = new Uint8Array(8); new DataView(bytes.buffer).setFloat64(0, value); return element(id, bytes);
};

export function createWebm(packets: VideoPacket[], width: number, height: number, fps: number, codec: 'vp8' | 'vp9'): Blob {
  if (!packets.length || !packets[0].key) throw new Error('animationEncodeFailed');
  const header = element(0x1a45dfa3, join([
    number(0x4286, 1), number(0x42f7, 1), number(0x42f2, 4), number(0x42f3, 8),
    text(0x4282, 'webm'), number(0x4287, 4), number(0x4285, 2),
  ]));
  const info = element(0x1549a966, join([
    number(0x2ad7b1, 1000000), float(0x4489, packets.length / fps * 1000),
    text(0x4d80, 'Sharp GUI'), text(0x5741, 'Sharp GUI'),
  ]));
  const tracks = element(0x1654ae6b, element(0xae, join([
    number(0xd7, 1), number(0x73c5, 1), number(0x83, 1), number(0x9c, 0),
    text(0x86, codec === 'vp9' ? 'V_VP9' : 'V_VP8'), number(0x23e383, Math.round(1e9 / fps)),
    element(0xe0, join([number(0xb0, width), number(0xba, height)])),
  ])));
  const clusters: Uint8Array<ArrayBuffer>[] = [];
  const cues: Uint8Array[] = [];
  let offset = info.length + tracks.length;
  let index = 0;
  while (index < packets.length) {
    const start = index;
    const time = Math.round(packets[start].timestamp / 1000);
    const blocks: Uint8Array[] = [number(0xe7, time)];
    do {
      const packet = packets[index];
      const delta = Math.round(packet.timestamp / 1000) - time;
      blocks.push(element(0xa3, join([new Uint8Array([0x81, (delta >> 8) & 255, delta & 255, packet.key ? 0x80 : 0]), packet.bytes])));
      index += 1;
    } while (index < packets.length && !packets[index].key && packets[index].timestamp / 1000 - time < 30000);
    const cluster = element(0x1f43b675, join(blocks));
    if (packets[start].key) cues.push(element(0xbb, join([
      number(0xb3, time), element(0xb7, join([number(0xf7, 1), number(0xf1, offset)])),
    ])));
    clusters.push(cluster); offset += cluster.length;
  }
  const cueData = element(0x1c53bb6b, join(cues));
  const segmentSize = offset + cueData.length;
  return new Blob([header, uint(0x18538067), vint(segmentSize), info, tracks, ...clusters, cueData], { type: 'video/webm' });
}

export interface VideoExportOptions {
  width: number; height: number; fps: number; frames: number;
  format?: AnimationVideoFormat;
  signal: AbortSignal;
  render: (index: number) => Promise<HTMLCanvasElement>;
  onProgress: (progress: number) => void;
}

export type AnimationVideoFormat = 'webm' | 'mp4';

export async function getAnimationEncoderConfig(width: number, height: number, fps: number, format: AnimationVideoFormat): Promise<VideoEncoderConfig> {
  if (typeof VideoEncoder === 'undefined' || typeof VideoFrame === 'undefined') throw new Error(format === 'mp4' ? 'animationMp4Unavailable' : 'animationCodecUnavailable');
  const bitrate = Math.round(width * height * fps * 0.28);
  const level = width * height <= 1920 * 1080 ? (fps > 30 ? '2a' : '28') : (fps > 30 ? '34' : '33');
  const codecs = format === 'mp4' ? [`avc1.6400${level}`, `avc1.4d00${level}`, `avc1.4200${level}`] : ['vp09.00.51.08', 'vp8'];
  for (const codec of codecs) {
    const candidate: VideoEncoderConfig = { codec, width, height, framerate: fps, bitrate,
      latencyMode: format === 'mp4' ? 'realtime' : 'quality',
      ...(format === 'mp4' ? { avc: { format: 'avc' as const } } : {}) };
    try { if ((await VideoEncoder.isConfigSupported(candidate)).supported) return candidate; } catch { /* Try next supported codec. */ }
  }
  throw new Error(format === 'mp4' ? 'animationMp4Unavailable' : 'animationCodecUnavailable');
}

export async function encodeAnimationVideo(options: VideoExportOptions): Promise<Blob> {
  const { width, height, fps, frames, signal, render, onProgress, format = 'webm' } = options;
  signal.throwIfAborted();
  const config = await getAnimationEncoderConfig(width, height, fps, format);
  const packets: VideoPacket[] = [];
  let description: Uint8Array<ArrayBuffer> | undefined;
  let bytes = 0;
  let failure: Error | null = null;
  const check = () => { signal.throwIfAborted(); if (failure) throw failure; };
  const encoder = new VideoEncoder({
    output: (chunk, metadata) => {
      bytes += chunk.byteLength;
      if (bytes > 512 * 1024 * 1024) { failure = new Error('animationMemoryLimit'); return; }
      const data = new Uint8Array(chunk.byteLength); chunk.copyTo(data);
      const configDescription = metadata?.decoderConfig?.description;
      if (format === 'mp4' && configDescription) {
        const next = new Uint8Array(ArrayBuffer.isView(configDescription)
          ? new Uint8Array(configDescription.buffer, configDescription.byteOffset, configDescription.byteLength)
          : new Uint8Array(configDescription));
        if (description && (description.length !== next.length || description.some((byte, index) => byte !== next[index]))) {
          failure = new Error('animationEncodeFailed'); return;
        }
        description = next;
      }
      packets.push({ bytes: data, timestamp: chunk.timestamp, key: chunk.type === 'key' });
    },
    error: () => { failure = new Error('animationEncodeFailed'); },
  });
  try {
    check(); encoder.configure(config);
    for (let index = 0; index < frames; index += 1) {
      check();
      const canvas = await render(index);
      check();
      const timestamp = Math.round(index * 1e6 / fps);
      const frame = new VideoFrame(canvas, { timestamp, duration: Math.round((index + 1) * 1e6 / fps) - timestamp, alpha: 'discard' });
      try { encoder.encode(frame, { keyFrame: index % (fps * 2) === 0 }); } finally { frame.close(); }
      // Bound pending GPU/codec work and yield to the Cancel button.
      if (encoder.encodeQueueSize >= 4) await encoder.flush();
      onProgress((index + 1) / frames);
      await new Promise<void>(resolve => setTimeout(resolve, 0));
    }
    await encoder.flush(); check();
    if (packets.length !== frames) throw new Error('animationEncodeFailed');
    if (format === 'mp4') {
      if (!description) throw new Error('animationEncodeFailed');
      return createMp4(packets, description, width, height, fps);
    }
    return createWebm(packets, width, height, fps, config.codec === 'vp8' ? 'vp8' : 'vp9');
  } finally {
    if (encoder.state !== 'closed') encoder.close();
    packets.length = 0;
  }
}
