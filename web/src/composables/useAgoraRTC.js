// Agora RTC audience path (1:1 via SDRTN). Server publishes avatar stream.
import AgoraRTC from 'agora-rtc-sdk-ng'

const AGORA_WEB_CODECS = new Set(['av1', 'h264', 'vp8', 'vp9', 'h265'])

function resolveWebCodec(codec) {
  const name = String(codec || 'h264').trim().toLowerCase()
  return AGORA_WEB_CODECS.has(name) ? name : 'h264'
}

export function useAgoraRTC(options = {}) {
  let client = null
  let sessionIdValue = 0
  let signalingWs = null
  let connectionInProgress = false
  let publisherUid = 10001
  let remoteVideoTrack = null
  let remoteAudioTrack = null

  const onWsMessage = typeof options.onWsMessage === 'function' ? options.onWsMessage : null
  const getAccessToken = typeof options.getAccessToken === 'function' ? options.getAccessToken : () => ''
  const getSessionId = typeof options.getSessionId === 'function' ? options.getSessionId : () => ''
  const getUserId = typeof options.getUserId === 'function' ? options.getUserId : () => ''

  const _openSignalingWs = (sessionid) => new Promise((resolve, reject) => {
    const accessToken = (getAccessToken() || '').trim()
    const sessionIdWs = (getSessionId() || '').trim()
    const wsScheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsQuery = new URLSearchParams()
    if (accessToken) wsQuery.set('access_token', accessToken)
    if (sessionIdWs) wsQuery.set('sessionid', sessionIdWs)
    const qs = wsQuery.toString()
    const wsUrl = qs ? `${wsScheme}//${location.host}/ws?${qs}` : `${wsScheme}//${location.host}/ws`

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
      const payload = { type: 'agora.attach', sessionid }
      if (accessToken) payload.access_token = accessToken
      if (sessionIdWs) payload.session_id = sessionIdWs
      ws.send(JSON.stringify(payload))
    }

    ws.onmessage = (event) => {
      let msg
      try { msg = JSON.parse(event.data) } catch (e) {
        ws.close()
        settle(reject, e)
        return
      }
      if (msg.type === 'agora.attached') {
        clearTimeout(timeout)
        signalingWs = ws
        settle(resolve, ws)
      } else if (msg.type === 'error') {
        clearTimeout(timeout)
        ws.close()
        settle(reject, new Error(msg.error || 'signaling error'))
      } else if (onWsMessage) {
        onWsMessage(msg)
      }
    }

    ws.onerror = () => {
      clearTimeout(timeout)
      settle(reject, new Error('WebSocket error'))
    }
  })

  const _releaseRemoteTracks = () => {
    if (remoteVideoTrack) {
      try { remoteVideoTrack.stop() } catch (_) {}
      remoteVideoTrack = null
    }
    if (remoteAudioTrack) {
      try { remoteAudioTrack.stop() } catch (_) {}
      remoteAudioTrack = null
    }
    const video = document.getElementById('video')
    if (video) video.srcObject = null
  }

  const _subscribePublisher = async (user, mediaType) => {
    const uidNum = Number(user.uid)
    if (uidNum !== Number(publisherUid)) return
    await client.subscribe(user, mediaType)
    if (mediaType === 'video' && user.videoTrack) {
      if (remoteVideoTrack && remoteVideoTrack !== user.videoTrack) {
        try { remoteVideoTrack.stop() } catch (_) {}
      }
      remoteVideoTrack = user.videoTrack
      const video = document.getElementById('video')
      if (video) {
        try { remoteVideoTrack.stop() } catch (_) {}
        await remoteVideoTrack.play(video)
      }
    }
    if (mediaType === 'audio' && user.audioTrack) {
      if (remoteAudioTrack && remoteAudioTrack !== user.audioTrack) {
        try { remoteAudioTrack.stop() } catch (_) {}
      }
      remoteAudioTrack = user.audioTrack
      remoteAudioTrack.play()
    }
  }

  const _subscribeExistingPublishers = async () => {
    if (!client) return
    for (const user of client.remoteUsers) {
      if (Number(user.uid) !== Number(publisherUid)) continue
      if (user.hasVideo) await _subscribePublisher(user, 'video')
      if (user.hasAudio) await _subscribePublisher(user, 'audio')
    }
  }

  const startPlay = async () => {
    if (connectionInProgress) {
      const err = new Error('Agora connection already in progress')
      err.code = 'CONNECTION_IN_PROGRESS'
      throw err
    }
    connectionInProgress = true

    _releaseRemoteTracks()
    if (client) {
      try { await client.leave() } catch (_) {}
      client = null
    }

    try {
      const selectedAvatar = JSON.parse(sessionStorage.getItem('selectedAvatar') || 'null')
      const accessToken = (getAccessToken() || '').trim()
      const coreSessionId = (getSessionId() || '').trim()
      const userId = (getUserId() || '').trim()
      const body = { avatar_id: selectedAvatar?.id ?? null }
      if (accessToken) body.access_token = accessToken
      if (userId) body.user_id = userId
      if (coreSessionId) body.session_id = coreSessionId
      // Reuse active Agora room only (not Core LLM session id).
      if (sessionIdValue > 0) body.sessionid = sessionIdValue

      const joinRes = await fetch('/agora/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
        body: JSON.stringify(body),
      })
      if (!joinRes.ok) {
        const errText = await joinRes.text()
        throw new Error(errText || `Agora join failed (${joinRes.status})`)
      }
      const joinData = await joinRes.json()
      sessionIdValue = joinData.sessionid
      publisherUid = joinData.publisher_uid ?? 10001
      if (joinData.reused) {
        console.log('ℹ️ Agora join reused active server session', joinData.channel)
      }

      const sessionInput = document.getElementById('sessionid')
      if (sessionInput) sessionInput.value = sessionIdValue

      client = AgoraRTC.createClient({
        mode: 'live',
        codec: resolveWebCodec(joinData.video_codec),
      })
      client.on('user-published', async (user, mediaType) => {
        await _subscribePublisher(user, mediaType)
      })

      await client.setClientRole('audience')
      const rtcToken = joinData.token_required === false || joinData.token == null || joinData.token === ''
        ? null
        : joinData.token
      await client.join(
        joinData.app_id,
        joinData.channel,
        rtcToken,
        joinData.uid ?? null,
      )
      await _subscribeExistingPublishers()

      await _openSignalingWs(sessionIdValue)
      console.log('✅ Agora RTC connected, sessionid=', sessionIdValue)
      return sessionIdValue
    } catch (error) {
      console.error('❌ Agora RTC connection failed:', error)
      if (client) {
        try { await client.leave() } catch (_) {}
        client = null
      }
      if (sessionIdValue) {
        try {
          await fetch('/agora/leave', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionid: sessionIdValue }),
          })
        } catch (_) {}
      }
      throw error
    } finally {
      connectionInProgress = false
    }
  }

  const stopPlay = async () => {
    if (signalingWs && signalingWs.readyState === WebSocket.OPEN) {
      try { signalingWs.send(JSON.stringify({ type: 'bye' })) } catch (_) {}
      signalingWs.close()
    }
    signalingWs = null

    _releaseRemoteTracks()
    if (client) {
      try { await client.leave() } catch (_) {}
      client = null
    }

    if (sessionIdValue) {
      try {
        await fetch('/agora/leave', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionid: sessionIdValue }),
        })
      } catch (_) {}
    }

    sessionIdValue = 0
  }

  const getSignalingSocket = () => signalingWs

  const sendWsMessage = (payload) => {
    if (!signalingWs || signalingWs.readyState !== WebSocket.OPEN) return false
    signalingWs.send(JSON.stringify(payload))
    return true
  }

  return { startPlay, stopPlay, getSignalingSocket, sendWsMessage }
}
