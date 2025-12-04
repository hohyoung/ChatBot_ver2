// src/pages/QueryPage.jsx
import React, { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import './QueryPage.css';
import ChatPanel from '../components/ChatPanel/ChatPanel.jsx';
import { openChatSocket } from '../api/ws.js';
import { post, SERVER_ERROR_MESSAGE } from '../api/http.js';

// WebSocket 연결 타임아웃 (15초)
const WS_CONNECT_TIMEOUT_MS = 15000;

export default function QueryPage() {
    const location = useLocation();
    const [answer, setAnswer] = useState('');
    const [sources, setSources] = useState([]);
    const [selectedSource, setSelectedSource] = useState(null); // ★ selected 인덱스 대신 source 객체를 직접 관리
    const [connecting, setConnecting] = useState(false);
    const [loadingStage, setLoadingStage] = useState(null); // GAR 진행 단계
    const [connectionFailed, setConnectionFailed] = useState(false); // 연결 실패 상태
    const [connectionRecovered, setConnectionRecovered] = useState(false); // 연결 복구 상태
    const [lastQ, setLastQ] = useState('');
    const [initialQuestion, setInitialQuestion] = useState(null); // DocsPage에서 전달된 초기 질문
    const wsRef = useRef(null);
    const timeoutRef = useRef(null); // 타임아웃 타이머

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
        // 타임아웃 클리어
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
        }
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
        setLoadingStage(null);
        const wasConnectionFailed = connectionFailed; // 이전에 실패 상태였는지 기록
        setConnectionFailed(false);
        setConnectionRecovered(false);
        setLastQ(q);

        let receivedAnyMessage = false; // 메시지 수신 여부 추적

        // 타임아웃 설정: 15초 내에 메시지를 받지 못하면 연결 실패로 처리
        timeoutRef.current = setTimeout(() => {
            if (!receivedAnyMessage && connecting) {
                console.error('WebSocket connection timeout');
                setConnectionFailed(true);
                setConnecting(false);
                cleanupWS();
            }
        }, WS_CONNECT_TIMEOUT_MS);

        wsRef.current = openChatSocket(q, {
            onMessage: (msg) => {
                // 첫 메시지 수신 시 처리
                if (!receivedAnyMessage) {
                    receivedAnyMessage = true;
                    // 타임아웃 클리어
                    if (timeoutRef.current) {
                        clearTimeout(timeoutRef.current);
                        timeoutRef.current = null;
                    }
                    // 이전에 연결 실패 상태였다면 복구 알림
                    if (wasConnectionFailed) {
                        setConnectionRecovered(true);
                    }
                }

                // 진행 단계 이벤트: GAR 파이프라인 단계
                if (msg?.type === 'stage') {
                    setLoadingStage({
                        stage: msg.stage,
                        message: msg.message
                    });
                    return;
                }
                // 토큰 이벤트: 스트리밍 중
                if (msg?.type === 'token' && msg.token) {
                    setLoadingStage(null);
                    setAnswer((prev) => prev + msg.token);
                    return;
                }
                // 최종 이벤트: 스트리밍 완료
                if (msg?.type === 'final' && msg.data) {
                    setLoadingStage(null);
                    setAnswer(msg.data.answer ?? '');
                    setSources(msg.data.chunks ?? msg.data.sources ?? []);
                    setConnecting(false);
                    cleanupWS();
                    return;
                }
                // 에러 이벤트
                if (msg?.type === 'error') {
                    console.error('Chat error:', msg.error);
                    setLoadingStage(null);
                    setAnswer('오류가 발생했습니다: ' + (msg.error || '알 수 없는 오류'));
                    setConnecting(false);
                    cleanupWS();
                    return;
                }
                // 레거시 형식 지원 (하위 호환)
                if (msg?.answer !== undefined) {
                    setAnswer(msg.answer || '');
                    setSources(msg.sources || []);
                    setConnecting(false);
                    cleanupWS();
                }
            },
            onClose: () => {
                // 메시지를 한 번도 받지 못한 채 연결이 끊긴 경우 = 연결 실패
                if (!receivedAnyMessage) {
                    setConnectionFailed(true);
                }
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

    // P0-4: 챗봇 사서 기능 - DocsPage에서 전달된 문서 정보로 자동 질문
    useEffect(() => {
        if (location.state?.initialQuestion) {
            // ChatPanel에 초기 질문 전달 (ChatPanel이 히스토리 관리)
            setInitialQuestion(location.state.initialQuestion);
        }
    }, [location.state]);

    return (
        <div className="query-page">
            <ChatPanel
                connecting={connecting}
                loadingStage={loadingStage}
                connectionFailed={connectionFailed}
                connectionRecovered={connectionRecovered}
                answer={answer}
                sources={sources}
                selectedSource={selectedSource}
                onSelectSource={handleSelectSource}
                onAsk={ask}
                onFeedback={vote}
                initialQuestion={initialQuestion}
            />
        </div>
    );
}
