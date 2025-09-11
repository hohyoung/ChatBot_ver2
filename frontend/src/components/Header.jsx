import React from 'react';
import { useHealth } from '../store/health.js';

export default function Header() {
    const { status, model, collection, refresh } = useHealth();
    return (
        <div className="header">
            <div className="title">사내 규정 챗봇</div>
            <button className="button" onClick={refresh}>헬스 체크</button>
            <div className="health">
                {status === 'ok' ? '🟢 OK' : status === 'warn' ? '🟡 WARN' : status === 'down' ? '🔴 DOWN' : '⚪ idle'}
                {model ? ` · ${model}` : ''}{collection ? ` · ${collection}` : ''}
            </div>
        </div>
    );
}
