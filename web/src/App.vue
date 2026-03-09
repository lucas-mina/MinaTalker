<!-- Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0. -->
<template>
  <!-- Password gate: show prompt until correct password entered -->
  <div v-if="!passwordUnlocked" class="password-gate">
    <div class="password-gate-box">
      <p class="password-gate-label">Enter password</p>
      <input
        v-model="passwordInput"
        type="password"
        class="password-gate-input"
        placeholder="Password"
        @keydown.enter="submitPassword"
      />
      <p v-if="passwordError" class="password-gate-error">{{ passwordError }}</p>
      <button type="button" class="password-gate-btn" @click="submitPassword">Enter</button>
    </div>
  </div>

  <template v-else>
  <!-- Avatar selection screen -->
  <SelectView v-if="!avatarSelected" @avatar-selected="onAvatarSelected" />

  <div v-else class="page-container">
    <!-- Full-screen video background -->
    <div class="video-container">
      <video id="video" autoplay playsinline class="remote-video"></video>

      <!-- Video idle overlay (no connection) -->
      <div class="video-idle-overlay" v-if="!isConnected">
        <div class="idle-content">
          <div class="idle-icon">
            <i class="bi bi-hourglass-split spin" v-if="!backendReady"></i>
            <i class="bi bi-person-standing-dress" v-else></i>
          </div>
          <p class="idle-text">{{ backendReady ? t('video.overlayTextReady') : t('video.overlayTextLoading') }}</p>
        </div>
      </div>

      <!-- Top header overlay -->
      <div class="top-header">
        <div class="header-left">
          <div class="logo-badge">
            <i class="bi bi-robot"></i>
            <span>{{ t('header.title') }}</span>
          </div>
          <div class="status-badge" :class="statusClass">
            <span class="status-dot"></span>
            <span class="status-text">{{ statusText }}</span>
          </div>
          <div class="session-chip" v-if="sessionId > 0">
            <i class="bi bi-hash"></i>
            <span>{{ sessionId }}</span>
          </div>
        </div>
        <div class="header-right">
          <button class="btn-back-select" @click="goToSelect" :title="t('header.backToSelect')">
            <i class="bi bi-grid-3x3-gap-fill"></i>
          </button>
          <SettingsPanel 
            @settings-changed="onSettingsChanged" 
            @notification="showNotification"
          />
        </div>
      </div>

      <!-- Recording badge -->
      <div class="recording-badge" v-if="SHOW_RECORDING_UI && isRecording">
        <i class="bi bi-record-circle"></i>
        {{ t('video.recording') }}
      </div>

      <!-- Chat records overlay (left side) -->
      <div class="chat-records-overlay" v-if="isConnected && showChatRecords">
        <div class="messages-list" ref="messagesRef">
          <div 
            v-for="(msg, index) in chatMessages" 
            :key="index"
            class="chat-bubble"
            :class="msg.type === 'user' ? 'bubble-user' : 'bubble-ai'"
          >
            <div class="bubble-meta">
              <i :class="msg.type === 'user' ? 'bi bi-person-circle' : 'bi bi-robot'"></i>
              <span>{{ msg.type === 'user' ? t('chat.you') : currentAvatarName }}</span>
              <span class="bubble-time" v-if="appSettings.showTimestamp">{{ msg.time }}</span>
            </div>
            <div class="bubble-text" v-html="renderMarkdown(msg.text)"></div>
          </div>
          <div v-if="isThinking" class="chat-bubble bubble-ai">
            <div class="bubble-meta">
              <i class="bi bi-robot"></i>
              <span>{{ currentAvatarName }}</span>
            </div>
            <div class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- TTS overlay panel -->
      <div class="tts-overlay" v-if="isConnected && activeMode === 'tts'">
        <div class="tts-panel">
          <div class="tts-panel-header">
            <i class="bi bi-file-text"></i>
            <span>{{ t('chat.ttsTitle') }}</span>
            <button class="icon-btn-sm" @click="activeMode = 'chat'">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          <textarea 
            v-model="ttsInput"
            :placeholder="t('chat.ttsInputPlaceholder')"
            rows="6"
          ></textarea>
          <button 
            class="tts-send-btn" 
            @click="sendTTSMessage" 
            :disabled="!ttsInput.trim()"
          >
            <i class="bi bi-play-circle-fill"></i>
            {{ t('chat.ttsButton') }}
          </button>
        </div>
      </div>

      <!-- Right side action buttons -->
      <div class="side-actions" v-if="isConnected">
        <button 
          class="side-btn"
          :class="{ active: showChatRecords }"
          @click="showChatRecords = !showChatRecords"
          :title="t('chat.title')"
        >
          <i class="bi bi-chat-dots"></i>
        </button>
        <button 
          class="side-btn"
          :class="{ active: activeMode === 'tts' }"
          @click="activeMode = activeMode === 'tts' ? 'chat' : 'tts'"
          :title="t('chat.ttsMode')"
        >
          <i class="bi bi-volume-up"></i>
        </button>
        <button
          class="side-btn"
          @click="triggerFlowerMode"
          :title="'Send Flower'"
        >
          <i class="bi bi-flower1"></i>
        </button>
        <button 
          v-if="SHOW_RECORDING_UI"
          class="side-btn"
          @click="handleStartRecord"
          :disabled="isRecording"
          :title="t('video.startRecord')"
        >
          <i class="bi bi-record-fill"></i>
        </button>
        <button 
          v-if="SHOW_RECORDING_UI"
          class="side-btn"
          @click="handleStopRecord"
          :disabled="!isRecording"
          :title="t('video.stopRecord')"
        >
          <i class="bi bi-stop-fill"></i>
        </button>
        <button 
          v-if="SHOW_RECORDING_UI"
          class="side-btn download-side-btn"
          @click="downloadRecord"
          :disabled="!lastRecordFile"
          :title="t('video.download')"
        >
          <i class="bi bi-download"></i>
        </button>
      </div>

      <!-- Bottom input overlay -->
      <div class="bottom-overlay">
        <!-- Connect / Disconnect button (when not connected) -->
        <div class="connect-row" v-if="!isConnected">
          <button 
            class="connect-btn" 
            @click="handleStartConnection"
            :disabled="!backendReady"
            :class="{ loading: connectionStatus === 'connecting' }"
          >
            <i class="bi bi-hourglass-split spin" v-if="!backendReady || connectionStatus === 'connecting'"></i>
            <i class="bi bi-play-circle-fill" v-else></i>
            {{ !backendReady ? t('video.backendStarting') : connectionStatus === 'connecting' ? t('header.status.connecting') : t('video.connect') }}
          </button>
        </div>

        <!-- Chat input row (when connected, chat mode) -->
        <div class="input-row" v-if="isConnected && activeMode === 'chat'">
          <div class="input-pill">
            <textarea 
              v-model="chatInput"
              @keydown.enter.exact.prevent="sendChatMessage"
              :placeholder="t('chat.inputPlaceholder')"
              rows="1"
              class="chat-textarea"
            ></textarea>
            <button 
              v-if="chatInput.trim()"
              class="clear-input-btn"
              @click="clearInput"
            >
              <i class="bi bi-x-circle-fill"></i>
            </button>
          </div>
          <button 
            class="voice-pill-btn"
            @mousedown="handleVoiceButtonPress"
            @mouseup="handleVoiceButtonRelease"
            @click="handleVoiceButtonClick"
            @touchstart.prevent="handleVoiceButtonPress"
            @touchend.prevent="handleVoiceButtonTouchEnd"
            :class="{ recording: isRecordingVoice && !isVoiceMuted, muted: isVoiceMuted, 'continuous-mode': appSettings.voiceContinuous }"
            :title="getVoiceButtonTitle"
          >
            <div class="voice-icon-wrapper">
              <i :class="isVoiceMuted ? 'bi bi-mic-mute-fill' : 'bi bi-mic-fill'"></i>
              <span v-if="isRecordingVoice && !isVoiceMuted" class="recording-pulse"></span>
            </div>
          </button>
          <button 
            class="send-pill-btn" 
            @click="sendChatMessage" 
            :disabled="!chatInput.trim()"
          >
            <i class="bi bi-send-fill"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Debug panel -->
    <DebugPanel 
      v-if="appSettings.showDebugPanel"
      :connection-status="connectionStatus"
      :session-id="sessionId"
    />
    
    <input type="hidden" id="sessionid" :value="sessionId">
    
    <!-- Notifications -->
    <div class="notification-container">
      <transition-group name="notification">
        <div 
          v-for="notification in notifications" 
          :key="notification.id"
          class="notification"
          :class="notification.type"
        >
          <i :class="getNotificationIcon(notification.type)"></i>
          <span>{{ notification.message }}</span>
        </div>
      </transition-group>
    </div>
  </div>
  </template>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import SelectView from './components/SelectView.vue'
