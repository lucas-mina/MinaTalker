<template>
  <div class="settings-wrapper">
    <!-- 设置按钮 -->
    <button class="settings-trigger" @click="toggleSettings" :class="{ active: showSettings }" :title="t('settings.title')">
      <i class="bi bi-gear-fill"></i>
    </button>

    <!-- 设置面板 -->
    <transition name="slide-fade">
      <div v-if="showSettings" class="settings-panel">
        <div class="settings-header">
          <h3><i class="bi bi-sliders"></i> {{ t('settings.systemSettings') }}</h3>
          <button class="close-btn" @click="showSettings = false">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>

        <div class="settings-content">
          <!-- WebRTC 设置 -->
          <div class="settings-section">
            <h4><i class="bi bi-broadcast"></i> {{ t('settings.webrtc.title') }}</h4>
            
            <div class="setting-item">
              <div class="setting-label">
                <label for="use-stun">{{ t('settings.webrtc.useStun') }}</label>
                <span class="setting-desc">{{ t('settings.webrtc.useStunDesc') }}</span>
              </div>
              <div class="setting-control">
                <label class="switch">
                  <input type="checkbox" id="use-stun" v-model="settings.useStun">
                  <span class="slider"></span>
                </label>
              </div>
            </div>

            <div class="setting-item" v-if="settings.useStun">
              <div class="setting-label">
                <label for="stun-server">{{ t('settings.webrtc.stunServer') }}</label>
              </div>
              <div class="setting-control">
                <select v-model="settings.stunServer" id="stun-server">
                  <option value="stun:stun.l.google.com:19302">{{ t('settings.webrtc.googleStun') }}</option>
                  <option value="stun:stun.miwifi.com:3478">{{ t('settings.webrtc.xiaomiStun') }}</option>
                  <option value="stun:stun.qq.com:3478">{{ t('settings.webrtc.tencentStun') }}</option>
                  <option value="custom">{{ t('settings.webrtc.customStun') }}</option>
                </select>
              </div>
            </div>

            <div class="setting-item" v-if="settings.useStun && settings.stunServer === 'custom'">
              <div class="setting-label">
                <label for="custom-stun">{{ t('settings.webrtc.customStunAddress') }}</label>
              </div>
              <div class="setting-control">
                <input 
                  type="text" 
                  id="custom-stun" 
                  v-model="settings.customStunServer"
                  placeholder="stun:your-server.com:3478 or turn:host:3478"
                >
              </div>
            </div>
            <div class="setting-item" v-if="settings.useStun">
              <div class="setting-label">
                <label for="turn-username">{{ t('settings.webrtc.turnUsername') }}</label>
                <span class="setting-desc">{{ t('settings.webrtc.turnUsernameDesc') }}</span>
              </div>
              <div class="setting-control">
                <input type="text" id="turn-username" v-model="settings.turnUsername" placeholder="username">
              </div>
            </div>
            <div class="setting-item" v-if="settings.useStun">
              <div class="setting-label">
                <label for="turn-credential">{{ t('settings.webrtc.turnCredential') }}</label>
                <span class="setting-desc">{{ t('settings.webrtc.turnCredentialDesc') }}</span>
              </div>
              <div class="setting-control">
                <input type="password" id="turn-credential" v-model="settings.turnCredential" placeholder="password">
              </div>
            </div>
          </div>

          <!-- Core API login (internal LLM / Bearer) -->
          <div class="settings-section" v-if="showCoreAuth">
            <h4><i class="bi bi-shield-lock"></i> {{ t('settings.coreApi.title') }}</h4>
            <div class="setting-item info-banner">
              <div class="info-content">
                <i class="bi bi-info-circle"></i>
                <div>
                  <p>{{ t('settings.coreApi.desc') }}</p>
                  <p class="core-api-status" :class="{ ok: coreSignedIn }">
                    <i :class="coreSignedIn ? 'bi bi-check-circle-fill' : 'bi bi-circle'"></i>
                    {{ coreSignedIn ? t('settings.coreApi.statusIn') : t('settings.coreApi.statusOut') }}
                  </p>
                </div>
              </div>
            </div>

            <template v-if="!coreSignedIn">
              <div class="setting-item">
                <div class="setting-label">
                  <label for="core-user">{{ t('settings.coreApi.username') }}</label>
                </div>
                <div class="setting-control">
                  <input id="core-user" v-model="coreUsername" type="text" autocomplete="username" class="core-auth-input">
                </div>
              </div>
              <div class="setting-item">
                <div class="setting-label">
                  <label for="core-pass">{{ t('settings.coreApi.password') }}</label>
                </div>
                <div class="setting-control">
                  <input id="core-pass" v-model="corePassword" type="password" autocomplete="current-password" class="core-auth-input">
                </div>
              </div>
              <div class="setting-item core-auth-actions">
                <button type="button" class="btn-primary" :disabled="coreLoginLoading" @click="submitCoreLogin">
                  <i class="bi bi-box-arrow-in-right"></i>
                  {{ coreLoginLoading ? t('settings.coreApi.signingIn') : t('settings.coreApi.signIn') }}
                </button>
              </div>
            </template>
            <div v-else class="setting-item core-auth-actions">
              <button type="button" class="btn-secondary" @click="submitCoreLogout">
                <i class="bi bi-box-arrow-right"></i>
                {{ t('settings.coreApi.signOut') }}
              </button>
            </div>
          </div>

          <!-- 录制设置（前端隐藏，仅保留内部配置） -->
          <div class="settings-section" v-if="showRecordingSettings">
            <h4><i class="bi bi-record-circle"></i> {{ t('settings.recording.title') }}</h4>
            
            <div class="setting-item">
              <div class="setting-label">
                <label for="auto-record">{{ t('settings.recording.autoRecord') }}</label>
                <span class="setting-desc">{{ t('settings.recording.autoRecordDesc') }}</span>
              </div>
              <div class="setting-control">
                <label class="switch">
                  <input type="checkbox" id="auto-record" v-model="settings.autoRecord">
                  <span class="slider"></span>
                </label>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="record-format">{{ t('settings.recording.format') }}</label>
              </div>
              <div class="setting-control">
                <select v-model="settings.recordFormat" id="record-format">
                  <option value="mp4">MP4 (H.264)</option>
                  <option value="webm">WebM (VP8)</option>
                  <option value="avi">AVI</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 界面设置 -->
          <div class="settings-section">
            <h4><i class="bi bi-palette"></i> {{ t('settings.display.title') }}</h4>
            
            <div class="setting-item">
              <div class="setting-label">
                <label for="show-debug">{{ t('settings.display.showDebug') }}</label>
                <span class="setting-desc">{{ t('settings.display.showDebugDesc') }}</span>
              </div>
              <div class="setting-control">
                <label class="switch">
                  <input type="checkbox" id="show-debug" v-model="settings.showDebugPanel">
                  <span class="slider"></span>
                </label>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="show-timestamp">{{ t('settings.display.showTimestamp') }}</label>
                <span class="setting-desc">{{ t('settings.display.showTimestampDesc') }}</span>
              </div>
              <div class="setting-control">
                <label class="switch">
                  <input type="checkbox" id="show-timestamp" v-model="settings.showTimestamp">
                  <span class="slider"></span>
                </label>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="theme">{{ t('settings.display.theme') }}</label>
              </div>
              <div class="setting-control">
                <select v-model="settings.theme" id="theme">
                  <option value="dark">{{ t('settings.display.themeDark') }}</option>
                  <option value="light">{{ t('settings.display.themeLight') }}</option>
                  <option value="auto">{{ t('settings.display.themeAuto') }}</option>
                </select>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="ui-language">{{ t('settings.display.language') }}</label>
              </div>
              <div class="setting-control">
                <select v-model="settings.uiLanguage" id="ui-language">
                  <option value="zh-CN">简体中文</option>
                  <option value="en-US">English</option>
                </select>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="video-size">{{ t('settings.display.videoSize') }}</label>
                <span class="setting-desc">{{ t('settings.display.videoSizeDesc') }}</span>
              </div>
              <div class="setting-control setting-range">
                <input 
                  type="range" 
                  id="video-size" 
                  v-model="settings.videoSize"
                  min="50" 
                  max="150"
                  step="5"
                >
                <span class="range-value">{{ settings.videoSize }}%</span>
              </div>
            </div>
          </div>

          <!-- 语音设置 -->
          <div class="settings-section">
            <h4><i class="bi bi-mic"></i> {{ t('settings.voice.title') }}</h4>
            
            <div class="setting-item info-banner">
              <div class="info-content">
                <i class="bi bi-info-circle"></i>
                <div>
                  <strong>{{ t('settings.voice.currentMode') }}</strong>
                  <p>{{ t('settings.voice.currentModeDesc') }}</p>
                  <p class="note">{{ t('settings.voice.currentModeNote') }}</p>
                </div>
              </div>
            </div>
            
            <div class="setting-item">
              <div class="setting-label">
                <label for="voice-continuous">{{ t('settings.voice.continuous') }}</label>
                <span class="setting-desc">{{ t('settings.voice.continuousDesc') }}</span>
              </div>
              <div class="setting-control">
                <label class="switch">
                  <input type="checkbox" id="voice-continuous" v-model="settings.voiceContinuous">
                  <span class="slider"></span>
                </label>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                <label for="voice-lang">{{ t('settings.voice.language') }}</label>
              </div>
              <div class="setting-control">
                <select v-model="settings.voiceLanguage" id="voice-lang">
                  <option value="auto">{{ t('settings.voice.langAuto') }}</option>
                  <option value="zh-CN">{{ t('settings.voice.langZhCN') }}</option>
                  <option value="en-US">{{ t('settings.voice.langEnUS') }}</option>
                  <option value="ja-JP">{{ t('settings.voice.langJaJP') }}</option>
                  <option value="ko-KR">{{ t('settings.voice.langKoKR') }}</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-footer">
          <button class="btn-secondary" @click="showResetConfirm = true">
            <i class="bi bi-arrow-counterclockwise"></i>
            {{ t('settings.resetDefault') }}
          </button>
          <button class="btn-primary" @click="saveSettings">
            <i class="bi bi-check-lg"></i>
            {{ t('settings.save') }}
          </button>
        </div>
      </div>
    </transition>

    <!-- 确认对话框 -->
    <transition name="fade">
      <div v-if="showResetConfirm" class="confirm-dialog-overlay" @click="showResetConfirm = false">
        <div class="confirm-dialog" @click.stop>
          <div class="confirm-header">
            <i class="bi bi-exclamation-triangle"></i>
            <h4>{{ t('settings.confirmTitle') }}</h4>
          </div>
          <div class="confirm-body">
            {{ t('settings.confirmMessage') }}
          </div>
          <div class="confirm-footer">
            <button class="btn-secondary" @click="showResetConfirm = false">{{ t('settings.cancel') }}</button>
            <button class="btn-danger" @click="resetSettings(); showResetConfirm = false">{{ t('settings.confirm') }}</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 遮罩层 -->
    <transition name="fade">
      <div v-if="showSettings" class="settings-overlay" @click="showSettings = false"></div>
    </transition>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useI18n } from '../composables/useI18n'
