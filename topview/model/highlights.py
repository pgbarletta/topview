"""Parm7 highlight and interaction helpers."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from topview.errors import ModelError
from topview.model.state import AtomMeta, Parm7Section
from topview.services.parm7 import parse_float_tokens, parse_int_tokens


class HighlightEngine:
    """Compute parm7 highlights and interaction metadata.

    Attributes
    ----------
    _sections
        Parm7 sections keyed by flag name.
    _meta_by_serial
        Atom metadata keyed by serial.
    _int_cache
        Cached integer section values.
    _float_cache
        Cached float section values.
    """

    def __init__(
        self,
        sections: Dict[str, Parm7Section],
        meta_by_serial: Dict[int, AtomMeta],
        int_cache: Dict[str, List[int]],
        float_cache: Dict[str, List[float]],
        bond_adjacency: Optional[Dict[int, set[int]]] = None,
    ) -> None:
        """Initialize the highlight engine.

        Parameters
        ----------
        sections
            Parm7 sections by flag name.
        meta_by_serial
            Atom metadata keyed by serial.
        int_cache
            Cached integer section values.
        float_cache
            Cached float section values.
        bond_adjacency
            Optional adjacency map for bonded atoms.
        """

        self._sections = sections
        self._meta_by_serial = meta_by_serial
        self._int_cache = int_cache
        self._float_cache = float_cache
        self._bond_adjacency = bond_adjacency

    def build_atom_highlights(self, meta: AtomMeta) -> List[Dict[str, object]]:
        """Compute base parm7 highlights for a single atom.

        Parameters
        ----------
        meta
            Atom metadata.

        Returns
        -------
        list
            Highlight spans for the atom.
        """

        highlights: List[Dict[str, object]] = []
        per_atom_sections = [
            "ATOM_NAME",
            "CHARGE",
            "ATOMIC_NUMBER",
            "MASS",
            "ATOM_TYPE_INDEX",
            "AMBER_ATOM_TYPE",
        ]
        for name in per_atom_sections:
            section = self._sections.get(name)
            if not section:
                continue
            index = meta.serial - 1
            if 0 <= index < len(section.tokens):
                token = section.tokens[index]
                highlights.append(
                    {"line": token.line, "start": token.start, "end": token.end, "section": name}
                )

        residue_sections = ["RESIDUE_LABEL", "RESIDUE_POINTER"]
        residue_index = meta.residue_index - 1
        for name in residue_sections:
            section = self._sections.get(name)
            if not section:
                continue
            if 0 <= residue_index < len(section.tokens):
                token = section.tokens[residue_index]
                highlights.append(
                    {"line": token.line, "start": token.start, "end": token.end, "section": name}
                )
        return highlights

    def get_highlights(
        self, serials: Sequence[int], mode: Optional[str] = None
    ) -> Tuple[List[Dict[str, object]], Optional[Dict[str, object]]]:
        """Compute highlights and interaction data for a selection.

        Parameters
        ----------
        serials
            Selected atom serials.
        mode
            Selection mode name.

        Returns
        -------
        tuple
            Highlight spans and interaction payload.

        Raises
        ------
        ModelError
            If serials are missing from the model.
        """

        if not serials:
            return [], None
        highlights: List[Dict[str, object]] = []
        seen: set = set()
        missing: List[str] = []
        for serial in serials:
            try:
                serial_int = int(serial)
            except (TypeError, ValueError):
                missing.append(str(serial))
                continue
            meta = self._meta_by_serial.get(serial_int)
            if meta is None:
                missing.append(str(serial))
                continue
            for hl in self.build_atom_highlights(meta):
                key = (hl["line"], hl["start"], hl["end"])
                if key in seen:
                    continue
                seen.add(key)
                highlights.append(hl)
        if missing:
            raise ModelError(
                "not_found", f"Atom serial(s) {', '.join(missing)} not found"
            )
        normalized_mode = (mode or "Atom").strip()
        interaction: Optional[Dict[str, object]] = None
        if normalized_mode == "Atom":
            for serial in serials:
                try:
                    serial_int = int(serial)
                except (TypeError, ValueError):
                    continue
                self._highlight_atom_lj(highlights, seen, serial_int)
        elif normalized_mode == "Bond":
            self._highlight_bond_entries(highlights, seen, serials)
            interaction = {
                "mode": normalized_mode,
                "bonds": self._extract_bond_params(serials),
            }
        elif normalized_mode == "Angle":
            self._highlight_angle_entries(highlights, seen, serials)
            interaction = {
                "mode": normalized_mode,
                "angles": self._extract_angle_params(serials),
            }
        elif normalized_mode == "Dihedral":
            self._highlight_dihedral_entries(highlights, seen, serials)
            interaction = {
                "mode": normalized_mode,
                "dihedrals": self._extract_dihedral_params(serials),
            }
        elif normalized_mode == "Improper":
            self._highlight_improper_entries(highlights, seen, serials)
            interaction = {
                "mode": normalized_mode,
                "dihedrals": self._extract_improper_params(serials),
            }
        elif normalized_mode == "1-4 Nonbonded":
            one_four = self._extract_14_params(serials)
            pair_serials = [entry["serials"] for entry in one_four] if one_four else None
            self._highlight_14_pairs(highlights, seen, serials)
            self._highlight_nonbonded_pair(
                highlights,
                seen,
                serials,
                pairs=pair_serials,
            )
            interaction = {
                "mode": normalized_mode,
                "one_four": one_four,
                "nonbonded": self._extract_nonbonded_params(
                    pair_serials[0] if pair_serials else serials,
                ),
            }
        elif normalized_mode == "Non-bonded":
            self._highlight_nonbonded_pair(highlights, seen, serials)
            interaction = {
                "mode": normalized_mode,
                "nonbonded": self._extract_nonbonded_params(serials),
            }
        return highlights, interaction

    def _get_int_section(self, name: str, section: Parm7Section) -> List[int]:
        cached = self._int_cache.get(name)
        if cached is not None:
            return cached
        values = parse_int_tokens(section.tokens)
        self._int_cache[name] = values
        return values

    def _get_atom_type_index(self, serial: int) -> Optional[int]:
        meta = self._meta_by_serial.get(int(serial))
        if not meta:
            return None
        value = meta.parm7.get("atom_type_index")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _highlight_atom_lj(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serial: int,
    ) -> None:
        type_index = self._get_atom_type_index(serial)
        if not type_index:
            return
        section = self._sections.get("NONBONDED_PARM_INDEX")
        if not section or not section.tokens:
            return
        values = self._get_int_section("NONBONDED_PARM_INDEX", section)
        if not values:
            return
        ntypes = self._get_ntypes(values)
        if not ntypes:
            return
        index = (int(type_index) - 1) * ntypes + (int(type_index) - 1)
        if index < 0 or index >= len(values):
            return
        nb_index = values[index]
        if nb_index > 0:
            self._add_param_highlight(
                highlights, seen, "LENNARD_JONES_ACOEF", nb_index
            )
        elif nb_index < 0:
            self._add_param_highlight(
                highlights, seen, "HBOND_ACOEF", abs(nb_index)
            )

    def _get_float_section(self, name: str, section: Parm7Section) -> List[float]:
        cached = self._float_cache.get(name)
        if cached is not None:
            return cached
        values = parse_float_tokens(section.tokens)
        self._float_cache[name] = values
        return values

    @staticmethod
    def _pointer_to_serial(value: int) -> int:
        return abs(value) // 3 + 1

    @staticmethod
    def _match_triplet(a: int, b: int, c: int, serials: Sequence[int]) -> bool:
        if len(serials) < 3:
            return False
        return (a == serials[0] and b == serials[1] and c == serials[2]) or (
            a == serials[2] and b == serials[1] and c == serials[0]
        )

    @staticmethod
    def _match_triplet_unordered(a: int, b: int, c: int, serials: Sequence[int]) -> bool:
        if len(serials) < 3:
            return False
        return sorted((a, b, c)) == sorted(serials[:3])

    @staticmethod
    def _match_quad(a: int, b: int, c: int, d: int, serials: Sequence[int]) -> bool:
        if len(serials) < 4:
            return False
        return (a, b, c, d) == tuple(serials[:4]) or (d, c, b, a) == tuple(serials[:4])

    @staticmethod
    def _match_quad_unordered(
        a: int, b: int, c: int, d: int, serials: Sequence[int]
    ) -> bool:
        if len(serials) < 4:
            return False
        return sorted((a, b, c, d)) == sorted(serials[:4])

    def _get_bond_adjacency(self) -> Dict[int, set[int]]:
        if self._bond_adjacency is not None:
            return self._bond_adjacency
        adjacency: Dict[int, set[int]] = {}
        for name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 2, 3):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                adjacency.setdefault(atom_a, set()).add(atom_b)
                adjacency.setdefault(atom_b, set()).add(atom_a)
        self._bond_adjacency = adjacency
        return adjacency

    @staticmethod
    def _order_improper(central: int, serials: Sequence[int]) -> List[int]:
        others: List[int] = []
        for value in serials:
            try:
                serial = int(value)
            except (TypeError, ValueError):
                continue
            if serial == central:
                continue
            others.append(serial)
        others.sort()
        return [int(central)] + others

    def _infer_improper_central(self, serials: Sequence[int]) -> Optional[int]:
        if len(serials) < 4:
            return None
        adjacency = self._get_bond_adjacency()
        if not adjacency:
            return None
        clean: List[int] = []
        for value in serials[:4]:
            try:
                clean.append(int(value))
            except (TypeError, ValueError):
                return None
        candidates: List[int] = []
        for candidate in clean:
            neighbors = adjacency.get(candidate, set())
            if all(other in neighbors for other in clean if other != candidate):
                candidates.append(candidate)
        return min(candidates) if candidates else None

    def _is_improper_record(
        self, central: int, record_serials: Sequence[int]
    ) -> bool:
        adjacency = self._get_bond_adjacency()
        if not adjacency:
            return False
        neighbors = adjacency.get(int(central), set())
        return all(
            int(other) in neighbors for other in record_serials if int(other) != int(central)
        )

    def _add_highlight(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        section: Parm7Section,
        token_index: int,
    ) -> None:
        if token_index < 0 or token_index >= len(section.tokens):
            return
        token = section.tokens[token_index]
        key = (token.line, token.start, token.end)
        if key in seen:
            return
        seen.add(key)
        highlights.append(
            {"line": token.line, "start": token.start, "end": token.end, "section": section.name}
        )

    def _add_param_highlight(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        section_name: str,
        param_index: int,
    ) -> None:
        if param_index <= 0:
            return
        section = self._sections.get(section_name)
        if not section:
            return
        self._add_highlight(highlights, seen, section, param_index - 1)

    def _get_param_value(
        self,
        section_name: str,
        param_index: int,
    ) -> Optional[float]:
        if param_index <= 0:
            return None
        section = self._sections.get(section_name)
        if not section:
            return None
        values = self._get_float_section(section_name, section)
        index = param_index - 1
        if index < 0 or index >= len(values):
            return None
        return values[index]

    def _get_ntypes(
        self, values: Sequence[int]
    ) -> Optional[int]:
        if not values:
            return None
        ntypes = int(math.sqrt(len(values)))
        if ntypes > 0 and ntypes * ntypes == len(values):
            return ntypes
        acoef_section = self._sections.get("LENNARD_JONES_ACOEF")
        if not acoef_section:
            return None
        acoef_count = len(acoef_section.tokens)
        if acoef_count <= 0:
            return None
        estimate = int((math.sqrt(8 * acoef_count + 1) - 1) / 2)
        if estimate > 0 and estimate * (estimate + 1) // 2 == acoef_count:
            return estimate
        return None

    def _nonbond_index(
        self, values: Sequence[int], ntypes: int, type_a: int, type_b: int
    ) -> Optional[Tuple[int, int]]:
        idx = (type_a - 1) * ntypes + (type_b - 1)
        if idx < 0 or idx >= len(values):
            return None
        return idx, int(values[idx])

    def _extract_bond_params(
        self, serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 2:
            return []
        target = {int(serials[0]), int(serials[1])}
        results: List[Dict[str, object]] = []
        for name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 2, 3):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                if {atom_a, atom_b} != target:
                    continue
                param_index = abs(values[idx + 2])
                type_a = self._get_atom_type_index(atom_a)
                type_b = self._get_atom_type_index(atom_b)
                results.append(
                    {
                        "serials": [atom_a, atom_b],
                        "param_index": param_index,
                        "type_indices": (
                            [type_a, type_b]
                            if type_a is not None and type_b is not None
                            else None
                        ),
                        "force_constant": self._get_param_value(
                            "BOND_FORCE_CONSTANT", param_index
                        ),
                        "equil_value": self._get_param_value(
                            "BOND_EQUIL_VALUE", param_index
                        ),
                    }
                )
        return results

    def _extract_angle_params(
        self, serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 3:
            return []
        results: List[Dict[str, object]] = []
        ordered_found = False
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet(atom_a, atom_b, atom_c, serials):
                    continue
                ordered_found = True
                param_index = abs(values[idx + 3])
                type_a = self._get_atom_type_index(atom_a)
                type_b = self._get_atom_type_index(atom_b)
                type_c = self._get_atom_type_index(atom_c)
                results.append(
                    {
                        "serials": [atom_a, atom_b, atom_c],
                        "param_index": param_index,
                        "type_indices": (
                            [type_a, type_b, type_c]
                            if type_a is not None
                            and type_b is not None
                            and type_c is not None
                            else None
                        ),
                        "force_constant": self._get_param_value(
                            "ANGLE_FORCE_CONSTANT", param_index
                        ),
                        "equil_value": self._get_param_value(
                            "ANGLE_EQUIL_VALUE", param_index
                        ),
                    }
                )
        if ordered_found or results:
            return results
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet_unordered(atom_a, atom_b, atom_c, serials):
                    continue
                param_index = abs(values[idx + 3])
                type_a = self._get_atom_type_index(atom_a)
                type_b = self._get_atom_type_index(atom_b)
                type_c = self._get_atom_type_index(atom_c)
                results.append(
                    {
                        "serials": [atom_a, atom_b, atom_c],
                        "param_index": param_index,
                        "type_indices": (
                            [type_a, type_b, type_c]
                            if type_a is not None
                            and type_b is not None
                            and type_c is not None
                            else None
                        ),
                        "force_constant": self._get_param_value(
                            "ANGLE_FORCE_CONSTANT", param_index
                        ),
                        "equil_value": self._get_param_value(
                            "ANGLE_EQUIL_VALUE", param_index
                        ),
                    }
                )
        return results

    def _extract_dihedral_params(
        self, serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 4:
            return []
        results: List[Dict[str, object]] = []
        ordered_found = False
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if not self._match_quad(atom_i, atom_j, atom_k, atom_l, serials):
                    continue
                ordered_found = True
                param_index = abs(raw_param)
                results.append(
                    {
                        "serials": [atom_i, atom_j, atom_k, atom_l],
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            "DIHEDRAL_FORCE_CONSTANT", param_index
                        ),
                        "periodicity": self._get_param_value(
                            "DIHEDRAL_PERIODICITY", param_index
                        ),
                        "phase": self._get_param_value(
                            "DIHEDRAL_PHASE", param_index
                        ),
                        "scee": self._get_param_value(
                            "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        if ordered_found or results:
            return results
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if not self._match_quad_unordered(
                    atom_i, atom_j, atom_k, atom_l, serials
                ):
                    continue
                param_index = abs(raw_param)
                results.append(
                    {
                        "serials": [atom_i, atom_j, atom_k, atom_l],
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            "DIHEDRAL_FORCE_CONSTANT", param_index
                        ),
                        "periodicity": self._get_param_value(
                            "DIHEDRAL_PERIODICITY", param_index
                        ),
                        "phase": self._get_param_value(
                            "DIHEDRAL_PHASE", param_index
                        ),
                        "scee": self._get_param_value(
                            "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        return results

    def _extract_improper_params(
        self, serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 4:
            return []
        central = self._infer_improper_central(serials)
        if central is None:
            return []
        ordered = self._order_improper(central, serials[:4])
        target_set = {int(value) for value in ordered}
        results: List[Dict[str, object]] = []
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                record = [atom_i, atom_j, atom_k, atom_l]
                if target_set != set(record):
                    continue
                if not self._is_improper_record(central, record):
                    continue
                param_index = abs(raw_param)
                results.append(
                    {
                        "serials": ordered,
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            "DIHEDRAL_FORCE_CONSTANT", param_index
                        ),
                        "periodicity": self._get_param_value(
                            "DIHEDRAL_PERIODICITY", param_index
                        ),
                        "phase": self._get_param_value(
                            "DIHEDRAL_PHASE", param_index
                        ),
                        "scee": self._get_param_value(
                            "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        return results

    def _extract_14_params(
        self, serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 2:
            return []
        target = {int(serials[0]), int(serials[1])}
        results: List[Dict[str, object]] = []
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                if raw_k < 0 or raw_l < 0:
                    continue
                atom_i = self._pointer_to_serial(raw_i)
                atom_l = self._pointer_to_serial(raw_l)
                if {atom_i, atom_l} != target:
                    continue
                param_index = abs(raw_param)
                type_i = self._get_atom_type_index(atom_i)
                type_l = self._get_atom_type_index(atom_l)
                results.append(
                    {
                        "serials": [atom_i, atom_l],
                        "param_index": param_index,
                        "type_indices": (
                            [type_i, type_l]
                            if type_i is not None and type_l is not None
                            else None
                        ),
                        "scee": self._get_param_value(
                            "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        return results

    def _extract_nonbonded_params(
        self,
        serials: Sequence[int],
    ) -> Optional[Dict[str, object]]:
        if len(serials) < 2:
            return None
        meta_a = self._meta_by_serial.get(int(serials[0]))
        meta_b = self._meta_by_serial.get(int(serials[1]))
        if not meta_a or not meta_b:
            return None
        type_a = meta_a.parm7.get("atom_type_index")
        type_b = meta_b.parm7.get("atom_type_index")
        if not type_a or not type_b:
            return None
        section = self._sections.get("NONBONDED_PARM_INDEX")
        if not section or not section.tokens:
            return None
        values = self._get_int_section("NONBONDED_PARM_INDEX", section)
        if not values:
            return None
        ntypes = self._get_ntypes(values)
        if not ntypes:
            return None
        primary = self._nonbond_index(values, ntypes, int(type_a), int(type_b))
        secondary = self._nonbond_index(values, ntypes, int(type_b), int(type_a))
        nb_index = primary[1] if primary else 0
        if nb_index == 0 and secondary:
            nb_index = secondary[1]
        acoef = None
        bcoef = None
        rmin = None
        epsilon = None
        if nb_index > 0:
            acoef = self._get_param_value("LENNARD_JONES_ACOEF", nb_index)
            bcoef = self._get_param_value("LENNARD_JONES_BCOEF", nb_index)
            if acoef and bcoef:
                epsilon = (bcoef * bcoef) / (4.0 * acoef)
                rmin = pow(2.0 * acoef / bcoef, 1.0 / 6.0)
        return {
            "serials": [int(serials[0]), int(serials[1])],
            "type_indices": [int(type_a), int(type_b)],
            "nb_index": nb_index,
            "acoef": acoef,
            "bcoef": bcoef,
            "rmin": rmin,
            "epsilon": epsilon,
        }

    def _highlight_nonbonded_pair(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
        pairs: Optional[Sequence[Sequence[int]]] = None,
    ) -> None:
        if len(serials) < 2 and not pairs:
            return
        section = self._sections.get("NONBONDED_PARM_INDEX")
        if not section or not section.tokens:
            return
        values = self._get_int_section("NONBONDED_PARM_INDEX", section)
        if not values:
            return
        ntypes = self._get_ntypes(values)
        if not ntypes:
            return
        serial_pairs = pairs or [serials[:2]]
        nb_indices: set = set()
        for pair in serial_pairs:
            if len(pair) < 2:
                continue
            meta_a = self._meta_by_serial.get(int(pair[0]))
            meta_b = self._meta_by_serial.get(int(pair[1]))
            if not meta_a or not meta_b:
                continue
            type_a = meta_a.parm7.get("atom_type_index")
            type_b = meta_b.parm7.get("atom_type_index")
            if not type_a or not type_b:
                continue
            candidates = [
                self._nonbond_index(values, ntypes, int(type_a), int(type_b)),
                self._nonbond_index(values, ntypes, int(type_b), int(type_a)),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                idx, nb_index = candidate
                self._add_highlight(highlights, seen, section, idx)
                if nb_index != 0:
                    nb_indices.add(nb_index)
        for nb_index in nb_indices:
            if nb_index > 0:
                self._add_param_highlight(
                    highlights, seen, "LENNARD_JONES_ACOEF", nb_index
                )
                self._add_param_highlight(
                    highlights, seen, "LENNARD_JONES_BCOEF", nb_index
                )
            else:
                hb_index = abs(nb_index)
                self._add_param_highlight(
                    highlights, seen, "HBOND_ACOEF", hb_index
                )
                self._add_param_highlight(
                    highlights, seen, "HBOND_BCOEF", hb_index
                )
                hbc_section = self._sections.get("HBCUT")
                if hbc_section and hbc_section.tokens:
                    self._add_highlight(highlights, seen, hbc_section, 0)

    def _highlight_bond_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 2:
            return
        target = {int(serials[0]), int(serials[1])}
        for name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 2, 3):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                if {atom_a, atom_b} != target:
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                param_index = abs(values[idx + 2])
                self._add_param_highlight(
                    highlights, seen, "BOND_FORCE_CONSTANT", param_index
                )
                self._add_param_highlight(
                    highlights, seen, "BOND_EQUIL_VALUE", param_index
                )

    def _highlight_angle_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 3:
            return
        ordered_found = False
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet(atom_a, atom_b, atom_c, serials):
                    continue
                ordered_found = True
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                param_index = abs(values[idx + 3])
                self._add_param_highlight(
                    highlights, seen, "ANGLE_FORCE_CONSTANT", param_index
                )
                self._add_param_highlight(
                    highlights, seen, "ANGLE_EQUIL_VALUE", param_index
                )
        if ordered_found:
            return
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet_unordered(atom_a, atom_b, atom_c, serials):
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                param_index = abs(values[idx + 3])
                self._add_param_highlight(
                    highlights, seen, "ANGLE_FORCE_CONSTANT", param_index
                )
                self._add_param_highlight(
                    highlights, seen, "ANGLE_EQUIL_VALUE", param_index
                )

    def _highlight_dihedral_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
        require_14: Optional[bool] = None,
    ) -> None:
        if len(serials) < 4:
            return
        ordered_found = False
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if require_14 is not None:
                    if require_14 and (raw_k < 0 or raw_l < 0):
                        continue
                    if not require_14 and raw_k < 0:
                        continue
                if not self._match_quad(atom_i, atom_j, atom_k, atom_l, serials):
                    continue
                ordered_found = True
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in (
                    "DIHEDRAL_FORCE_CONSTANT",
                    "DIHEDRAL_PERIODICITY",
                    "DIHEDRAL_PHASE",
                    "SCEE_SCALE_FACTOR",
                    "SCNB_SCALE_FACTOR",
                ):
                    self._add_param_highlight(
                        highlights, seen, param_section, param_index
                    )
        if ordered_found:
            return
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if require_14 is not None:
                    if require_14 and (raw_k < 0 or raw_l < 0):
                        continue
                    if not require_14 and raw_k < 0:
                        continue
                if not self._match_quad_unordered(
                    atom_i, atom_j, atom_k, atom_l, serials
                ):
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in (
                    "DIHEDRAL_FORCE_CONSTANT",
                    "DIHEDRAL_PERIODICITY",
                    "DIHEDRAL_PHASE",
                    "SCEE_SCALE_FACTOR",
                    "SCNB_SCALE_FACTOR",
                ):
                    self._add_param_highlight(
                        highlights, seen, param_section, param_index
                    )

    def _highlight_improper_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 4:
            return
        central = self._infer_improper_central(serials)
        if central is None:
            return
        ordered = self._order_improper(central, serials[:4])
        target_set = {int(value) for value in ordered}
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                record = [atom_i, atom_j, atom_k, atom_l]
                if target_set != set(record):
                    continue
                if not self._is_improper_record(central, record):
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in (
                    "DIHEDRAL_FORCE_CONSTANT",
                    "DIHEDRAL_PERIODICITY",
                    "DIHEDRAL_PHASE",
                    "SCEE_SCALE_FACTOR",
                    "SCNB_SCALE_FACTOR",
                ):
                    self._add_param_highlight(
                        highlights, seen, param_section, param_index
                    )

    def _highlight_14_pairs(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 2:
            return
        target = {int(serials[0]), int(serials[1])}
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = self._sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                if raw_k < 0 or raw_l < 0:
                    continue
                atom_i = self._pointer_to_serial(raw_i)
                atom_l = self._pointer_to_serial(raw_l)
                if {atom_i, atom_l} != target:
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in ("SCEE_SCALE_FACTOR", "SCNB_SCALE_FACTOR"):
                    self._add_param_highlight(
                        highlights, seen, param_section, param_index
                    )
