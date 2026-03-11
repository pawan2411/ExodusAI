/**
 * GeminiClient: WebSocket client for communicating with the ExodusAI backend.
 */

export class GeminiClient {
    /**
     * @param {string} wsUrl - WebSocket URL (e.g., ws://localhost:8080/ws)
     */
    constructor(wsUrl) {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.handlers = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    /**
     * Connect to the backend WebSocket.
     */
    connect() {
        this.ws = new WebSocket(this.wsUrl);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this._emit('connected');
        };

        this.ws.onclose = (event) => {
            this._emit('disconnected', { code: event.code, reason: event.reason });
        };

        this.ws.onerror = (error) => {
            this._emit('error', error);
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this._emit(msg.type, msg.data);
            } catch (e) {
                console.error('Failed to parse message:', e);
            }
        };
    }

    /**
     * Send a base64-encoded PCM audio chunk.
     * @param {string} base64Pcm
     */
    sendAudio(base64Pcm) {
        this._send({ type: 'audio', data: base64Pcm });
    }

    /**
     * Send a base64-encoded JPEG video frame.
     * @param {string} base64Jpeg
     */
    sendVideo(base64Jpeg) {
        this._send({ type: 'video', data: base64Jpeg });
    }

    /**
     * Send a text message.
     * @param {string} text
     */
    sendText(text) {
        this._send({ type: 'text', data: text });
    }

    /**
     * Send any structured message to the backend.
     * @param {{ type: string, data?: any }} msg
     */
    sendMessage(msg) {
        this._send(msg);
    }

    /**
     * Register an event handler.
     * @param {string} event - Event name (e.g., 'audio', 'transcript', 'report', 'connected')
     * @param {Function} handler - Callback function
     */
    on(event, handler) {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event].push(handler);
    }

    /**
     * Remove an event handler.
     * @param {string} event
     * @param {Function} handler
     */
    off(event, handler) {
        const handlers = this.handlers[event];
        if (handlers) {
            this.handlers[event] = handlers.filter(h => h !== handler);
        }
    }

    /**
     * Disconnect from the backend.
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Check if the connection is open.
     * @returns {boolean}
     */
    get isConnected() {
        return this.ws?.readyState === WebSocket.OPEN;
    }

    // ── Private ──

    _send(msg) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    _emit(event, data) {
        const handlers = this.handlers[event] || [];
        for (const handler of handlers) {
            try {
                handler(data);
            } catch (e) {
                console.error(`Error in ${event} handler:`, e);
            }
        }
    }
}
