"""Frame dataclasses for PMU protocol V2/V3."""
from dataclasses import dataclass, field

@dataclass
class CommandFrame:
    version: int
    idcode: str
    soc: int
    fracsec: int
    cmd: int

@dataclass
class ConfigFrame:
    version: int
    cfg_type: int
    idcode: str
    soc: int
    fracsec: int
    d_frame: int
    meas_rate: int
    num_pmu: int
    stn: str
    pmu_idcode: str
    format_flags: int
    phnmr: int
    annmr: int
    dgnmr: int
    channel_names: list[str] = field(default_factory=list)
    phunit: list[int] = field(default_factory=list)
    anunit: list[int] = field(default_factory=list)
    digunit: list[tuple[int, int]] = field(default_factory=list)
    fnom: int = 0
    period: int = 0

    @property
    def period_ms(self) -> float:
        base_freq = 50 if (self.fnom & 0x01) else 60
        base_period_ms = 1000.0 / base_freq
        multiplier = self.period / 100.0
        return multiplier * base_period_ms

    def analog_factor(self, index: int) -> float:
        if 0 <= index < len(self.anunit):
            return self.anunit[index] * 0.00001
        return 1.0

@dataclass
class DataFrame:
    version: int
    idcode: str
    soc: int
    fracsec: int
    stat: int
    phasors: list[tuple[int, int]] = field(default_factory=list)
    freq: int = 0
    dfreq: int = 0
    analog: list[int] = field(default_factory=list)
    digital: list[int] = field(default_factory=list)

    @property
    def data_valid(self) -> bool:
        return (self.stat & 0x8000) == 0

    @property
    def sync_ok(self) -> bool:
        return (self.stat & 0x2000) == 0
