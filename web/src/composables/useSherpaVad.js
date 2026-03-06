// Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
const SHERPA_VAD_BASE = '/sherpa-vad/sherpa-onnx-wasm-simd-v1.12.28-vad'
const SHERPA_VAD_HELPER_JS = `${SHERPA_VAD_BASE}/sherpa-onnx-vad.js`
const SHERPA_VAD_WASM_MAIN_JS = `${SHERPA_VAD_BASE}/sherpa-onnx-wasm-main-vad.js`
const SHERPA_VAD_WORKLET_JS = '/sherpa-vad/sherpa-vad-worklet.js'

let sherpaRuntimePromise = null

const loadScript = (src) => new Promise((resolve, reject) => {
  const existing = document.querySelector(`script[data-sherpa-src="${src}"]`)
  if (existing) {
    if (existing.dataset.loaded === '1') {
      resolve()
      return
    }
    existing.addEventListener('load', () => resolve(), { once: true })
    existing.addEventListener('error', (e) => reject(e), { once: true })
    return
  }

  const script = document.createElement('script')
  script.src = src
  script.async = true
  script.dataset.sherpaSrc = src
  script.onload = () => {
    script.dataset.loaded = '1'
    resolve()
  }
  script.onerror = (e) => reject(e)
  document.head.appendChild(script)
})

const ensureSherpaRuntime = async () => {
  if (sherpaRuntimePromise) return sherpaRuntimePromise

  sherpaRuntimePromise = new Promise(async (resolve, reject) => {
    try {
      const moduleObj = window.Module || {}
      moduleObj.locateFile = (path) => `${SHERPA_VAD_BASE}/${path}`
      moduleObj.setStatus = () => {}
      moduleObj.onRuntimeInitialized = () => resolve(moduleObj)
      window.Module = moduleObj

      await loadScript(SHERPA_VAD_HELPER_JS)
      await loadScript(SHERPA_VAD_WASM_MAIN_JS)
    } catch (err) {
      sherpaRuntimePromise = null
      reject(err)
    }
  })

  return sherpaRuntimePromise
}

const fileExists = (Module, filename) => {
  const filenameLen = Module.lengthBytesUTF8(filename) + 1
  const ptr = Module._malloc(filenameLen)
  Module.stringToUTF8(filename, ptr, filenameLen)
  const exists = Module._SherpaOnnxFileExists(ptr) === 1
  Module._free(ptr)
  return exists
}

const downsampleBuffer = (buffer, sourceRate, targetRate) => {
  if (sourceRate === targetRate) return buffer
  const ratio = sourceRate / targetRate
  const newLength = Math.round(buffer.length / ratio)
  const result = new Float32Array(newLength)
  let offsetResult = 0
  let offsetBuffer = 0

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
    let accum = 0
    let count = 0
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i]
      count++
    }
    result[offsetResult] = count > 0 ? accum / count : 0
    offsetResult++
    offsetBuffer = nextOffsetBuffer
  }
  return result
}

const mixToMono = (inputBuffer) => {
  const channels = inputBuffer.numberOfChannels || 1
  if (channels <= 1) {
    return new Float32Array(inputBuffer.getChannelData(0))
  }

  const length = inputBuffer.length
  const mono = new Float32Array(length)
  for (let c = 0; c < channels; c++) {
    const data = inputBuffer.getChannelData(c)
    for (let i = 0; i < length; i++) {
      mono[i] += data[i]
    }
  }
  const scale = 1 / channels
  for (let i = 0; i < length; i++) {
    mono[i] *= scale
  }
  return mono
}

const buildVadConfig = (Module, options = {}) => {
  const {
    isMobile = false,
    threshold,
    minSilenceDuration,
    minSpeechDuration,
    maxSpeechDuration,
    bufferSizeInSeconds,
  } = options

  const tunedThreshold = threshold ?? (isMobile ? 0.55 : 0.5)
  const tunedMinSilence = minSilenceDuration ?? 0.35
  const tunedMinSpeech = minSpeechDuration ?? 0.25
  const tunedMaxSpeech = maxSpeechDuration ?? 20
  const tunedBufferSize = bufferSizeInSeconds ?? 30

  const config = {
    sileroVad: {
      model: '',
      threshold: tunedThreshold,
      minSilenceDuration: tunedMinSilence,
      minSpeechDuration: tunedMinSpeech,
      maxSpeechDuration: tunedMaxSpeech,
      windowSize: 512,
    },
    tenVad: {
      model: '',
      threshold: tunedThreshold,
      minSilenceDuration: tunedMinSilence,
      minSpeechDuration: tunedMinSpeech,
      maxSpeechDuration: tunedMaxSpeech,
      windowSize: 256,
    },
    sampleRate: 16000,
    numThreads: 1,
    provider: 'cpu',
    debug: 0,
    bufferSizeInSeconds: tunedBufferSize,
  }

  if (fileExists(Module, 'silero_vad.onnx')) {
    config.sileroVad.model = 'silero_vad.onnx'
  } else if (fileExists(Module, 'ten-vad.onnx')) {
    config.tenVad.model = 'ten-vad.onnx'
  } else {
    throw new Error('No VAD model found in sherpa wasm assets')
  }

  return config
}

