import { ref, reactive } from "vue";
import type { DataInfo } from "../types";

export interface LogEntry {
  time: string;
  idcode: string;
  direction: string;
  summary: string;
  hex?: string;
}

const logs = reactive<LogEntry[]>([]);
const latestData = ref<{ idcode: string; data: DataInfo } | null>(null);
const MAX_LOGS = 1000;

export function useCommLog() {
  function addLog(idcode: string, direction: string, summary: string, hex?: string) {
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;
    logs.unshift({ time, idcode, direction, summary, hex });
    if (logs.length > MAX_LOGS) logs.splice(MAX_LOGS);
  }

  function addData(idcode: string, data: DataInfo) {
    latestData.value = { idcode, data };
  }

  function clear() {
    logs.splice(0);
    latestData.value = null;
  }

  return { logs, latestData, addLog, addData, clear };
}
