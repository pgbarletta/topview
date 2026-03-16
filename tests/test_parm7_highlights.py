from topview.model.highlights import HighlightEngine
from topview.model.state import AtomMeta, Parm7Section, Parm7Token, ResidueMeta


def _make_section(name: str, values: list[object], line_offset: int) -> Parm7Section:
    tokens = [
        Parm7Token(
            value=str(value),
            line=line_offset + idx,
            start=0,
            end=len(str(value)),
        )
        for idx, value in enumerate(values)
    ]
    return Parm7Section(
        name=name,
        count=1,
        width=max((len(token.value) for token in tokens), default=1),
        flag_line=max(0, line_offset - 1),
        end_line=line_offset + max(0, len(tokens) - 1),
        tokens=tokens,
    )


def _make_meta_by_serial(type_indices: list[int]) -> dict[int, AtomMeta]:
    residue = ResidueMeta(resid=1, resname="TST")
    meta_by_serial: dict[int, AtomMeta] = {}
    for idx, type_index in enumerate(type_indices, start=1):
        meta_by_serial[idx] = AtomMeta(
            serial=idx,
            atom_name=f"A{idx}",
            element="C",
            residue=residue,
            residue_index=1,
            coords=(float(idx), 0.0, 0.0),
            parm7={"atom_type_index": type_index},
        )
    return meta_by_serial


def _section_names(highlights: list[dict[str, object]]) -> set[str]:
    return {
        str(entry["section"])
        for entry in highlights
        if entry.get("section") is not None
    }


def test_improper_highlights_include_record_and_parameter_sections() -> None:
    sections = {
        "DIHEDRALS_INC_HYDROGEN": _make_section(
            "DIHEDRALS_INC_HYDROGEN", [0, 3, 6, -9, 1], 10
        ),
        "DIHEDRAL_FORCE_CONSTANT": _make_section("DIHEDRAL_FORCE_CONSTANT", [1.5], 30),
        "DIHEDRAL_PERIODICITY": _make_section("DIHEDRAL_PERIODICITY", [2.0], 40),
        "DIHEDRAL_PHASE": _make_section("DIHEDRAL_PHASE", [180.0], 50),
    }
    engine = HighlightEngine(
        sections,
        _make_meta_by_serial([1, 1, 1, 1]),
        int_cache={},
        float_cache={},
    )

    highlights, interaction = engine.get_highlights([1, 2, 3, 4], mode="Improper")
    section_names = _section_names(highlights)

    assert "DIHEDRALS_INC_HYDROGEN" in section_names
    assert "DIHEDRAL_FORCE_CONSTANT" in section_names
    assert "DIHEDRAL_PERIODICITY" in section_names
    assert "DIHEDRAL_PHASE" in section_names
    assert interaction is not None
    assert interaction["mode"] == "Improper"


def test_dihedral_highlights_include_term_and_parameter_sections() -> None:
    sections = {
        "DIHEDRALS_WITHOUT_HYDROGEN": _make_section(
            "DIHEDRALS_WITHOUT_HYDROGEN", [0, 3, 6, 9, 1], 100
        ),
        "DIHEDRAL_FORCE_CONSTANT": _make_section("DIHEDRAL_FORCE_CONSTANT", [0.25], 120),
        "DIHEDRAL_PERIODICITY": _make_section("DIHEDRAL_PERIODICITY", [3.0], 130),
        "DIHEDRAL_PHASE": _make_section("DIHEDRAL_PHASE", [0.0], 140),
    }
    engine = HighlightEngine(
        sections,
        _make_meta_by_serial([1, 2, 3, 4]),
        int_cache={},
        float_cache={},
    )

    highlights, interaction = engine.get_highlights([1, 2, 3, 4], mode="Dihedral")
    section_names = _section_names(highlights)

    assert "DIHEDRALS_WITHOUT_HYDROGEN" in section_names
    assert "DIHEDRAL_FORCE_CONSTANT" in section_names
    assert "DIHEDRAL_PERIODICITY" in section_names
    assert "DIHEDRAL_PHASE" in section_names
    assert interaction is not None
    assert interaction["mode"] == "Dihedral"


def test_one_four_highlights_include_dihedral_record_and_scaling_sections() -> None:
    sections = {
        "DIHEDRALS_WITHOUT_HYDROGEN": _make_section(
            "DIHEDRALS_WITHOUT_HYDROGEN", [0, 3, 6, 9, 1], 200
        ),
        "SCEE_SCALE_FACTOR": _make_section("SCEE_SCALE_FACTOR", [1.2], 220),
        "SCNB_SCALE_FACTOR": _make_section("SCNB_SCALE_FACTOR", [2.0], 230),
    }
    engine = HighlightEngine(
        sections,
        _make_meta_by_serial([1, 2, 3, 4]),
        int_cache={},
        float_cache={},
    )

    highlights, interaction = engine.get_highlights([1, 4], mode="1-4 Nonbonded")
    section_names = _section_names(highlights)

    assert "DIHEDRALS_WITHOUT_HYDROGEN" in section_names
    assert "SCEE_SCALE_FACTOR" in section_names
    assert "SCNB_SCALE_FACTOR" in section_names
    assert interaction is not None
    assert interaction["mode"] == "1-4 Nonbonded"
