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

function subtract(posA, posB) {
  if (!posA || !posB) {
    return null;
  }
  return {
    x: posA.x - posB.x,
    y: posA.y - posB.y,
    z: posA.z - posB.z,
  };
}

function dot(vecA, vecB) {
  if (!vecA || !vecB) {
    return null;
  }
  return vecA.x * vecB.x + vecA.y * vecB.y + vecA.z * vecB.z;
}

function cross(vecA, vecB) {
  if (!vecA || !vecB) {
    return null;
  }
  return {
    x: vecA.y * vecB.z - vecA.z * vecB.y,
    y: vecA.z * vecB.x - vecA.x * vecB.z,
    z: vecA.x * vecB.y - vecA.y * vecB.x,
  };
}

function magnitude(vec) {
  if (!vec) {
    return null;
  }
  return Math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z);
}

function normalize(vec) {
  const mag = magnitude(vec);
  if (!vec || !mag) {
    return null;
  }
  return {
    x: vec.x / mag,
    y: vec.y / mag,
    z: vec.z / mag,
  };
}

/**
 * Compute the Cartesian distance between two positions.
 * @param {{x:number,y:number,z:number}|null} posA
 * @param {{x:number,y:number,z:number}|null} posB
 * @returns {number|null}
 */
export function distance(posA, posB) {
  const delta = subtract(posA, posB);
  return magnitude(delta);
}

/**
 * Compute the angle ABC in degrees.
 * @param {{x:number,y:number,z:number}|null} posA
 * @param {{x:number,y:number,z:number}|null} posB
 * @param {{x:number,y:number,z:number}|null} posC
 * @returns {number|null}
 */
export function angleDegrees(posA, posB, posC) {
  const vecBA = subtract(posA, posB);
  const vecBC = subtract(posC, posB);
  const magBA = magnitude(vecBA);
  const magBC = magnitude(vecBC);
  const numerator = dot(vecBA, vecBC);
  if (!magBA || !magBC || numerator === null) {
    return null;
  }
  const cosine = Math.max(-1, Math.min(1, numerator / (magBA * magBC)));
  return (Math.acos(cosine) * 180) / Math.PI;
}

/**
 * Compute the dihedral angle ABCD in degrees.
 * @param {{x:number,y:number,z:number}|null} posA
 * @param {{x:number,y:number,z:number}|null} posB
 * @param {{x:number,y:number,z:number}|null} posC
 * @param {{x:number,y:number,z:number}|null} posD
 * @returns {number|null}
 */
export function dihedralDegrees(posA, posB, posC, posD) {
  const b0 = subtract(posA, posB);
  const b1 = subtract(posC, posB);
  const b2 = subtract(posD, posC);
  const b1Unit = normalize(b1);
  if (!b0 || !b1 || !b2 || !b1Unit) {
    return null;
  }
  const n0 = cross(b0, b1);
  const n1 = cross(b1, b2);
  const n0Unit = normalize(n0);
  const n1Unit = normalize(n1);
  if (!n0Unit || !n1Unit) {
    return null;
  }
  const m1 = cross(n0Unit, b1Unit);
  const x = dot(n0Unit, n1Unit);
  const y = dot(m1, n1Unit);
  if (x === null || y === null) {
    return null;
  }
  return (Math.atan2(y, x) * 180) / Math.PI;
}
