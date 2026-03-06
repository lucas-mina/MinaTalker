class SherpaVadProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input = inputs[0]
    if (input && input.length > 0) {
      const channels = input.length
      const len = input[0]?.length || 0
      if (len > 0) {
        const mono = new Float32Array(len)
        for (let c = 0; c < channels; c++) {
          const channelData = input[c]
          for (let i = 0; i < len; i++) {
            mono[i] += channelData[i]
          }
        }
        const scale = 1 / channels
        for (let i = 0; i < len; i++) {
          mono[i] *= scale
        }
        this.port.postMessage(mono, [mono.buffer])
      }
    }

    const output = outputs[0]
    if (output && output.length > 0) {
      for (let c = 0; c < output.length; c++) {
        output[c].fill(0)
      }
    }
    return true
  }
}

registerProcessor('sherpa-vad-processor', SherpaVadProcessor)