import {
  isInternalAuthConfigured,
  getStoredAccessToken,
  loginInternalAuth,
  clearInternalAuth,
  stopAuthRefreshLoop,
} from '../composables/useInternalAuth'

const { t } = useI18n()
const showSettings = ref(false)

const showCoreAuth = computed(() => isInternalAuthConfigured())
const coreSignedIn = ref(false)
const coreUsername = ref('')
const corePassword = ref('')
const coreLoginLoading = ref(false)

function syncCoreSignedIn() {
  coreSignedIn.value = !!getStoredAccessToken()
}

watch(showSettings, (open) => {
  if (open) syncCoreSignedIn()
})

// 是否展示录制相关设置（当前产品阶段隐藏）
const showRecordingSettings = false

// 默认设置
const defaultSettings = {
  // WebRTC
  useStun: true,
  stunServer: 'custom',
  customStunServer: 'turn:101.78.221.190:3478',
  turnUsername: 'username',
  turnCredential: 'password',

  // 录制
  autoRecord: false,
  recordFormat: 'mp4',
  
  // 界面
  showDebugPanel: false,
  showTimestamp: true,
  theme: 'dark',
  uiLanguage: 'en-US',
  videoSize: 100,
  
  // 语音（auto = 服务端自动检测语言）
  voiceContinuous: true,
  voiceLanguage: 'auto'
}