import DebugPanel from './components/DebugPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { useWebRTC } from './composables/useWebRTC'
import { useSpeechRecognition } from './composables/useSpeechRecognition'
import { createSherpaVadSession } from './composables/useSherpaVad'
import { useI18n } from './composables/useI18n'
import { marked } from 'marked'
import hljs from 'highlight.js'

// 配置 marked
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (err) {
        console.error('代码高亮失败:', err)
      }
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true
})

const { t, setLocale, loadLocale } = useI18n()

// ── Password gate ────────────────────────────────────────────────────────────
const PASSWORD = 'anim'
const passwordUnlocked = ref(!!sessionStorage.getItem('mina_password_unlocked'))
const passwordInput = ref('')
const passwordError = ref('')

function submitPassword() {
  passwordError.value = ''
  if (passwordInput.value === PASSWORD) {
    sessionStorage.setItem('mina_password_unlocked', '1')
    passwordUnlocked.value = true
  } else {
    passwordError.value = 'Incorrect password'
  }
}

// ── Avatar selection gate ────────────────────────────────────────────────────
const avatarSelected = ref(!!sessionStorage.getItem('selectedAvatar'))

const currentAvatarName = ref('Mina')
try {
  const _stored = sessionStorage.getItem('selectedAvatar')
  if (_stored) {
    const _parsed = JSON.parse(_stored)
    if (_parsed?.name) currentAvatarName.value = _parsed.name
  }
} catch (_) {}

function onAvatarSelected(avatar) {
  // Only live avatars enter the chat UI; others are handled inside SelectView
  if (avatar.live) {
    currentAvatarName.value = avatar.name || 'Mina'
    avatarSelected.value = true
    // Set welcome message with this avatar's name (sessionStorage already set by SelectView)
    const welcomeText = t('chat.welcomeMessage', { avatarName: currentAvatarName.value })
    chatMessages.value = [{ type: 'ai', text: welcomeText, time: getCurrentTime() }]
    // Auto-connect: attempt once view is ready, or when backend becomes ready (see watcher)
    shouldAutoConnectAfterAvatar.value = true
    nextTick(() => {
      if (backendReady.value && connectionStatus.value === 'disconnected') {
        shouldAutoConnectAfterAvatar.value = false
        handleStartConnection()
      }
    })
  }
}

// Markdown 渲染函数
const renderMarkdown = (text) => {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch (error) {
    console.error('Markdown 解析错误:', error)
    return text
  }
}

const sessionId = ref(0)
const connectionStatus = ref('disconnected')
const isRecording = ref(false)
const activeMode = ref('chat')
const chatInput = ref('')
const ttsInput = ref('')
const isThinking = ref(false)
const isRecordingVoice = ref(false)
const isVoiceMuted = ref(/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || ''))
const antiEchoEnabled = ref(true)
const antiEchoDuckedVolume = 0.2
const defaultRemoteVolume = 1.0
const isMobileClient = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')
const antiEchoMobileVolume = 0.0
let ignoreNextVoiceClick = false
let lastVoiceToggleAt = 0
const voiceToggleDebounceMs = 400
const messagesRef = ref(null)
const notifications = ref([])
let notificationIdCounter = 0
const lastRecordFile = ref(null)
const backendReady = ref(false)
const showChatRecords = ref(true)
/** When true, we should auto-connect once (after avatar select or when backend becomes ready) */
const shouldAutoConnectAfterAvatar = ref(false)
/** ASR mode from server config: 'server' = use server ASR only; 'browser' | 'auto' = may use browser speech */
const asrModeFromServer = ref('browser')
const avatarSpeaking = ref(false)
let avatarSpeakPollTimer = null
let avatarSpeakWsReady = false
let lastAvatarSpeakingAt = 0
const avatarSpeakCooldownMs = 1200
let wsHumanRequestSeq = 0
const wsHumanPending = new Map()

// 是否在界面中展示录制相关按钮
const SHOW_RECORDING_UI = false

// 应用设置
const appSettings = ref({
  useStun: true,
  stunServer: 'custom',
  customStunServer: 'turn:101.78.221.190:3478',
  turnUsername: 'username',
  turnCredential: 'password',
  autoRecord: false,
  recordFormat: 'mp4',
  showDebugPanel: false,
  showTimestamp: true,
  theme: 'dark',
  uiLanguage: 'en-US',
  videoSize: 100,
  voiceContinuous: true,
  voiceLanguage: 'auto'
})

const chatMessages = ref([
  { 
    type: 'ai', 
    text: '',  // 将在 onMounted 中设置
    time: getCurrentTime()
  }
])

const isConnected = computed(() => connectionStatus.value === 'connected')

const statusClass = computed(() => {
  return {
    'status-connected': connectionStatus.value === 'connected',
    'status-connecting': connectionStatus.value === 'connecting',
    'status-disconnected': connectionStatus.value === 'disconnected'
  }
})

const statusText = computed(() => {
  const statusMap = {
    'connected': t('header.status.connected'),
    'connecting': t('header.status.connecting'),
    'disconnected': t('header.status.disconnected')
  }
  return statusMap[connectionStatus.value] || t('header.status.disconnected')
})

const getVoiceButtonTitle = computed(() => {
  if (!isConnected.value) {
    return t('tooltips.voiceDisabled')
  }
  if (asrModeFromServer.value === 'server') {
    return isVoiceMuted.value ? t('tooltips.voiceUnmute') : t('tooltips.voiceMute')
  }
  if (appSettings.value.voiceContinuous) {
    return isRecordingVoice.value ? t('tooltips.voiceRecording') : t('tooltips.voiceContinuous')
  }
  return t('tooltips.voiceHold')
})

function getCurrentTime() {
  const now = new Date()
  return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
}

function getWelcomeMessage() {
  return t('chat.welcomeMessage', { avatarName: currentAvatarName.value })
}

// Navigate back to avatar selection page
const goToSelect = () => {
  // Stop any active connection first so the old session is torn down
  if (connectionStatus.value !== 'disconnected') {
    handleStopConnection()
  }

  // Reset all session/chat state
  connectionStatus.value = 'disconnected'
  sessionId.value = 0
  chatMessages.value = [{ type: 'ai', text: getWelcomeMessage(), time: getCurrentTime() }]
  chatInput.value = ''
  ttsInput.value = ''
  isThinking.value = false
  isRecordingVoice.value = false
  isVoiceMuted.value = false
  activeMode.value = 'chat'
  showChatRecords.value = true

  currentAvatarName.value = 'Mina'
  sessionStorage.removeItem('selectedAvatar')
  avatarSelected.value = false
  shouldAutoConnectAfterAvatar.value = false
}

// 通知系统
const showNotification = (message, type = 'info') => {
  const id = notificationIdCounter++
  const notification = { id, message, type }
  notifications.value.push(notification)
  
  // 3秒后自动移除
  setTimeout(() => {
    const index = notifications.value.findIndex(n => n.id === id)
    if (index > -1) {
      notifications.value.splice(index, 1)
    }
  }, 3000)
}

const getNotificationIcon = (type) => {
  switch (type) {
    case 'success': return 'bi bi-check-circle-fill'
    case 'error': return 'bi bi-x-circle-fill'
    case 'warning': return 'bi bi-exclamation-triangle-fill'
    default: return 'bi bi-info-circle-fill'
  }
}

