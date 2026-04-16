<script setup lang="ts">
import { computed } from "vue";
import { useSessions } from "../composables/useSessions";

const { selectedIdcode, configs } = useSessions();
const cfg = computed(() => configs.get(selectedIdcode.value));
</script>

<template>
  <div v-if="cfg">
    <fieldset>
      <legend>基本信息</legend>
      <table class="info-table">
        <tr><td>配置类型</td><td>CFG-{{ cfg.cfgType }}</td></tr>
        <tr><td>协议版本</td><td>V{{ cfg.version }}</td></tr>
        <tr><td>站名</td><td>{{ cfg.stn }}</td></tr>
        <tr><td>IDCODE</td><td>{{ cfg.idcode }}</td></tr>
        <tr><td>FORMAT</td><td>0x{{ cfg.formatFlags.toString(16).padStart(4, '0').toUpperCase() }}</td></tr>
        <tr><td>PERIOD</td><td>{{ cfg.period }}</td></tr>
        <tr><td>MEAS_RATE</td><td>{{ cfg.measRate }}</td></tr>
      </table>
    </fieldset>
    <fieldset>
      <legend>模拟量通道 ({{ cfg.annmr }})</legend>
      <table class="data-table">
        <thead><tr><th>#</th><th>名称</th><th>ANUNIT</th><th>系数</th></tr></thead>
        <tbody>
          <tr v-for="(name, i) in cfg.channelNames.slice(cfg.phnmr, cfg.phnmr + cfg.annmr)" :key="i">
            <td>{{ i + 1 }}</td>
            <td>{{ name }}</td>
            <td>{{ cfg.anunit[i] || 0 }}</td>
            <td>{{ ((cfg.anunit[i] || 0) * 0.00001).toFixed(5) }}</td>
          </tr>
        </tbody>
      </table>
    </fieldset>
  </div>
  <div v-else class="empty">选择子站查看配置</div>
</template>

<style scoped>
fieldset { margin: 8px 0; border: 1px solid #ddd; border-radius: 3px; padding: 8px; }
.info-table td:first-child { font-weight: 600; width: 100px; color: #555; }
.info-table td { padding: 2px 8px; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 3px 8px; text-align: left; border-bottom: 1px solid #eee; }
.data-table th { background: #f8f8f8; font-weight: 600; color: #555; }
.empty { padding: 20px; color: #999; text-align: center; }
</style>
