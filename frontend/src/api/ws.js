// frontend/src/api/ws.js
import { API_BASE, getAuthToken } from "./http.js";

function wsBaseOrigin() {
    const base = API_BASE || window.location.origin;
    // http(s) → ws(s)
    return base.replace(/^http/i, "ws").replace(/\/+$/, "");
}

export function openChatSocket(question, { onMessage, onClose } = {}) {
    const token = getAuthToken();
    const base = wsBaseOrigin();
    const url = token ? `${base}/api/chat/?token=${encodeURIComponent(token)}` : `${base}/api/chat/`;

    const ws = new WebSocket(url);

    ws.onopen = () => {
        // 서버가 첫 메시지에 바로 질문 문자열을 기대하는 현재 프로토콜 유지
        ws.send(typeof question === "string" ? question : String(question || ""));
    };

    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            onMessage && onMessage(msg);
        } catch (err) {
            console.error("WS parse error", err);
        }
    };

    ws.onclose = () => onClose && onClose();
    ws.onerror = (e) => console.error("WS error", e);

    return ws;
}
