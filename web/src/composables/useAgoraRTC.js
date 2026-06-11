// Agora RTC audience path (1:1 via SDRTN). Server publishes avatar stream.
import AgoraRTC from 'agora-rtc-sdk-ng'

export function useAgoraRTC(options = {}) {
  let client = null
  let sessionIdValue = 0
  let signalingWs = null
  let connectionInProgress = false
  let publisherUid = 10001

  const onWsMessage = typeof options.onWsMessage === 'function' ? options.onWsMessage : null
  const getAccessToken = typeof options.getAccessToken === 'function' ? options.getAccessToken : () => ''
  const getSessionId = typeof options.getSessionId === 'function' ? options.getSessionId : () => ''

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

  const startPlay = async () => {
    if (connectionInProgress) {
      const err = new Error('Agora connection already in progress')
      err.code = 'CONNECTION_IN_PROGRESS'
      throw err
    }
    connectionInProgress = true

    if (client) {
      try { await client.leave() } catch (_) {}
      client = null
    }

    try {
      const selectedAvatar = JSON.parse(sessionStorage.getItem('selectedAvatar') || 'null')
      const accessToken = (getAccessToken() || '').trim()
      const body = { avatar_id: selectedAvatar?.id ?? null }
      if (accessToken) body.access_token = accessToken
      const sessionIdWs = (getSessionId() || '').trim()
      if (sessionIdWs) body.sessionid = sessionIdWs

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

      const sessionInput = document.getElementById('sessionid')
      if (sessionInput) sessionInput.value = sessionIdValue

      client = AgoraRTC.createClient({ mode: 'live', codec: 'vp8' })
      client.on('user-published', async (user, mediaType) => {
        const uidNum = Number(user.uid)
        if (uidNum !== Number(publisherUid)) return
        await client.subscribe(user, mediaType)
        if (mediaType === 'video' && user.videoTrack) {
          const video = document.getElementById('video')
          if (video) user.videoTrack.play(video)
        }
        if (mediaType === 'audio' && user.audioTrack) {
          user.audioTrack.play()
        }
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

    const video = document.getElementById('video')
    if (video) video.srcObject = null
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
