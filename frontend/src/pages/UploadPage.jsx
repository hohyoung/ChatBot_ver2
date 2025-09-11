import React, { useEffect, useRef, useState } from 'react';
import { post, get } from '../api/http.js';



export default function UploadPage() {
    const [files, setFiles] = useState([]);
    const [job, setJob] = useState(null); // {job_id, accepted, skipped}
    const [status, setStatus] = useState(null); // {status, processed, total?, errors?}
    const timerRef = useRef(null);

    const onPick = (e) => setFiles(Array.from(e.target.files || []));
    const onDrop = (e) => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files || [])); };
    const onDrag = (e) => e.preventDefault();

    const upload = async () => {
        if (!files.length) return;
        const form = new FormData();
        files.forEach(f => form.append('files', f));
        const data = await post('/api/docs/upload', form);
        setJob(data); // { job_id, accepted, skipped }
    };

    // 폴링
    useEffect(() => {
        if (!job?.job_id) return;
        const poll = async () => {
            try {
                const st = await get(`/api/docs/${job.job_id}/status`);
                setStatus(st);
                if (st.status === 'succeeded' || st.status === 'failed') {
                    clearInterval(timerRef.current); timerRef.current = null;
                }
            } catch (e) {
                console.error(e);
            }
        };
        poll();
        timerRef.current = setInterval(poll, 1500);
        return () => timerRef.current && clearInterval(timerRef.current);
    }, [job]);

    return (
        <div className="col" style={{ gap: 16 }}>
            <div className="section" onDrop={onDrop} onDragOver={onDrag}>
                <h3 style={{ marginTop: 0 }}>문서 업로드</h3>
                <div className="row">
                    <input type="file" multiple onChange={onPick} />
                    <button className="button" onClick={upload}>업로드</button>
                </div>
                <div className="small">여러 파일 선택 가능. 업로드 후 인덱싱 상태를 폴링합니다.</div>
            </div>

            <div className="section">
                <h3 style={{ marginTop: 0 }}>상태</h3>
                <div className="card">
                    <div>선택 파일: {files.length}</div>
                    <div>잡: {job ? JSON.stringify(job) : '—'}</div>
                    <div>진행: {status ? JSON.stringify(status) : '—'}</div>
                </div>
            </div>
        </div>
    );
}
