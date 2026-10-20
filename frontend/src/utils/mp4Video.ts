/** Single AVC track with no reordered frames; fixed-rate timestamps use a 90 kHz clock. */
export interface AvcPacket {
  bytes: Uint8Array<ArrayBuffer>;
  timestamp: number;
  key: boolean;
}

const join = (parts: Uint8Array[]): Uint8Array<ArrayBuffer> => {
  const output = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.length; }
  return output;
};
const u32 = (...values: number[]) => {
  const bytes = new Uint8Array(values.length * 4); const view = new DataView(bytes.buffer);
  values.forEach((value, index) => view.setUint32(index * 4, value));
  return bytes;
};
const u16 = (...values: number[]) => {
  const bytes = new Uint8Array(values.length * 2); const view = new DataView(bytes.buffer);
  values.forEach((value, index) => view.setUint16(index * 2, value));
  return bytes;
};
const ascii = (value: string) => new TextEncoder().encode(value);
const box = (name: string, ...parts: Uint8Array[]) => join([u32(8 + parts.reduce((sum, part) => sum + part.length, 0)), ascii(name), ...parts]);
const fullBox = (name: string, flags: number, ...parts: Uint8Array[]) => box(name, u32(flags), ...parts);
const matrix = () => u32(0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000);

export function createMp4(packets: AvcPacket[], description: Uint8Array<ArrayBuffer>, width: number, height: number, fps: number): Blob {
  if (!packets.length || !packets[0].key || description.length < 7 || description[0] !== 1
    || ![24, 30, 60].includes(fps) || !Number.isInteger(width) || !Number.isInteger(height)
    || width < 1 || height < 1 || width > 65535 || height > 65535
    || packets.some((packet, index) => !packet.bytes.length || Math.abs(packet.timestamp - Math.round(index * 1e6 / fps)) > 1)) {
    throw new Error('animationEncodeFailed');
  }
  const timescale = 90000; const delta = timescale / fps; const duration = delta * packets.length;
  const ftyp = box('ftyp', ascii('isom'), u32(0x200), ascii('isomiso2avc1mp41'));
  const movie = fullBox('mvhd', 0, u32(0, 0, timescale, duration, 0x10000), u16(0x100, 0),
    u32(0, 0), matrix(), u32(0, 0, 0, 0, 0, 0, 2));
  const track = fullBox('tkhd', 7, u32(0, 0, 1, 0, duration, 0, 0), u16(0, 0, 0, 0), matrix(), u32(width * 65536, height * 65536));
  const media = fullBox('mdhd', 0, u32(0, 0, timescale, duration), u16(0x55c4, 0)); // und
  const handler = fullBox('hdlr', 0, u32(0), ascii('vide'), u32(0, 0, 0), ascii('Sharp GUI\0'));
  const sample = box('avc1', new Uint8Array(6), u16(1), new Uint8Array(16), u16(width, height),
    u32(0x480000, 0x480000, 0), u16(1), new Uint8Array(32), u16(24, 0xffff), box('avcC', description));
  const samples = fullBox('stsd', 0, u32(1), sample);
  const timing = fullBox('stts', 0, u32(1, packets.length, delta));
  const chunks = fullBox('stsc', 0, u32(1, 1, packets.length, 1));
  const sizes = fullBox('stsz', 0, u32(0, packets.length), u32(...packets.map(packet => packet.bytes.length)));
  const keys = packets.flatMap((packet, index) => packet.key ? [index + 1] : []);
  const sync = fullBox('stss', 0, u32(keys.length, ...keys));
  const dataReference = fullBox('dref', 0, u32(1), fullBox('url ', 1));
  const makeMoov = (offset: number) => box('moov', movie, box('trak', track, box('mdia', media, handler,
    box('minf', fullBox('vmhd', 1, u16(0, 0, 0, 0)), box('dinf', dataReference),
      box('stbl', samples, timing, chunks, sizes, fullBox('stco', 0, u32(1, offset)), sync)))));
  // Fast-start metadata precedes the one chunk of AVC samples.
  const moov = makeMoov(ftyp.length + makeMoov(0).length + 8);
  const payloadBytes = packets.reduce((sum, packet) => sum + packet.bytes.length, 0);
  return new Blob([ftyp, moov, u32(payloadBytes + 8), ascii('mdat'), ...packets.map(packet => packet.bytes)], { type: 'video/mp4' });
}
