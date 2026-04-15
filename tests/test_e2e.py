"""End-to-end smoke test: MasterStation with a mock substation."""
import asyncio
import queue
import struct
import unittest

from protocol.builder import FrameBuilder
from protocol.parser import FrameParser
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from protocol.constants import Cmd, FrameType
from network.master import MasterStation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def read_frame(reader: asyncio.StreamReader) -> bytes:
    """Read one complete PMU frame from *reader*."""
    header = await reader.readexactly(4)
    frame_size = struct.unpack_from("!H", header, 2)[0]
    remaining = await reader.readexactly(frame_size - 4)
    return header + remaining


def _heartbeat_frame(idcode: str) -> bytes:
    return FrameBuilder.build(CommandFrame(
        version=3, idcode=idcode, soc=0, fracsec=0, cmd=Cmd.HEARTBEAT,
    ))


def _cfg1_frame(idcode: str) -> bytes:
    cfg = ConfigFrame(
        version=3,
        cfg_type=int(FrameType.CFG1),   # == 2
        idcode=idcode,
        soc=0,
        fracsec=0,
        d_frame=0,
        meas_rate=50,
        num_pmu=1,
        stn="TEST_STN",
        pmu_idcode=idcode,
        format_flags=0x0000,
        phnmr=0,
        annmr=2,
        dgnmr=0,
        channel_names=["AN1", "AN2"],
        phunit=[],
        anunit=[10000, 20000],   # factors: 0.1 and 0.2
        digunit=[],
        fnom=0x0000,             # 60 Hz base
        period=100,
    )
    return FrameBuilder.build(cfg)


def _data_frame(idcode: str, analog_values: list) -> bytes:
    frame = DataFrame(
        version=3,
        idcode=idcode,
        soc=0,
        fracsec=0,
        stat=0x0000,
        phasors=[],
        freq=0,
        dfreq=0,
        analog=analog_values,
        digital=[],
    )
    return FrameBuilder.build(frame, phnmr=0, annmr=len(analog_values), dgnmr=0)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestE2ESmokeTest(unittest.IsolatedAsyncioTestCase):

    async def test_full_session(self):
        IDCODE = "TESTSUB1"
        event_q: queue.Queue = queue.Queue()

        # ------------------------------------------------------------------
        # Step 1: Start MasterStation (listens only for data connections)
        # ------------------------------------------------------------------
        master = MasterStation(event_q, data_port=0)
        await master.start()
        data_port = master.data_port

        # ------------------------------------------------------------------
        # Step 2: Start mock TCP server for management pipe (substation side)
        # ------------------------------------------------------------------
        mgmt_conn_event = asyncio.Event()
        mgmt_reader_holder = {}
        mgmt_writer_holder = {}
        mgmt_done_event = asyncio.Event()

        async def _mock_mgmt_handler(reader, writer):
            mgmt_reader_holder['r'] = reader
            mgmt_writer_holder['w'] = writer
            mgmt_conn_event.set()
            # Keep alive until test signals done
            await mgmt_done_event.wait()

        mock_mgmt_server = await asyncio.start_server(
            _mock_mgmt_handler, "127.0.0.1", 0
        )
        mgmt_port = mock_mgmt_server.sockets[0].getsockname()[1]

        try:
            # ------------------------------------------------------------------
            # Step 3: Master connects TO the mock substation's management port
            # ------------------------------------------------------------------
            await master.connect_to_substation("127.0.0.1", mgmt_port)

            # Wait for mock substation to accept the connection
            await asyncio.wait_for(mgmt_conn_event.wait(), timeout=2)
            mgmt_reader = mgmt_reader_holder['r']
            mgmt_writer = mgmt_writer_holder['w']

            # ------------------------------------------------------------------
            # Step 4: Mock substation sends heartbeat to identify itself
            # ------------------------------------------------------------------
            mgmt_writer.write(_heartbeat_frame(IDCODE))
            await mgmt_writer.drain()

            # Step 5: Verify session was created (keyed by real IDCODE after heartbeat)
            await asyncio.sleep(0.2)
            self.assertIn(IDCODE, master.sessions, "Session should be keyed by IDCODE after heartbeat")
            session = master.sessions[IDCODE]

            # ------------------------------------------------------------------
            # Step 6: Master requests CFG-1
            # ------------------------------------------------------------------
            master.send_command("request_cfg1", idcode=IDCODE)

            # Step 7: Mock substation reads the SEND_CFG1 command and verifies it
            raw = await asyncio.wait_for(read_frame(mgmt_reader), timeout=2)
            cmd_frame = FrameParser.parse(raw)
            self.assertIsInstance(cmd_frame, CommandFrame)
            self.assertEqual(cmd_frame.cmd, Cmd.SEND_CFG1)

            # Step 8: Mock substation sends CFG-1
            mgmt_writer.write(_cfg1_frame(IDCODE))
            await mgmt_writer.drain()

            # Step 9: Verify master received CFG-1
            await asyncio.sleep(0.3)
            self.assertIsNotNone(session.cfg1, "Master should have received CFG-1")
            self.assertEqual(session.cfg1.annmr, 2)

            # ------------------------------------------------------------------
            # Step 10: Set cfg2 so master can parse data frames correctly
            # ------------------------------------------------------------------
            cfg1 = session.cfg1
            from protocol.frames import ConfigFrame as CF
            session.cfg2 = CF(
                version=cfg1.version, cfg_type=int(FrameType.CFG2),
                idcode=cfg1.idcode, soc=cfg1.soc, fracsec=cfg1.fracsec,
                d_frame=cfg1.d_frame, meas_rate=cfg1.meas_rate,
                num_pmu=cfg1.num_pmu, stn=cfg1.stn, pmu_idcode=cfg1.pmu_idcode,
                format_flags=cfg1.format_flags,
                phnmr=cfg1.phnmr, annmr=cfg1.annmr, dgnmr=cfg1.dgnmr,
                channel_names=list(cfg1.channel_names),
                phunit=list(cfg1.phunit), anunit=list(cfg1.anunit),
                digunit=list(cfg1.digunit), fnom=cfg1.fnom, period=cfg1.period,
            )

            # ------------------------------------------------------------------
            # Step 11: Mock substation connects to master's data port
            # ------------------------------------------------------------------
            data_reader, data_writer = await asyncio.open_connection("127.0.0.1", data_port)

            # Step 12: Send a data frame
            analog_values = [100, 200]
            data_writer.write(_data_frame(IDCODE, analog_values))
            await data_writer.drain()

            # Step 13: Verify data_frame event was emitted with correct analog values
            await asyncio.sleep(0.3)

            data_events = []
            while not event_q.empty():
                evt = event_q.get_nowait()
                if evt[0] == "data_frame":
                    data_events.append(evt)

            self.assertTrue(len(data_events) >= 1, "Expected at least one data_frame event")
            evt_type, evt_kwargs = data_events[-1]
            self.assertEqual(evt_kwargs["idcode"], IDCODE)
            received_frame: DataFrame = evt_kwargs["frame"]
            self.assertIsInstance(received_frame, DataFrame)
            self.assertEqual(received_frame.analog, analog_values)

            # Cleanup
            mgmt_done_event.set()
            data_writer.close()
            mgmt_writer.close()

        finally:
            mock_mgmt_server.close()
            await mock_mgmt_server.wait_closed()
            await master.stop()
