"""The shock calendar, 1912–2026 — the century's weather, as data.

Each shock carries three effect dials the fact expansions read:
  production_halt  — 1 stops shoot-day event emission inside the window
  cost_mult        — multiplies ledger actuals for productions in the window
  attendance_mult  — multiplies theatrical demand in the window

These are the real events (the influenza closures, the Depression and the
receivership that followed it, wartime set-cost caps beside a wartime
attendance boom, the strike calendar from the CSU to the 2023 double strike,
COVID's halt and cliff), dated to the real calendar so a query that joins
`shock_calendar` explains the dents it finds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Shock:
    shock_id: str
    name: str
    kind: str            # pandemic | depression | war | strike | recession | regulation | corporate
    start: date
    end: date
    production_halt: int
    cost_mult: float
    attendance_mult: float


SHOCKS: list[Shock] = [
    Shock("flu_1918", "1918 influenza theater closures", "pandemic",
          date(1918, 10, 1), date(1918, 12, 15), 0, 1.00, 0.35),
    Shock("depression_1930", "Depression box-office collapse", "depression",
          date(1930, 1, 1), date(1933, 12, 31), 0, 0.90, 0.62),
    Shock("receivership_1933", "Studio receivership and austerity", "corporate",
          date(1933, 4, 1), date(1935, 3, 31), 0, 0.85, 1.00),
    Shock("wwii_caps", "Wartime materials rationing (set-cost caps) and attendance boom", "war",
          date(1942, 1, 1), date(1945, 8, 31), 0, 0.92, 1.25),
    Shock("csu_1945", "CSU craft strikes", "strike",
          date(1945, 3, 12), date(1946, 12, 31), 0, 1.04, 1.00),
    Shock("decree_1948", "Divestiture decree — theaters stripped, block booking ends", "regulation",
          date(1948, 5, 3), date(1949, 12, 31), 0, 1.00, 0.90),
    Shock("sag_wga_1960", "Writers' and actors' strikes — residuals are born", "strike",
          date(1960, 1, 16), date(1960, 6, 30), 1, 1.05, 1.00),
    Shock("recession_1969", "Industry recession — the roadshow glut unwinds", "recession",
          date(1969, 1, 1), date(1971, 12, 31), 0, 1.00, 0.85),
    Shock("wga_1981", "Writers' strike", "strike",
          date(1981, 4, 11), date(1981, 7, 11), 1, 1.03, 1.00),
    Shock("wga_1988", "Writers' strike — 22 weeks", "strike",
          date(1988, 3, 7), date(1988, 8, 7), 1, 1.06, 1.00),
    Shock("wga_2007", "Writers' strike — 100 days", "strike",
          date(2007, 11, 5), date(2008, 2, 12), 1, 1.04, 1.00),
    Shock("covid_halt", "COVID production halt", "pandemic",
          date(2020, 3, 13), date(2020, 9, 15), 1, 1.15, 1.00),
    Shock("covid_closure", "COVID theater closures", "pandemic",
          date(2020, 3, 13), date(2020, 8, 20), 0, 1.00, 0.04),
    Shock("covid_capacity", "COVID capacity limits and slow return", "pandemic",
          date(2020, 8, 21), date(2021, 6, 30), 0, 1.00, 0.30),
    Shock("double_strike_2023", "Writers' and actors' double strike", "strike",
          date(2023, 5, 2), date(2023, 11, 9), 1, 1.08, 1.00),
]


def halted(d: date) -> bool:
    return any(s.production_halt and s.start <= d <= s.end for s in SHOCKS)


def cost_mult(d: date) -> float:
    m = 1.0
    for s in SHOCKS:
        if s.start <= d <= s.end:
            m *= s.cost_mult
    return m


def attendance_mult(d: date) -> float:
    m = 1.0
    for s in SHOCKS:
        if s.start <= d <= s.end:
            m *= s.attendance_mult
    return m


def rows() -> list[list]:
    """shock_calendar table rows."""
    return [[s.shock_id, s.name, s.kind, s.start, s.end,
             s.production_halt, s.cost_mult, s.attendance_mult] for s in SHOCKS]
