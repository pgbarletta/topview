export const DEFAULT_SELECTION_MODE = "Atom";
export const DEFAULT_STYLE_KEY = "sticks";
export const HIGHLIGHT_COLOR = "#111827";
export const HIGHLIGHT_ATOM_OPACITY = 0.2;
export const HIGHLIGHT_LINE_OPACITY = 0.65;
export const MAX_ATOM_CACHE = 2000;
export const PARM7_FONT_MIN = 8;
export const PARM7_FONT_MAX = 32;
export const INFO_FONT_MIN = 8;
export const INFO_FONT_MAX = 32;
export const CHARGE_SCALE = 18.2223;

export const SECTION_MODE_MAP = {
  ATOM_NAME: "Atom",
  CHARGE: "Atom",
  ATOMIC_NUMBER: "Atom",
  MASS: "Atom",
  ATOM_TYPE_INDEX: "Atom",
  AMBER_ATOM_TYPE: "Atom",
  BONDS_INC_HYDROGEN: "Bond",
  BONDS_WITHOUT_HYDROGEN: "Bond",
  BOND_FORCE_CONSTANT: "Bond",
  BOND_EQUIL_VALUE: "Bond",
  ANGLES_INC_HYDROGEN: "Angle",
  ANGLES_WITHOUT_HYDROGEN: "Angle",
  ANGLE_FORCE_CONSTANT: "Angle",
  ANGLE_EQUIL_VALUE: "Angle",
  DIHEDRALS_INC_HYDROGEN: "Dihedral",
  DIHEDRALS_WITHOUT_HYDROGEN: "Dihedral",
  DIHEDRAL_FORCE_CONSTANT: "Dihedral",
  DIHEDRAL_PERIODICITY: "Dihedral",
  DIHEDRAL_PHASE: "Dihedral",
  SCEE_SCALE_FACTOR: "1-4 Nonbonded",
  SCNB_SCALE_FACTOR: "1-4 Nonbonded",
  NONBONDED_PARM_INDEX: "Non-bonded",
  NUMBER_EXCLUDED_ATOMS: "Non-bonded",
  EXCLUDED_ATOMS_LIST: "Non-bonded",
  LENNARD_JONES_ACOEF: "Non-bonded",
  LENNARD_JONES_BCOEF: "Non-bonded",
};

export const STYLE_PRESETS = {
  sticks: { stick: { radius: 0.2 } },
  spheres: { sphere: { radius: 0.7 } },
  lines: { line: {} },
  ballstick: { stick: { radius: 0.2 }, sphere: { scale: 0.3 } },
  cartoon: { cartoon: { color: "spectrum" } },
  cartoon_ligand: {
    protein: { cartoon: { color: "spectrum" } },
    other: { stick: { radius: 0.2 } },
  },
};
