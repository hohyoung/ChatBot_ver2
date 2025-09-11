import React from 'react';
import { useHealth } from '../store/health.js';

export default function SettingsPage() {
    const { status, model, collection, refresh } = useHealth();
    return (
        <div className="col" style={{ gap: 16 }}>
            <div className="section">
                <h3 style={{ marginTop: 0 }}>서버 상태</h3>
                <div className="row">
                    <button className="button" onClick={refresh}>헬스 체크</button>
                    <div className="small">status: {status || 'idle'} · model: {model || '—'} · collection: {collection || '—'}</div>
                </div>
            </div>

            <div className="section">
                <h3 style={{ marginTop: 0 }}>화면 설정(로컬)</h3>
                <div className="small">필요하면 나중에 기본 태그, 자동 스크롤 같은 옵션을 여기에 넣자.</div>
            </div>
        </div>
    );
}
