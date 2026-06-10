# WebSocket Messages (Client <-> Server)

This document lists the **current** WebSocket message contract used between client and server on endpoint:

- `ws://<host>/ws` (or `wss://<host>/ws`)

### WebSocket URL query (optional)

When opening the socket, the client may append query parameters (same pattern as `access_token`):

- `access_token` — Bearer token for internal auth.
- `session_id` — canonical Core/internal LLM thread id (string) on the query string.
- `sessionid` — **client alias** for the same Core thread id when opening `/ws` (non-numeric string, e.g. UUID). The server normalizes to the internal LLM field `session_id` when talking to Core.

The server keeps the resolved Core id for this connection and uses it as the default for `chat.request` when the message omits a Core id. A Core id on each `chat.request` overrides for that turn only.

Example: `wss://host/ws?access_token=...&sessionid=core-thread-uuid` (or `&session_id=...`)

The bundled web client uses query `sessionid` and puts Core id on the first `offer` as `sessionid` when configured (`internalLlmSessionId` ref or `sessionStorage` key `internal_llm_session_id`).

## Client -> Server

### 1) `offer`
Starts WebRTC negotiation.

```json
{
  "type": "offer",
  "sdp": "<local offer sdp>",
  "avatar_id": 1,
  "access_token": "<optional bearer token>",
  "sessionid": "<optional Core LLM thread id (client key; server maps to session_id for Core)>"
}
```

### 2) `candidate`
Trickle ICE candidate from browser to server.

```json
{
  "type": "candidate",
  "candidate": "candidate:...",
  "sdpMid": "0",
  "sdpMLineIndex": 0
}
```

### 3) `chat.request`
Send chat/echo text request through WS (main text path).

```json
{
  "type": "chat.request",
  "request_id": "12345",
  "message_type": "chat",
  "text": "hello",
  "interrupt": true,
  "access_token": "<optional bearer token>"
}
```

Notes:
- `message_type`: `"chat"` or `"echo"`.
- `request_id` is echoed back in `chat.response`.
- `lang` (optional): omit the field when unused. If set (e.g. `zh-CN`), server forwards it to the LLM; for `internal` provider it becomes Core `chat` payload `data.lang`.
- Core LLM thread (optional): send **`session_id`** (canonical) or **`sessionid`** when the value is a **non-numeric** string (e.g. UUID). The server always forwards to Core as **`data.session_id`**. Numeric `sessionid` in the message is treated as the **WebRTC avatar room** id (legacy); after negotiation the server usually resolves the room from the WebSocket context, so the bundled client omits numeric `sessionid` on `chat.request` and only sends `sessionid` for Core when needed.

### 4) `interrupt_talk`
Interrupt current speaking output.

```json
{
  "type": "interrupt_talk",
  "sessionid": 123456,
  "access_token": "<optional bearer token>"
}
```

### 5) `is_speaking`
Ask server to return speaking state immediately.

```json
{
  "type": "is_speaking",
  "sessionid": 123456
}
```

### 6) `ping`
Optional app-level ping.

```json
{ "type": "ping" }
```

### 7) `bye`
Close session gracefully.

```json
{ "type": "bye" }
```

## Server -> Client

### 1) `answer`
WebRTC answer to client offer.

```json
{
  "type": "answer",
  "sdp": "<answer sdp>",
  "sessionid": 123456
}
```

### 2) `candidate`
Trickle ICE candidate from server to browser.

```json
{
  "type": "candidate",
  "candidate": "candidate:...",
  "sdpMid": "0",
  "sdpMLineIndex": 0
}
```

### 3) `chat.response`
Response for `chat.request`.

```json
{
  "type": "chat.response",
  "request_id": "12345",
  "code": 0,
  "msg": "ok",
  "response": "..."
}
```

### 4) `interrupt_response`
Response for `interrupt_talk`.

```json
{
  "type": "interrupt_response",
  "code": 0,
  "msg": "ok"
}
```

### 5) `speaking_state`
Current speaking state push/poll result.

```json
{
  "type": "speaking_state",
  "sessionid": 123456,
  "speaking": false
}
```

### 6) `pong`
Response to app-level `ping`.

```json
{ "type": "pong" }
```

### 7) `bye`
Server confirms close.

```json
{ "type": "bye" }
```

### 8) `error`
Protocol or runtime error.

```json
{
  "type": "error",
  "error": "unknown message type: 'xxx'"
}
```

## Auth Token Handling (Current)

- Client may pass token by:
  - WS URL query: `?access_token=...`
  - Message field: `access_token`
- Server forwards token to internal LLM flow when provider is `internal`.
- For `chat.request`, if message token is missing, server falls back to session token captured during offer/WS connect.
