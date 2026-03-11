/**
 * Media handler: microphone capture, camera capture, and audio playback.
 */

// ── Audio Capture ──

let audioContext = null;
let audioStream = null;
let workletNode = null;

/**
 * Initialize microphone capture with PCM AudioWorklet.
 * @param {Function} onAudioChunk - Callback receiving base64-encoded PCM data.
 * @returns {Promise<void>}
 */
export async function initAudioCapture(onAudioChunk) {
    audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
        }
    });

    // Create AudioContext at 16kHz for Gemini Live API
    audioContext = new AudioContext({ sampleRate: 16000 });

    // Load the PCM processor worklet
    const processorUrl = new URL('./pcm-processor.js', import.meta.url).href;
    await audioContext.audioWorklet.addModule(processorUrl);

    const source = audioContext.createMediaStreamSource(audioStream);
    workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');

    workletNode.port.onmessage = (event) => {
        // event.data is an ArrayBuffer of Int16 PCM
        const base64 = arrayBufferToBase64(event.data);
        onAudioChunk(base64);
    };

    source.connect(workletNode);
    // Don't connect to destination — we don't want to hear our own mic
}

/**
 * Stop audio capture and release resources.
 */
export function stopAudioCapture() {
    if (workletNode) {
        workletNode.disconnect();
        workletNode = null;
    }
    if (audioStream) {
        audioStream.getTracks().forEach(t => t.stop());
        audioStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
}

// ── Video Capture ──

let videoStream = null;
let videoElement = null;
let videoCanvas = null;
let videoInterval = null;

/**
 * Initialize webcam capture, sending JPEG frames at ~1 FPS.
 * @param {Function} onVideoFrame - Callback receiving base64-encoded JPEG data.
 * @param {HTMLVideoElement} [existingVideo] - Optional existing video element to use.
 * @returns {Promise<HTMLVideoElement>} The video element showing the camera feed.
 */
export async function initVideoCapture(onVideoFrame, existingVideo = null) {
    videoStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 }
    });

    videoElement = existingVideo || document.createElement('video');
    videoElement.srcObject = videoStream;
    videoElement.autoplay = true;
    videoElement.muted = true;
    await videoElement.play();

    videoCanvas = document.createElement('canvas');
    videoCanvas.width = 768;
    videoCanvas.height = 768;
    const ctx = videoCanvas.getContext('2d');

    // Capture a frame every second (1 FPS)
    videoInterval = setInterval(() => {
        ctx.drawImage(videoElement, 0, 0, 768, 768);
        const dataUrl = videoCanvas.toDataURL('image/jpeg', 0.7);
        const base64 = dataUrl.split(',')[1];
        onVideoFrame(base64);
    }, 1000);

    return videoElement;
}

/**
 * Stop video capture and release resources.
 */
export function stopVideoCapture() {
    if (videoInterval) {
        clearInterval(videoInterval);
        videoInterval = null;
    }
    if (videoStream) {
        videoStream.getTracks().forEach(t => t.stop());
        videoStream = null;
    }
}

// ── Audio Playback ──

/**
 * AudioPlayer manages playback of PCM audio received from the server.
 * Gemini Live API sends 24kHz PCM audio.
 */
export class AudioPlayer {
    constructor() {
        this.context = new AudioContext({ sampleRate: 24000 });
        this.queue = [];
        this.isPlaying = false;
    }

    /**
     * Enqueue a base64-encoded PCM audio chunk for playback.
     * @param {string} base64Pcm - Base64-encoded Int16 PCM audio.
     */
    enqueue(base64Pcm) {
        const arrayBuffer = base64ToArrayBuffer(base64Pcm);
        const int16 = new Int16Array(arrayBuffer);

        // Convert Int16 to Float32 for Web Audio API
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768.0;
        }

        this.queue.push(float32);
        if (!this.isPlaying) {
            this._playNext();
        }
    }

    /**
     * Clear the audio queue (used when user interrupts / barge-in).
     */
    interrupt() {
        this.queue = [];
        this.isPlaying = false;
    }

    async _playNext() {
        if (this.queue.length === 0) {
            this.isPlaying = false;
            return;
        }

        this.isPlaying = true;
        const samples = this.queue.shift();

        const buffer = this.context.createBuffer(1, samples.length, 24000);
        buffer.getChannelData(0).set(samples);

        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);

        source.onended = () => this._playNext();
        source.start();
    }

    /**
     * Close the audio context.
     */
    close() {
        this.interrupt();
        this.context.close();
    }
}

// ── Utilities ──

function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}