const settings = ref({ ...defaultSettings })

// 定义事件
const emit = defineEmits(['settings-changed', 'notification', 'core-auth-changed'])

const toggleSettings = () => {
  showSettings.value = !showSettings.value
}

const saveSettings = () => {
  // 保存到 localStorage
  localStorage.setItem('linly-talker-stream-settings', JSON.stringify(settings.value))
  
  // 触发设置变更事件
  emit('settings-changed', settings.value)
  
  showSettings.value = false
  
  // 显示提示
  emit('notification', t('notifications.settingsSaved'), 'success')
}

const showResetConfirm = ref(false)

const resetSettings = () => {
  settings.value = { ...defaultSettings }
  localStorage.removeItem('linly-talker-stream-settings')
  emit('settings-changed', settings.value)
  emit('notification', t('notifications.settingsReset'), 'success')
}

// 加载保存的设置
async function submitCoreLogin() {
  const u = coreUsername.value.trim()
  const p = corePassword.value
  if (!u || !p) {
    emit('notification', t('settings.coreApi.fillBoth'), 'warning')
    return
  }
  coreLoginLoading.value = true
  try {
    await loginInternalAuth(u, p)
    corePassword.value = ''
    syncCoreSignedIn()
    emit('core-auth-changed', { loggedIn: true })
    emit('notification', t('notifications.coreLoginOk'), 'success')
  } catch (e) {
    emit('notification', e instanceof Error ? e.message : String(e), 'error')
  } finally {
    coreLoginLoading.value = false
  }
}