const handleWsMessage = (msg) => {
  if (msg?.type === 'speaking_state') {
    avatarSpeakWsReady = true
    const speaking = !!msg.speaking
    avatarSpeaking.value = speaking
    if (speaking) {
      lastAvatarSpeakingAt = Date.now()
    }
    return
  }

  if (msg?.type === 'human_response') {
    const requestId = msg.request_id
    if (!requestId || !wsHumanPending.has(requestId)) return
    const pending = wsHumanPending.get(requestId)
    wsHumanPending.delete(requestId)
    clearTimeout(pending.timeoutId)
    pending.resolve(msg)
  }
}

const { startPlay, stopPlay, sendWsMessage, getSignalingSocket } = useWebRTC({
  onNotification: showNotification,
  onWsMessage: handleWsMessage
})

// 设置变更处理
const onSettingsChanged = (newSettings) => {
  appSettings.value = { ...newSettings }
  console.log('设置已更新:', appSettings.value)
  
  // 更新语音识别设置
  if (updateSettings) {
    updateSettings({
      language: newSettings.voiceLanguage,
      continuous: newSettings.voiceContinuous
    })
  }
  
  // 更新视频大小
  updateVideoSize(newSettings.videoSize)
  
  // 更新主题
  updateTheme(newSettings.theme)
  
  // 更新界面语言
  if (newSettings.uiLanguage) {
    setLocale(newSettings.uiLanguage)
  }
}

const updateVideoSize = (size) => {
  const video = document.getElementById('video')
  if (video) {
    video.style.width = `${size}%`
  }
}

// 更新主题
const updateTheme = (theme) => {
  const root = document.documentElement
  
  if (theme === 'auto') {
    // 跟随系统
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    theme = prefersDark ? 'dark' : 'light'
  }
  
  if (theme === 'light') {
    // 浅色模式
    root.style.setProperty('--primary', '#6366f1')
    root.style.setProperty('--primary-dark', '#4f46e5')
    root.style.setProperty('--primary-light', '#818cf8')
    root.style.setProperty('--success', '#10b981')
    root.style.setProperty('--warning', '#f59e0b')
    root.style.setProperty('--danger', '#ef4444')
    root.style.setProperty('--bg-primary', '#ffffff')
    root.style.setProperty('--bg-secondary', '#f8fafc')
    root.style.setProperty('--bg-tertiary', '#e2e8f0')
    root.style.setProperty('--text-primary', '#0f172a')
    root.style.setProperty('--text-secondary', '#475569')
    root.style.setProperty('--text-muted', '#64748b')
    root.style.setProperty('--border', '#cbd5e1')
    root.style.setProperty('--shadow', '0 4px 6px -1px rgba(0, 0, 0, 0.1)')
    root.style.setProperty('--shadow-lg', '0 10px 15px -3px rgba(0, 0, 0, 0.15)')
    root.style.setProperty('--bg-gradient', 'linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%)')
  } else {
    // 深色模式（默认）
    root.style.setProperty('--primary', '#6366f1')
    root.style.setProperty('--primary-dark', '#4f46e5')
    root.style.setProperty('--primary-light', '#818cf8')
    root.style.setProperty('--success', '#10b981')
    root.style.setProperty('--warning', '#f59e0b')
    root.style.setProperty('--danger', '#ef4444')
    root.style.setProperty('--bg-primary', '#0f172a')
    root.style.setProperty('--bg-secondary', '#1e293b')
    root.style.setProperty('--bg-tertiary', '#334155')
    root.style.setProperty('--text-primary', '#f8fafc')
    root.style.setProperty('--text-secondary', '#cbd5e1')
    root.style.setProperty('--text-muted', '#94a3b8')
    root.style.setProperty('--border', '#475569')
    root.style.setProperty('--shadow', '0 4px 6px -1px rgba(0, 0, 0, 0.3)')
    root.style.setProperty('--shadow-lg', '0 10px 15px -3px rgba(0, 0, 0, 0.4)')
    root.style.setProperty('--bg-gradient', 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)')
  }
}

// 检查后端是否就绪，并拉取 ASR 等公开配置
const checkBackendReady = async () => {
  try {
    const response = await fetch('/health')
    if (response.ok) {
      const data = await response.json()
      if (data.ready) {
        backendReady.value = true
        console.log('✅ 后端已就绪')
        try {
          const configRes = await fetch('/config')
          if (configRes.ok) {
            const configData = await configRes.json()
            const mode = configData?.asr?.mode ?? 'browser'
            const type = configData?.asr?.type ?? 'whisper'
            asrModeFromServer.value = mode
            if (mode === 'server') console.log(`✅ ASR 模式: 服务端 ${type} + VAD`)
          }
        } catch (_) {}
        return true
      }
    }
  } catch (error) {
    console.log('⏳ 等待后端启动...')
  }
  return false
}

const handleStartConnection = async (isRetry = false) => {
  console.log('🚀 用户点击"开始连接"按钮')
  
  // 再次确认后端是否就绪
  if (!backendReady.value) {
    showNotification(t('notifications.backendNotReady'), 'warning')
    return
  }
  
  // 防止快速重复点击导致多个 startPlay 同时进行（WebRTC 状态错乱）
  if (connectionStatus.value === 'connecting' && !isRetry) {
    return
  }
  
  connectionStatus.value = 'connecting'
  
  try {
    // 使用设置中的 STUN/TURN 配置（支持 TURN 用户名/密码）
    let iceConfig = null
    if (appSettings.value.useStun) {
      const url = appSettings.value.stunServer === 'custom'
        ? (appSettings.value.customStunServer || '').trim()
        : (appSettings.value.stunServer || '').trim()
      const hasAuth = !!(appSettings.value.turnUsername || appSettings.value.turnCredential)
      if (hasAuth && url) {
        const urlList = url.split(',').map(s => s.trim()).filter(Boolean)
        if (urlList.length > 0) {
          iceConfig = {
            urls: urlList.length > 1 ? urlList : urlList[0],
            username: appSettings.value.turnUsername || undefined,
            credential: appSettings.value.turnCredential || undefined
          }
        } else {
          iceConfig = null
        }
      } else {
        iceConfig = url || null
      }
    }
    const newSessionId = await startPlay(iceConfig)
    if (newSessionId) {
      sessionId.value = newSessionId
      startAvatarSpeakingPoll()
      showNotification(t('notifications.connectSuccess'), 'success')
    }
    
    const checkConnection = setInterval(() => {
      const video = document.getElementById('video')
      if (video && video.readyState >= 3 && video.videoWidth > 0) {
        connectionStatus.value = 'connected'
        clearInterval(checkConnection)
        if (asrModeFromServer.value === 'server' && !isRecordingVoice.value && !isVoiceMuted.value) {
          startVoiceRecording()
        }
        
        // 自动录制
        if (appSettings.value.autoRecord) {
          setTimeout(() => {
            handleStartRecord()
          }, 1000)
        }
      }
    }, 2000)
    
    setTimeout(() => {
      if (connectionStatus.value === 'connecting') {
        connectionStatus.value = 'disconnected'
        showNotification(t('notifications.connectTimeout'), 'error')
      }
      clearInterval(checkConnection)
    }, 60000)
  } catch (error) {
    console.error('连接失败:', error)
    connectionStatus.value = 'disconnected'
    // Retry once on wrong-state / in-progress (e.g. user clicked too fast)
    const msg = error?.message || ''
    const isWrongState = msg.includes('wrong state') || msg.includes('stable') || error?.code === 'CONNECTION_IN_PROGRESS'
    if (!isRetry && isWrongState) {
      await new Promise(r => setTimeout(r, 400))
      return handleStartConnection(true)
    }
    // Return to home page when error (only on non-retry or after retry failed)
    sessionStorage.removeItem('selectedAvatar')
    avatarSelected.value = false
    shouldAutoConnectAfterAvatar.value = false
  }
}

const handleStopConnection = async () => {
  await stopVoiceRecording({ submitAudio: false })
  stopAvatarSpeakingPoll()
  isVoiceMuted.value = false
  stopPlay()
  connectionStatus.value = 'disconnected'
  showNotification(t('notifications.disconnected'), 'info')
}

// Auto-connect when backend becomes ready after user selected an avatar
watch(backendReady, (ready) => {
  if (ready && shouldAutoConnectAfterAvatar.value && avatarSelected.value && connectionStatus.value === 'disconnected') {
    shouldAutoConnectAfterAvatar.value = false
    handleStartConnection()
  }
})

