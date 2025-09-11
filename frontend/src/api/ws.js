export function openChatSocket(question, { onMessage, onClose } = {}) {
    // http(s) → ws(s)
    const wsUrl = (location.origin.replace(/^http/, 'ws')) + '/api/chat/';
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => {
        ws.send(typeof question === 'string' ? question : String(question || ''));
    };
    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            onMessage && onMessage(msg);
        } catch (err) {
            console.error('WS parse error', err);
        }
    };
    ws.onclose = () => onClose && onClose();
    ws.onerror = (e) => console.error('WS error', e);
    return ws;
}