function submitCoreLogout() {
  stopAuthRefreshLoop()
  clearInternalAuth()
  syncCoreSignedIn()
  emit('core-auth-changed', { loggedIn: false })
}

onMounted(() => {
  syncCoreSignedIn()
  const savedSettings = localStorage.getItem('linly-talker-stream-settings')
  if (savedSettings) {
    try {
      settings.value = { ...defaultSettings, ...JSON.parse(savedSettings) }
      emit('settings-changed', settings.value)
    } catch (e) {
      console.error('Failed to load settings:', e)
    }
  } else {
    // 首次加载，发送默认设置
    emit('settings-changed', settings.value)
  }
})

// 监听设置变化，自动保存
watch(settings, () => {
  emit('settings-changed', settings.value)
}, { deep: true })
</script>

<style scoped>
.settings-wrapper {
  position: relative;
}

.settings-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.75rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 600;
}

.settings-trigger:hover {
  background: var(--primary);
  border-color: var(--primary);
  transform: translateY(-2px);
}

.settings-trigger.active {
  background: var(--primary);
  border-color: var(--primary);
}

.settings-trigger i {
  font-size: 1.125rem;
}

.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
}

.settings-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 480px;
  height: 100vh;
  height: 100dvh;
  min-height: -webkit-fill-available;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

.settings-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-tertiary);
}

.settings-header h3 {
  margin: 0;
  font-size: 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.settings-section {
  margin-bottom: 2rem;
}

.settings-section h4 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 1rem 0;
  color: var(--primary-light);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--bg-tertiary);
  border-radius: 8px;
  margin-bottom: 0.75rem;
}

