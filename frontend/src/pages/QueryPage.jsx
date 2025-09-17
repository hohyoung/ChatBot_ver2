import React, { useEffect, useRef, useState } from 'react';
import './QueryPage.css';
import ChatPanel from '../components/ChatPanel/ChatPanel.jsx';
import DocViewer from '../components/DocViewer/DocViewer.jsx';
import { openChatSocket } from '../api/ws.js';
import { post } from '../api/http.js';

export default function QueryPage() {
    const [answer, setAnswer] = useState('');
    const [sources, setSources] = useState([]);
    const [selected, setSelected] = useState(null);
    const [connecting, setConnecting] = useState(false);
    const [lastQ, setLastQ] = useState('');
    const wsRef = useRef(null);
    const handleSelectSource = (src, idx) => {
        setSelected(idx);     // 인덱스만 저장
    };

    useEffect(() => {
        if (!sources?.length) { setSelected(null); return; }
        const idx = sources.findIndex(s => !!s.doc_url);
        setSelected(idx >= 0 ? idx : 0);
    }, [sources]);

    const cleanupWS = () => {
        if (wsRef.current) {
            try { wsRef.current.close(); } catch { }
            wsRef.current = null;
        }
    };

    const ask = (q) => {
        // 이전 연결 정리
        cleanupWS();

        // 상태 초기화
        setAnswer('');
        setSources([]);
        setConnecting(true);
        setLastQ(q);

        wsRef.current = openChatSocket(q, {
            onMessage: (msg) => {
                // 스트리밍 청크
                if (msg?.type === 'chunk' && msg.delta) {
                    setAnswer(prev => prev + msg.delta);
                    return;
                }

                // 최종 응답 (신규 프로토콜)
                if (msg?.type === 'final' && msg.data) {
                    setAnswer(msg.data.answer ?? '');
                    setSources(msg.data.chunks ?? msg.data.sources ?? []);
                    // ✅ 여기서 연결을 직접 닫고 connecting 해제
                    setConnecting(false);
                    cleanupWS();
                    return;
                }

                // 구버전 단발 응답
                if (msg?.answer !== undefined) {
                    setAnswer(msg.answer || '');
                    setSources(msg.sources || []);
                    setConnecting(false);
                    cleanupWS();
                    return;
                }
            },
            onClose: () => {
                // 서버가 먼저 닫은 경우도 케어
                setConnecting(false);
                cleanupWS();
            },
        });
    };

    const vote = async (chunk_id, v) => {
        try {
            await post('/api/feedback', { chunk_id, vote: v, tag_context: [], query: lastQ });
        } catch (e) {
            console.error(e);
        }
    };

    const selectedSource = (selected != null && sources[selected]) ? sources[selected] : null;

    return (
        <div className="qgrid">
            <div className="qgrid__left">
                <ChatPanel
                    connecting={connecting}
                    answer={answer}
                    sources={sources}
                    selectedIndex={selected}
                    onSelectSource={handleSelectSource}
                    onAsk={ask}
                    onFeedback={vote}
                />
            </div>
            <div className="qgrid__right">
                <DocViewer source={selectedSource} />
            </div>
        </div>
    );
}
