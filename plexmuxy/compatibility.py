"""Standardized environment compatibility requirements for settings.

Some settings only make sense with certain external tool versions.  Rather than
scattering ad-hoc version checks throughout the codebase, every setting (or
setting *value*) declares its requirements in one place using a compact,
standardized notation::

    "<tool><operator><version>"

For example ``"mkvmerge>=66"`` means the option requires mkvmerge v66 or newer.
Supported operators are ``>=``, ``>``, ``<=``, ``<`` and ``==``; the version is a
dotted numeric string with an optional leading ``v`` (``66``, ``v66``, ``66.0.0``).

``SETTING_COMPATIBILITY`` maps a stable *setting id* -- a dotted path mirroring
the config location, optionally suffixed with the option value it applies to --
to a tuple of requirement strings.  All requirements for an id must be satisfied
for the option to be considered available (logical AND).

``evaluate_compatibility`` takes the detected tool versions and produces a plain
data report that the GUI (or any other frontend) consumes to enable/disable the
matching controls.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Requirement",
    "SETTING_COMPATIBILITY",
    "evaluate_compatibility",
    "parse_requirement",
    "parse_version",
]


_REQUIREMENT_PATTERN = re.compile(
    r"^\s*(?P<tool>[A-Za-z][\w-]*)\s*(?P<operator>>=|<=|==|>|<)\s*"
    r"v?(?P<version>\d+(?:\.\d+)*)\s*$"
)

_OPERATOR_SYMBOL = {">=": "\u2265", "<=": "\u2264", "==": "=", ">": ">", "<": "<"}


def parse_version(value: Any) -> tuple[int, ...] | None:
    """Extract a numeric version tuple from an arbitrary version string.

    Returns ``None`` when no leading numeric version can be found (e.g. the tool
    is missing or reports an unparseable string).
    """

    if value is None:
        return None
    match = re.match(r"^\s*[vV]?(\d+(?:\.\d+)*)", str(value).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    length = max(len(left), len(right))
    padded_left = tuple(left) + (0,) * (length - len(left))
    padded_right = tuple(right) + (0,) * (length - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


@dataclass(frozen=True, slots=True)
class Requirement:
    """A single, standardized version requirement (e.g. ``mkvmerge>=66``)."""

    tool: str
    operator: str
    version: tuple[int, ...]
    raw: str

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)

    def is_satisfied_by(self, detected: tuple[int, ...] | None) -> bool:
        """Return whether ``detected`` satisfies this requirement.

        An unknown (``None``) detected version is given the benefit of the doubt
        so that a failed probe never silently hides a setting.
        """

        if detected is None:
            return True
        result = _compare(detected, self.version)
        if self.operator == ">=":
            return result >= 0
        if self.operator == ">":
            return result > 0
        if self.operator == "<=":
            return result <= 0
        if self.operator == "<":
            return result < 0
        return result == 0

    def describe(self) -> str:
        """Human-readable form, e.g. ``mkvmerge \u2265 66``."""

        return f"{self.tool} {_OPERATOR_SYMBOL[self.operator]} {self.version_text}"


def parse_requirement(text: str) -> Requirement:
    """Parse a standardized requirement string into a :class:`Requirement`."""

    match = _REQUIREMENT_PATTERN.match(str(text))
    if not match:
        raise ValueError(f"Invalid compatibility requirement: {text!r}")
    version = tuple(int(part) for part in match.group("version").split("."))
    return Requirement(
        tool=match.group("tool").casefold(),
        operator=match.group("operator"),
        version=version,
        raw=str(text).strip(),
    )


# Registry of setting ids -> required tool versions.
#
# Add new entries here as settings gain version-specific behavior.  The id is a
# dotted path; when a requirement only applies to one option value, suffix the id
# with that value (e.g. ``font.mime_mode.modern``).
SETTING_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    # Modern font MIME types (font/ttf, font/otf, font/collection) are only
    # emitted correctly by mkvmerge v66 and newer.
    "font.mime_mode.modern": ("mkvmerge>=66",),
}


def evaluate_compatibility(
    versions: Mapping[str, str | None] | None,
) -> dict[str, dict[str, Any]]:
    """Evaluate every registered setting against the detected tool versions.

    ``versions`` maps tool names to their raw version strings (as reported by the
    dependency inspection, e.g. ``{"mkvmerge": "66.0.0"}``).  The return value is
    a JSON-serializable report keyed by setting id::

        {
          "font.mime_mode.modern": {
            "satisfied": False,
            "requirements": [
              {"tool": "mkvmerge", "operator": ">=", "version": "66",
               "raw": "mkvmerge>=66", "describe": "mkvmerge \u2265 66",
               "detected": "65.0.0", "satisfied": False},
            ],
            "unmet": ["mkvmerge>=66"],
            "unmet_describe": ["mkvmerge \u2265 66"],
          }
        }
    """

    detected: dict[str, tuple[int, ...] | None] = {
        str(tool).casefold(): parse_version(value)
        for tool, value in dict(versions or {}).items()
    }

    report: dict[str, dict[str, Any]] = {}
    for setting_id, requirement_specs in SETTING_COMPATIBILITY.items():
        entries: list[dict[str, Any]] = []
        satisfied = True
        for spec in requirement_specs:
            requirement = parse_requirement(spec)
            tool_version = detected.get(requirement.tool)
            ok = requirement.is_satisfied_by(tool_version)
            satisfied = satisfied and ok
            entries.append(
                {
                    "tool": requirement.tool,
                    "operator": requirement.operator,
                    "version": requirement.version_text,
                    "raw": requirement.raw,
                    "describe": requirement.describe(),
                    "detected": (
                        ".".join(str(part) for part in tool_version)
                        if tool_version is not None
                        else None
                    ),
                    "satisfied": ok,
                }
            )
        report[setting_id] = {
            "satisfied": satisfied,
            "requirements": entries,
            "unmet": [entry["raw"] for entry in entries if not entry["satisfied"]],
            "unmet_describe": [
                entry["describe"] for entry in entries if not entry["satisfied"]
            ],
        }
    return report
