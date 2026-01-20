/**
 * Escape HTML special characters.
 * @param {string} text
 * @returns {string}
 */
export function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Format a numeric value to 3 decimal places.
 * @param {number|string|null|undefined} value
 * @returns {string|null}
 */
export function formatNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return null;
  }
  return num.toFixed(3);
}

/**
 * Decode a base64 string.
 * @param {string} b64
 * @returns {string}
 */
export function decodeBase64(b64) {
  return atob(b64);
}

/**
 * Compute the midpoint between two positions.
 * @param {{x:number,y:number,z:number}|null} posA
 * @param {{x:number,y:number,z:number}|null} posB
 * @returns {{x:number,y:number,z:number}|null}
 */
export function midpoint(posA, posB) {
  if (!posA || !posB) {
    return null;
  }
  return {
    x: (posA.x + posB.x) / 2,
    y: (posA.y + posB.y) / 2,
    z: (posA.z + posB.z) / 2,
  };
}

/**
 * Compute the centroid for a list of positions.
 * @param {Array<{x:number,y:number,z:number}|null>} positions
 * @returns {{x:number,y:number,z:number}|null}
 */
export function centroid(positions) {
  if (!positions || !positions.length) {
    return null;
  }
  let x = 0;
  let y = 0;
  let z = 0;
  let count = 0;
  positions.forEach((pos) => {
    if (!pos) {
      return;
    }
    x += pos.x;
    y += pos.y;
    z += pos.z;
    count += 1;
  });
  if (!count) {
    return null;
  }
  return { x: x / count, y: y / count, z: z / count };
}
