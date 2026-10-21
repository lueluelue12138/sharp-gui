import type { ViewerOrientationHint } from '@/types/modelPreview';

const HEADER_MAX_BYTES = 512 * 1024;
const SHARP_SUPPLEMENT = [
  ['extrinsic', '16', 'float'], ['intrinsic', '9', 'float'],
  ['image_size', '2', 'uint'], ['frame', '2', 'int'],
  ['disparity', '2', 'float'], ['color_space', '1', 'uchar'], ['version', '3', 'uchar'],
];
const GAUSSIAN_PROPERTIES = [
  'x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity',
  'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3',
];

// Match the complete upstream ml-sharp save_ply schema, never names or geometry.
// The backend repeats this bounded check when the file is added to the library.
export function hasMlSharpPlyHeader(header: string): boolean {
  const end = /^[ \t]*end_header[ \t]*\r?$/m.exec(header);
  if (!end) return false;
  const lines = header.slice(0, end.index).split(/\r?\n/)
    .map((line) => line.trim().replace(/\s+/g, ' ')).filter(Boolean);
  if (lines[0] !== 'ply' || !lines.some((line) => /^format (ascii|binary_little_endian|binary_big_endian) 1\.0$/.test(line))) return false;
  const elements: string[][] = [];
  const properties = new Map<string, string[]>();
  let current = '';
  for (const line of lines.slice(1)) {
    const [keyword, ...parts] = line.split(/\s+/);
    if (keyword === 'element') {
      elements.push(parts);
      current = parts[0];
    } else if (keyword === 'property') {
      const entries = properties.get(current) ?? [];
      entries.push(parts.join(' '));
      properties.set(current, entries);
    }
  }
  if (elements.length !== 8 || elements[0].length !== 2 || elements[0][0] !== 'vertex'
    || !/^\d+$/.test(elements[0][1]) || String(Number(elements[0][1])) !== elements[0][1]
    || Number(elements[0][1]) < 1) return false;
  if (!SHARP_SUPPLEMENT.every(([name, count, type], index) =>
    elements[index + 1].join(' ') === `${name} ${count}`
      && properties.get(name)?.length === 1 && properties.get(name)?.[0] === `${type} ${name}`)) return false;
  return GAUSSIAN_PROPERTIES.every((name) => properties.get('vertex')?.includes(`float ${name}`));
}

export async function detectImportedModelOrientation(file: Blob, format: string): Promise<ViewerOrientationHint> {
  if (format !== 'ply') return 'y-front';
  try {
    return hasMlSharpPlyHeader(await file.slice(0, HEADER_MAX_BYTES).text()) ? 'default' : 'y-front';
  } catch {
    // Detection is optional; a file read error must not prevent previewing it.
    return 'y-front';
  }
}