.setting-label {
  flex: 1;
}

.setting-label label {
  display: block;
  font-weight: 500;
  margin-bottom: 0.25rem;
  color: var(--text-primary);
}

.setting-desc {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.setting-control {
  margin-left: 1rem;
}

.setting-control select,
.setting-control input[type="text"] {
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
  min-width: 150px;
}

.setting-control select:focus,
.setting-control input[type="text"]:focus {
  outline: none;
  border-color: var(--primary);
}

/* Range Slider */
.setting-range {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-width: 200px;
}

.setting-control input[type="range"] {
  flex: 1;
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 3px;
  outline: none;
  -webkit-appearance: none;
}

.setting-control input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  background: var(--primary);
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s;
}

.setting-control input[type="range"]::-webkit-slider-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2);
}

.setting-control input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  background: var(--primary);
  border-radius: 50%;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.setting-control input[type="range"]::-moz-range-thumb:hover {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2);
}

.range-value {
  font-size: 0.875rem;
  color: var(--primary);
  font-weight: 600;
  min-width: 45px;
  text-align: right;
}

/* Toggle Switch */
.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-secondary);
  border: 2px solid var(--border);
  transition: 0.3s;
  border-radius: 26px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 2px;
  bottom: 2px;
  background: var(--text-muted);
  transition: 0.3s;
  border-radius: 50%;
}

input:checked + .slider {
  background: var(--primary);
  border-color: var(--primary);
}

input:checked + .slider:before {
  transform: translateX(22px);
  background: white;
}

.settings-footer {
  padding: 1.5rem;
  padding-bottom: max(1.5rem, env(safe-area-inset-bottom, 0));
  border-top: 1px solid var(--border);
  display: flex;
  gap: 1rem;
  background: var(--bg-tertiary);
}

.settings-footer button {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-dark);
}

/* 动画 */
.slide-fade-enter-active {
  transition: all 0.3s ease;
}

.slide-fade-leave-active {
  transition: all 0.3s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateX(100%);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 滚动条 */
.settings-content::-webkit-scrollbar {
  width: 6px;
}

.settings-content::-webkit-scrollbar-track {
  background: var(--bg-secondary);
}

.settings-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

/* 信息提示框 */
.info-banner {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.info-content {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
}

.info-content > i {
  font-size: 1.25rem;
  color: var(--primary-light);
  flex-shrink: 0;
  margin-top: 2px;
}

.info-content strong {
  display: block;
  color: var(--primary-light);
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
}

.info-content p {
  margin: 0.25rem 0;
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.info-content .note {
  color: var(--warning);
  font-size: 0.8rem;
  margin-top: 0.5rem;
}

.core-api-status {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 600;
  margin-top: 0.5rem !important;
  color: var(--text-muted) !important;
}

.core-api-status.ok {
  color: var(--success) !important;
}

.core-auth-input {
  width: 100%;
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.9rem;
}

.core-auth-actions {
  margin-top: 0.5rem;
}

.core-auth-actions .btn-primary,
.core-auth-actions .btn-secondary {
  width: 100%;
  justify-content: center;
}

.settings-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* 响应式 */
@media (max-width: 768px) {
  .settings-panel {
    width: 100%;
  }
}

/* 确认对话框 */
.confirm-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
}

.confirm-dialog {
  background: var(--bg-secondary);
  border-radius: 12px;
  min-width: 400px;
  max-width: 500px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
  border: 1px solid var(--border);
}

.confirm-header {
  padding: 1.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.confirm-header i {
  font-size: 1.5rem;
  color: var(--warning);
}

.confirm-header h4 {
  margin: 0;
  font-size: 1.125rem;
  color: var(--text-primary);
}

.confirm-body {
  padding: 1.5rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.confirm-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-danger {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--danger);
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}

@media (max-width: 768px) {
  .confirm-dialog {
    min-width: auto;
    width: 90%;
    max-width: 400px;
  }
}
</style>
