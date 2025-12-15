import React from 'react';
import { useState, useEffect, useRef } from 'react';
import './ChatPanel.css';
import { FaPaperPlane, FaThumbsUp, FaThumbsDown, FaQuestionCircle, FaTimes, FaPlus, FaImage, FaTable, FaExclamationTriangle } from 'react-icons/fa';
import MarkdownRenderer from '../MarkdownRenderer';
import FAQList from '../FAQ/FAQList';
import PDFModal from '../PDFModal/PDFModal';
import LoadingSpinner from '../LoadingSpinner/LoadingSpinner';
import { SERVER_ERROR_MESSAGE } from '../../api/http';

// 로컬 스토리지 키 및 TTL (24시간)
const HISTORY_STORAGE_KEY = 'chat_history';
const HISTORY_TTL_MS = 24 * 60 * 60 * 1000; // 24시간

// 대화 내역 로드 (만료 체크 포함)
const loadHistoryFromStorage = () => {
    try {
        const stored = localStorage.getItem(HISTORY_STORAGE_KEY);
        if (!stored) return [];

        const { history, savedAt } = JSON.parse(stored);
        const now = Date.now();

        // 24시간 경과 시 삭제
        if (now - savedAt > HISTORY_TTL_MS) {
            localStorage.removeItem(HISTORY_STORAGE_KEY);
            return [];
        }

        // thinking 상태인 메시지 제거 (이전 세션에서 완료되지 않은 응답)
        return (history || []).filter(item => !item.thinking);
    } catch {
        return [];
    }
};

// 대화 내역 저장
const saveHistoryToStorage = (history) => {
    try {
        // thinking 상태나 스트리밍 중인 메시지는 저장하지 않음
        const saveable = history.filter(item => !item.thinking && !item.isStreaming);
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify({
            history: saveable,
            savedAt: Date.now()
        }));
    } catch {
        // 스토리지 용량 초과 등 에러 무시
    }
};

// GAR 단계별 아이콘 매핑
const getStageIcon = (stage) => {
    const icons = {
        intent: '🤔',
        expand: '🔍',
        search: '📚',
        rerank: '⭐',
        generate: '✍️'
    };
    return icons[stage] || '⏳';
};

