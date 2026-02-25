// Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
export function useWebRTC(options = {}) {
  let pc = null
  let sessionIdValue = 0
  const { onNotification } = options
  
  /**
   * Build ICE servers from config.
   * @param {string|null|undefined|{ urls: string|string[], username?: string, credential?: string }} iceConfig
   *   - string: single STUN/TURN URL (no auth)
   *   - object: { urls, username?, credential? } for TURN with optional auth (like main.yaml turn_config)
   *   - null/undefined: no ICE servers
   */
  const startPlay = async (iceConfig = 'stun:stun.miwifi.com:3478') => {
    console.log('开始连接 WebRTC...')
    console.log('ICE 配置:', iceConfig == null ? '不使用' : (typeof iceConfig === 'string' ? iceConfig : '[TURN with auth]'))

    // 关闭之前的连接
    if (pc) {
      console.log('关闭旧连接...')
      pc.close()
      pc = null
    }

    try {
      console.log('✅ 创建 RTCPeerConnection...')

      const configuration = { iceServers: [] }

      if (iceConfig != null) {
        if (typeof iceConfig === 'string') {
          configuration.iceServers.push({ urls: iceConfig })
        } else if (typeof iceConfig === 'object' && iceConfig !== null) {
          const raw = iceConfig.urls
          const urlList = Array.isArray(raw)
            ? raw.filter(u => typeof u === 'string').map(u => u.trim()).filter(Boolean)
            : (typeof raw === 'string' && raw.trim() ? [raw.trim()] : [])
          if (urlList.length > 0) {
            const entry = { urls: urlList.length === 1 ? urlList[0] : urlList }
            if (typeof iceConfig.username === 'string' && iceConfig.username.trim()) entry.username = iceConfig.username.trim()
            if (typeof iceConfig.credential === 'string' && iceConfig.credential.trim()) entry.credential = iceConfig.credential.trim()
            configuration.iceServers.push(entry)
          }
        }
      }

      pc = new RTCPeerConnection(configuration)
      
      // 添加接收 track 的处理
      pc.ontrack = (event) => {
        console.log('📺 收到媒体流:', event.track.kind)
        const video = document.getElementById('video')
        if (video && event.streams && event.streams[0]) {
          video.srcObject = event.streams[0]
          console.log('✅ 视频流已设置到 video 元素')
        }
      }
      
      // 监听连接状态
      pc.onconnectionstatechange = () => {
        console.log('📡 连接状态:', pc.connectionState)
      }
      
      pc.oniceconnectionstatechange = () => {
        console.log('🧊 ICE 连接状态:', pc.iceConnectionState)
      }
      
      // 添加 transceiver 来接收音视频
      pc.addTransceiver('audio', { direction: 'recvonly' })
      pc.addTransceiver('video', { direction: 'recvonly' })
      
      console.log('📤 创建 Offer...')
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      
      console.log('🔗 发送 Offer 到服务器...')
      const selectedAvatar = JSON.parse(sessionStorage.getItem('selectedAvatar') || 'null')
      const response = await fetch('/offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sdp: pc.localDescription.sdp,
          type: pc.localDescription.type,
          avatar_id: selectedAvatar?.id ?? null
        })
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      const data = await response.json()
      console.log('📥 收到服务器响应，会话ID:', data.sessionid)
      
      // 保存 sessionId
      sessionIdValue = data.sessionid
      const sessionInput = document.getElementById('sessionid')
      if (sessionInput) {
        sessionInput.value = data.sessionid
      }
      
      // 设置远程描述
      const answer = new RTCSessionDescription({
        sdp: data.sdp,
        type: data.type
      })
      await pc.setRemoteDescription(answer)
      
      console.log('✅ WebRTC 连接建立成功！')
      
      return sessionIdValue
      
    } catch (error) {
      console.error('❌ WebRTC 连接失败:', error)
      if (onNotification) {
        onNotification(`WebRTC 连接失败: ${error.message}`, 'error')
      }
      if (pc) {
        pc.close()
        pc = null
      }
      throw error
    }
  }
  
  const stopPlay = () => {
    console.log('停止 WebRTC 连接...')
    
    if (pc) {
      pc.close()
      pc = null
      console.log('✅ WebRTC 连接已关闭')
    }
    
    const video = document.getElementById('video')
    if (video) {
      video.srcObject = null
    }
  }
  
  return {
    startPlay,
    stopPlay
  }
}
