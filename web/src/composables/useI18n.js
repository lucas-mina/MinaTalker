// 语言管理 Composable
import { ref, computed } from 'vue'
import zhCN from '../locales/zh-CN.js'
import enUS from '../locales/en-US.js'

const languages = {
  'zh-CN': zhCN,
  'en-US': enUS
}

// 当前语言，默认中文
const currentLocale = ref('zh-CN')

export function useI18n() {
  // 获取翻译文本
  const t = (key, params = {}) => {
    const keys = key.split('.')
    let value = languages[currentLocale.value]
    
    for (const k of keys) {
      if (value && typeof value === 'object') {
        value = value[k]
      } else {
        return key // 如果找不到，返回 key 本身
      }
    }
    
    let result = value || key
    // Replace {placeholder} tokens with params values
    if (params && typeof result === 'string') {
      result = result.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
    }
    return result
  }
  
  // 切换语言
  const setLocale = (locale) => {
    if (languages[locale]) {
      currentLocale.value = locale
      // 保存到 localStorage
      localStorage.setItem('linly-talker-stream-language', locale)
    }
  }
  
  // 从 localStorage 加载语言设置
  const loadLocale = () => {
    const savedLocale = localStorage.getItem('linly-talker-stream-language')
    if (savedLocale && languages[savedLocale]) {
      currentLocale.value = savedLocale
    }
  }
  
  // 获取当前语言
  const locale = computed(() => currentLocale.value)
  
  return {
    t,
    locale,
    setLocale,
    loadLocale
  }
}
