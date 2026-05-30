document.addEventListener("DOMContentLoaded", () => {
    const startBtn = document.getElementById("start-btn");
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const logOutput = document.getElementById("log-output");
    
    const metricsCard = document.getElementById("metrics-card");
    const metricPhase = document.getElementById("metric-phase");
    const metricRows = document.getElementById("metric-rows");
    const metricHash = document.getElementById("metric-hash");

    let eventSource = null;

    function appendLog(msg) {
        const div = document.createElement("div");
        div.className = "log-line";
        
        // Basic log coloring
        if (msg.includes("ERROR") || msg.includes("FAILED")) div.classList.add("error");
        else if (msg.includes("SUCCESS")) div.classList.add("success");
        else if (msg.includes("Phase") || msg.includes("=== ")) div.classList.add("info");
        else div.classList.add("system");
        
        div.textContent = msg;
        logOutput.appendChild(div);
        
        // Auto-scroll to bottom
        logOutput.scrollTop = logOutput.scrollHeight;
        
        // Parse metrics dynamically from logs
        if (msg.includes("Phase")) {
            const phaseMatch = msg.match(/Phase (\d+)/);
            if (phaseMatch) {
                metricPhase.textContent = "Phase " + phaseMatch[1];
                metricPhase.classList.add("highlight");
                setTimeout(() => metricPhase.classList.remove("highlight"), 1000);
            }
        }
        if (msg.includes("Successfully loaded")) {
            const rowsMatch = msg.match(/loaded (\d+) rows/);
            if (rowsMatch) {
                const current = parseInt(metricRows.textContent.replace(/,/g, '') || 0);
                metricRows.textContent = (current + parseInt(rowsMatch[1])).toLocaleString();
                metricRows.classList.add("highlight");
                setTimeout(() => metricRows.classList.remove("highlight"), 500);
            }
        }
        if (msg.includes("Hash:")) {
            const hashMatch = msg.match(/Hash: ([a-z0-9]+)/i);
            if (hashMatch) metricHash.textContent = hashMatch[1];
        }
    }

    function connectSSE() {
        if (eventSource) eventSource.close();
        
        eventSource = new EventSource("/api/logs");
        
        eventSource.onmessage = function(event) {
            const data = event.data;
            if (data.includes("[COMPLETED]")) {
                appendLog(data);
                finishMigration();
            } else {
                appendLog(data);
            }
        };
        
        eventSource.onerror = function() {
            // Error handling
        };
    }

    function finishMigration() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        
        statusDot.className = "dot ready";
        statusText.textContent = "Migration Complete";
        
        startBtn.disabled = false;
        startBtn.querySelector('.btn-text').textContent = "RE-RUN PIPELINE";
        metricsCard.classList.remove("active-pulse");
    }

    startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        startBtn.querySelector('.btn-text').textContent = "MIGRATING...";
        
        statusDot.className = "dot running";
        statusText.textContent = "Pipeline Active";
        metricsCard.classList.add("active-pulse");
        
        logOutput.innerHTML = "";
        appendLog("Initializing Secure Connection to Backend...");
        
        metricPhase.textContent = "Phase 0";
        metricPhase.classList.remove("highlight");
        metricRows.textContent = "0";
        metricRows.classList.remove("highlight");
        metricHash.textContent = "-";
        
        try {
            const response = await fetch("/api/start", { method: "POST" });
            const data = await response.json();
            
            if (data.status === "success") {
                appendLog("Backend orchestration triggered successfully.");
                connectSSE();
            } else {
                appendLog(`ERROR: ${data.message}`);
                finishMigration();
            }
        } catch (error) {
            appendLog(`ERROR: Failed to connect to server - ${error}`);
            finishMigration();
        }
    });
});
