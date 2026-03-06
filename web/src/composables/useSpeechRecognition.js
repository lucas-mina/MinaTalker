// Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
import { ref } from 'vue'

export function useSpeechRecognition(options = {}) {
  const {
    onResult = () => {},
    onFinalResult = () => {},
    onError = () => {},
    language = 'zh-CN',
    continuous = true
  } = options
  
  const isSupported = ref(
    'webkitSpeechRecognition' in window || 'SpeechRecognition' in window
  )
  
  let recognition = null
  let isRecognizing = false
  let shouldContinue = false
  
  if (isSupported.value) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    recognition = new SpeechRecognition()
    
    recognition.continuous = continuous
    recognition.interimResults = true
    recognition.lang = language
    
    recognition.onresult = (event) => {
      let interimTranscript = ''
      let finalTranscript = ''
      
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const transcript = event.results[i][0].transcript
        
        if (event.results[i].isFinal) {
          finalTranscript += transcript
        } else {
          interimTranscript += transcript
        }
      }
      
      if (interimTranscript) {
        onResult(interimTranscript)
      }
      
      if (finalTranscript) {
        onFinalResult(finalTranscript)
      }
    }
    
    recognition.onerror = (event) => {
      console.error('语音识别错误:', event.error)
      
      // no-speech 错误在连续模式下很常见，不需要特别处理
      if (event.error === 'no-speech' && shouldContinue) {
        console.log('未检测到语音，继续监听...')
        return
      }
      
      onError(event.error)
    }
    
    recognition.onend = () => {
      isRecognizing = false
      console.log('语音识别结束，shouldContinue:', shouldContinue)
      
      // 在连续模式下，如果标志为 true，则自动重启识别
      if (shouldContinue) {
        console.log('连续模式：自动重启语音识别')
        setTimeout(() => {
          if (shouldContinue && !isRecognizing) {
            try {
              recognition.start()
              isRecognizing = true
            } catch (error) {
              console.error('重启语音识别失败:', error)
            }
          }
        }, 100)
      }
    }
  }
  
  const startRecognition = () => {
    if (recognition && !isRecognizing) {
      try {
        shouldContinue = true
        recognition.start()
        isRecognizing = true
        console.log('启动语音识别，连续模式:', recognition.continuous)
      } catch (error) {
        console.error('启动语音识别失败:', error)
      }
    }
  }
  
  const stopRecognition = () => {
    if (recognition) {
      try {
        shouldContinue = false
        if (isRecognizing) {
          recognition.stop()
        }
        console.log('停止语音识别')
      } catch (error) {
        console.error('停止语音识别失败:', error)
      }
    }
  }
  
  const updateSettings = (settings) => {
    if (recognition) {
      const lang = settings.language && settings.language !== 'auto' ? settings.language : 'en-US'
      recognition.lang = lang
      recognition.continuous = settings.continuous !== undefined ? settings.continuous : true
    }
  }
  
  return {
    isSupported: isSupported.value,
    startRecognition,
    stopRecognition,
    updateSettings
  }
}
