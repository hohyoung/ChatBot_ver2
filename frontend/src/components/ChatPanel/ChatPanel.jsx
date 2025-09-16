import React, { useState } from 'react';
import './ChatPanel.css';

export default function ChatPanel({
    connecting = false,
    answer = '',
    sources = [],
    selectedIndex = null,
    onAsk,
    onSelectSource,
    onFeedback,
}) {
    const [q, setQ] = useState('');
    const send = () => {
        const t = q.trim();
        if (!t || connecting) return;
        onAsk?.(t);
    };

    return (
        <div className="chat">
            <div className="chat__box">
                <input
                    className="chat__input"
                    value={q}
                    placeholder="질문을 입력하세요…"
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => (e.key === 'Enter' && !e.shiftKey ? send() : null)}
                />
                <button
                    className="btn btn-primary"
                    disabled={connecting || !q.trim()}
                    onClick={send}
                    title="보내기"
                >
                    전송
                </button>
            </div>

            <section className="chat__answer">
                <div className="card">
                    <div className="card__title">답변</div>
                    <div className="card__body">{answer || '—'}</div>
                </div>
            </section>

            <section className="chat__sources">
                <div className="card">
                    <div className="card__title">근거 문서</div>
                    <div className="card__body">
                        {!sources?.length && <div className="empty">근거가 표시될 영역입니다.</div>}
                        {sources.map((s, i) => (
                            <div
                                key={s.chunk_id || i}
                                className={'source ' + (selectedIndex === i ? 'is-selected' : '')}
                                onClick={() => onSelectSource?.(s, i)}
                            >
                                <div className="source__header">
                                    <div className="source__title">{s.doc_title || s.doc_id || '문서'}</div>
                                    <div className="source__meta">
                                        {s.doc_url ? <span className="pill">연결됨</span> : <span className="pill pill--muted">미리보기 없음</span>}
                                    </div>
                                </div>

                                {/* ✅ 핵심 문장 */}
                                {s.focus_sentence ? (
                                    <div className="source__focus" title={s.focus_sentence}>
                                        “{s.focus_sentence}”
                                    </div>
                                ) : (
                                    <div className="source__focus source__focus--muted">핵심 문장을 찾지 못했습니다.</div>
                                )}

                                {/* 부가 메타 */}
                                <div className="source__foot">
                                    <div className="source__id">chunk_id: {s.chunk_id}</div>
                                    <div className="source__actions">
                                        <button
                                            className="btn btn-ghost"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onFeedback?.(s.chunk_id, 'up');
                                            }}
                                        >
                                            👍 좋았어요
                                        </button>
                                        <button
                                            className="btn btn-ghost"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onFeedback?.(s.chunk_id, 'down');
                                            }}
                                        >
                                            👎 별로였어요
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}
