// src/pages/QueryPage.jsx
import React, { useEffect, useRef, useState } from 'react';
import './QueryPage.css';
import ChatPanel from '../components/ChatPanel/ChatPanel.jsx';
import DocViewer from '../components/DocViewer/DocViewer.jsx';
import { openChatSocket } from '../api/ws.js';
import { post } from '../api/http.js';

export default function QueryPage() {
    const [answer, setAnswer] = useState('');
    const [sources, setSources] = useState([]);
    const [selectedSource, setSelectedSource] = useState(null); // ★ selected 인덱스 대신 source 객체를 직접 관리
    const [connecting, setConnecting] = useState(false);
    const [lastQ, setLastQ] = useState('');
    const wsRef = useRef(null);

    const handleSelectSource = (source) => {
        setSelectedSource(source);
    };

    // sources 배열(답변의 근거 목록)이 업데이트될 때마다
    // 가장 첫 번째 문서를 기본으로 선택하여 미리보기에 띄워줍니다.
    useEffect(() => {
        if (sources?.length > 0) {
            const firstDoc = sources.find((s) => !!s.doc_url);
            setSelectedSource(firstDoc || sources[0]);
        } else {
            setSelectedSource(null);
        }
    }, [sources]);

    const cleanupWS = () => {
        if (wsRef.current) {
            try {
                wsRef.current.close();
            } catch { }
            wsRef.current = null;
        }
    };

    const ask = (q) => {
        cleanupWS();
        setAnswer('');
        setSources([]);
        setConnecting(true);
        setLastQ(q);

        wsRef.current = openChatSocket(q, {
            onMessage: (msg) => {
                if (msg?.type === 'chunk' && msg.delta) {
                    setAnswer((prev) => prev + msg.delta);
                    return;
                }
                if (msg?.type === 'final' && msg.data) {
                    setAnswer(msg.data.answer ?? '');
                    setSources(msg.data.chunks ?? msg.data.sources ?? []);
                    setConnecting(false);
                    cleanupWS();
                    return;
                }
                if (msg?.answer !== undefined) {
                    setAnswer(msg.answer || '');
                    setSources(msg.sources || []);
                    setConnecting(false);
                    cleanupWS();
                }
            },
            onClose: () => {
                setConnecting(false);
                cleanupWS();
            },
        });
    };

    const vote = async (chunk_id, vote, query) => {
        try {
            // ★ 피드백 API 호출 시 query를 함께 전송
            await post('/api/feedback', { chunk_id, vote, tag_context: [], query });
        } catch (e) {
            console.error('Feedback submission failed:', e);
        }
    };

    return (

        < div className="qgrid" >
            <div className="qgrid__left">
                <ChatPanel
                    connecting={connecting}
                    answer={answer}
                    sources={sources}
                    // selectedSource를 직접 전달하여 ChatPanel이 현재 선택된 소스를 알 수 있게 함
                    selectedSource={selectedSource}
                    onSelectSource={handleSelectSource}
                    onAsk={ask}
                    onFeedback={vote}
                />
            </div>
            <div className="qgrid__right">
                <DocViewer source={selectedSource} />
            </div>
        </div >
    );
}
