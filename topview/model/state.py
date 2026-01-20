"""Dataclasses for model state and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from concurrent.futures import Future


@dataclass(frozen=True)
class ResidueMeta:
    """Metadata describing a residue.

    Attributes
    ----------
    resid
        Residue id.
    resname
        Residue name.
    segid
        Segment id.
    chain
        Chain identifier.
    """

    resid: int
    resname: str
    segid: Optional[str] = None
    chain: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        """Serialize residue metadata for the bridge.

        Returns
        -------
        dict
            JSON-ready residue metadata.
        """
        return {
            "resid": self.resid,
            "resname": self.resname,
            "segid": self.segid,
            "chain": self.chain,
        }


@dataclass(frozen=True)
class AtomMeta:
    """Metadata describing an atom.

    Attributes
    ----------
    serial
        1-based atom serial.
    atom_name
        Atom name.
    element
        Element symbol.
    residue
        Residue metadata.
    residue_index
        1-based residue index in the topology.
    coords
        Cartesian coordinates.
    parm7
        Parm7-derived metadata.
    """

    serial: int
    atom_name: str
    element: Optional[str]
    residue: ResidueMeta
    residue_index: int
    coords: Tuple[float, float, float]
    parm7: Dict[str, Optional[object]]

    def to_dict(self) -> Dict[str, object]:
        """Serialize atom metadata for the bridge.

        Returns
        -------
        dict
            JSON-ready atom metadata.
        """
        return {
            "serial": self.serial,
            "atom_name": self.atom_name,
            "element": self.element,
            "residue": self.residue.to_dict(),
            "coords": {"x": self.coords[0], "y": self.coords[1], "z": self.coords[2]},
            "parm7": self.parm7,
        }


@dataclass(frozen=True)
class Parm7Token:
    """Token metadata for a parm7 field.

    Attributes
    ----------
    value
        Raw token value.
    line
        Line index in the parm7 file.
    start
        Start character offset.
    end
        End character offset.
    """

    value: str
    line: int
    start: int
    end: int


@dataclass(frozen=True)
class Parm7Section:
    """Parsed parm7 section metadata.

    Attributes
    ----------
    name
        Section flag name.
    count
        Token count per line.
    width
        Token width.
    flag_line
        Line index of the %FLAG line.
    end_line
        Line index of the last line in the section.
    tokens
        Parsed tokens for the section.
    """

    name: str
    count: int
    width: int
    flag_line: int
    end_line: int
    tokens: List[Parm7Token]


@dataclass
class ModelState:
    """Mutable model state shared across API calls.

    Attributes
    ----------
    meta_by_serial
        Atom metadata keyed by serial.
    meta_list
        Atom metadata in serial order.
    residue_keys_by_resid
        Mapping of resid to residue keys.
    residue_index
        Mapping of residue key to atom serials.
    parm7_text_b64
        Base64-encoded parm7 text.
    parm7_sections
        Parsed parm7 sections keyed by flag.
    int_section_cache
        Cached integer section values.
    float_section_cache
        Cached float section values.
    system_info
        Cached system info tables payload.
    system_info_future
        Background future for system info table generation.
    load_timings
        Timing breakdown for the last load.
    load_started_at
        Perf counter timestamp when the last load started.
    loaded
        Whether a system is currently loaded.
    """

    meta_by_serial: Dict[int, AtomMeta] = field(default_factory=dict)
    meta_list: List[AtomMeta] = field(default_factory=list)
    residue_keys_by_resid: Dict[int, List[str]] = field(default_factory=dict)
    residue_index: Dict[str, List[int]] = field(default_factory=dict)
    parm7_text_b64: Optional[str] = None
    parm7_sections: Dict[str, Parm7Section] = field(default_factory=dict)
    int_section_cache: Dict[str, List[int]] = field(default_factory=dict)
    float_section_cache: Dict[str, List[float]] = field(default_factory=dict)
    system_info: Optional[Dict[str, Dict[str, object]]] = None
    system_info_future: Optional[Future] = None
    load_timings: Optional[Dict[str, float]] = None
    load_started_at: Optional[float] = None
    loaded: bool = False
