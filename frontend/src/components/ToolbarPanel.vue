<script setup lang="ts">
import { ref } from "vue";
import { invoke } from "@tauri-apps/api/core";

const protocol = ref("V3");
const dataPort = ref("8001");
const running = ref(false);

function onProtocolChange() {
  dataPort.value = protocol.value === "V2" ? "7001" : "8001";
}

async function start() {
  await invoke("start_server", { dataPort: parseInt(dataPort.value), protocol: protocol.value });
  running.value = true;
}

async function stop() {
  await invoke("stop_server");
  running.value = false;
}
</script>

<template>
  <div class="toolbar">
    <button @click="start" :disabled="running">&#9654; 启动</button>
    <button @click="stop" :disabled="!running">&#9632; 停止</button>
    <span class="sep"></span>
    <label>协议:</label>
    <select v-model="protocol" @change="onProtocolChange">
      <option>V2</option>
      <option>V3</option>
    </select>
    <span class="sep"></span>
    <label>数据端口:</label>
    <input v-model="dataPort" type="text" style="width: 60px" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: #e8e8e8; border-bottom: 1px solid #ccc; }
.toolbar button { padding: 4px 12px; border: 1px solid #bbb; border-radius: 3px; background: #ddd; cursor: pointer; }
.toolbar button:disabled { opacity: 0.5; cursor: default; }
.toolbar input, .toolbar select { padding: 2px 4px; border: 1px solid #bbb; border-radius: 3px; }
.sep { width: 1px; height: 20px; background: #bbb; margin: 0 4px; }
label { color: #555; }
</style>
