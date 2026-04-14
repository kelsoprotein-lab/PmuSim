"""Substation session management and state machine."""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
from protocol.frames import ConfigFrame


class SessionState(Enum):
    CONNECTED = auto()         # At least one pipe connected
    CFG1_RECEIVED = auto()     # CFG-1 received from substation
    CFG2_SENT = auto()         # CFG-2 sent to substation
    STREAMING = auto()         # Real-time data flowing
    DISCONNECTED = auto()      # All connections closed


@dataclass
class SubStationSession:
    """Represents one connected substation with its management and data pipes."""
    idcode: str
    version: int = 0                    # Detected from first frame
    peer_ip: str = ""                   # Remote IP for V2 pairing
    state: SessionState = SessionState.CONNECTED

    # Asyncio streams (set when pipes connect)
    mgmt_reader: Optional[asyncio.StreamReader] = field(default=None, repr=False)
    mgmt_writer: Optional[asyncio.StreamWriter] = field(default=None, repr=False)
    data_reader: Optional[asyncio.StreamReader] = field(default=None, repr=False)
    data_writer: Optional[asyncio.StreamWriter] = field(default=None, repr=False)

    cfg1: Optional[ConfigFrame] = None
    cfg2: Optional[ConfigFrame] = None

    last_heartbeat: float = field(default_factory=time.time)
    missed_heartbeats: int = 0

    @property
    def mgmt_connected(self) -> bool:
        return self.mgmt_writer is not None and not self.mgmt_writer.is_closing()

    @property
    def data_connected(self) -> bool:
        return self.data_writer is not None and not self.data_writer.is_closing()

    @property
    def fully_connected(self) -> bool:
        return self.mgmt_connected and self.data_connected

    def close(self):
        """Close all connections."""
        for writer in (self.mgmt_writer, self.data_writer):
            if writer and not writer.is_closing():
                writer.close()
        self.state = SessionState.DISCONNECTED
