<!-- Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0. -->
<template>
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
            <i class="bi bi-robot" v-else></i>
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
      <div class="recording-badge" v-if="isRecording">
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
              <span>{{ msg.type === 'user' ? t('chat.you') : t('chat.ai') }}</span>
              <span class="bubble-time" v-if="appSettings.showTimestamp">{{ msg.time }}</span>
            </div>
            <div class="bubble-text" v-html="renderMarkdown(msg.text)"></div>
          </div>
          <div v-if="isThinking" class="chat-bubble bubble-ai">
            <div class="bubble-meta">
              <i class="bi bi-robot"></i>
              <span>{{ t('chat.ai') }}</span>
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
          @click="handleStartRecord"
          :disabled="isRecording"
          :title="t('video.startRecord')"
        >
          <i class="bi bi-record-fill"></i>
        </button>
        <button 
          class="side-btn"
          @click="handleStopRecord"
          :disabled="!isRecording"
          :title="t('video.stopRecord')"
        >
          <i class="bi bi-stop-fill"></i>
        </button>
        <button 
          class="side-btn download-side-btn"
          @click="downloadRecord"
          :disabled="!lastRecordFile"
          :title="t('video.download')"
        >
          <i class="bi bi-download"></i>
        </button>
        <button 
          class="side-btn danger-side-btn"
          @click="clearChatHistory"
          :title="'清空历史'"
        >
          <i class="bi bi-trash"></i>
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
            @touchend="handleVoiceButtonRelease"
            :class="{ recording: isRecordingVoice, 'continuous-mode': appSettings.voiceContinuous }"
            :title="getVoiceButtonTitle"
          >
            <div class="voice-icon-wrapper">
              <i class="bi bi-mic-fill"></i>
              <span v-if="isRecordingVoice" class="recording-pulse"></span>
            </div>
          </button>
          <button 
            class="send-pill-btn" 
            @click="sendChatMessage" 
            :disabled="!chatInput.trim()"
          >
            <i class="bi bi-send-fill"></i>
          </button>
          <button 
            class="disconnect-pill-btn" 
            @click="handleStopConnection"
            :title="t('video.disconnect')"
          >
            <i class="bi bi-stop-circle"></i>
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

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import SelectView from './components/SelectView.vue'
import DebugPanel from './components/DebugPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { useWebRTC } from './composables/useWebRTC'
import { useSpeechRecognition } from './composables/useSpeechRecognition'
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

// ── Avatar selection gate ────────────────────────────────────────────────────
const avatarSelected = ref(!!sessionStorage.getItem('selectedAvatar'))

function onAvatarSelected(avatar) {
  // Only live avatars enter the chat UI; others are handled inside SelectView
  if (avatar.live) {
    avatarSelected.value = true
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
const messagesRef = ref(null)
const notifications = ref([])
let notificationIdCounter = 0
const lastRecordFile = ref(null)
const backendReady = ref(false)
const showChatRecords = ref(true)

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
  voiceContinuous: false,
  voiceLanguage: 'en-US'
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
  if (appSettings.value.voiceContinuous) {
    return isRecordingVoice.value ? t('tooltips.voiceRecording') : t('tooltips.voiceContinuous')
  }
  return t('tooltips.voiceHold')
})

function getCurrentTime() {
  const now = new Date()
  return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
}

