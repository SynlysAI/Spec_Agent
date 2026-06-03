<script setup>
import { QuestionFilled } from '@element-plus/icons-vue'

defineProps({
  label: {
    type: String,
    required: true,
  },
  tooltip: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <span class="form-label-tooltip">
    <span>{{ label }}</span>
    <el-tooltip v-if="tooltip" placement="top" effect="light" :show-after="120">
      <template #content>
        <div class="form-label-tooltip__content">{{ tooltip }}</div>
      </template>
      <el-icon class="form-label-tooltip__icon"><QuestionFilled /></el-icon>
    </el-tooltip>
  </span>
</template>

<style scoped>
.form-label-tooltip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  line-height: 1.4;
}

.form-label-tooltip__icon {
  color: #7a8ca8;
  cursor: help;
}

.form-label-tooltip__content {
  max-width: 280px;
  white-space: normal;
  line-height: 1.5;
}
</style>
