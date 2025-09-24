import React from 'react';
import { useState, useEffect, useRef } from 'react';
import './ChatPanel.css';
import { FaPaperPlane, FaThumbsUp, FaThumbsDown } from 'react-icons/fa';

const SourceCard = ({ source, onSelect, onFeedback, lastQuery }) => {
    const [feedbackSent, setFeedbackSent] = useState(null);
    const pageLabel = source.page_start ? `p.${source.page_start}` : null;

    const handleFeedback = (vote, e) => {
        e.stopPropagation();
        if (feedbackSent) return;
        onFeedback(source.chunk_id, vote, lastQuery);
        setFeedbackSent(vote);
    };

    return (
        <div className="source-card" onClick={onSelect}>
            <div className="source-card-header">
                <h4 className="source-card-title">{source.doc_title || 'Untitled Document'}</h4>
                {pageLabel && <span className="source-card-page">{pageLabel}</span>}
            </div>
            <p className="source-card-content">{source.content}</p>
            <div className="feedback-area">
                {feedbackSent ? (
                    <span className="feedback-thanks">피드백 주셔서 감사합니다!</span>
                ) : (
                    <>
                        <button className="feedback-btn good" onClick={(e) => handleFeedback('up', e)}>
                            <FaThumbsUp /> 유용해요
                        </button>
                        <button className="feedback-btn bad" onClick={(e) => handleFeedback('down', e)}>
                            <FaThumbsDown /> 관련 없어요
                        </button>
                    </>
                )}
            </div>
        </div>
    );
};

export default function ChatPanel({
    connecting,
    answer,
    sources,
    selectedSource,        // (추후 필요 시 사용)
    onSelectSource,
    onAsk,
    onFeedback
}) {
    const [history, setHistory] = useState([]);
    const [question, setQuestion] = useState('');
    const [lastQuery, setLastQuery] = useState('');
    const [modalSources, setModalSources] = useState(null);
    const [showWelcome, setShowWelcome] = useState(true); // ★ 첫 진입 웰컴 말풍선
    const lastAnswerId = useRef(null);
    const historyEndRef = useRef(null);

    useEffect(() => {
        historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [history, connecting]);

    useEffect(() => {
        if (answer && answer !== lastAnswerId.current) {
            setHistory(prev => {
                const newHistory = [...prev];
                const lastItem = newHistory[newHistory.length - 1];
                const newAnswerItem = { type: 'bot', content: answer, sources: sources };

                if (lastItem && lastItem.type === 'bot' && lastItem.thinking) {
                    newHistory[newHistory.length - 1] = newAnswerItem;
                } else {
                    newHistory.push(newAnswerItem);
                }
                return newHistory;
            });
            lastAnswerId.current = answer;
        }
    }, [answer, sources]);

    const handleAskSubmit = (e) => {
        e.preventDefault();
        if (!question.trim() || connecting) return;
        onAsk(question);
        setLastQuery(question);
        setHistory(prev => [
            ...prev,
            { type: 'user', content: question },
            { type: 'bot', thinking: true }
        ]);
        setQuestion('');
        lastAnswerId.current = null;
        // 첫 질문 시 웰컴 말풍선 제거
        if (showWelcome) setShowWelcome(false);
    };

    const handleBubbleClick = (item) => {
        if (item.type === 'bot' && item.sources?.length > 0) {
            onSelectSource(item.sources[0]);
        }
    };

    return (
        <div className="chat-container">
            <div className="chat-history">
                {/* ★ 웰컴 말풍선: 첫 진입 시에만 보이고, 질문하면 사라짐 */}
                {showWelcome && history.length === 0 && (
                    <div className="chat-bubble bot is-welcome">
                        안녕하세요! 👋<br />
                        오른쪽에는 답변의 근거가 된 문서가 미리보기로 표시돼요.<br />
                        아래 입력창에 질문을 입력해 대화를 시작해 보세요.<br />
                        문서 내 표나 그림 등의 내용은 답변하기 어려워요!

                    </div>
                )}

                {history.map((item, index) => {
                    if (item.type === 'user') {
                        return <div key={index} className="chat-bubble user">{item.content}</div>;
                    }
                    if (item.type === 'bot') {
                        if (item.thinking) {
                            return (
                                <div key={index} className="chat-bubble thinking">
                                    <div className="thinking-dot"></div>
                                    <div className="thinking-dot"></div>
                                    <div className="thinking-dot"></div>
                                </div>
                            );
                        }
                        return (
                            <div key={index} className="chat-bubble bot" onClick={() => handleBubbleClick(item)}>
                                {item.content}
                                {item.sources && item.sources.length > 0 && (
                                    <div className="source-button-area">
                                        <button
                                            className="btn btn-secondary"
                                            onClick={(e) => { e.stopPropagation(); setModalSources(item.sources); }}
                                        >
                                            상세 근거 문서
                                        </button>
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

            {/* 근거 모달 */}
            {modalSources && (
                <div className="source-modal-overlay" onClick={() => setModalSources(null)}>
                    <div className="source-modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="source-modal-header">
                            <h3 className="source-modal-title">답변 근거 (클릭시 이동)</h3>
                            <button className="source-modal-close" onClick={() => setModalSources(null)}>&times;</button>
                        </div>
                        <div className="source-list">
                            {modalSources.map((source, index) => (
                                <SourceCard
                                    key={source.chunk_id + index}
                                    source={source}
                                    lastQuery={lastQuery}
                                    onSelect={() => { onSelectSource(source); setModalSources(null); }}
                                    onFeedback={onFeedback}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
