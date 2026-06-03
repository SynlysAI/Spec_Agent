<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    required: true,
  },
  highlights: {
    type: Array,
    default: () => [],
  },
})
</script>

<template>
  <section class="task-intro-card">
    <div class="task-intro-copy">
      <div class="task-intro-kicker">任务说明</div>
      <h4 class="task-intro-title">{{ title }}</h4>
      <p class="task-intro-description">{{ description }}</p>
    </div>

    <div class="task-intro-results">
      <div class="task-intro-results-title">提交后可得到</div>
      <ul class="task-intro-list">
        <li v-for="item in highlights" :key="item" class="task-intro-item">
          {{ item }}
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.task-intro-card {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.9fr);
  gap: 18px;
  margin-bottom: 18px;
  padding: 18px 20px;
  border: 1px solid #d9e6f5;
  border-radius: 14px;
  background:
    linear-gradient(135deg, rgba(245, 250, 255, 0.98), rgba(237, 245, 255, 0.94)),
    linear-gradient(180deg, #ffffff, #f8fbff);
}

.task-intro-copy {
  min-width: 0;
}

.task-intro-kicker {
  color: #5f7fa8;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.task-intro-title {
  margin: 6px 0 8px;
  color: #15345f;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.4;
}

.task-intro-description {
  margin: 0;
  color: #4b607f;
  font-size: 14px;
  line-height: 1.7;
}

.task-intro-results {
  padding: 14px 16px;
  border: 1px solid rgba(140, 174, 220, 0.32);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.76);
}

.task-intro-results-title {
  color: #1d4f91;
  font-size: 13px;
  font-weight: 700;
}

.task-intro-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.task-intro-item {
  position: relative;
  padding-left: 14px;
  color: #405574;
  font-size: 13px;
  line-height: 1.7;
}

.task-intro-item + .task-intro-item {
  margin-top: 6px;
}

.task-intro-item::before {
  content: '';
  position: absolute;
  top: 9px;
  left: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #4b8de8;
}

@media (max-width: 900px) {
  .task-intro-card {
    grid-template-columns: 1fr;
    gap: 14px;
  }
}
</style>
