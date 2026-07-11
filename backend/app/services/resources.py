"""Compute the CPU/RAM footprint of a Ludus range config.

The single source of truth for "how much does this cost". Every VM in a
Ludus range config declares its own ``cpus`` and ``ram_gb``; the resource
cost of a range is simply the sum across its ``ludus:`` VM list. Sessions
then multiply that per-range cost by how many ranges they deploy:

* ``shared``    -> exactly one range is deployed (the lead student's), so
  the session demand equals the per-range cost regardless of headcount.
* ``dedicated`` -> one range per student, so demand is
  ``student_count * per-range cost``.

This module is deliberately pure (no DB, no FastAPI) so it can be reused by
provisioning (quota enforcement), the labs service (per-range cap), and the
quota preflight endpoint alike.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from app.models.session import SessionMode


@dataclass(frozen=True)
class RangeResources:
    """Aggregate CPU/RAM/VM totals for a range (or a whole session)."""

    cpus: int = 0
    ram_gb: int = 0
    vm_count: int = 0

    def __add__(self, other: RangeResources) -> RangeResources:
        return RangeResources(
            cpus=self.cpus + other.cpus,
            ram_gb=self.ram_gb + other.ram_gb,
            vm_count=self.vm_count + other.vm_count,
        )

    def scaled(self, factor: int) -> RangeResources:
        """Return these resources multiplied by an integer ``factor``."""
        return RangeResources(
            cpus=self.cpus * factor,
            ram_gb=self.ram_gb * factor,
            vm_count=self.vm_count * factor,
        )


def _coerce_int(value: object) -> int:
    """Best-effort convert a YAML scalar to a non-negative int (0 on failure).

    Range configs are hand-written YAML; ``cpus``/``ram_gb`` are normally
    plain ints but may arrive as strings ("4") or be missing. We never want
    a malformed field to crash a cost computation, so unparseable values
    contribute 0 rather than raising.
    """
    if isinstance(value, bool):  # bool is an int subclass; treat as absent
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(float(value.strip())), 0)
        except (ValueError, TypeError):
            return 0
    return 0


def compute_range_resources(range_config_yaml: str) -> RangeResources:
    """Sum ``cpus`` and ``ram_gb`` across the VMs in a range config.

    Returns a zeroed :class:`RangeResources` when the YAML is invalid, is
    not a mapping, or has no ``ludus:`` list - callers decide whether an
    empty footprint is acceptable. Jinja placeholders (e.g. ``{{ range_id }}``)
    only ever appear in string fields, so ``yaml.safe_load`` parses the
    numeric ``cpus``/``ram_gb`` fields without issue.
    """
    try:
        data = yaml.safe_load(range_config_yaml)
    except yaml.YAMLError:
        return RangeResources()
    if not isinstance(data, dict):
        return RangeResources()

    vms = data.get("ludus")
    if not isinstance(vms, list):
        return RangeResources()

    total = RangeResources()
    for vm in vms:
        if not isinstance(vm, dict):
            continue
        total = total + RangeResources(
            cpus=_coerce_int(vm.get("cpus")),
            ram_gb=_coerce_int(vm.get("ram_gb")),
            vm_count=1,
        )
    return total


def compute_session_demand(
    per_range: RangeResources,
    mode: SessionMode,
    student_count: int,
) -> RangeResources:
    """Scale a per-range cost to a session's total footprint.

    ``shared`` deploys a single range no matter how many students enrol;
    ``dedicated`` deploys one range per student. A session with zero
    students has zero demand.
    """
    if student_count <= 0:
        return RangeResources()
    if mode == SessionMode.shared:
        return per_range.scaled(1)
    return per_range.scaled(student_count)


__all__ = [
    "RangeResources",
    "compute_range_resources",
    "compute_session_demand",
]
