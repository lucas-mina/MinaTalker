// Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
export function useWebRTC(options = {}) {
  let pc = null
  let sessionIdValue = 0
  /** Prevents overlapping startPlay() calls (e.g. double-click / fast avatar switch). */
  let connectionInProgress = false
  const { onNotification } = options
  
  /**
   * Build ICE servers from config.
   * @param {string|null|undefined|{ urls: string|string[], username?: string, credential?: string }} iceConfig
   *   - string: single STUN/TURN URL (no auth)
   *   - object: { urls, username?, credential? } for TURN with optional auth (like main.yaml turn_config)
   *   - null/undefined: no ICE servers
   */
  const startPlay = async (iceConfig = 'stun:stun.miwifi.com:3478') => {
    if (connectionInProgress) {
      const err = new Error('WebRTC connection already in progress')
      err.code = 'CONNECTION_IN_PROGRESS'
      throw err
    }
    connectionInProgress = true
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
      
      const selectedAvatar = JSON.parse(sessionStorage.getItem('selectedAvatar') || 'null')
      const payload = {
        type: 'offer',
        sdp: pc.localDescription.sdp,
        avatar_id: selectedAvatar?.id ?? null
      }

      let data
      const useWs = options.useWs !== false
      if (useWs) {
        console.log('🔗 通过 WebSocket 发送 Offer...')
        const wsScheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${wsScheme}//${location.host}/ws`
        data = await new Promise((resolve, reject) => {
          const ws = new WebSocket(wsUrl)
          let settled = false

          const settle = (fn, value) => {
            if (settled) return
            settled = true
            fn(value)
          }

          const timeout = setTimeout(() => {
            ws.close()
            settle(reject, new Error('WebSocket signaling timeout'))
          }, 30000)

          ws.onopen = () => {
            ws.send(JSON.stringify(payload))

            // Trickle ICE candidates to the server as they are gathered
            pc.onicecandidate = (event) => {
              if (!event.candidate || ws.readyState !== WebSocket.OPEN) return
              ws.send(JSON.stringify({
                type: 'candidate',
                candidate: event.candidate.candidate,
                sdpMid: event.candidate.sdpMid,
                sdpMLineIndex: event.candidate.sdpMLineIndex,
              }))
            }
          }

          ws.onmessage = (event) => {
            let msg
            try { msg = JSON.parse(event.data) } catch (e) {
              ws.close()
              settle(reject, e)
              return
            }
            if (msg.type === 'answer') {
              clearTimeout(timeout)
              // Keep ws open for trickle; store on pc so stopPlay can send bye
              pc._signalingWs = ws
              settle(resolve, msg)
            } else if (msg.type === 'candidate') {
              // Server-side trickle candidate — add to local PC
              if (pc.remoteDescription && msg.candidate) {
                pc.addIceCandidate({ candidate: msg.candidate, sdpMid: msg.sdpMid, sdpMLineIndex: msg.sdpMLineIndex })
                  .catch(e => console.warn('addIceCandidate error:', e))
              }
            } else if (msg.type === 'pong') {
              // Heartbeat response — nothing to do
            } else if (msg.type === 'bye') {
              ws.close()
            } else if (msg.type === 'error') {
              clearTimeout(timeout)
              ws.close()
              settle(reject, new Error(msg.error || 'signaling error'))
            }
          }

          ws.onerror = () => {
            clearTimeout(timeout)
            settle(reject, new Error('WebSocket error'))
          }

          ws.onclose = () => {
            clearTimeout(timeout)
          }
        })
      } else {
        console.log('🔗 通过 HTTP POST 发送 Offer...')
        const response = await fetch('/offer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sdp: payload.sdp,
            type: pc.localDescription.type,
            avatar_id: payload.avatar_id
          })
        })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        data = await response.json()
      }

      console.log('📥 收到服务器响应，会话ID:', data.sessionid)
      
      // 保存 sessionId
      sessionIdValue = data.sessionid
      const sessionInput = document.getElementById('sessionid')
      if (sessionInput) {
        sessionInput.value = data.sessionid
      }
      
      // 设置远程描述（仅当此 PC 仍在等待 answer，避免错用另一轮连接的 answer）
      if (pc.signalingState !== 'have-local-offer') {
        throw new Error('PeerConnection was replaced or closed; ignoring stale answer')
      }
      const answer = new RTCSessionDescription({
        sdp: data.sdp,
        type: data.type
      })
      await pc.setRemoteDescription(answer)
      
      console.log('✅ WebRTC 连接建立成功！')
      
      return sessionIdValue
      
    } catch (error) {
      console.error('❌ WebRTC 连接失败:', error)
      // Hide error message if instance not yet ready
      // if (onNotification) {
      //   onNotification(`WebRTC 连接失败: ${error.message}`, 'error')
      // }
      if (pc) {
        pc.close()
        pc = null
      }
      throw error
    } finally {
      connectionInProgress = false
    }
  }
  
  const stopPlay = () => {
    console.log('停止 WebRTC 连接...')
    
    if (pc) {
      // Send bye to the server before tearing down
      const ws = pc._signalingWs
      if (ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(JSON.stringify({ type: 'bye' })) } catch (_) {}
        ws.close()
      }
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
