<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createInviteCode, disableInviteCode, getApiErrorMessage, listInviteCodes } from '../api/specAgentApi'

const loading = ref(false)
const creating = ref(false)
const disablingInviteId = ref('')
const tableData = ref([])
const latestCreatedCode = ref('')

const formModel = reactive({
  expires_hours: 72,
  max_uses: 1,
})

const activeInviteCount = computed(() => tableData.value.filter((item) => item.status === 'active').length)

/**
 * 按创建时间倒序排序邀请码列表。
 *
 * Args:
 *   items: 原始邀请码列表。
 *
 * Returns:
 *   排序后的邀请码列表。
 */
function sortInviteCodes(items) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.created_at || 0).getTime()
    const rightTime = new Date(right.created_at || 0).getTime()
    return rightTime - leftTime
  })
}

/**
 * 将时间格式化为可读字符串。
 *
 * Args:
 *   value: 时间字符串。
 *
 * Returns:
 *   格式化后的时间。
 */
function formatDateTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

/**
 * 转换邀请码状态中文文案。
 *
 * Args:
 *   status: 邀请码状态编码。
 *
 * Returns:
 *   状态中文标签。
 */
function formatStatusLabel(status) {
  if (status === 'active') {
    return '可用'
  }
  if (status === 'disabled') {
    return '已禁用'
  }
  if (status === 'expired') {
    return '已过期'
  }
  if (status === 'used_up') {
    return '已用尽'
  }
  return status || '-'
}

/**
 * 根据邀请码状态生成标签类型。
 *
 * Args:
 *   status: 邀请码状态。
 *
 * Returns:
 *   Element Plus 标签类型。
 */
function resolveStatusTagType(status) {
  if (status === 'active') {
    return 'success'
  }
  if (status === 'disabled') {
    return 'danger'
  }
  if (status === 'expired' || status === 'used_up') {
    return 'warning'
  }
  return 'info'
}

/**
 * 查询邀请码列表。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchInviteCodes() {
  loading.value = true
  try {
    const data = await listInviteCodes()
    tableData.value = sortInviteCodes(data?.items || [])
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

/**
 * 创建邀请码。
 *
 * Returns:
 *   Promise<void>
 */
async function handleCreateInviteCode() {
  creating.value = true
  try {
    const data = await createInviteCode({
      expires_hours: Number(formModel.expires_hours),
      max_uses: Number(formModel.max_uses),
    })
    latestCreatedCode.value = data?.invite_code || ''
    ElMessage.success('邀请码创建成功')
    await fetchInviteCodes()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    creating.value = false
  }
}

/**
 * 禁用指定邀请码。
 *
 * Args:
 *   invite: 邀请码列表项。
 *
 * Returns:
 *   Promise<void>
 */
async function handleDisableInvite(invite) {
  const inviteId = invite?.invite_id
  if (!inviteId || invite.status !== 'active') {
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认禁用邀请码“${invite.invite_code}”吗？`,
      '禁用确认',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  disablingInviteId.value = inviteId
  try {
    await disableInviteCode(inviteId)
    ElMessage.success('邀请码已禁用')
    await fetchInviteCodes()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    disablingInviteId.value = ''
  }
}

onMounted(fetchInviteCodes)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">邀请码管理</h3>
        <p class="panel-subtitle">当前共 {{ tableData.length }} 个邀请码，其中可用 {{ activeInviteCount }} 个。</p>
      </div>
      <el-button type="primary" plain :loading="loading" @click="fetchInviteCodes">刷新</el-button>
    </div>
    <div class="panel-body">
      <el-alert
        v-if="latestCreatedCode"
        class="invite-alert"
        title="最新创建的邀请码"
        type="success"
        :closable="false"
      >
        <template #default>
          <span class="invite-code-text">{{ latestCreatedCode }}</span>
        </template>
      </el-alert>

      <el-form inline class="create-form">
        <el-form-item label="有效期（小时）">
          <el-input-number v-model="formModel.expires_hours" :min="1" :max="720" :step="1" />
        </el-form-item>
        <el-form-item label="最大使用次数">
          <el-input-number v-model="formModel.max_uses" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="creating" @click="handleCreateInviteCode">创建邀请码</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="tableData" empty-text="暂无邀请码数据">
        <el-table-column prop="invite_code" label="邀请码" min-width="220" />
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="resolveStatusTagType(row.status)">
              {{ formatStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="有效期" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.expires_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="max_uses" label="最大次数" min-width="100" />
        <el-table-column prop="used_count" label="已使用次数" min-width="120" />
        <el-table-column label="操作" min-width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              type="danger"
              link
              :loading="disablingInviteId === row.invite_id"
              @click="handleDisableInvite(row)"
            >
              禁用
            </el-button>
            <span v-else class="table-action-placeholder">-</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.panel-subtitle {
  margin: 8px 0 0;
  color: #7b8798;
  font-size: 13px;
}

.invite-alert {
  margin-bottom: 16px;
}

.invite-code-text {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  letter-spacing: 0.3px;
}

.create-form {
  margin-bottom: 16px;
}

.table-action-placeholder {
  color: #98a2b3;
}
</style>
