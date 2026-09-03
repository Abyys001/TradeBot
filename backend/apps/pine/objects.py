"""The runtime value model for user-defined types and enums.

Two shapes live here, and neither is a ``ta.*`` indicator or a ``Series`` — they
are plain values a variable holds, the same way a ``Decimal`` or a ``str`` is.

  **``PineObject``** is an instance of a ``type`` declaration: a ``type_name``
  and a ``fields`` dict. Assigned **by reference** (``objects.md`` "Copying
  objects"), so two variables bound to the same object see each other's field
  writes; ``copy()`` is the shallow copy that breaks that link.

  **``EnumType`` / ``EnumValue``** back an ``enum`` declaration. ``Direction.up``
  resolves to the one ``EnumValue`` for that member — equality is by
  ``(enum, name)``, so ``dir == Direction.up`` in a ``switch`` works and
  ``str(dir)`` gives the member's title for a log line.

Kept out of ``runtime.py`` only so that file stays about *evaluation*. Imports
stdlib only, like the rest of ``apps/pine/``.
"""

from __future__ import annotations

from dataclasses import dataclass


class PineObject:
    """One instance of a UDT. Mutable — a bar mutates fields in place."""

    __slots__ = ("type_name", "fields")

    def __init__(self, type_name: str, fields: dict) -> None:
        self.type_name = type_name
        self.fields = fields

    def copy(self) -> PineObject:
        """A shallow copy — a new object, the same field *values* (objects.md).

        v1 has no ``array``/``label``/… fields, so shallow and deep coincide
        here; the method exists because scripts call ``obj.copy()`` explicitly.
        """
        return PineObject(self.type_name, dict(self.fields))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        body = ", ".join(f"{k}={v!r}" for k, v in self.fields.items())
        return f"{self.type_name}({body})"


@dataclass(frozen=True, slots=True)
class EnumValue:
    """One member of an enum. Frozen: it is a value, compared by identity of
    ``(enum, name)`` which the dataclass ``__eq__`` gives (``title`` is derived
    from the declaration, so it never disagrees for a given member)."""

    enum: str
    name: str
    title: str

    def __str__(self) -> str:
        return self.title

    def __bool__(self) -> bool:
        # An enum member is always a "real" value; only `na` is falsey. This
        # keeps `switch dir` and `x ? a : b` on an enum behaving sanely.
        return True


class EnumType:
    """The namespace an ``enum`` declaration introduces: ``Name.member``."""

    __slots__ = ("name", "_members")

    def __init__(self, name: str, members: dict[str, EnumValue]) -> None:
        self.name = name
        self._members = members

    @classmethod
    def from_def(cls, enum_def) -> EnumType:
        members = {
            member.name: EnumValue(enum_def.name, member.name, member.title or member.name)
            for member in enum_def.members
        }
        return cls(enum_def.name, members)

    def has(self, member: str) -> bool:
        return member in self._members

    def member(self, name: str) -> EnumValue | None:
        return self._members.get(name)

    def values(self) -> tuple[EnumValue, ...]:
        return tuple(self._members.values())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"EnumType({self.name}, {list(self._members)})"
