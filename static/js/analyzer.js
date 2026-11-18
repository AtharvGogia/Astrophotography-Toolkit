'use strict';

(() => {
    const $ = (id) => document.getElementById(id);
    const POLL_MS = 5000;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    function log(message) {
        const li = document.createElement('li');
        li.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
        $('log').appendChild(li);
        $('log').scrollTop = $('log').scrollHeight;
    }

    let timer = null;
    function startClock() {
        const t0 = Date.now();
        clearInterval(timer);
        timer = setInterval(() => {
            const s = Math.floor((Date.now() - t0) / 1000);
            $('elapsed').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
        }, 1000);
    }

    async function getJSON(url, options) {
        const resp = await fetch(url, options);
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
        return data;
    }

    $('analyzeForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        $('analyzerError').textContent = '';
        const file = $('imageUpload').files[0];
        if (!file) {
            $('analyzerError').textContent = 'Choose a photo first.';
            return;
        }

        const btn = $('analyzeBtn');
        btn.disabled = true;
        btn.textContent = 'Working…';
        $('output').hidden = true;
        $('progress').hidden = false;
        $('log').innerHTML = '';
        $('progressBar').value = 5;
        startClock();

        try {
            log(`Uploading ${file.name}…`);
            const form = new FormData();
            form.append('image', file);
            const { sub_id: subId } = await getJSON('/api/upload', { method: 'POST', body: form });
            log(`Uploaded (submission ${subId}). Waiting for astrometry.net…`);
            $('progressBar').value = 20;

            let status = 'pending', jobId = null, annotatedUrl = null, lastStatus = '';
            while (status !== 'success' && status !== 'failure') {
                await sleep(POLL_MS);
                const s = await getJSON(`/api/status/${subId}`);
                ({ status, job_id: jobId, annotated_image_url: annotatedUrl } = s);
                if (status !== lastStatus) {
                    log(status === 'solving' ? 'Solving…' : !jobId ? 'In the queue…' : `Status: ${status}`);
                    lastStatus = status;
                }
                const cap = status === 'solving' ? 85 : 45;
                $('progressBar').value = Math.min(cap, $('progressBar').value + 3);
            }
            if (status === 'failure') throw new Error('astrometry.net could not solve this image.');

            log('Solved. Fetching the list of objects…');
            const { annotations } = await getJSON(`/api/results/${jobId}`);
            $('annotatedImage').src = annotatedUrl;

            const rows = $('objectRows');
            rows.innerHTML = '';
            if (!annotations.length) {
                rows.innerHTML = '<tr><td colspan="2">No named objects in this field.</td></tr>';
            }
            for (const a of annotations) {
                const tr = document.createElement('tr');
                const [main = 'Unnamed object', ...others] = Array.isArray(a.names) ? a.names : [];
                tr.innerHTML = '<td></td><td></td>';
                tr.children[0].textContent = main;
                tr.children[1].textContent = others.join(', ');
                rows.appendChild(tr);
            }
            $('progressBar').value = 100;
            log('Done.');
            $('output').hidden = false;
        } catch (err) {
            $('analyzerError').textContent = err.message;
            log(`Stopped: ${err.message}`);
        } finally {
            clearInterval(timer);
            btn.disabled = false;
            btn.textContent = 'Analyze';
        }
    });
})();
