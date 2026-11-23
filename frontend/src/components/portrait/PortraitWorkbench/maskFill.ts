export type MaskSpan = { x: number; y: number; width: number };

const emptyAlpha = 5;

// Walk transparent runs from every edge. Runs limit the work queue to rows of pixels.
function exterior({ data, width, height }: ImageData, threshold: number) {
  const visited = new Uint8Array(width * height);
  const seeds: number[] = [];
  const lastRow = visited.length - width;
  const open = (pixel: number) => !visited[pixel] && data[pixel * 4 + 3] <= threshold;

  for (let x = 0; x < width; x += 1) seeds.push(x, lastRow + x);
  for (let row = width; row < lastRow; row += width) seeds.push(row, row + width - 1);

  while (seeds.length) {
    const pixel = seeds.pop()!;
    if (!open(pixel)) continue;

    const rowStart = pixel - pixel % width;
    const rowEnd = rowStart + width - 1;
    let left = pixel;
    let right = pixel;
    while (left > rowStart && open(left - 1)) left -= 1;
    while (right < rowEnd && open(right + 1)) right += 1;

    let upWasOpen = false;
    let downWasOpen = false;
    for (let column = left; column <= right; column += 1) {
      visited[column] = 1;
      const upIsOpen = rowStart > 0 && open(column - width);
      const downIsOpen = rowStart < lastRow && open(column + width);
      if (upIsOpen && !upWasOpen) seeds.push(column - width);
      if (downIsOpen && !downWasOpen) seeds.push(column + width);
      upWasOpen = upIsOpen;
      downWasOpen = downIsOpen;
    }
  }
  return visited;
}

export function findNewMaskHoles(before: ImageData, after: ImageData): MaskSpan[] {
  let outsideBefore: Uint8Array | undefined;
  return interiorSpans(after, emptyAlpha, (pixel) => {
    if (before.data[pixel * 4 + 3] > emptyAlpha) return false;
    outsideBefore ??= exterior(before, emptyAlpha);
    return Boolean(outsideBefore[pixel]);
  });
}

export function findNativeMaskHoles(mask: ImageData) {
  // GH_MaskCropV2 binarizes at 0.1 and fills all enclosed holes.
  return interiorSpans(mask, 25);
}

function interiorSpans(mask: ImageData, threshold: number, include?: (pixel: number) => boolean) {
  const { data, width, height } = mask;
  const outside = exterior(mask, threshold);
  const spans: MaskSpan[] = [];

  for (let y = 0; y < height; y += 1) {
    let span: MaskSpan | undefined;
    for (let x = 0; x < width; x += 1) {
      const pixel = y * width + x;
      const alpha = pixel * 4 + 3;
      if (outside[pixel] || data[alpha] > threshold || (include && !include(pixel))) {
        span = undefined;
        continue;
      }
      if (span) {
        span.width += 1;
      } else {
        span = { x, y, width: 1 };
        spans.push(span);
      }
    }
  }
  return spans;
}
