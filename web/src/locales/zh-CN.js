// 中文语言包
export default {
  header: {
    title: 'Linly-Talker-Stream',
    subtitle: '全双工实时交互数字人',
    status: {
      connected: '已连接',
      connecting: '连接中...',
      disconnected: '未连接'
    },
    session: '会话',
    github: 'GitHub',
    backToSelect: '返回选择 Avatar'
  },
  
  chat: {
    title: '对话交互',
    chatMode: '对话模式',
    ttsMode: '朗读模式',
    inputPlaceholder: '输入消息，按 Enter 发送...',
    inputPlaceholderDisconnected: '请先启动连接...',
    sendButton: '发送',
    voiceButton: '按住说话',
    voiceButtonContinuous: '连续识别',
    voiceButtonRecording: '松开发送',
    voiceButtonRecordingContinuous: '识别中...',
    ttsInputPlaceholder: '在这里输入想让数字人朗读的文字内容...',
    ttsButton: '开始朗读',
    ttsTitle: '输入朗读文本',
    welcomeMessage: '你好！我是 Linly 数字人，很高兴见到你。点击右侧"启动连接"开始我们的对话吧！',
    you: '你',
    ai: 'Linly'
  },
  
  video: {
    title: '数字人视频',
    connect: '启动连接',
    disconnect: '断开连接',
    startRecord: '开始录制',
    stopRecord: '停止录制',
    download: '下载录制',
    recording: '录制中',
    overlayTextReady: '点击"启动连接"开始',
    overlayTextLoading: '后端正在启动中，请稍候...',
    backendStarting: '后端启动中...'
  },
  
  settings: {
    title: '设置',
    systemSettings: '系统设置',
    save: '保存设置',
    resetDefault: '恢复默认',
    cancel: '取消',
    confirm: '确定',
    confirmTitle: '确认操作',
    confirmMessage: '确定要恢复默认设置吗？这将清除所有自定义配置。',
    
    webrtc: {
      title: 'WebRTC 连接',
      useStun: '使用 STUN 服务器',
      useStunDesc: '启用 STUN 可提高 NAT 穿透能力',
      stunServer: 'STUN 服务器地址',
      googleStun: 'Google STUN (推荐)',
      xiaomiStun: '小米 STUN',
      tencentStun: '腾讯 STUN',
      customStun: '自定义...',
      customStunAddress: '自定义 STUN 地址',
      turnUsername: 'TURN 用户名',
      turnUsernameDesc: 'TURN 服务器认证用户名（可选）',
      turnCredential: 'TURN 密码',
      turnCredentialDesc: 'TURN 服务器认证密码（可选）'
    },
    
    recording: {
      title: '录制功能',
      autoRecord: '自动录制',
      autoRecordDesc: '连接成功后自动开始录制',
      format: '录制格式'
    },
    
    display: {
      title: '界面显示',
      showDebug: '显示调试面板',
      showDebugDesc: '显示连接状态和技术信息',
      showTimestamp: '消息时间戳',
      showTimestampDesc: '在对话中显示消息时间',
      theme: '主题色调',
      themeDark: '深色模式 (默认)',
      themeLight: '浅色模式',
      themeAuto: '跟随系统',
      language: '界面语言',
      videoSize: '视频大小',
      videoSizeDesc: '调整数字人视频的显示尺寸'
    },
    
    voice: {
      title: '语音识别',
      currentMode: '当前模式：浏览器语音识别 (Web Speech API)',
      currentModeDesc: '使用浏览器内置语音识别，无需发送音频到服务器，实时识别速度快。',
      currentModeNote: '⚠️ 仅支持 Chrome/Edge 浏览器，需要联网。',
      continuous: '连续识别',
      continuousDesc: '持续监听语音输入',
      language: '识别语言',
      langZhCN: '中文 (简体)',
      langEnUS: '英语 (美国)',
      langJaJP: '日语',
      langKoKR: '韩语'
    }
  },
  
  notifications: {
    settingsSaved: '设置已保存',
    settingsReset: '已恢复默认设置',
    backendReady: '后端已就绪，可以开始连接',
    backendTimeout: '后端启动超时，请检查服务状态',
    connectSuccess: '连接成功！现在你可以开始和我对话了。',
    connectFailed: '连接失败，请稍后重试',
    connectTimeout: '连接超时，请检查后端服务是否正常运行',
    disconnected: '连接已断开',
    recordStart: '开始录制',
    recordStartFailed: '录制失败',
    recordStop: '录制已保存，点击下载按钮获取视频',
    recordStopSimple: '录制已保存',
    recordStopFailed: '停止录制失败',
    noRecordFile: '没有可下载的录制文件',
    downloading: '开始下载...',
    messageFailed: '消息发送失败，请重试',
    ttsFailed: '朗读请求发送失败',
    micPermission: '无法访问麦克风，请检查浏览器权限设置',
    voiceRecognizing: '正在识别语音...',
    voiceRecognized: '语音识别完成',
    voiceNoContent: '未识别到语音内容',
    voiceFailed: '语音识别失败',
    voiceRequestFailed: '语音识别请求失败',
    voiceMessageFailed: '语音消息发送失败，请重试',
    connectFirst: '请先启动连接',
    backendNotReady: '后端尚未完全启动，请稍候...'
  },
  
  tooltips: {
    connectDisabled: '后端正在启动中，请稍候...',
    recordDisabled: '请先启动连接后再录制',
    downloadDisabled: '暂无可下载的录制文件',
    voiceDisabled: '请先启动连接',
    voiceContinuous: '点击开始连续识别',
    voiceRecording: '点击停止',
    voiceHold: '按住说话'
  }
}
