<script setup lang="ts">
import { ref } from "vue";
import { useCommLog, type LogEntry } from "../composables/useCommLog";

const { logs } = useCommLog();
const selectedLog = ref<LogEntry | null>(null);

function selectLog(entry: LogEntry) {
  selectedLog.value = entry;
}
</script>

<template>
  <div class="log-tab">
    <div class="log-list">
      <table class="log-table">
        <thead>
          <tr><th>时间</th><th>子站</th><th>方向</th><th>摘要</th></tr>
        </thead>
        <tbody>
          <tr v-for="(entry, i) in logs" :key="i"
              :class="{ selected: selectedLog === entry }"
              @click="selectLog(entry)">
            <td>{{ entry.time }}</td>
            <td>{{ entry.idcode }}</td>
            <td>{{ entry.direction === 'send' ? '\u2192' : entry.direction === 'recv' ? '\u2190' : entry.direction }}</td>
            <td>{{ entry.summary }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="hex-panel">
      <code v-if="selectedLog?.hex">{{ selectedLog.hex }}</code>
      <span v-else class="empty">选择日志查看 hex</span>
    </div>
  </div>
</template>

<style scoped>
.log-tab { display: flex; flex-direction: column; height: 100%; }
.log-list { flex: 1; overflow: auto; }
.log-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.log-table th, .log-table td { padding: 3px 6px; border-bottom: 1px solid #eee; white-space: nowrap; }
.log-table th { background: #f8f8f8; font-weight: 600; position: sticky; top: 0; }
.log-table tr { cursor: pointer; }
.log-table tr.selected { background: #e3f2fd; }
.log-table tr:hover { background: #f5f5f5; }
.hex-panel { height: 80px; border-top: 1px solid #ddd; padding: 4px 8px; font-family: monospace; font-size: 12px; overflow: auto; background: #fafafa; }
.empty { color: #999; }
</style>
