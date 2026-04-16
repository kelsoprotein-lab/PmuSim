<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { useCommLog } from "../composables/useCommLog";
import { useSessions } from "../composables/useSessions";

const { latestData } = useCommLog();
const { selectedIdcode, configs } = useSessions();

interface DataRow { timestamp: string; values: string[]; stat: string; }
const rows = ref<DataRow[]>([]);

const columns = computed(() => {
  const cfg = configs.get(selectedIdcode.value);
  if (!cfg) return ["时间戳", "STAT"];
  const cols = ["时间戳"];
  for (let i = 0; i < cfg.annmr; i++) {
    const idx = cfg.phnmr + i;
    cols.push(cfg.channelNames[idx] || `AN${i + 1}`);
  }
  cols.push("开关量", "STAT");
  return cols;
});

watch(latestData, (val) => {
  if (!val || val.idcode !== selectedIdcode.value) return;
  const d = val.data;
  const ts = `SOC:${d.soc}.${d.fracsec}`;
  const values = d.analog.map((v) => v.toFixed(4));
  const digital = d.digital.map((v) => v.toString(2).padStart(16, "0")).join(" ");
  values.push(digital);
  rows.value.unshift({ timestamp: ts, values, stat: `0x${d.stat.toString(16).padStart(4, "0")}` });
  if (rows.value.length > 500) rows.value.splice(500);
});
</script>

<template>
  <div class="data-tab">
    <table class="data-table">
      <thead>
        <tr><th v-for="col in columns" :key="col">{{ col }}</th></tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td>{{ row.timestamp }}</td>
          <td v-for="(v, j) in row.values" :key="j">{{ v }}</td>
          <td>{{ row.stat }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="rows.length === 0" class="empty">暂无数据</div>
  </div>
</template>

<style scoped>
.data-tab { overflow: auto; }
.data-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
.data-table th, .data-table td { padding: 3px 6px; border-bottom: 1px solid #eee; white-space: nowrap; }
.data-table th { background: #f8f8f8; font-weight: 600; position: sticky; top: 0; }
.empty { padding: 20px; color: #999; text-align: center; }
</style>
