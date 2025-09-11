import { useState } from 'react';
import { get } from '../api/http.js';

export function useHealth() {
    const [status, setStatus] = useState(null);
    const [model, setModel] = useState(null);
    const [collection, setCollection] = useState(null);

    async function refresh() {
        try {
            const h = await get('/api/health'); // FastAPI에서 제공
            setStatus('ok');
            setModel(h.openai_model || h.model || null);
            setCollection(h.vector_collection || h.collection || h.collection_name || null);
        } catch (e) {
            setStatus('down');
            setModel(null);
            setCollection(null);
        }
    }

    return { status, model, collection, refresh };
}