// Navigate back to avatar selection page
const goToSelect = () => {
  sessionStorage.removeItem('selectedAvatar')
  avatarSelected.value = false
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

const { startPlay, stopPlay } = useWebRTC({
  onNotification: showNotification
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

// 检查后端是否就绪
const checkBackendReady = async () => {
  try {
    const response = await fetch('/health')
    if (response.ok) {
      const data = await response.json()
      if (data.ready) {
        backendReady.value = true
        console.log('✅ 后端已就绪')
        return true
      }
    }
  } catch (error) {
    console.log('⏳ 等待后端启动...')
  }
  return false
}

const handleStartConnection = async () => {
  console.log('🚀 用户点击"开始连接"按钮')
  
  // 再次确认后端是否就绪
  if (!backendReady.value) {
    showNotification(t('notifications.backendNotReady'), 'warning')
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
      showNotification(t('notifications.connectSuccess'), 'success')
    }
    
    const checkConnection = setInterval(() => {
      const video = document.getElementById('video')
      if (video && video.readyState >= 3 && video.videoWidth > 0) {
        connectionStatus.value = 'connected'
        clearInterval(checkConnection)
        
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
    showNotification(t('notifications.connectFailed'), 'error')
  }
}

const handleStopConnection = () => {
  stopPlay()
  connectionStatus.value = 'disconnected'
  showNotification(t('notifications.disconnected'), 'info')
}

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
    const response = await fetch('/human', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: message,
        type: 'chat',
        interrupt: true,
        sessionid: sessionId.value
      })
    })
    
    if (response.ok) {
      const data = await response.json()
      console.log('收到大模型回复:', data)
      
      // 显示大模型的回复
      if (data.response || data.text) {
        isThinking.value = false
        addMessage(data.response || data.text, 'ai')
      }
    } else {
      throw new Error(`HTTP ${response.status}`)
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
    await fetch('/human', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: message,
        type: 'echo',
        interrupt: true,
        sessionid: sessionId.value
      })
    })
    
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

const { startRecognition, stopRecognition, isSupported, updateSettings } = useSpeechRecognition({
  onResult: (text) => {
    // 实时显示识别的中间结果
    chatInput.value = text
  },
  language: appSettings.value.voiceLanguage,
  continuous: appSettings.value.voiceContinuous,
  onFinalResult: async (text) => {
    // 在非连续模式下，识别完成后自动停止录音
    if (!appSettings.value.voiceContinuous && isRecordingVoice.value && mediaRecorder) {
      console.log('识别完成，自动停止录音（非连续模式）')
      stopVoiceRecording()
    }
    
    if (text.trim()) {
      addMessage(text, 'user')
      // 清空输入框，准备下一次识别
      chatInput.value = ''
      isThinking.value = true
      
      try {
        const response = await fetch('/human', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            type: 'chat',
            interrupt: true,
            sessionid: sessionId.value
          })
        })
        
        if (response.ok) {
          const data = await response.json()
          console.log('收到大模型回复:', data)
          
          // 显示大模型的回复
          if (data.response || data.text) {
            isThinking.value = false
            addMessage(data.response || data.text, 'ai')
          }
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

const startVoiceRecording = async () => {
  if (isRecordingVoice.value) return
  
  // 检查是否已连接
  if (!isConnected.value) {
    showNotification(t('notifications.connectFirst'), 'warning')
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)
    
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data)
      }
    }
    
    mediaRecorder.start()
    isRecordingVoice.value = true
    
    if (isSupported) {
      startRecognition()
    }
  } catch (error) {
    console.error('无法访问麦克风:', error)
    showNotification(t('notifications.micPermission'), 'error')
  }
}

