<script setup>
import { ref } from 'vue'

import ToolAccuracyEvaluationView from './ToolAccuracyEvaluationView.vue'
import ToolConsistencyEvaluationView from './ToolConsistencyEvaluationView.vue'

const activeTab = ref('accuracy')
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">评测中心</h3>
    </div>
    <div class="panel-body">
      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="解析准确性评测" name="accuracy">
          <ToolAccuracyEvaluationView />
        </el-tab-pane>
        <el-tab-pane label="设备重复性评测" name="consistency">
          <ToolConsistencyEvaluationView />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
:deep(.el-tabs__content) {
  padding: 16px 0 0;
}
</style>
