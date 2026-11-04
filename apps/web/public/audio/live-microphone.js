/* PCM microphone stream, independently resampled to Gemini's 16 kHz input. */
class LiveMicrophone extends AudioWorkletProcessor {
  constructor() { super(); this.frame = new Int16Array(1600); this.used=0; this.clock=0; this.sum=0; this.count=0; }
  process(inputs) {
    const input=inputs[0]?.[0];
    if (input) for (const sample of input) {
      this.clock++; this.sum+=sample; this.count++;
      if (this.clock>=sampleRate/16000) {
        const value=Math.max(-1,Math.min(1,this.sum/this.count));
        this.frame[this.used++]=value<0 ? value*32768 : value*32767;
        this.clock-=sampleRate/16000; this.sum=0; this.count=0;
        if (this.used===1600) { this.port.postMessage(this.frame.buffer,[this.frame.buffer]); this.frame=new Int16Array(1600); this.used=0; }
      }
    }
    return true;
  }
}
registerProcessor('haytile-live-microphone',LiveMicrophone);
