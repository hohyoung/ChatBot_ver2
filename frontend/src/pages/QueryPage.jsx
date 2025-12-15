// src/pages/QueryPage.jsx
import React, { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { openChatSocket } from '../api/ws.js';
import { post, authApi, SERVER_ERROR_MESSAGE } from '../api/http.js';

import ChatPanel from '../components/ChatPanel/ChatPanel.jsx';

import './QueryPage.css';

// 질의 중 health 체크 간격 (3초)
const HEALTH_CHECK_INTERVAL_MS = 3000;
// 질의 절대 타임아웃 (90초) - 이 시간 초과 시 무조건 실패 처리
const ABSOLUTE_TIMEOUT_MS = 90000;

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

    // 팀 관련 상태
    const [teams, setTeams] = useState([]);
    const [teamsLoading, setTeamsLoading] = useState(true); // 팀 목록 로딩 상태
    const [selectedTeamId, setSelectedTeamId] = useState(null); // null = 전체 검색 (레거시 호환)

    const wsRef = useRef(null);
    const queryHealthCheckRef = useRef(null); // 질의 중 health 체크 타이머
    const absoluteTimeoutRef = useRef(null); // 절대 타임아웃 타이머
    const recoveryCheckRef = useRef(null); // 복구 체크 타이머

    // 팀 목록 로드
    useEffect(() => {
        (async () => {
            setTeamsLoading(true);
            try {
                const list = await authApi.teams();
                setTeams(list || []);
                // 기본 선택: 첫 번째 팀 (있으면)
                if (list && list.length > 0) {
                    setSelectedTeamId(list[0].id);
                }
            } catch {
                // 로그인 안 했거나 팀 조회 실패 시 무시
                setTeams([]);
            } finally {
                setTeamsLoading(false);
            }
        })();
    }, []);

    // 연결 실패 상태일 때 주기적으로 health 체크하여 복구 감지
    useEffect(() => {
        if (connectionFailed && !connecting) {
            // 실패 상태 + 질의 중 아닐 때만 복구 체크
            const checkRecovery = async () => {
                try {
                    const response = await fetch('/api/health');
                    if (response.ok) {
                        setConnectionFailed(false);
                        setConnectionRecovered(true);
                    }
                } catch {
                    // 아직 연결 안 됨
                }
            };
            checkRecovery();
            recoveryCheckRef.current = setInterval(checkRecovery, HEALTH_CHECK_INTERVAL_MS);
        }

        return () => {
            if (recoveryCheckRef.current) {
                clearInterval(recoveryCheckRef.current);
                recoveryCheckRef.current = null;
            }
        };
    }, [connectionFailed, connecting]);

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

    // 질의 관련 타이머/리소스 정리
    const cleanupQuery = () => {
        if (queryHealthCheckRef.current) {
            clearInterval(queryHealthCheckRef.current);
            queryHealthCheckRef.current = null;
        }
        if (absoluteTimeoutRef.current) {
            clearTimeout(absoluteTimeoutRef.current);
            absoluteTimeoutRef.current = null;
        }
        if (wsRef.current) {
            try {
                wsRef.current.close();
            } catch { }
            wsRef.current = null;
        }
    };

    // 질의 실패 처리
    const handleQueryFailed = () => {
        setConnectionFailed(true);
        setConnecting(false);
        cleanupQuery();
    };

    const ask = (q) => {
        cleanupQuery();
        setAnswer('');
        setSources([]);
        setConnecting(true);
        setLoadingStage(null);
        const wasConnectionFailed = connectionFailed;
        setConnectionFailed(false);
        setConnectionRecovered(false);
        setLastQ(q);

        let isCompleted = false; // 질의 완료 여부

        // 질의 완료 처리 함수
        const completeQuery = () => {
            isCompleted = true;
            cleanupQuery();
        };

        // 1) 절대 타임아웃: 90초 후 무조건 실패
        absoluteTimeoutRef.current = setTimeout(() => {
            if (!isCompleted) {
                handleQueryFailed();
            }
        }, ABSOLUTE_TIMEOUT_MS);

        // 2) 질의 중 health 체크: 3초마다 서버 상태 확인
        queryHealthCheckRef.current = setInterval(async () => {
            if (isCompleted) return;
            try {
                const response = await fetch('/api/health');
                if (!response.ok) {
                    handleQueryFailed();
                }
            } catch {
                // health 체크 실패 = 서버 다운
                handleQueryFailed();
            }
        }, HEALTH_CHECK_INTERVAL_MS);

        wsRef.current = openChatSocket(q, {
            teamId: selectedTeamId,
            onMessage: (msg) => {
                // 이전 연결 실패 상태였다면 복구 알림
                if (wasConnectionFailed) {
                    setConnectionRecovered(true);
                }

                // 진행 단계 이벤트
                if (msg?.type === 'stage') {
                    setLoadingStage({
                        stage: msg.stage,
                        message: msg.message
                    });
                    return;
                }
                // 토큰 이벤트
                if (msg?.type === 'token' && msg.token) {
                    setLoadingStage(null);
                    setAnswer((prev) => prev + msg.token);
                    return;
                }
                // 최종 이벤트
                if (msg?.type === 'final' && msg.data) {
                    setLoadingStage(null);
                    setAnswer(msg.data.answer ?? '');
                    setSources(msg.data.chunks ?? msg.data.sources ?? []);
                    setConnecting(false);
                    completeQuery();
                    return;
                }
                // 에러 이벤트
                if (msg?.type === 'error') {
                    setLoadingStage(null);
                    setAnswer('오류가 발생했습니다: ' + (msg.error || '알 수 없는 오류'));
                    setConnecting(false);
                    completeQuery();
                    return;
                }
                // 레거시 형식
                if (msg?.answer !== undefined) {
                    setAnswer(msg.answer || '');
                    setSources(msg.sources || []);
                    setConnecting(false);
                    completeQuery();
                }
            },
            onClose: ({ wasClean } = {}) => {
                if (!isCompleted) {
                    // 완료되지 않은 상태에서 연결 끊김 = 실패
                    handleQueryFailed();
                }
            },
            onError: () => {
                if (!isCompleted) {
                    handleQueryFailed();
                }
            },
        });
    };

    const vote = async (chunk_id, vote, query) => {
        try {
            await post('/api/feedback', { chunk_id, vote, tag_context: [], query });
        } catch {
            // 피드백 실패는 사용자 경험에 영향 없음
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
                teams={teams}
                teamsLoading={teamsLoading}
                selectedTeamId={selectedTeamId}
                onTeamChange={setSelectedTeamId}
            />
        </div>
    );
}
