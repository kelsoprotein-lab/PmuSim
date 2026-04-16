import { listen } from "@tauri-apps/api/event";
import type { PmuEvent } from "../types";
import { useSessions } from "./useSessions";
import { useCommLog } from "./useCommLog";

export function usePmuEvents() {
  const { addSession, updateState, removeSession, setConfig } = useSessions();
  const { addLog, addData } = useCommLog();

  async function startListening() {
    await listen<PmuEvent>("pmu-event", ({ payload }) => {
      switch (payload.type) {
        case "SessionCreated":
          addSession(payload.idcode, payload.peer_ip);
          break;
        case "SessionDisconnected":
          updateState(payload.idcode, "disconnected");
          break;
        case "Cfg1Received":
          updateState(payload.idcode, "cfg1_received");
          setConfig(payload.idcode, payload.cfg);
          break;
        case "Cfg2Sent":
          updateState(payload.idcode, "cfg2_sent");
          break;
        case "Cfg2Received":
          setConfig(payload.idcode, payload.cfg);
          break;
        case "StreamingStarted":
          updateState(payload.idcode, "streaming");
          break;
        case "StreamingStopped":
          updateState(payload.idcode, "cfg2_sent");
          break;
        case "DataFrame":
          addData(payload.idcode, payload.data);
          break;
        case "RawFrame":
          addLog(payload.idcode, payload.direction, payload.hex);
          break;
        case "HeartbeatTimeout":
          updateState(payload.idcode, "disconnected");
          break;
        case "Error":
          addLog(payload.idcode, "!", payload.error);
          break;
      }
    });
  }

  return { startListening };
}
