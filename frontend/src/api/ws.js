// frontend/src/api/ws.js
import { API_BASE, getAuthToken } from "./http.js";

/**
 * API_BASE가 절대 URL(https://...)이면 ws(s)로 치환.
 * API_BASE가 상대 경로(/api 등)이면 현재 호스트를 붙여 ws(s) 절대 URL로 변환.
 * 마지막 슬래시는 제거해서 뒤에 경로를 붙일 때 // 가 생기지 않도록 함.
 */
function buildWsBase() {
    const base = API_BASE || "/api";

    // 절대 URL인 경우: http(s) → ws(s)
    if (/^https?:\/\//i.test(base)) {
        return base.replace(/^http/i, "ws").replace(/\/+$/, "");
    }

    // 상대 경로인 경우: 현재 페이지의 프로토콜/호스트 사용
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host; // 예: localhost:5173
    // base는 /api 같은 경로라고 가정
    return `${proto}//${host}${base}`.replace(/\/+$/, "");
}

// 예: ws://localhost:5173/api  또는 ws://localhost:8000/api
const WS_BASE = buildWsBase();

/**
 * 채팅 소켓을 연다.
 * - 서버 라우트가 /api/chat (백엔드에서 프록시를 타든 직접 접근하든 동일하게 맞춤)
 * - 토큰이 있으면 ?token=... 쿼리로 전달
 * - 최초 onopen 시 클라이언트가 질문 문자열을 바로 전송(기존 프로토콜 유지)
 */
export function openChatSocket(question, { onMessage, onClose } = {}) {
    const token = getAuthToken();
    // WS_BASE는 /api까지 포함하므로 뒤에는 /chat만 붙인다 (중복 /api 방지)
    const url =
        token
            ? `${WS_BASE}/chat/?token=${encodeURIComponent(token)}`
            : `${WS_BASE}/chat/`;

    const ws = new WebSocket(url);

    ws.onopen = () => {
        try {
            const payload =
                typeof question === "string" ? question : String(question ?? "");
            ws.send(payload);
        } catch (err) {
            console.error("WS send error", err);
        }
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