export default function ChatPanel({
    connecting,
    loadingStage,
    connectionFailed,  // 서버 연결 실패 상태
    connectionRecovered, // 서버 연결 복구 상태
    answer,
    sources,
    selectedSource,
    onSelectSource,
    onAsk,
    onFeedback,
    initialQuestion,  // 외부에서 전달된 초기 질문 (DocsPage 요약 등)
    teams = [],       // 팀 목록
    teamsLoading = false, // 팀 목록 로딩 상태
    selectedTeamId,   // 선택된 팀 ID
    onTeamChange,     // 팀 변경 핸들러
}) {
    // 로컬 스토리지에서 대화 내역 로드
    const [history, setHistory] = useState(() => loadHistoryFromStorage());
    const [question, setQuestion] = useState('');
    const [pdfModalSource, setPdfModalSource] = useState(null);
    const [imageModalSrc, setImageModalSrc] = useState(null); // 이미지 확대 모달
    const [showWelcome, setShowWelcome] = useState(() => loadHistoryFromStorage().length === 0);
    const [faqOpen, setFaqOpen] = useState(true); // 기본 열림 상태
    const historyEndRef = useRef(null);
    const processedInitialRef = useRef(null); // 이미 처리한 initialQuestion 추적

    // 대화 내역 변경 시 로컬 스토리지에 저장
    useEffect(() => {
        saveHistoryToStorage(history);
    }, [history]);

    useEffect(() => {
        historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [history, connecting]);

    // 외부에서 전달된 초기 질문 처리 (DocsPage 요약 버튼 등)
    useEffect(() => {
        if (initialQuestion && initialQuestion !== processedInitialRef.current) {
            processedInitialRef.current = initialQuestion;
            // 히스토리에 질문 추가 후 봇 응답 대기 상태 추가
            setHistory(prev => [
                ...prev,
                { type: 'user', content: initialQuestion },
                { type: 'bot', thinking: true }
            ]);
            // 웰컴 메시지 숨김
            setShowWelcome(false);
            // 질문 전송
            onAsk(initialQuestion);
        }
    }, [initialQuestion, onAsk]);

    // 스트리밍 응답 처리: answer가 변경될 때마다 마지막 bot 메시지 업데이트
    useEffect(() => {
        if (answer) {
            setHistory(prev => {
                const newHistory = [...prev];
                const lastItem = newHistory[newHistory.length - 1];

                // 마지막 항목이 bot 메시지(thinking 포함)라면 업데이트
                if (lastItem && lastItem.type === 'bot') {
                    newHistory[newHistory.length - 1] = {
                        type: 'bot',
                        content: answer,
                        sources: sources,
                        isStreaming: connecting  // 스트리밍 중 여부 추적
                    };
                } else {
                    // 마지막 항목이 bot이 아니면 새로 추가 (이론적으로 발생하지 않아야 함)
                    newHistory.push({
                        type: 'bot',
                        content: answer,
                        sources: sources,
                        isStreaming: connecting
                    });
                }
                return newHistory;
            });
        }
    }, [answer, sources, connecting]);

    // 연결 실패 처리: thinking 상태인 마지막 메시지를 실패 메시지로 교체
    useEffect(() => {
        if (connectionFailed) {
            setHistory(prev => {
                const newHistory = [...prev];
                const lastItem = newHistory[newHistory.length - 1];

                // 마지막 항목이 thinking 상태의 bot 메시지라면 실패 메시지로 교체
                if (lastItem && lastItem.type === 'bot' && lastItem.thinking) {
                    newHistory[newHistory.length - 1] = {
                        type: 'bot',
                        connectionFailed: true  // 연결 실패 표시
                    };
                }
                return newHistory;
            });
        }
    }, [connectionFailed]);

    // 연결 복구 처리: 이전 실패 메시지를 히스토리에서 제거
    useEffect(() => {
        if (connectionRecovered) {
            setHistory(prev => {
                // 실패 상태인 메시지를 히스토리에서 제거
                return prev.filter(item => !(item.type === 'bot' && item.connectionFailed));
            });
        }
    }, [connectionRecovered]);

    const handleAskSubmit = (e) => {
        e.preventDefault();
        if (!question.trim() || connecting) return;

        const q = question.trim();
        // 히스토리에 질문 추가 후 봇 응답 대기 상태 추가
        setHistory(prev => [
            ...prev,
            { type: 'user', content: q },
            { type: 'bot', thinking: true }
        ]);
        // 입력창 초기화 (먼저!)
        setQuestion('');
        // 질문 전송
        onAsk(q);
        // 첫 질문 시 웰컴 말풍선 제거
        if (showWelcome) setShowWelcome(false);
    };

    const handleDocBadgeClick = (source) => {
        setPdfModalSource(source);
    };

    const handleFAQClick = (faqQuestion) => {
        // FAQ 클릭 시 즉시 질의 전송
        if (showWelcome) setShowWelcome(false);

        // 히스토리에 질문 추가 후 봇 응답 대기 상태 추가
        setHistory(prev => [
            ...prev,
            { type: 'user', content: faqQuestion },
            { type: 'bot', thinking: true }
        ]);

        // 질문 전송
        onAsk(faqQuestion);

        // 모바일에서 FAQ 패널 닫기
        if (window.innerWidth <= 768) {
            setFaqOpen(false);
        }
    };

    const toggleFaq = () => {
        setFaqOpen(prev => !prev);
    };

    // 대화 내역 초기화
    const handleClearHistory = () => {
        if (history.length === 0) return;
        if (window.confirm('대화 내역을 모두 삭제하시겠습니까?')) {
            setHistory([]);
            setShowWelcome(true);
            localStorage.removeItem(HISTORY_STORAGE_KEY);
        }
    };

    return (
        <div className={`chat-container ${faqOpen ? 'faq-panel-open' : ''}`}>
            {/* 메인 채팅 영역 */}
            <div className="chat-main">
                {/* 채팅 헤더: 팀 선택 + 새 대화 + FAQ 버튼 */}
                <div className="chat-header">
                    {/* 팀 선택 드롭다운 (칩 스타일) */}
                    <div className="team-selector">
                        {teamsLoading ? (
                            <div className="team-selector-loading">
                                <span className="team-loading-dot"></span>
                                <span>로딩 중</span>
                            </div>
                        ) : teams.length > 0 ? (
                            <select
                                value={selectedTeamId ?? ''}
                                onChange={(e) => onTeamChange && onTeamChange(e.target.value ? Number(e.target.value) : null)}
                                disabled={connecting}
                                title="답변을 검색할 팀을 선택하세요"
                            >
                                {teams.map((t) => (
                                    <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                            </select>
                        ) : null}
                    </div>
                    <div className="chat-header-buttons">
                        <button
                            type="button"
                            className="btn-new-chat"
                            onClick={handleClearHistory}
                            disabled={connecting || history.length === 0}
                        >
                            <FaPlus />
                            <span>새 대화</span>
                        </button>
                        <button
                            type="button"
                            className={`btn-faq-header ${faqOpen ? 'active' : ''}`}
                            onClick={toggleFaq}
                        >
                            <FaQuestionCircle />
                            <span>FAQ</span>
                        </button>
                    </div>
                </div>

                <div className="chat-history">
                    {/* 웰컴 말풍선: 첫 진입 시에만 보이고, 질문하면 사라짐 */}
                    {showWelcome && history.length === 0 && (
                        <div className="chat-bubble bot is-welcome">
                            안녕하세요! 👋<br />
                            사내 규정에 대해 궁금한 점을 물어보세요.<br />
                            답변 하단에 표시되는 문서 카드를 클릭하면 원본 PDF를 확인할 수 있어요.
                        </div>
                    )}

                    {history.map((item, index) => {
                        if (item.type === 'user') {
                            return <div key={index} className="chat-bubble user">{item.content}</div>;
                        }
                        if (item.type === 'bot') {
                            // 연결 실패 상태 표시
                            if (item.connectionFailed) {
                                return (
                                    <div key={index} className="loading-stage connection-failed">
                                        <div className="stage-icon error-icon">
                                            <FaExclamationTriangle />
                                        </div>
                                        <div className="connection-failed-content">
                                            <p className="stage-message error-title">{SERVER_ERROR_MESSAGE.title}</p>
                                            <p className="error-detail">{SERVER_ERROR_MESSAGE.detail}</p>
                                            <p className="error-contact">{SERVER_ERROR_MESSAGE.contact}</p>
                                        </div>
                                    </div>
                                );
                            }
                            if (item.thinking) {
                                // 로딩 단계 메시지 표시 (GAR 파이프라인)
                                if (loadingStage) {
                                    return (
                                        <div key={index} className="loading-stage">
                                            <div className="stage-icon">{getStageIcon(loadingStage.stage)}</div>
                                            <p className="stage-message">{loadingStage.message}</p>
                                            <div className="stage-dots">
                                                <span>.</span><span>.</span><span>.</span>
                                            </div>
                                        </div>
                                    );
                                }
                                // 초기 연결 상태: 스피너와 함께 "연결 중" 표시
                                return (
                                    <div key={index} className="loading-stage connecting">
                                        <LoadingSpinner size="md" />
                                        <p className="stage-message">서버에 연결 중...</p>
                                    </div>
                                );
                            }
                            // sources에서 imageRefs 생성 (has_image가 있는 청크들)
                            const imageRefs = (item.sources || [])
                                .filter(src => src.has_image && src.image_url)
                                .map((src, idx) => ({
                                    ref: `[IMG${idx + 1}]`,
                                    url: src.image_url,
                                    type: src.image_type || 'image',
                                    doc_title: src.doc_title,
                                    page: src.page_start
                                }));

                            return (
                                <div key={index} className={`chat-bubble bot ${item.isStreaming ? 'streaming' : ''}`}>
                                    <div className="bot-symbol">
                                        <span className="bot-symbol-icon">&#x1F539;</span>
                                    </div>
                                    <MarkdownRenderer
                                        content={item.content}
                                        isStreaming={item.isStreaming}
                                        imageRefs={imageRefs}
                                    />
                                    {item.sources && item.sources.length > 0 && (
                                        <div className="source-docs-area">
                                            <div className="source-docs-label">참고 문서:</div>
                                            <div className="source-docs-list">
                                                {item.sources.map((src, idx) => (
                                                    <div
                                                        key={src.chunk_id + idx}
                                                        className="source-doc-badge"
                                                        onClick={() => handleDocBadgeClick(src)}
                                                    >
                                                        <span className="doc-badge-icon">📄</span>
                                                        <span className="doc-badge-title">{src.doc_title || 'Untitled'}</span>
                                                        {src.page_start && (
                                                            <span className="doc-badge-page">p.{src.page_start}</span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        }
                        return null;
                    })}
                    <div ref={historyEndRef} />
                </div>

                {/* 입력 영역 */}
                <div className="chat-input-area">
                    <form onSubmit={handleAskSubmit} className="chat-input-form">
                        <input
                            type="text"
                            className="chat-input chat-input--lg"
                            placeholder="질문을 입력하세요… (Enter로 전송)"
                            value={question}
                            onChange={(e) => setQuestion(e.target.value)}
                            disabled={connecting}
                        />
                        <button type="submit" className="btn btn-primary btn-send" disabled={connecting || !question.trim()}>
                            <FaPaperPlane />
                        </button>
                    </form>
                </div>
            </div>

            {/* FAQ 사이드 패널 (데스크톱) / 바텀 시트 (모바일) */}
            <div className={`faq-panel ${faqOpen ? 'open' : ''}`}>
                <div className="faq-panel-header">
                    <h3>자주 묻는 질문</h3>
                    <button
                        className="faq-panel-close"
                        onClick={() => setFaqOpen(false)}
                        aria-label="FAQ 닫기"
                    >
                        <FaTimes />
                    </button>
                </div>
                <div className="faq-panel-content">
                    <FAQList onQuestionClick={handleFAQClick} isInPanel={true} />
                </div>
            </div>

            {/* FAQ 오버레이 (모바일) */}
            {faqOpen && <div className="faq-overlay" onClick={() => setFaqOpen(false)} />}

            {/* PDF 미리보기 모달 */}
            {pdfModalSource && (
                <PDFModal
                    source={pdfModalSource}
                    onClose={() => setPdfModalSource(null)}
                />
            )}

            {/* 이미지 확대 모달 */}
            {imageModalSrc && (
                <div className="image-modal-overlay" onClick={() => setImageModalSrc(null)}>
                    <div className="image-modal-content" onClick={(e) => e.stopPropagation()}>
                        <button
                            className="image-modal-close"
                            onClick={() => setImageModalSrc(null)}
                            aria-label="닫기"
                        >
                            <FaTimes />
                        </button>
                        <img
                            src={imageModalSrc}
                            alt="원본 이미지"
                            className="image-modal-img"
                        />
                        <div className="image-modal-hint">클릭하여 닫기</div>
                    </div>
                </div>
            )}
        </div>
    );
}
