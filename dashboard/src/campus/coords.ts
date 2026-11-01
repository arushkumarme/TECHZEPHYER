// Campus SVG geometry. The artwork is 1920x1240; the shipped copy is cropped to MAP_CROP.
export const MAP_CROP = { x: 48, y: 155, w: 1255, h: 1010 };
export const SVG_HEIGHT = 1240;

/** Leaflet CRS.Simple uses [lat, lng] = [up, right]; SVG y points down. */
export function toLatLng(x: number, y: number): [number, number] {
  return [SVG_HEIGHT - y, x];
}

export const IMAGE_BOUNDS: [[number, number], [number, number]] = [
  [75, 48],
  [1085, 1303],
];
