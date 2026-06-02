<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { getApiErrorMessage, listAdminUsers, updateAdminUserStatus } from '../api/specAgentApi'

const loading = ref(false)
const tableData = ref([])
const updatingUserId = ref('')

const activeUserCount = computed(() => tableData.value.filter((item) => item.status === 'active').length)
const disabledUserCount = computed(() => tableData.value.filter((item) => item.status === 'disabled').length)

/**
 * 按用户名与用户 ID 对用户列表排序。
 *
 * Args:
 *   items: 原始用户列表。
 *
 * Returns:
 *   排序后的用户列表。
 */
function sortUsers(items) {
  return [...items].sort((left, right) => {
    const usernameCompare = String(left.username || '').localeCompare(String(right.username || ''), 'zh-Hans-CN')
    if (usernameCompare !== 0) {
      return usernameCompare
    }
    return String(left.user_id || '').localeCompare(String(right.user_id || ''), 'zh-Hans-CN')
  })
}

/**
 * 转换角色显示文案。
 *
 * Args:
 *   role: 角色编码。
 *
 * Returns:
 *   角色中文标签。
 */
function formatRoleLabel(role) {
  if (role === 'admin') {
    return '管理员'
  }
  if (role === 'user') {
    return '普通用户'
  }
  return role || '-'
}

/**
 * 转换状态显示文案。
 *
 * Args:
 *   status: 状态编码。
 *
 * Returns:
 *   状态中文标签。
 */
function formatStatusLabel(status) {
  if (status === 'active') {
    return '启用'
  }
  if (status === 'disabled') {
    return '禁用'
  }
  return status || '-'
}

/**
 * 根据状态返回标签类型。
 *
 * Args:
 *   status: 用户状态。
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
  return 'info'
}

/**
 * 查询管理员用户列表。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchAdminUsers() {
  loading.value = true
  try {
    const data = await listAdminUsers()
    tableData.value = sortUsers(data?.items || [])
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

/**
 * 判断指定用户是否允许禁用。
 *
 * Args:
 *   user: 用户列表项。
 *
 * Returns:
 *   是否允许执行禁用操作。
 */
function canDisableUser(user) {
  return user?.status === 'active' && user?.role !== 'admin'
}

/**
 * 判断指定用户是否允许启用。
 *
 * Args:
 *   user: 用户列表项。
 *
 * Returns:
 *   是否允许执行启用操作。
 */
function canEnableUser(user) {
  return user?.status === 'disabled'
}

/**
 * 更新指定用户状态。
 *
 * Args:
 *   user: 当前用户列表项。
 *   nextStatus: 目标状态。
 *
 * Returns:
 *   Promise<void>
 */
async function handleUpdateStatus(user, nextStatus) {
  const userId = user?.user_id
  if (!userId || user.status === nextStatus) {
    return
  }

  const actionLabel = nextStatus === 'active' ? '启用' : '禁用'
  try {
    await ElMessageBox.confirm(
      `确认${actionLabel}用户“${user.username || userId}”吗？`,
      '状态变更确认',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  updatingUserId.value = userId
  try {
    await updateAdminUserStatus(userId, { status: nextStatus })
    ElMessage.success(`用户已${actionLabel}`)
    await fetchAdminUsers()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    updatingUserId.value = ''
  }
}

onMounted(fetchAdminUsers)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">用户管理</h3>
        <p class="panel-subtitle">当前共 {{ tableData.length }} 个用户，启用 {{ activeUserCount }} 个，禁用 {{ disabledUserCount }} 个。</p>
      </div>
      <el-button type="primary" plain :loading="loading" @click="fetchAdminUsers">刷新</el-button>
    </div>
    <div class="panel-body">
      <el-table v-loading="loading" :data="tableData" empty-text="暂无用户数据">
        <el-table-column prop="username" label="用户名" min-width="180" />
        <el-table-column label="角色" min-width="120">
          <template #default="{ row }">
            <el-tag effect="plain" :type="row.role === 'admin' ? 'warning' : 'info'">
              {{ formatRoleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="resolveStatusTagType(row.status)">
              {{ formatStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="180" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button
                v-if="canDisableUser(row)"
                type="danger"
                link
                :loading="updatingUserId === row.user_id"
                @click="handleUpdateStatus(row, 'disabled')"
              >
                禁用
              </el-button>
              <el-button
                v-if="canEnableUser(row)"
                type="primary"
                link
                :loading="updatingUserId === row.user_id"
                @click="handleUpdateStatus(row, 'active')"
              >
                启用
              </el-button>
              <span v-if="!canDisableUser(row) && !canEnableUser(row)" class="table-action-placeholder">-</span>
            </div>
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

.table-actions {
  display: flex;
  align-items: center;
  min-height: 24px;
}

.table-action-placeholder {
  color: #98a2b3;
}
</style>
