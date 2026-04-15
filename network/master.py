"""MasterStation: master=client for management pipe, master=server for data pipe."""
from __future__ import annotations
import asyncio
import logging
import queue
import struct
import time
from typing import Optional
from protocol.constants import (
    FrameType, ProtocolVersion, Cmd, IDCODE_LEN, SYNC_BYTE, parse_sync,
)
from protocol.parser import FrameParser, ParseError
from protocol.builder import FrameBuilder
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from network.session import SubStationSession, SessionState
from utils.time_utils import current_soc

logger = logging.getLogger(__name__)


class MasterStation:
    """PMU master station simulator managing multiple substation connections."""

    def __init__(self, event_queue: queue.Queue, mgmt_port: int = 8000,
                 data_port: int = 8001, heartbeat_interval: float = 30.0):
        self.event_queue = event_queue
        self.mgmt_port = mgmt_port   # kept for reference / backward compat; not listened on
        self.data_port = data_port
        self.heartbeat_interval = heartbeat_interval

        self.sessions: dict[str, SubStationSession] = {}
        self._pending_data: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter, str]] = {}

        self._data_server: Optional[asyncio.Server] = None
        self._cmd_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._tasks = []

    def send_command(self, cmd_type: str, **kwargs):
        """Thread-safe: enqueue a command from UI to be processed in asyncio loop."""
        self._cmd_queue.put_nowait((cmd_type, kwargs))

    async def start(self):
        """Start data TCP server (master listens for data pipe connections from substations)."""
        self._running = True
        self._data_server = await asyncio.start_server(
            self._handle_data_connection, "0.0.0.0", self.data_port
        )
        # Update data_port in case port=0 was used (auto-assign)
        self.data_port = self._data_server.sockets[0].getsockname()[1]
        self._tasks.append(asyncio.create_task(self._command_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._emit("server_started", data_port=self.data_port)
        logger.info(f"MasterStation started, data server on port {self.data_port}")

    async def stop(self):
        """Stop servers and close all sessions."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self._data_server:
            self._data_server.close()
            await self._data_server.wait_closed()
        for session in list(self.sessions.values()):
            session.close()
        self.sessions.clear()
        self._pending_data.clear()
        self._emit("server_stopped")
        logger.info("MasterStation stopped")

    # --- Outbound management connection (master → substation) ---

    async def connect_to_substation(self, host: str, mgmt_port: int):
        """Connect to a substation's management port (master is TCP client)."""
        try:
            reader, writer = await asyncio.open_connection(host, mgmt_port)
        except Exception as e:
            logger.error(f"Failed to connect to {host}:{mgmt_port}: {e}")
            self._emit("error", idcode="", error=f"连接子站失败 {host}:{mgmt_port}: {e}")
            return

        # Use temporary idcode until first frame reveals real one
        tmp_id = f"{host}:{mgmt_port}"
        session = SubStationSession(
            idcode=tmp_id, version=0, peer_ip=host,
            peer_host=host, peer_mgmt_port=mgmt_port,
        )
        session.mgmt_reader = reader
        session.mgmt_writer = writer
        self.sessions[tmp_id] = session
        self._emit("session_created", idcode=tmp_id, peer_ip=host)
        logger.info(f"Management pipe connected to {host}:{mgmt_port}")

        # Start reading management frames in background
        self._tasks.append(asyncio.create_task(self._mgmt_read_loop(session)))

    async def _mgmt_read_loop(self, session: SubStationSession):
        """Read frames from an outbound management connection (master=client side)."""
        reader = session.mgmt_reader
        tmp_id = session.idcode  # may be "host:port" initially

        try:
            while self._running and not reader.at_eof():
                try:
                    frame_data = await self._read_frame(reader)
                    frame = FrameParser.parse(frame_data)
                except asyncio.IncompleteReadError:
                    break
                except ParseError as e:
                    self._emit("parse_error", idcode=session.idcode, error=str(e))
                    continue

                # If this is the first real frame, update idcode from frame
                if isinstance(frame, (CommandFrame, ConfigFrame)):
                    real_id = frame.idcode
                    if real_id and real_id != session.idcode:
                        # Re-key the session under real idcode
                        old_id = session.idcode
                        session.idcode = real_id
                        if old_id in self.sessions:
                            del self.sessions[old_id]
                        self.sessions[real_id] = session
                        if session.version == 0:
                            session.version = frame.version
                        self._emit("session_created", idcode=real_id, peer_ip=session.peer_ip)

                await self._process_mgmt_frame(session, frame, frame_data)

        except Exception as e:
            logger.error(f"Management read loop error: {e}")
        finally:
            writer = session.mgmt_writer
            if writer and not writer.is_closing():
                writer.close()
            session.mgmt_writer = None
            if not session.data_connected:
                session.state = SessionState.DISCONNECTED
                self._emit("session_disconnected", idcode=session.idcode)

    # --- Inbound data connection (substation → master) ---

    async def _handle_data_connection(self, reader: asyncio.StreamReader,
                                       writer: asyncio.StreamWriter):
        """Handle a new data pipe connection."""
        peer = writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else "unknown"
        logger.info(f"Data connection from {peer_ip}")

        session = None
        try:
            # Read first frame to determine version
            frame_data = await self._read_frame(reader)

            # Peek at SYNC to determine version
            sync = struct.unpack_from("!H", frame_data, 0)[0]
            _, version = parse_sync(sync)

            if version == ProtocolVersion.V3:
                # V3 data frames contain IDCODE
                idcode = frame_data[4:4 + IDCODE_LEN].decode("ascii", errors="replace")
                session = self._get_or_create_session(idcode, peer_ip, int(version))
            else:
                # V2 data frames don't contain IDCODE - pair by IP
                session = self._find_session_by_ip(peer_ip)
                if not session:
                    logger.warning(f"No management session found for data connection from {peer_ip}")
                    writer.close()
                    return

            session.data_reader = reader
            session.data_writer = writer
            self._emit("data_connected", idcode=session.idcode, peer_ip=peer_ip)

            # Parse and process the first data frame
            if session.cfg2:
                frame = FrameParser.parse(
                    frame_data,
                    phnmr=session.cfg2.phnmr,
                    annmr=session.cfg2.annmr,
                    dgnmr=session.cfg2.dgnmr,
                )
                if isinstance(frame, DataFrame):
                    if not frame.idcode:
                        frame.idcode = session.idcode
                    self._emit("data_frame", idcode=session.idcode, frame=frame)

            # Continue reading data frames
            while self._running and not reader.at_eof():
                try:
                    frame_data = await self._read_frame(reader)
                    if session.cfg2:
                        frame = FrameParser.parse(
                            frame_data,
                            phnmr=session.cfg2.phnmr,
                            annmr=session.cfg2.annmr,
                            dgnmr=session.cfg2.dgnmr,
                        )
                        if isinstance(frame, DataFrame):
                            if not frame.idcode:
                                frame.idcode = session.idcode
                            self._emit("data_frame", idcode=session.idcode, frame=frame)
                    self._emit("raw_frame", idcode=session.idcode, direction="recv",
                               data=frame_data)
                except ParseError as e:
                    self._emit("parse_error", idcode=session.idcode if session else "?",
                               error=str(e))
                except asyncio.IncompleteReadError:
                    break

        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Data connection error: {e}")
        finally:
            if not writer.is_closing():
                writer.close()
            if session:
                session.data_writer = None
                if not session.mgmt_connected:
                    session.state = SessionState.DISCONNECTED
                    self._emit("session_disconnected", idcode=session.idcode)

    # --- Frame Processing ---

    async def _process_mgmt_frame(self, session: SubStationSession, frame, raw: bytes):
        """Process a frame received on the management pipe."""
        self._emit("raw_frame", idcode=session.idcode, direction="recv", data=raw)

        if isinstance(frame, CommandFrame):
            if frame.cmd == Cmd.HEARTBEAT:
                session.last_heartbeat = time.time()
                session.missed_heartbeats = 0
                self._emit("heartbeat_recv", idcode=session.idcode)
            elif frame.cmd == Cmd.ACK:
                self._emit("ack_recv", idcode=session.idcode)
            elif frame.cmd == Cmd.NACK:
                self._emit("nack_recv", idcode=session.idcode)

        elif isinstance(frame, ConfigFrame):
            if frame.cfg_type == int(FrameType.CFG1):
                session.cfg1 = frame
                session.state = SessionState.CFG1_RECEIVED
                self._emit("cfg1_received", idcode=session.idcode, cfg=frame)
            elif frame.cfg_type == int(FrameType.CFG2):
                session.cfg2 = frame
                self._emit("cfg2_received", idcode=session.idcode, cfg=frame)

    # --- Command Sending ---

    async def _send_command(self, session: SubStationSession, cmd: int):
        """Send a command frame to a substation via management pipe."""
        if not session.mgmt_connected:
            self._emit("error", idcode=session.idcode, error="Management pipe not connected")
            return

        frame = CommandFrame(
            version=session.version,
            idcode=session.idcode,
            soc=current_soc(),
            fracsec=0,
            cmd=cmd,
        )
        raw = FrameBuilder.build(frame)
        session.mgmt_writer.write(raw)
        await session.mgmt_writer.drain()
        self._emit("raw_frame", idcode=session.idcode, direction="send", data=raw)

    async def _send_cfg2(self, session: SubStationSession, period: Optional[int] = None):
        """Send CFG-2 config frame to substation."""
        if not session.cfg1:
            self._emit("error", idcode=session.idcode, error="No CFG-1 available")
            return
        if not session.mgmt_connected:
            self._emit("error", idcode=session.idcode, error="Management pipe not connected")
            return

        # Build CFG-2 based on CFG-1
        cfg2 = ConfigFrame(
            version=session.cfg1.version,
            cfg_type=2,
            idcode=session.cfg1.idcode,
            soc=current_soc(),
            fracsec=0,
            d_frame=session.cfg1.d_frame,
            meas_rate=session.cfg1.meas_rate,
            num_pmu=session.cfg1.num_pmu,
            stn=session.cfg1.stn,
            pmu_idcode=session.cfg1.pmu_idcode,
            format_flags=session.cfg1.format_flags,
            phnmr=session.cfg1.phnmr,
            annmr=session.cfg1.annmr,
            dgnmr=session.cfg1.dgnmr,
            channel_names=list(session.cfg1.channel_names),
            phunit=list(session.cfg1.phunit),
            anunit=list(session.cfg1.anunit),
            digunit=list(session.cfg1.digunit),
            fnom=session.cfg1.fnom,
            period=period if period is not None else session.cfg1.period,
        )
        session.cfg2 = cfg2

        raw = FrameBuilder.build(cfg2)
        session.mgmt_writer.write(raw)
        await session.mgmt_writer.drain()
        session.state = SessionState.CFG2_SENT
        self._emit("raw_frame", idcode=session.idcode, direction="send", data=raw)
        self._emit("cfg2_sent", idcode=session.idcode, cfg=cfg2)

    # --- Command Loop (processes UI commands) ---

    async def _command_loop(self):
        """Process commands from the UI thread."""
        while self._running:
            try:
                cmd_type, kwargs = await asyncio.wait_for(self._cmd_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            idcode = kwargs.get("idcode", "")
            session = self.sessions.get(idcode)

            if cmd_type == "connect":
                host = kwargs.get("host", "")
                port = kwargs.get("port", 7000)
                await self.connect_to_substation(host, port)
            elif cmd_type == "request_cfg1" and session:
                await self._send_command(session, Cmd.SEND_CFG1)
            elif cmd_type == "send_cfg2_cmd" and session:
                await self._send_command(session, Cmd.SEND_CFG2_CMD)
            elif cmd_type == "send_cfg2" and session:
                await self._send_cfg2(session, period=kwargs.get("period"))
            elif cmd_type == "request_cfg2" and session:
                await self._send_command(session, Cmd.SEND_CFG2)
            elif cmd_type == "open_data" and session:
                await self._send_command(session, Cmd.OPEN_DATA)
                session.state = SessionState.STREAMING
                self._emit("streaming_started", idcode=idcode)
            elif cmd_type == "close_data" and session:
                await self._send_command(session, Cmd.CLOSE_DATA)
                session.state = SessionState.CFG2_SENT
                self._emit("streaming_stopped", idcode=idcode)
            elif cmd_type == "auto_handshake" and session:
                await self._auto_handshake(session, period=kwargs.get("period"))

    async def _auto_handshake(self, session: SubStationSession, period: Optional[int] = None):
        """Automated handshake: request CFG-1 -> send CFG-2 cmd -> send CFG-2 -> request CFG-2 -> open data."""
        try:
            # Step 1: Request CFG-1
            await self._send_command(session, Cmd.SEND_CFG1)
            await asyncio.sleep(1.0)  # Wait for response

            if not session.cfg1:
                self._emit("error", idcode=session.idcode, error="CFG-1 not received after request")
                return

            # Step 2: Send CFG-2 command
            await self._send_command(session, Cmd.SEND_CFG2_CMD)
            await asyncio.sleep(0.5)

            # Step 3: Send CFG-2 config
            await self._send_cfg2(session, period=period)
            await asyncio.sleep(0.5)

            # Step 4: Request CFG-2 back
            await self._send_command(session, Cmd.SEND_CFG2)
            await asyncio.sleep(0.5)

            # Step 5: Open data
            await self._send_command(session, Cmd.OPEN_DATA)
            session.state = SessionState.STREAMING
            self._emit("streaming_started", idcode=session.idcode)

        except Exception as e:
            self._emit("error", idcode=session.idcode, error=f"Auto handshake failed: {e}")

    # --- Heartbeat ---

    async def _heartbeat_loop(self):
        """Periodically send heartbeats to all connected substations."""
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            for session in list(self.sessions.values()):
                if session.mgmt_connected and session.state != SessionState.DISCONNECTED:
                    try:
                        await self._send_command(session, Cmd.HEARTBEAT)
                        session.missed_heartbeats += 1
                        if session.missed_heartbeats >= 3:
                            session.state = SessionState.DISCONNECTED
                            self._emit("heartbeat_timeout", idcode=session.idcode)
                    except Exception:
                        pass

    # --- Helpers ---

    async def _read_frame(self, reader: asyncio.StreamReader) -> bytes:
        """Read a complete frame from a TCP stream."""
        header = await reader.readexactly(4)
        sync = struct.unpack_from("!H", header, 0)[0]
        if (sync >> 8) != SYNC_BYTE:
            raise ParseError(f"Invalid sync byte: {sync:#06x}")
        frame_size = struct.unpack_from("!H", header, 2)[0]
        if frame_size < 4:
            raise ParseError(f"Invalid frame size: {frame_size}")
        remaining = await reader.readexactly(frame_size - 4)
        return header + remaining

    def _get_or_create_session(self, idcode: str, peer_ip: str, version: int) -> SubStationSession:
        """Find existing session by idcode or create a new one."""
        if idcode in self.sessions:
            session = self.sessions[idcode]
            session.peer_ip = peer_ip
            return session
        session = SubStationSession(idcode=idcode, version=version, peer_ip=peer_ip)
        self.sessions[idcode] = session
        self._emit("session_created", idcode=idcode, peer_ip=peer_ip)
        return session

    def _find_session_by_ip(self, peer_ip: str) -> Optional[SubStationSession]:
        """Find a session by peer IP (for V2 data pipe pairing)."""
        for session in self.sessions.values():
            if session.peer_ip == peer_ip:
                return session
        return None

    def _emit(self, event_type: str, **kwargs):
        """Send an event to the UI thread via queue."""
        self.event_queue.put_nowait((event_type, kwargs))
