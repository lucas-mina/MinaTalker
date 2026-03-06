// English language pack
export default {
  header: {
    title: 'MinaMina',
    subtitle: 'Real-time Interactive Digital Human',
    status: {
      connected: 'Connected',
      connecting: 'Connecting...',
      disconnected: 'Disconnected'
    },
    session: 'Session',
    github: 'GitHub',
    backToSelect: 'Back to Avatar Selection'
  },
  
  chat: {
    title: 'Chat Interaction',
    chatMode: 'Chat Mode',
    ttsMode: 'TTS Mode',
    inputPlaceholder: 'Type a message, press Enter to send...',
    inputPlaceholderDisconnected: 'Please connect first...',
    sendButton: 'Send',
    voiceButton: 'Hold to Talk',
    voiceButtonContinuous: 'Continuous',
    voiceButtonRecording: 'Release to Send',
    voiceButtonRecordingContinuous: 'Recognizing...',
    ttsInputPlaceholder: 'Enter text for the digital human to read aloud...',
    ttsButton: 'Start Reading',
    ttsTitle: 'Input Text to Read',
    welcomeMessage: "Hello!, I'm {avatarName}",
    you: 'You',
    ai: 'Mina'
  },
  
  video: {
    title: 'Digital Human Video',
    connect: 'Start Connection',
    disconnect: 'Disconnect',
    startRecord: 'Start Recording',
    stopRecord: 'Stop Recording',
    download: 'Download Recording',
    recording: 'Recording',
    overlayTextReady: 'Click "Start Connection" to begin',
    overlayTextLoading: 'Backend is starting, please wait...',
    backendStarting: 'Backend Starting...'
  },
  
  settings: {
    title: 'Settings',
    systemSettings: 'System Settings',
    save: 'Save Settings',
    resetDefault: 'Reset to Default',
    cancel: 'Cancel',
    confirm: 'OK',
    confirmTitle: 'Confirm',
    confirmMessage: 'Are you sure you want to reset to default settings? This will clear all custom configurations.',
    
    webrtc: {
      title: 'WebRTC Connection',
      useStun: 'Use STUN Server',
      useStunDesc: 'Enable STUN for better NAT traversal',
      stunServer: 'STUN Server Address',
      googleStun: 'Google STUN (Recommended)',
      xiaomiStun: 'Xiaomi STUN',
      tencentStun: 'Tencent STUN',
      customStun: 'Custom...',
      customStunAddress: 'Custom STUN Address',
      turnUsername: 'TURN Username',
      turnUsernameDesc: 'TURN server auth username (optional)',
      turnCredential: 'TURN Password',
      turnCredentialDesc: 'TURN server auth credential (optional)'
    },
    
    recording: {
      title: 'Recording',
      autoRecord: 'Auto Recording',
      autoRecordDesc: 'Start recording automatically after connection',
      format: 'Recording Format'
    },
    
    display: {
      title: 'Interface',
      showDebug: 'Show Debug Panel',
      showDebugDesc: 'Display connection status and technical info',
      showTimestamp: 'Message Timestamp',
      showTimestampDesc: 'Show message time in chat',
      theme: 'Theme',
      themeDark: 'Dark Mode (Default)',
      themeLight: 'Light Mode',
      themeAuto: 'Follow System',
      language: 'Interface Language',
      videoSize: 'Video Size',
      videoSizeDesc: 'Adjust the display size of digital human video'
    },
    
    voice: {
      title: 'Voice Recognition',
      currentMode: 'Current Mode: Server SenseVoice + VAD',
      currentModeDesc: 'Client audio is captured continuously, then server-side VAD filters silence before SenseVoice recognition.',
      currentModeNote: 'Tip: use the mic button to mute/unmute listening.',
      continuous: 'Continuous Recognition',
      continuousDesc: 'Continuously listen for voice input',
      language: 'Recognition Language',
      langAuto: 'Auto-detect (server)',
      langZhCN: 'Chinese (Simplified)',
      langEnUS: 'English (US)',
      langJaJP: 'Japanese',
      langKoKR: 'Korean'
    }
  },
  
  notifications: {
    settingsSaved: 'Settings saved',
    settingsReset: 'Reset to default settings',
    backendReady: 'Backend is ready, you can start connecting',
    backendTimeout: 'Backend startup timeout, please check service status',
    connectSuccess: 'Connected successfully! You can now start chatting with me.',
    connectFailed: 'Connection failed, please try again later',
    connectTimeout: 'Connection timeout, please check if backend service is running',
    disconnected: 'Connection closed',
    recordStart: 'Recording started',
    recordStartFailed: 'Recording failed',
    recordStop: 'Recording saved, click download button to get the video',
    recordStopSimple: 'Recording saved',
    recordStopFailed: 'Failed to stop recording',
    noRecordFile: 'No recording file available',
    downloading: 'Starting download...',
    messageFailed: 'Failed to send message, please try again',
    ttsFailed: 'Failed to send TTS request',
    micPermission: 'Cannot access microphone, please check browser permissions',
    voiceRecognizing: 'Recognizing voice...',
    voiceRecognized: 'Voice recognition completed',
    voiceNoContent: 'No voice content recognized',
    voiceNoSpeech: 'No speech detected',
    voiceFailed: 'Voice recognition failed',
    voiceRequestFailed: 'Voice recognition request failed',
    voiceMessageFailed: 'Failed to send voice message, please try again',
    sherpaVadFailed: 'Sherpa VAD failed to initialize or run. Please refresh and try again.',
    voiceMuted: 'Microphone muted',
    voiceUnmuted: 'Microphone unmuted',
    connectFirst: 'Please connect first',
    backendNotReady: 'Backend is not fully started, please wait...'
  },
  
  tooltips: {
    connectDisabled: 'Backend is starting, please wait...',
    recordDisabled: 'Please connect first before recording',
    downloadDisabled: 'No recording file available',
    voiceDisabled: 'Please connect first',
    voiceMute: 'Click to mute microphone',
    voiceUnmute: 'Click to unmute microphone',
    voiceContinuous: 'Click to start continuous recognition',
    voiceRecording: 'Click to stop',
    voiceHold: 'Hold to talk'
  }
}
