from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrinterSelection:
    """Immutable selection state shared by the printer checklist and tests."""

    available: tuple[str, ...] = ()
    selected: frozenset[str] = frozenset()

    @classmethod
    def all(cls, printers: list[str] | tuple[str, ...]) -> PrinterSelection:
        available = tuple(sorted(set(printers), key=str.casefold))
        return cls(available, frozenset(available))

    @property
    def all_selected(self) -> bool:
        return bool(self.available) and self.selected == frozenset(self.available)

    @property
    def count(self) -> int:
        return len(self.selected)

    def with_available(self, printers: list[str] | tuple[str, ...]) -> PrinterSelection:
        available = tuple(sorted(set(printers), key=str.casefold))
        if self.all_selected or not self.available:
            selected = frozenset(available)
        else:
            selected = self.selected.intersection(available)
        return PrinterSelection(available, frozenset(selected))

    def select_all(self, active: bool) -> PrinterSelection:
        return PrinterSelection(
            self.available,
            frozenset(self.available) if active else frozenset(),
        )

    def set_selected(self, printer: str, active: bool) -> PrinterSelection:
        if printer not in self.available:
            return self
        selected = set(self.selected)
        if active:
            selected.add(printer)
        else:
            selected.discard(printer)
        return PrinterSelection(self.available, frozenset(selected))

    def matches(self, printer: str) -> bool:
        return printer in self.selected
