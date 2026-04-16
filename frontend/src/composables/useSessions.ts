import { reactive, ref } from "vue";
import type { SessionInfo, ConfigInfo } from "../types";

const sessions = reactive(new Map<string, SessionInfo>());
const configs = reactive(new Map<string, ConfigInfo>());
const selectedIdcode = ref<string>("");

export function useSessions() {
  function addSession(idcode: string, peerIp: string) {
    sessions.set(idcode, { idcode, peerIp, state: "connected" });
  }
  function updateState(idcode: string, state: SessionInfo["state"]) {
    const s = sessions.get(idcode);
    if (s) s.state = state;
  }
  function removeSession(idcode: string) {
    sessions.delete(idcode);
    configs.delete(idcode);
  }
  function setConfig(idcode: string, cfg: ConfigInfo) {
    configs.set(idcode, cfg);
  }
  function clear() {
    sessions.clear();
    configs.clear();
    selectedIdcode.value = "";
  }
  return { sessions, configs, selectedIdcode, addSession, updateState, removeSession, setConfig, clear };
}