export const createSherpaVadSession = ({ getStream, onSpeechSegment, onError, vadOptions = {} }) => {
  let running = false
  let audioCtx = null
  let mediaNode = null
  let processorNode = null
  let workletNode = null
  let stream = null
  let vad = null
  let pendingSamples = new Float32Array(0)
  let targetSampleRate = 16000
  let windowSize = 512
  let sourceRate = 16000
  let processedFrames = 0
  let emittedSegments = 0
  let lastStatLogAt = 0

  const stop = async () => {
    running = false

    try {
      if (processorNode) processorNode.disconnect()
    } catch (_) {}
    try {
      if (workletNode) workletNode.disconnect()
    } catch (_) {}
    try {
      if (mediaNode) mediaNode.disconnect()
    } catch (_) {}

    processorNode = null
    workletNode = null
    mediaNode = null

    if (stream) {
      stream.getTracks().forEach(track => track.stop())
      stream = null
    }

    if (audioCtx) {
      try {
        await audioCtx.close()
      } catch (_) {}
      audioCtx = null
    }

    if (vad) {
      try {
        vad.free()
      } catch (_) {}
      vad = null
    }
    pendingSamples = new Float32Array(0)
  }

  const concatFloat32 = (a, b) => {
    if (!a || a.length === 0) return b
    if (!b || b.length === 0) return a
    const out = new Float32Array(a.length + b.length)
    out.set(a, 0)
    out.set(b, a.length)
    return out
  }

  const processSamples = (inputSamples) => {
    if (!running || !vad || !inputSamples || inputSamples.length === 0) return
    let samples = inputSamples
    if (sourceRate !== targetSampleRate) {
      samples = downsampleBuffer(samples, sourceRate, targetSampleRate)
    }

    pendingSamples = concatFloat32(pendingSamples, samples)
    processedFrames += samples.length
    while (pendingSamples.length >= windowSize) {
      const chunk = pendingSamples.subarray(0, windowSize)
      vad.acceptWaveform(chunk)
      pendingSamples = pendingSamples.slice(windowSize)

      while (!vad.isEmpty()) {
        const segment = vad.front()
        vad.pop()
        if (segment?.samples?.length > 0) {
          emittedSegments += 1
          console.log('[SherpaVAD] segment emitted:', {
            samples: segment.samples.length,
            seconds: (segment.samples.length / targetSampleRate).toFixed(3),
            start: segment.start,
            emittedSegments,
          })
          onSpeechSegment?.(segment.samples, targetSampleRate)
        }
      }
    }

    const now = Date.now()
    if (now - lastStatLogAt > 2000) {
      lastStatLogAt = now
      console.log('[SherpaVAD] processing stats:', {
        processedFrames,
        pendingSamples: pendingSamples.length,
        sourceRate,
        targetSampleRate,
        windowSize,
        emittedSegments,
      })
    }
  }

  const start = async () => {
    if (running) return
    if (!getStream) throw new Error('getStream is required')

    const Module = await ensureSherpaRuntime()
    const config = buildVadConfig(Module, vadOptions)

    targetSampleRate = config.sampleRate || 16000
    windowSize = config.sileroVad?.model ? (config.sileroVad.windowSize || 512) : (config.tenVad.windowSize || 256)
    vad = window.createVad(Module, config)
    pendingSamples = new Float32Array(0)
    processedFrames = 0
    emittedSegments = 0
    lastStatLogAt = Date.now()

    stream = await getStream()
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext
    if (!AudioContextCtor) {
      throw new Error('AudioContext is not supported')
    }
    // Request 16k context explicitly; if unsupported, browser returns closest rate.
    audioCtx = new AudioContextCtor({ sampleRate: targetSampleRate })
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume()
    }
    sourceRate = audioCtx.sampleRate || targetSampleRate
    mediaNode = audioCtx.createMediaStreamSource(stream)
    running = true

    console.log('[SherpaVAD] start:', {
      audioContextState: audioCtx.state,
      sourceRate,
      targetSampleRate,
      windowSize,
      hasWorklet: !!audioCtx.audioWorklet,
    })

    if (audioCtx.audioWorklet && typeof window.AudioWorkletNode !== 'undefined') {
      await audioCtx.audioWorklet.addModule(SHERPA_VAD_WORKLET_JS)
      workletNode = new window.AudioWorkletNode(audioCtx, 'sherpa-vad-processor', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1,
        outputChannelCount: [1],
      })

      workletNode.port.onmessage = (event) => {
        try {
          const data = event.data
          const samples = data instanceof Float32Array
            ? data
            : (data instanceof ArrayBuffer ? new Float32Array(data) : new Float32Array(data))
          processSamples(samples)
        } catch (err) {
          onError?.(err)
        }
      }

      mediaNode.connect(workletNode)
      workletNode.connect(audioCtx.destination)
    } else {
      // Compatibility path for browsers without AudioWorklet.
      processorNode = audioCtx.createScriptProcessor(4096, 1, 1)
      processorNode.onaudioprocess = (event) => {
        try {
          processSamples(mixToMono(event.inputBuffer))
        } catch (err) {
          onError?.(err)
        }
      }
      mediaNode.connect(processorNode)
      processorNode.connect(audioCtx.destination)
    }
  }

  return {
    start,
    stop,
    isRunning: () => running,
  }
}

