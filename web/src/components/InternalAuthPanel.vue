<!-- Linly-Talker-Stream. Sign in to core API for Bearer token (internal LLM / WS). -->
<template>
  <div class="internal-auth-gate">
    <div class="internal-auth-box">
      <p class="internal-auth-title">{{ t('internalAuth.title') }}</p>
      <p class="internal-auth-hint">{{ t('internalAuth.hint') }}</p>

      <label class="internal-auth-label">{{ t('internalAuth.username') }}</label>
      <input
        v-model="username"
        type="text"
        class="internal-auth-input"
        autocomplete="username"
        :disabled="loading"
        @keydown.enter="submit"
      />

      <label class="internal-auth-label">{{ t('internalAuth.password') }}</label>
      <input
        v-model="password"
        type="password"
        class="internal-auth-input"
        autocomplete="current-password"
        :disabled="loading"
        @keydown.enter="submit"
      />

      <p v-if="error" class="internal-auth-error">{{ error }}</p>

      <div class="internal-auth-actions">
        <button type="button" class="internal-auth-btn primary" :disabled="loading" @click="submit">
          <span v-if="loading" class="spin-inline"><i class="bi bi-hourglass-split"></i></span>
          {{ loading ? t('internalAuth.signingIn') : t('internalAuth.signIn') }}
        </button>
        <button
          v-if="allowSkip"
          type="button"
          class="internal-auth-btn ghost"
          :disabled="loading"
          @click="skip"
        >
          {{ t('internalAuth.skip') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../composables/useI18n'
import { loginInternalAuth } from '../composables/useInternalAuth'

const emit = defineEmits(['logged-in', 'skipped'])

const { t } = useI18n()

const allowSkip = import.meta.env.VITE_INTERNAL_AUTH_OPTIONAL === 'true'

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  const u = username.value.trim()
  const p = password.value
  if (!u || !p) {
    error.value = t('internalAuth.fillBoth')
    return
  }
  loading.value = true
  try {
    await loginInternalAuth(u, p)
    emit('logged-in')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function skip() {
  sessionStorage.setItem('internal_auth_skip', '1')
  emit('skipped')
}
</script>

<style scoped>
.internal-auth-gate {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
  padding: 1.5rem;
}

.internal-auth-box {
  width: 100%;
  max-width: 400px;
  background: rgba(30, 41, 59, 0.95);
  border: 1px solid #475569;
  border-radius: 12px;
  padding: 1.75rem;
  box-shadow: var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.4));
}

.internal-auth-title {
  font-size: 1.15rem;
  font-weight: 600;
  color: #f8fafc;
  margin-bottom: 0.35rem;
}

.internal-auth-hint {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-bottom: 1.25rem;
  line-height: 1.4;
}

.internal-auth-label {
  display: block;
  font-size: 0.75rem;
  color: #cbd5e1;
  margin-bottom: 0.35rem;
}

.internal-auth-input {
  width: 100%;
  padding: 0.65rem 0.75rem;
  border-radius: 8px;
  border: 1px solid #475569;
  background: #0f172a;
  color: #f8fafc;
  margin-bottom: 0.85rem;
  font-size: 0.95rem;
}

.internal-auth-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}

.internal-auth-error {
  color: #f87171;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.internal-auth-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-top: 0.5rem;
}

.internal-auth-btn {
  flex: 1;
  min-width: 120px;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  font-size: 0.9rem;
}

.internal-auth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.internal-auth-btn.primary {
  background: #6366f1;
  color: #fff;
}

.internal-auth-btn.primary:hover:not(:disabled) {
  background: #4f46e5;
}

.internal-auth-btn.ghost {
  background: transparent;
  color: #94a3b8;
  border: 1px solid #475569;
}

.internal-auth-btn.ghost:hover:not(:disabled) {
  color: #e2e8f0;
  border-color: #64748b;
}

.spin-inline i {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
