<script setup>
const props = defineProps({
  type: {
    type: String,
    default: '模块',
  },
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ props.type }} 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-empty :description="`${props.type} 提交页正在接入后端能力，当前版本暂未开放。`" />
    </div>
  </div>
</template>
