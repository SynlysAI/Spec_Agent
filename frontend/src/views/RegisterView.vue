<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { getApiErrorMessage, registerWithInviteCode } from '../api/specAgentApi'

const router = useRouter()
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({
  inviteCode: '',
  username: '',
  password: '',
  confirmPassword: '',
})

/**
 * 校验确认密码是否一致。
 *
 * Args:
 *   _rule: Element Plus 校验规则对象。
 *   value: 当前字段值。
 *   callback: 校验完成回调。
 */
function validateConfirmPassword(_rule, value, callback) {
  if (!value) {
    callback(new Error('请再次输入密码'))
    return
  }
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const rules = {
  inviteCode: [{ required: true, message: '请输入邀请码', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: 'blur' }],
}

/**
 * 提交注册表单。
 *
 * Returns:
 *   Promise<void>
 */
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    await registerWithInviteCode({
      invite_code: form.inviteCode.trim(),
      username: form.username.trim(),
      password: form.password,
    })
    ElMessage.success('注册成功，请登录')
    router.replace('/login')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-background"></div>
    <section class="register-panel">
      <div class="register-brand">
        <div class="register-brand-mark">S</div>
        <div>
          <div class="register-brand-title">Spec Agent</div>
          <div class="register-brand-subtitle">邀请码注册入口</div>
        </div>
      </div>

      <div class="register-heading">
        <h1>创建账号</h1>
        <p>请输入管理员分发的邀请码，完成本地用户注册后再登录系统。</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="register-form">
        <el-form-item label="邀请码" prop="inviteCode">
          <el-input v-model="form.inviteCode" placeholder="请输入邀请码" autocomplete="off" />
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入注册用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            show-password
            placeholder="请再次输入密码"
            autocomplete="new-password"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-button type="primary" class="register-submit" :loading="submitting" @click="handleSubmit">
          注册账号
        </el-button>
      </el-form>

      <div class="register-footer">
        <span>已有账号？</span>
        <router-link class="register-link" to="/login">去登录</router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(26, 119, 255, 0.22), transparent 34%),
    radial-gradient(circle at right 20%, rgba(0, 179, 155, 0.16), transparent 28%),
    linear-gradient(160deg, #071c3a 0%, #0a2a56 48%, #f2f7ff 48%, #edf3fb 100%);
}

.register-background {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.7), transparent 80%);
}

.register-panel {
  position: relative;
  width: min(460px, calc(100vw - 32px));
  padding: 30px 28px 28px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.42);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(20px);
  box-shadow:
    0 22px 58px rgba(7, 31, 67, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.55);
}

.register-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.register-brand-mark {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: #ffffff;
  font-size: 24px;
  font-weight: 700;
  background: linear-gradient(145deg, #155eef, #00a3ad);
  box-shadow: 0 14px 28px rgba(21, 94, 239, 0.28);
}

.register-brand-title {
  color: #0d2449;
  font-size: 22px;
  font-weight: 700;
}

.register-brand-subtitle {
  margin-top: 4px;
  color: #6f82a3;
  font-size: 13px;
}

.register-heading {
  margin-top: 28px;
}

.register-heading h1 {
  margin: 0;
  color: #0f2345;
  font-size: 28px;
}

.register-heading p {
  margin: 10px 0 0;
  color: #627697;
  font-size: 14px;
  line-height: 1.7;
}

.register-form {
  margin-top: 24px;
}

.register-submit {
  width: 100%;
  height: 44px;
  margin-top: 8px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(90deg, #155eef, #008a9e);
  box-shadow: 0 14px 24px rgba(21, 94, 239, 0.22);
}

.register-footer {
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 6px;
  color: #627697;
  font-size: 14px;
}

.register-link {
  color: #155eef;
  font-weight: 600;
  text-decoration: none;
}

@media (max-width: 640px) {
  .register-page {
    align-items: start;
    padding-top: 48px;
    padding-bottom: 24px;
  }

  .register-panel {
    padding: 24px 20px 22px;
    border-radius: 20px;
  }

  .register-heading h1 {
    font-size: 24px;
  }
}
</style>
