from typing import Iterable, List


class PdbWriterError(Exception):
    pass


def _format_atom_name(name: str) -> str:
    name = (name or "").strip()
    if len(name) > 4:
        return name[:4]
    return name.rjust(4)


def _format_resname(resname: str) -> str:
    resname = (resname or "").strip()
    if len(resname) > 3:
        return resname[:3]
    return resname.ljust(3)


def _format_element(element: str) -> str:
    element = (element or "").strip()
    if not element:
        return "  "
    if len(element) == 1:
        return f" {element.upper()}"
    return element[0].upper() + element[1].lower()


def write_pdb(atom_metas: Iterable[object]) -> str:
    lines: List[str] = []
    for meta in atom_metas:
        serial = int(meta.serial)
        name = _format_atom_name(meta.atom_name)
        resname = _format_resname(meta.residue.resname)
        chain = (meta.residue.chain or " ")[:1]
        resid = int(meta.residue.resid)
        x, y, z = meta.coords
        occ = 1.00
        temp = 0.00
        element = _format_element(meta.element)

        line = (
            f"ATOM  "
            f"{serial:5d} "
            f"{name}"
            f" "
            f"{resname} "
            f"{chain}"
            f"{resid:4d}"
            f"    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}"
            f"{occ:6.2f}{temp:6.2f}"
            f"          "
            f"{element:>2}"
        )
        lines.append(line)
    lines.append("END")
    return "\n".join(lines) + "\n"