watch(
  [isRecordingVoice, isVoiceMuted, connectionStatus, antiEchoEnabled],
  () => {
    applyAntiEchoVolume()
  }
)

const handleStartRecord = async () => {
  if (!sessionId.value) {
    console.error('无法录制：sessionId 为空')
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }
  
  console.log('🔴 开始录制，sessionId:', sessionId.value)
  
  try {
    const response = await fetch('/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'start_record',
        sessionid: sessionId.value
      })
    })
    
    console.log('录制请求响应状态:', response.status)
    
    if (response.ok) {
      const data = await response.json()
      console.log('录制开始成功:', data)
      isRecording.value = true
      showNotification(t('notifications.recordStart'), 'success')
    } else {
      const errorText = await response.text()
      console.error('录制开始失败:', response.status, errorText)
      showNotification(`${t('notifications.recordStartFailed')}: ${response.status}`, 'error')
    }
  } catch (error) {
    console.error('Failed to start recording:', error)
    showNotification(`${t('notifications.recordStartFailed')}: ${error.message}`, 'error')
  }
}

const handleStopRecord = async () => {
  if (!sessionId.value) {
    console.error('无法停止录制：sessionId 为空')
    return
  }
  
  console.log('⏹️ 停止录制，sessionId:', sessionId.value)
  
  try {
    const response = await fetch('/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'end_record',
        sessionid: sessionId.value
      })
    })
    
    console.log('停止录制响应状态:', response.status)
    
    if (response.ok) {
      const data = await response.json()
      console.log('录制停止成功:', data)
      isRecording.value = false
      
      // 保存文件信息
      if (data.filename) {
        lastRecordFile.value = {
          filename: data.filename,
          filepath: data.filepath
        }
        showNotification(t('notifications.recordStop'), 'success')
      } else {
        showNotification(t('notifications.recordStopSimple'), 'success')
      }
    } else {
      const errorText = await response.text()
      console.error('停止录制失败:', response.status, errorText)
      showNotification(`${t('notifications.recordStopFailed')}: ${response.status}`, 'error')
    }
  } catch (error) {
    console.error('Failed to stop recording:', error)
    showNotification(`${t('notifications.recordStopFailed')}: ${error.message}`, 'error')
  }
}

const downloadRecord = () => {
  if (!lastRecordFile.value) {
    showNotification(t('notifications.noRecordFile'), 'warning')
    return
  }
  
  const downloadUrl = `/download/${lastRecordFile.value.filename}`
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = lastRecordFile.value.filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  showNotification(t('notifications.downloading'), 'info')
}

const addMessage = (text, type = 'user') => {
  chatMessages.value.push({ 
    text, 
    type, 
    time: getCurrentTime() 
  })
  
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 清空输入框
const clearInput = () => {
  chatInput.value = ''
}

const sendHumanMessageViaWs = (payload) => {
  const ws = getSignalingSocket()
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return null
  }

  const requestId = `${sessionId.value}-${Date.now()}-${++wsHumanRequestSeq}`
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      wsHumanPending.delete(requestId)
      reject(new Error('WebSocket human request timeout'))
    }, 30000)

    wsHumanPending.set(requestId, { resolve, reject, timeoutId })
    const sent = sendWsMessage({
      type: 'human',
      request_id: requestId,
      message_type: payload.type,
      text: payload.text,
      interrupt: payload.interrupt ?? true,
      sessionid: payload.sessionid
    })

    if (!sent) {
      clearTimeout(timeoutId)
      wsHumanPending.delete(requestId)
      reject(new Error('WebSocket is not open'))
    }
  })
}

