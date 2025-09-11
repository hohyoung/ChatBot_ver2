import React, { useRef, useState } from 'react';
import { openChatSocket } from '../api/ws.js';
import { post } from '../api/http.js';

export default function QueryPage() {
    const [question, setQuestion] = useState('');
    const [answer, setAnswer] = useState('');
    const [sources, setSources] = useState([]);  // [{doc_title, chunk_id, ...}]
    const [connecting, setConnecting] = useState(false);
    const wsRef = useRef(null);

    const send = () => {
        if (!question.trim() || connecting) return;
        setAnswer('');
        setSources([]);
        setConnecting(true);
        wsRef.current = openChatSocket(question, {
            onMessage: (msg) => {
                // 서버 구현에 따라 'final'만 오거나, 'chunk' + 'end'가 올 수 있음 둘 다 처리
                if (msg.type === 'chunk' && msg.delta) {
                    setAnswer(prev => prev + msg.delta);
                } else if ((msg.type === 'end' || msg.type === 'final') && (msg.answer || msg.data?.answer)) {
                    const a = msg.answer || msg.data?.answer || '';
                    const s = msg.sources || msg.data?.chunks || msg.data?.sources || [];
                    setAnswer(a);
                    setSources(Array.isArray(s) ? s : []);
                    setConnecting(false);
                    wsRef.current && wsRef.current.close();
                } else if (msg.type === 'error') {
                    setConnecting(false);
                    alert(msg.message || '오류가 발생했습니다.');
                }
            },
            onClose: () => setConnecting(false)
        });
    };

    const feedback = async (chunk_id, vote) => {
        try {
            const body = {
                chunk_id,
                vote,                    // 'up' | 'down'
                tag_context: [],         // 필요하면 설정 페이지에서 가져와 넣기
                query: question,
                // weight: 1.0
            };
            const res = await post('/api/feedback', body);
            if (res?.ok) alert(`피드백 반영됨 (boost=${res.updated?.new_boost ?? 'n/a'})`);
            else alert('피드백 반영 실패');
        } catch (e) {
            alert('피드백 오류: ' + e.message);
        }
    };

    return (
        <div className="col" style={{ gap: 16 }}>
            <div className="section">
                <div className="row">
                    <input
                        className="input"
                        placeholder="질문을 입력하세요…"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        onKeyDown={(e) => (e.key === 'Enter' ? send() : null)}
                    />
                    <button className="button" onClick={send} disabled={connecting}>전송</button>
                </div>
                <div className="small" style={{ marginTop: 8 }}>
                    WS: /api/chat · 답변은 서버가 계산해서 최종 JSON으로 내려옵니다.
                </div>
            </div>

            <div className="section">
                <h3 style={{ marginTop: 0 }}>답변</h3>
                <div className="card" style={{ minHeight: 120, whiteSpace: 'pre-wrap' }}>{answer || '—'}</div>
            </div>

            <div className="section">
                <h3 style={{ marginTop: 0 }}>근거 문서</h3>
                {sources.length === 0 && <div className="small">근거가 표시될 영역입니다.</div>}
                <div className="col">
                    {sources.map((s, i) => (
                        <div key={s.chunk_id || i} className="card">
                            <div><b>{s.doc_title || s.doc_id || '문서'}</b></div>
                            {s.section_title && <div className="small">섹션: {s.section_title}</div>}
                            {s.page !== undefined && <div className="small">페이지: {s.page}</div>}
                            <div className="small">chunk_id: {s.chunk_id}</div>
                            <div className="row" style={{ marginTop: 8 }}>
                                <button className="button" onClick={() => feedback(s.chunk_id, 'up')}>👍 좋았어요</button>
                                <button className="button" onClick={() => feedback(s.chunk_id, 'down')}>👎 별로였어요</button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