const stopVoiceRecording = async () => {
  if (!isRecordingVoice.value || !mediaRecorder) return
  
  console.log('停止语音录音')
  
  mediaRecorder.stop()
  isRecordingVoice.value = false
  
  // 清空输入框中的临时识别结果
  chatInput.value = ''
  
  // 停止浏览器语音识别
  if (isSupported) {
    stopRecognition()
  }
  
  // 等待录音数据收集完成（用于可能的后端识别）
  mediaRecorder.onstop = async () => {
    // 关闭麦克风流
    mediaRecorder.stream.getTracks().forEach(track => track.stop())
    
    // 如果浏览器支持 Web Speech API，优先使用浏览器识别，不发送到后端
    // 浏览器识别的结果会通过 onFinalResult 回调处理
    if (isSupported) {
      console.log('使用浏览器语音识别，无需发送到后端')
      audioChunks = []
      return
    }
    
    // 浏览器不支持时，才发送音频到后端进行 ASR 识别
    if (audioChunks.length > 0) {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' })
      
      try {
        showNotification(t('notifications.voiceRecognizing'), 'info')
        
        const formData = new FormData()
        formData.append('file', audioBlob, 'voice.webm')
        formData.append('sessionid', sessionId.value)
        
        const response = await fetch('/asr', {
          method: 'POST',
          body: formData
        })
        
        if (response.ok) {
          const data = await response.json()
          console.log('ASR 识别成功:', data)
          
          if (data.text) {
            // 显示用户说的话
            addMessage(data.text, 'user')
            showNotification(t('notifications.voiceRecognized'), 'success')
            
            // 显示 AI 的回复
            if (data.response) {
              addMessage(data.response, 'ai')
            }
          } else {
            showNotification(t('notifications.voiceNoContent'), 'warning')
          }
        } else {
          console.error('ASR 识别失败:', response.status)
          showNotification(t('notifications.voiceFailed'), 'error')
        }
      } catch (error) {
        console.error('ASR 请求失败:', error)
        showNotification(t('notifications.voiceRequestFailed'), 'error')
      }
    }
    
    // 清空音频数据
    audioChunks = []
  }
}

// 处理语音按钮的按下事件（用于按住说话模式）
const handleVoiceButtonPress = (e) => {
  // 在连续识别模式下，不处理按下事件
  if (appSettings.value.voiceContinuous) {
    return
  }
  startVoiceRecording()
}

// 处理语音按钮的释放事件（用于按住说话模式）
const handleVoiceButtonRelease = (e) => {
  // 在连续识别模式下，不处理释放事件
  if (appSettings.value.voiceContinuous) {
    return
  }
  stopVoiceRecording()
}

// 处理语音按钮的点击事件（用于连续识别模式）
const handleVoiceButtonClick = (e) => {
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

// 清空对话历史
const clearChatHistory = async () => {
  if (!isConnected.value) {
    showNotification('请先连接', 'warning')
    return
  }
  
  try {
    const response = await fetch('/clear_history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionid: sessionId.value
      })
    })
    
    if (response.ok) {
      // 清空前端显示的消息（保留欢迎消息）
      chatMessages.value = [
        { 
          type: 'ai', 
          text: t('chat.welcomeMessage'),
          time: getCurrentTime()
        }
      ]
      showNotification('对话历史已清空', 'success')
    } else {
      throw new Error(`HTTP ${response.status}`)
    }
  } catch (error) {
    console.error('Failed to clear history:', error)
    showNotification('清空历史失败，请重试', 'error')
  }
}

onMounted(async () => {
  console.log('✅ Vue 应用已挂载')
  console.log('后端 API 地址: /offer (通过 Vite proxy 转发到 localhost:8010)')
  
  // 加载语言设置
  loadLocale()
  
  // 设置欢迎消息
  if (chatMessages.value.length > 0 && !chatMessages.value[0].text) {
    chatMessages.value[0].text = t('chat.welcomeMessage')
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

/* ── Full-screen page ── */
.page-container {
  width: 100%;
  height: 100vh;
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
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 20;
  padding: 12px 12px 20px;
  background: linear-gradient(to top, rgba(0,0,0,0.85), rgba(0,0,0,0.5), transparent);
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
}

.input-pill {
  flex: 1;
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
  background: transparent;
  border: none;
  color: white;
  font-size: 0.95rem;
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
.send-pill-btn,
.disconnect-pill-btn {
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

.disconnect-pill-btn {
  background: rgba(239, 68, 68, 0.7);
  color: white;
  backdrop-filter: blur(8px);
}

.disconnect-pill-btn:hover {
  background: var(--danger);
  transform: scale(1.08);
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
}
</style>