const sendChatMessage = async () => {
  if (!chatInput.value.trim()) return
  
  // 检查是否已连接
  if (!isConnected.value) {
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }
  
  const message = chatInput.value
  addMessage(message, 'user')
  chatInput.value = ''
  
  isThinking.value = true
  
  try {
    const payload = {
      text: message,
      type: 'chat',
      interrupt: true,
      sessionid: sessionId.value
    }
    let data = null
    const wsResponse = await sendHumanMessageViaWs(payload)
      .catch(() => null)

    if (wsResponse) {
      data = wsResponse
    } else {
      const response = await fetch('/human', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      data = await response.json()
    }

    console.log('收到大模型回复:', data)
    if (data.code && data.code !== 0) {
      throw new Error(data.msg || 'message failed')
    }
    if (data.response || data.text) {
      isThinking.value = false
      addMessage(data.response || data.text, 'ai')
    }
  } catch (error) {
    console.error('Failed to send message:', error)
    showNotification(t('notifications.messageFailed'), 'error')
  } finally {
    isThinking.value = false
  }
}

const sendTTSMessage = async () => {
  if (!ttsInput.value.trim()) return
  
  // 检查是否已连接
  if (!isConnected.value) {
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }
  
  const message = ttsInput.value
  
  try {
    const payload = {
      text: message,
      type: 'echo',
      interrupt: true,
      sessionid: sessionId.value
    }
    const wsResponse = await sendHumanMessageViaWs(payload)
      .catch(() => null)
    if (!wsResponse) {
      await fetch('/human', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    } else if (wsResponse.code && wsResponse.code !== 0) {
      throw new Error(wsResponse.msg || 'TTS request failed')
    }
    
    addMessage(`已发送朗读请求：${message.substring(0, 50)}${message.length > 50 ? '...' : ''}`, 'system')
    ttsInput.value = ''
  } catch (error) {
    console.error('Failed to send TTS message:', error)
    showNotification(t('notifications.ttsFailed'), 'error')
  }
}

// 语音识别
let mediaRecorder = null
let audioChunks = []
let asrUploadQueue = Promise.resolve()
let serverAsrStream = null
let serverAsrLoopActive = false
let sherpaVadSession = null
let sherpaVadErrorShown = false
const sherpaVadMinSpeechMs = isMobileClient ? 250 : 180
const sherpaVadMinRms = isMobileClient ? 0.008 : 0.006
const sherpaVadNoiseMultiplier = 1.0
const sherpaVadCalibrationMs = 0
const sherpaVadUploadCooldownMs = 0
let sherpaVadCalibrationUntil = 0
let sherpaVadNoiseFloorRms = 0
let sherpaVadLastUploadAt = 0
let sherpaVadRejectStats = {
  empty: 0,
  duration: 0,
  rmsMin: 0,
  calibration: 0,
  adaptive: 0,
  cooldown: 0,
  pass: 0,
}
let sherpaVadLastRejectLogAt = 0

const { startRecognition, stopRecognition, isSupported, updateSettings } = useSpeechRecognition({
  onResult: (text) => {
    // 实时显示识别的中间结果
    chatInput.value = text
  },
  // 浏览器语音不支持 auto，用 en-US 兜底；服务端 ASR 时仍会发送 voiceLanguage（含 auto）
  language: appSettings.value.voiceLanguage === 'auto' ? 'en-US' : appSettings.value.voiceLanguage,
  continuous: appSettings.value.voiceContinuous,
  onFinalResult: async (text) => {
    // 在非连续模式下，识别完成后自动停止录音
    if (!appSettings.value.voiceContinuous && isRecordingVoice.value) {
      console.log('识别完成，自动停止录音（非连续模式）')
      stopVoiceRecording()
    }
    
    if (text.trim()) {
      addMessage(text, 'user')
      // 清空输入框，准备下一次识别
      chatInput.value = ''
      isThinking.value = true
      
      try {
        const payload = {
          text: text,
          type: 'chat',
          interrupt: true,
          sessionid: sessionId.value
        }
        let data = null
        const wsResponse = await sendHumanMessageViaWs(payload).catch(() => null)
        if (wsResponse) {
          data = wsResponse
        } else {
          const response = await fetch('/human', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          })
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`)
          }
          data = await response.json()
        }
        console.log('收到大模型回复:', data)
        if (data.code && data.code !== 0) {
          throw new Error(data.msg || 'voice message failed')
        }
        if (data.response || data.text) {
          isThinking.value = false
          addMessage(data.response || data.text, 'ai')
        }
        } catch (error) {
        console.error('Failed to send voice message:', error)
        showNotification(t('notifications.voiceMessageFailed'), 'error')
      } finally {
        isThinking.value = false
      }
    }
  }
})

const sendAudioChunkToServer = async (audioBlob, filename = 'voice.webm') => {
  if (!audioBlob || audioBlob.size <= 0 || !sessionId.value) return

  const formData = new FormData()
  formData.append('file', audioBlob, filename)
  formData.append('sessionid', sessionId.value)
  formData.append('language', appSettings.value.voiceLanguage || 'auto')

  try {
    const response = await fetch('/asr', {
      method: 'POST',
      body: formData
    })
    if (!response.ok) {
      console.error('ASR 识别失败:', response.status)
      return
    }

    const data = await response.json()
    if (data.silent) return
    if (data.partial) return
    if (!data.text) return

    addMessage(data.text, 'user')
    if (data.response) {
      addMessage(data.response, 'ai')
    }
  } catch (error) {
    console.error('ASR 请求失败:', error)
    showNotification(t('notifications.voiceRequestFailed'), 'error')
  }
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))
const getMicAudioConstraints = () => ({
  echoCancellation: { ideal: true },
  noiseSuppression: { ideal: true },
  autoGainControl: { ideal: true },
  channelCount: { ideal: 1 },
  sampleRate: { ideal: 16000 },
})

const applyAntiEchoVolume = () => {
  const video = document.getElementById('video')
  if (!video) return
  const shouldDuck =
    antiEchoEnabled.value &&
    isConnected.value &&
    isRecordingVoice.value &&
    !isVoiceMuted.value
  if (!shouldDuck) {
    video.volume = defaultRemoteVolume
    return
  }
  // Mobile speakers are close to the mic and AEC quality varies by device/browser.
  // Fully muting remote playback while listening is the most reliable anti-echo strategy.
  video.volume = isMobileClient ? antiEchoMobileVolume : antiEchoDuckedVolume
}

const interruptCurrentSpeech = async () => {
  if (!sessionId.value) return
  try {
    await fetch('/interrupt_talk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionid: sessionId.value })
    })
  } catch (error) {
    console.warn('中断旧语音失败:', error)
  }
}

const startAvatarSpeakingPoll = () => {
  avatarSpeakWsReady = false
  if (avatarSpeakPollTimer) {
    clearInterval(avatarSpeakPollTimer)
    avatarSpeakPollTimer = null
  }

  const wsSent = sendWsMessage({ type: 'is_speaking', sessionid: sessionId.value })
  if (!wsSent) {
    console.warn('WebSocket is unavailable for speaking_state; skip HTTP polling fallback')
    return
  }
}

const stopAvatarSpeakingPoll = () => {
  if (avatarSpeakPollTimer) {
    clearInterval(avatarSpeakPollTimer)
    avatarSpeakPollTimer = null
  }
  avatarSpeakWsReady = false
  avatarSpeaking.value = false
}

const shouldBlockByEchoGuard = () => {
  if (avatarSpeaking.value) return true
  if (Date.now() - lastAvatarSpeakingAt < avatarSpeakCooldownMs) return true
  return false
}

const pcm16ToWavBlob = (pcm, sampleRate = 16000) => {
  const bytesPerSample = 2
  const blockAlign = bytesPerSample
  const byteRate = sampleRate * blockAlign
  const dataSize = pcm.length * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  let offset = 0
  const writeString = (str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset++, str.charCodeAt(i))
    }
  }

  writeString('RIFF')
  view.setUint32(offset, 36 + dataSize, true); offset += 4
  writeString('WAVE')
  writeString('fmt ')
  view.setUint32(offset, 16, true); offset += 4
  view.setUint16(offset, 1, true); offset += 2
  view.setUint16(offset, 1, true); offset += 2
  view.setUint32(offset, sampleRate, true); offset += 4
  view.setUint32(offset, byteRate, true); offset += 4
  view.setUint16(offset, blockAlign, true); offset += 2
  view.setUint16(offset, 16, true); offset += 2
  writeString('data')
  view.setUint32(offset, dataSize, true); offset += 4

  for (let i = 0; i < pcm.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, pcm[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

const calcAudioRms = (audio) => {
  if (!audio || audio.length === 0) return 0
  let sum = 0
  for (let i = 0; i < audio.length; i++) {
    const v = audio[i]
    sum += v * v
  }
  return Math.sqrt(sum / audio.length)
}

const isSherpaSegmentValid = (audio, sampleRate = 16000) => {
  if (!audio || audio.length === 0) {
    sherpaVadRejectStats.empty += 1
    return false
  }
  const now = Date.now()
  const durationMs = (audio.length / sampleRate) * 1000
  if (durationMs < sherpaVadMinSpeechMs) {
    sherpaVadRejectStats.duration += 1
    return false
  }

  const rms = calcAudioRms(audio)
  if (rms < sherpaVadMinRms) {
    sherpaVadRejectStats.rmsMin += 1
    return false
  }

  // Warm up on start: learn ambient noise and ignore early unstable detections.
  if (now < sherpaVadCalibrationUntil) {
    sherpaVadNoiseFloorRms = Math.max(sherpaVadNoiseFloorRms, rms)
    sherpaVadRejectStats.calibration += 1
    return false
  }

  const adaptiveFloor = Math.max(sherpaVadMinRms, sherpaVadNoiseFloorRms * sherpaVadNoiseMultiplier)
  if (rms < adaptiveFloor) {
    sherpaVadRejectStats.adaptive += 1
    return false
  }

  if (now - sherpaVadLastUploadAt < sherpaVadUploadCooldownMs) {
    sherpaVadRejectStats.cooldown += 1
    return false
  }
  sherpaVadLastUploadAt = now
  sherpaVadRejectStats.pass += 1

  if (now - sherpaVadLastRejectLogAt > 2000) {
    sherpaVadLastRejectLogAt = now
    console.log('[SherpaVAD][App] validation stats:', {
      ...sherpaVadRejectStats,
      noiseFloorRms: Number(sherpaVadNoiseFloorRms.toFixed(4)),
      minRms: sherpaVadMinRms,
      minSpeechMs: sherpaVadMinSpeechMs,
      noiseMultiplier: sherpaVadNoiseMultiplier,
      cooldownMs: sherpaVadUploadCooldownMs,
      adaptiveFloor: Number(adaptiveFloor.toFixed(4)),
    })
  }
  return true
}

const startServerAsrLoop = async () => {
  if (serverAsrLoopActive) return

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    console.error('当前浏览器不支持麦克风录音')
    showNotification(t('notifications.micPermission'), 'error')
    return
  }

  try {
    serverAsrLoopActive = true
    isRecordingVoice.value = true
    sherpaVadErrorShown = false
    sherpaVadCalibrationUntil = Date.now() + sherpaVadCalibrationMs
    sherpaVadNoiseFloorRms = 0
    sherpaVadLastUploadAt = 0
    sherpaVadLastRejectLogAt = Date.now()
    sherpaVadRejectStats = {
      empty: 0,
      duration: 0,
      rmsMin: 0,
      calibration: 0,
      adaptive: 0,
      cooldown: 0,
      pass: 0,
    }
    console.log('[SherpaVAD][App] start loop with config:', {
      isMobileClient,
      sherpaVadMinSpeechMs,
      sherpaVadMinRms,
      sherpaVadNoiseMultiplier,
      sherpaVadCalibrationMs,
      sherpaVadUploadCooldownMs,
      threshold: isMobileClient ? 0.55 : 0.5,
      minSpeechDuration: 0.25,
      minSilenceDuration: 0.35
    })
    sherpaVadSession = createSherpaVadSession({
      getStream: () => navigator.mediaDevices.getUserMedia({ audio: getMicAudioConstraints() }),
      vadOptions: {
        isMobile: isMobileClient,
        threshold: isMobileClient ? 0.55 : 0.5,
        minSpeechDuration: 0.25,
        minSilenceDuration: 0.35
      },
      onSpeechSegment: (audio, sampleRate = 16000) => {
        if (!serverAsrLoopActive || !isConnected.value || isVoiceMuted.value) return
        if (shouldBlockByEchoGuard()) return
        if (!audio || audio.length === 0) return
        const durationMs = (audio.length / sampleRate) * 1000
        const rms = calcAudioRms(audio)
        console.log('[SherpaVAD][App] raw segment:', {
          durationMs: Number(durationMs.toFixed(2)),
          rms: Number(rms.toFixed(4)),
          sampleRate,
          samples: audio.length,
        })
        if (!isSherpaSegmentValid(audio, sampleRate)) return

        const wavBlob = pcm16ToWavBlob(audio, sampleRate)
        asrUploadQueue = asrUploadQueue
          .then(async () => {
            await interruptCurrentSpeech()
            await sendAudioChunkToServer(wavBlob, 'voice.wav')
          })
          .catch((err) => {
            console.error('ASR 上传队列异常:', err)
          })
      },
      onError: (err) => {
        console.error('Sherpa VAD 处理异常:', err)
        if (!sherpaVadErrorShown) {
          sherpaVadErrorShown = true
          showNotification(t('notifications.sherpaVadFailed'), 'error')
        }
      }
    })
    await sherpaVadSession.start()
    while (serverAsrLoopActive && isConnected.value) {
      await sleep(200)
    }
  } catch (error) {
    console.error('无法访问麦克风:', error)
    const micErrorNames = [
      'NotAllowedError',
      'NotFoundError',
      'NotReadableError',
      'OverconstrainedError',
      'SecurityError',
      'AbortError',
    ]
    const isMicError = micErrorNames.includes(error?.name)
    showNotification(
      isMicError ? t('notifications.micPermission') : t('notifications.sherpaVadFailed'),
      'error'
    )
  } finally {
    serverAsrLoopActive = false
    if (sherpaVadSession) {
      await sherpaVadSession.stop()
      sherpaVadSession = null
    }
    if (serverAsrStream) {
      serverAsrStream.getTracks().forEach(track => track.stop())
      serverAsrStream = null
    }
    isRecordingVoice.value = false
  }
}

const startVoiceRecording = async () => {
  if (isRecordingVoice.value) return
  
  // 检查是否已连接
  if (!isConnected.value) {
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }

  // 服务端配置为 server 时强制使用后端 ASR（SenseVoice）；否则优先使用浏览器语音识别
  const useServerASR = asrModeFromServer.value === 'server'
  if (useServerASR) {
    await startServerAsrLoop()
    return
  }

  if (!useServerASR && isSupported) {
    try {
      isRecordingVoice.value = true
      startRecognition()
      return
    } catch (error) {
      console.error('启动浏览器语音识别失败:', error)
      showNotification(t('notifications.voiceFailed'), 'error')
      isRecordingVoice.value = false
      return
    }
  }
  
  // 使用 MediaRecorder + 后端 ASR（配置为 server 或浏览器不支持 Web Speech API 时）
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    console.error('当前浏览器不支持麦克风录音')
    showNotification(t('notifications.micPermission'), 'error')
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: getMicAudioConstraints() })
    
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)
    
    mediaRecorder.ondataavailable = (e) => {
      if (!e.data || e.data.size <= 0) return
      audioChunks.push(e.data)
    }

    mediaRecorder.onstop = () => {
      if (mediaRecorder?.stream) {
        mediaRecorder.stream.getTracks().forEach(track => track.stop())
      }
      mediaRecorder = null
      audioChunks = []
    }

    mediaRecorder.start(100)
    isRecordingVoice.value = true
  } catch (error) {
    console.error('无法访问麦克风:', error)
    showNotification(t('notifications.micPermission'), 'error')
  }
}

const stopVoiceRecording = async ({ submitAudio = true } = {}) => {
  if (!isRecordingVoice.value) return
  
  console.log('停止语音录音')
  
  // 清空输入框中的临时识别结果
  chatInput.value = ''
  
  if (asrModeFromServer.value === 'server') {
    serverAsrLoopActive = false
    if (sherpaVadSession) {
      await sherpaVadSession.stop()
      sherpaVadSession = null
    }
    if (serverAsrStream) {
      serverAsrStream.getTracks().forEach(track => track.stop())
      serverAsrStream = null
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try {
        mediaRecorder.stop()
      } catch (_) {}
    }
    isRecordingVoice.value = false
    return
  }

  // 如果本次使用的是浏览器语音识别（未强制服务端 ASR），直接停止识别即可
  if (isSupported && asrModeFromServer.value !== 'server') {
    try {
      stopRecognition()
    } catch (error) {
      console.error('停止浏览器语音识别失败:', error)
    } finally {
      isRecordingVoice.value = false
    }
    return
  }
  
  // 否则为 MediaRecorder + 后端 ASR 流程
  if (!mediaRecorder) {
    isRecordingVoice.value = false
    return
  }
  
  // Wire up onstop BEFORE calling stop() to avoid a race where the event
  // fires before the handler is assigned (can happen when recording is very short)
  mediaRecorder.onstop = async () => {
    // 关闭麦克风流
    mediaRecorder.stream.getTracks().forEach(track => track.stop())
    
    // 发送音频到后端进行 ASR 识别
    if (submitAudio && audioChunks.length > 0) {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' })
      await sendAudioChunkToServer(audioBlob)
    }
    
    // 清空音频数据
    audioChunks = []
    mediaRecorder = null
  }

  // Now safe to call stop() — onstop handler is already registered above
  mediaRecorder.stop()
  isRecordingVoice.value = false
}

// 处理语音按钮的按下事件（用于按住说话模式）
const handleVoiceButtonPress = (e) => {
  if (asrModeFromServer.value === 'server') {
    return
  }
  // 在连续识别模式下，不处理按下事件
  if (appSettings.value.voiceContinuous) {
    return
  }
  startVoiceRecording()
}

// 处理语音按钮的释放事件（用于按住说话模式）
const handleVoiceButtonRelease = (e) => {
  if (asrModeFromServer.value === 'server') {
    return
  }
  // 在连续识别模式下，不处理释放事件
  if (appSettings.value.voiceContinuous) {
    return
  }
  stopVoiceRecording()
}

const toggleServerMute = () => {
  const now = Date.now()
  if (now - lastVoiceToggleAt < voiceToggleDebounceMs) {
    return
  }
  lastVoiceToggleAt = now

  if (isVoiceMuted.value) {
    isVoiceMuted.value = false
    if (!isRecordingVoice.value) startVoiceRecording()
    showNotification(t('notifications.voiceUnmuted'), 'success')
  } else {
    isVoiceMuted.value = true
    showNotification(t('notifications.voiceMuted'), 'info')
  }
}

// 处理触屏结束事件：服务端模式按点击切换静音；非服务端维持按住说话逻辑
const handleVoiceButtonTouchEnd = (e) => {
  if (asrModeFromServer.value === 'server') {
    ignoreNextVoiceClick = true
    toggleServerMute()
    return
  }
  handleVoiceButtonRelease(e)
}

// 处理语音按钮的点击事件（用于连续识别模式）
const handleVoiceButtonClick = (e) => {
  if (asrModeFromServer.value === 'server') {
    if (ignoreNextVoiceClick) {
      ignoreNextVoiceClick = false
      return
    }
    toggleServerMute()
    return
  }
  // 只在连续识别模式下处理点击事件
  if (!appSettings.value.voiceContinuous) {
    return
  }
  
  // 切换录音状态
  if (isRecordingVoice.value) {
    stopVoiceRecording()
  } else {
    startVoiceRecording()
  }
}

// Trigger per-avatar "flower" custom video/audio state
const triggerFlowerMode = async () => {
  if (!isConnected.value) {
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }
  if (!sessionId.value) {
    showNotification('Session not ready', 'warning')
    return
  }

  let avatarId = null
  try {
    const stored = sessionStorage.getItem('selectedAvatar')
    if (stored) {
      const parsed = JSON.parse(stored)
      avatarId = parsed?.id ?? null
    }
  } catch (e) {
    console.error('Failed to read selectedAvatar from sessionStorage:', e)
  }

  if (!avatarId) {
    showNotification('Avatar not found for flower action', 'warning')
    return
  }

  try {
    const resp = await fetch('/flower', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionid: sessionId.value,
        avatar_id: avatarId
      })
    })
    if (!resp.ok) {
      const text = await resp.text()
      console.error('Flower API failed:', resp.status, text)
      showNotification('Failed to trigger flower video', 'error')
      return
    }
    const data = await resp.json().catch(() => ({}))
    if (data.code !== 0) {
      console.error('Flower API error payload:', data)
      showNotification('Failed to trigger flower video', 'error')
      return
    }
    showNotification('Flower video triggered', 'success')
  } catch (err) {
    console.error('Flower API exception:', err)
    showNotification('Failed to trigger flower video', 'error')
  }
}

// ── iOS Chrome keyboard offset ─────────────────────────────────────────────
// On iOS Chrome, position:fixed elements are anchored to the layout viewport and
// stay hidden behind the virtual keyboard. We use the Visual Viewport API to
// track keyboard height and push the bottom-overlay up via a CSS custom property.
let _vpHandler = null

function _applyViewportOffset() {
  if (!window.visualViewport) return
  const kbHeight = Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop)
  document.documentElement.style.setProperty('--vvp-bottom-offset', `${kbHeight}px`)
}

onUnmounted(() => {
  wsHumanPending.forEach(({ reject, timeoutId }) => {
    clearTimeout(timeoutId)
    reject(new Error('component unmounted'))
  })
  wsHumanPending.clear()
  serverAsrLoopActive = false
  stopAvatarSpeakingPoll()
  if (sherpaVadSession) {
    sherpaVadSession.stop().catch(() => {})
    sherpaVadSession = null
  }
  if (serverAsrStream) {
    serverAsrStream.getTracks().forEach(track => track.stop())
    serverAsrStream = null
  }
  if (window.visualViewport && _vpHandler) {
    window.visualViewport.removeEventListener('resize', _vpHandler)
    window.visualViewport.removeEventListener('scroll', _vpHandler)
  }
})

onMounted(async () => {
  console.log('✅ Vue 应用已挂载')
  console.log('后端 API 地址: /offer (通过 Vite proxy 转发到 localhost:8010)')

  // Visual Viewport API: lift fixed bottom-overlay above the iOS virtual keyboard
  if (window.visualViewport) {
    _vpHandler = _applyViewportOffset
    window.visualViewport.addEventListener('resize', _vpHandler)
    window.visualViewport.addEventListener('scroll', _vpHandler)
  }
  
  // 加载语言设置
  loadLocale()
  
  // 设置欢迎消息
  if (chatMessages.value.length > 0 && !chatMessages.value[0].text) {
    chatMessages.value[0].text = getWelcomeMessage()
  }
  
  // 应用初始主题
  updateTheme(appSettings.value.theme)
  
  // 开始轮询检查后端是否就绪
  console.log('🔍 开始检查后端状态...')
  const checkInterval = setInterval(async () => {
    const ready = await checkBackendReady()
    if (ready) {
      clearInterval(checkInterval)
      showNotification(t('notifications.backendReady'), 'success')
    }
  }, 2000)  // 每2秒检查一次
  
  // 最多检查60秒
  setTimeout(() => {
    if (!backendReady.value) {
      clearInterval(checkInterval)
      showNotification(t('notifications.backendTimeout'), 'error')
    }
  }, 60000)

  applyAntiEchoVolume()
})
</script>

<style>
@import 'highlight.js/styles/atom-one-dark.css';

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --primary-light: #818cf8;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --text-primary: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #94a3b8;
  --border: #475569;
  --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
}

html, body {
  margin: 0;
  padding: 0;
  overflow: hidden;
  width: 100%;
  height: 100%;
}

#app {
  width: 100%;
  height: 100%;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #000;
  color: var(--text-primary);
}

/* ── Password gate ── */
.password-gate {
  position: fixed;
  inset: 0;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.password-gate-box {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 2rem;
  min-width: 280px;
  box-shadow: var(--shadow-lg);
}

.password-gate-label {
  margin-bottom: 0.75rem;
  font-size: 1rem;
  color: var(--text-primary);
}

.password-gate-input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  font-size: 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.password-gate-input:focus {
  outline: none;
  border-color: var(--primary);
}

.password-gate-error {
  color: var(--danger);
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
}

.password-gate-btn {
  width: 100%;
  padding: 0.6rem 1rem;
  font-size: 1rem;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.password-gate-btn:hover {
  background: var(--primary-dark);
}

/* ── Full-screen page ── */
.page-container {
  width: 100%;
  height: 100vh;
  height: 100dvh; /* visible viewport on mobile, avoids bottom crop */
  min-height: -webkit-fill-available;
  background: #000;
  overflow: hidden;
  position: relative;
}

.video-container {
  position: absolute;
  inset: 0;
}

.remote-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* ── Idle overlay ── */
.video-idle-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}

.idle-content {
  text-align: center;
  color: var(--text-muted);
}

.idle-icon {
  font-size: 5rem;
  margin-bottom: 1rem;
  opacity: 0.6;
}

.idle-text {
  font-size: 1rem;
  opacity: 0.7;
}

/* ── Top header overlay ── */
.top-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  padding: 12px 16px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.75), transparent);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.logo-badge {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.9rem;
  background: rgba(99, 102, 241, 0.85);
  border-radius: 20px;
  font-weight: 700;
  font-size: 0.9rem;
  color: white;
  backdrop-filter: blur(8px);
}

.logo-badge i {
  font-size: 1rem;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.8rem;
  border-radius: 20px;
  background: rgba(30, 41, 59, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  font-size: 0.8rem;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.status-connected .status-dot { background: var(--success); }
.status-connecting .status-dot { background: var(--warning); }
.status-disconnected .status-dot { background: var(--danger); }

.session-chip {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.35rem 0.75rem;
  background: rgba(30, 41, 59, 0.7);
  border-radius: 20px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  backdrop-filter: blur(8px);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-back-select {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(139, 92, 246, 0.15);
  color: #a78bfa;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, transform 0.15s;
}
.btn-back-select:hover {
  background: rgba(139, 92, 246, 0.35);
  transform: scale(1.08);
}

.icon-btn {
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 50%;
  background: rgba(30, 41, 59, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(8px);
  font-size: 1.1rem;
  text-decoration: none;
}

.icon-btn:hover {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

/* ── Recording badge ── */
.recording-badge {
  position: fixed;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  background: var(--danger);
  color: white;
  padding: 0.4rem 1rem;
  border-radius: 20px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.85rem;
  animation: pulse 2s infinite;
}

/* ── Chat records overlay ── */
.chat-records-overlay {
  position: fixed;
  bottom: 120px;
  left: 12px;
  width: min(420px, calc(100vw - 100px));
  max-height: 40vh;
  z-index: 10;
  display: flex;
  flex-direction: column;
}

.messages-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.5rem;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.2) transparent;
}

.messages-list::-webkit-scrollbar {
  width: 4px;
}

.messages-list::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.2);
  border-radius: 2px;
}

.chat-bubble {
  max-width: 85%;
  animation: slideIn 0.3s ease;
}

.bubble-ai {
  align-self: flex-start;
}

.bubble-user {
  align-self: flex-end;
}

.bubble-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 0.25rem;
}

.bubble-meta i {
  font-size: 0.85rem;
}

.bubble-time {
  opacity: 0.6;
  margin-left: auto;
}

.bubble-text {
  padding: 0.6rem 0.9rem;
  border-radius: 14px;
  backdrop-filter: blur(12px);
  font-size: 0.9rem;
  line-height: 1.5;
}

.bubble-ai .bubble-text {
  background: rgba(30, 41, 59, 0.82);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

.bubble-user .bubble-text {
  background: rgba(99, 102, 241, 0.85);
  color: white;
  border-bottom-right-radius: 4px;
}

/* Markdown in bubbles */
.bubble-text :deep(h1),
.bubble-text :deep(h2),
.bubble-text :deep(h3) {
  margin: 0.4rem 0;
  font-weight: 600;
}

.bubble-text :deep(p) { margin: 0.3rem 0; }
.bubble-text :deep(p:first-child) { margin-top: 0; }
.bubble-text :deep(p:last-child) { margin-bottom: 0; }
.bubble-text :deep(ul), .bubble-text :deep(ol) { margin: 0.3rem 0; padding-left: 1.2rem; }
.bubble-text :deep(code) {
  background: rgba(0,0,0,0.25);
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
  font-size: 0.85em;
  font-family: 'Consolas', monospace;
}
.bubble-text :deep(pre) {
  background: rgba(0,0,0,0.3);
  padding: 0.75rem;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.4rem 0;
}
.bubble-text :deep(pre code) { background: transparent; padding: 0; }
.bubble-text :deep(a) { color: var(--primary-light); text-decoration: none; }
.bubble-text :deep(strong) { font-weight: 700; }
.bubble-text :deep(em) { font-style: italic; }

/* ── TTS overlay panel ── */
.tts-overlay {
  position: fixed;
  bottom: 120px;
  left: 12px;
  width: min(420px, calc(100vw - 100px));
  z-index: 20;
}

.tts-panel {
  background: rgba(15, 23, 42, 0.9);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 16px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.tts-panel-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.tts-panel-header span {
  flex: 1;
}

.icon-btn-sm {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: rgba(255,255,255,0.1);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.8rem;
}

.icon-btn-sm:hover {
  background: var(--danger);
  color: white;
}

.tts-panel textarea {
  width: 100%;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  padding: 0.75rem;
  color: var(--text-primary);
  font-size: 0.9rem;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
}

.tts-panel textarea:focus {
  outline: none;
  border-color: var(--primary);
}

.tts-send-btn {
  width: 100%;
  padding: 0.7rem;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: white;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.tts-send-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, var(--primary-dark), #4338ca);
  transform: translateY(-1px);
}

.tts-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Side action buttons ── */
.side-actions {
  position: fixed;
  right: 12px;
  bottom: 130px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-btn {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(88, 87, 87, 0.55);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(8px);
  font-size: 1rem;
  border: 1px solid rgba(255,255,255,0.1);
}

.side-btn:hover:not(:disabled) {
  background: var(--primary);
  transform: scale(1.1);
}

.side-btn.active {
  background: var(--primary);
}

.side-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.download-side-btn:not(:disabled) {
  background: rgba(16, 185, 129, 0.6);
}

.download-side-btn:not(:disabled):hover {
  background: var(--success);
}

.danger-side-btn:hover:not(:disabled) {
  background: var(--danger);
}

/* ── Bottom overlay ── */
.bottom-overlay {
  position: fixed;
  bottom: var(--vvp-bottom-offset, 0px);
  left: 0;
  right: 0;
  z-index: 20;
  padding: 12px 12px max(20px, env(safe-area-inset-bottom, 0));
  background: linear-gradient(to top, rgba(0,0,0,0.85), rgba(0,0,0,0.5), transparent);
  transition: bottom 0.1s ease-out;
}

.connect-row {
  display: flex;
  justify-content: center;
}

.connect-btn {
  padding: 0.85rem 2.5rem;
  background: linear-gradient(135deg, var(--success), #059669);
  color: white;
  border: none;
  border-radius: 28px;
  font-weight: 700;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  transition: all 0.2s;
  box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
}

.connect-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(16, 185, 129, 0.5);
}

.connect-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.connect-btn.loading {
  background: linear-gradient(135deg, var(--warning), #d97706);
  box-shadow: 0 4px 16px rgba(245, 158, 11, 0.4);
}

/* Input row */
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  min-width: 0; /* allow row to shrink inside viewport */
}

.input-pill {
  flex: 1;
  min-width: 0; /* allow pill to shrink so textarea gets space */
  position: relative;
  background: rgba(255,255,255,0.12);
  backdrop-filter: blur(12px);
  border-radius: 24px;
  border: 1px solid rgba(255,255,255,0.15);
  display: flex;
  align-items: center;
}

.chat-textarea {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  color: white;
  font-size: 1rem; /* 16px — prevents iOS auto-zoom on focus */
  padding: 0.8rem 1.1rem;
  padding-right: 2.5rem;
  resize: none;
  font-family: inherit;
  line-height: 1.4;
  min-height: 42px;
  max-height: 100px;
}

.chat-textarea::placeholder {
  color: rgba(255,255,255,0.45);
}

.chat-textarea:focus {
  outline: none;
}

.clear-input-btn {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.45);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  font-size: 1rem;
  transition: color 0.2s;
}

.clear-input-btn:hover {
  color: var(--danger);
}

/* Round action buttons in input row */
.voice-pill-btn,
.send-pill-btn {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.voice-pill-btn {
  background: rgba(88, 87, 87, 0.6);
  color: white;
  backdrop-filter: blur(8px);
  position: relative;
}

.voice-pill-btn:hover {
  background: rgba(99, 102, 241, 0.8);
}

.voice-pill-btn.recording {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.3);
}

.voice-pill-btn.muted {
  background: rgba(107, 114, 128, 0.85);
}

.voice-pill-btn.continuous-mode:not(.recording) {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.voice-icon-wrapper {
  position: relative;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.recording-pulse {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: rgba(255,255,255,0.3);
  animation: pulse-ring 1.5s ease-out infinite;
}

.send-pill-btn {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: white;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.4);
}

.send-pill-btn:hover:not(:disabled) {
  transform: scale(1.08);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.5);
}

.send-pill-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 0.5rem 0;
}

.typing-indicator span {
  width: 7px;
  height: 7px;
  background: rgba(255,255,255,0.6);
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

/* ── Notifications ── */
.notification-container {
  position: fixed;
  top: 70px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.notification {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.92);
  backdrop-filter: blur(12px);
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  border-left: 3px solid var(--primary);
  min-width: 260px;
  max-width: 360px;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.notification i { font-size: 1rem; flex-shrink: 0; }
.notification.success { border-left-color: var(--success); }
.notification.success i { color: var(--success); }
.notification.error { border-left-color: var(--danger); }
.notification.error i { color: var(--danger); }
.notification.warning { border-left-color: var(--warning); }
.notification.warning i { color: var(--warning); }
.notification.info i { color: var(--primary); }

/* ── Animations ── */
@keyframes slideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-8px); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes pulse-ring {
  0% { transform: scale(0.8); opacity: 1; }
  100% { transform: scale(2); opacity: 0; }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  display: inline-block;
  animation: spin 1.5s linear infinite;
}

.notification-enter-active { animation: notification-in 0.3s ease-out; }
.notification-leave-active { animation: notification-out 0.3s ease-in; }

@keyframes notification-in {
  from { opacity: 0; transform: translateX(80px); }
  to { opacity: 1; transform: translateX(0); }
}

@keyframes notification-out {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(80px); }
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.35); }

/* ── Responsive ── */
@media (max-width: 640px) {
  .chat-records-overlay, .tts-overlay {
    width: calc(100vw - 70px);
  }

  .logo-badge span {
    display: none;
  }

  .status-badge .status-text {
    display: none;
  }

  /* Chatroom bottom UI: prevent overflow and keep usable on small screens */
  .bottom-overlay {
    padding: 8px 8px max(12px, env(safe-area-inset-bottom, 0));
  }

  .input-row {
    gap: 6px;
  }

  .input-pill {
    border-radius: 20px;
  }

  .chat-textarea {
    font-size: 1rem; /* keep 16px to prevent iOS auto-zoom */
    padding: 0.65rem 0.9rem;
    padding-right: 2.25rem;
    min-height: 38px;
    max-height: 88px;
  }

  .voice-pill-btn,
  .send-pill-btn {
    width: 40px;
    height: 40px;
    font-size: 1rem;
  }

  .connect-btn {
    padding: 0.75rem 1.75rem;
    font-size: 0.9rem;
  }
}

@media (max-width: 380px) {
  .bottom-overlay {
    padding: 6px 6px max(10px, env(safe-area-inset-bottom, 0));
  }

  .input-row {
    gap: 4px;
  }

  .voice-pill-btn,
  .send-pill-btn {
    width: 36px;
    height: 36px;
    font-size: 0.95rem;
  }

  .chat-textarea {
    font-size: 16px; /* avoid zoom on focus on iOS */
    padding: 0.5rem 0.75rem;
    padding-right: 2rem;
    min-height: 36px;
  }

  .clear-input-btn {
    right: 6px;
    font-size: 0.9rem;
  }
}
</style>
