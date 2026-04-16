<script setup lang="ts">
import { onMounted, ref } from "vue";
import { usePmuEvents } from "./composables/usePmuEvents";
import { useSessions } from "./composables/useSessions";
import ToolbarPanel from "./components/ToolbarPanel.vue";
import StationListPanel from "./components/StationListPanel.vue";
import ConfigTab from "./components/ConfigTab.vue";
import DataTab from "./components/DataTab.vue";
import LogTab from "./components/LogTab.vue";

const { startListening } = usePmuEvents();
const { sessions } = useSessions();
const activeTab = ref("config");

onMounted(() => {
  startListening();
});
</script>

<template>
  <div class="app">
    <ToolbarPanel />
    <div class="content">
      <StationListPanel />
      <div class="main-panel">
        <div class="tabs">
          <button :class="{ active: activeTab === 'config' }" @click="activeTab = 'config'">配置</button>
          <button :class="{ active: activeTab === 'data' }" @click="activeTab = 'data'">实时数据</button>
          <button :class="{ active: activeTab === 'log' }" @click="activeTab = 'log'">通信日志</button>
        </div>
        <div class="tab-content">
          <ConfigTab v-if="activeTab === 'config'" />
          <DataTab v-if="activeTab === 'data'" />
          <LogTab v-if="activeTab === 'log'" />
        </div>
      </div>
    </div>
    <div class="status-bar">已连接子站: {{ sessions.size }}</div>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 13px; }
.app { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
.content { display: flex; flex: 1; overflow: hidden; padding: 4px; gap: 4px; }
.main-panel { flex: 1; display: flex; flex-direction: column; background: white; border-radius: 4px; overflow: hidden; }
.tabs { display: flex; border-bottom: 1px solid #ddd; background: #fafafa; }
.tabs button { padding: 8px 16px; border: none; background: none; cursor: pointer; border-bottom: 2px solid transparent; }
.tabs button.active { border-bottom-color: #0078d7; color: #0078d7; font-weight: 600; }
.tab-content { flex: 1; overflow: auto; padding: 8px; }
.status-bar { padding: 4px 8px; background: #e8e8e8; border-top: 1px solid #ccc; font-size: 12px; color: #666; }
</style>
