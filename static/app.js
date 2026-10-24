let config = null;
let currentSymbol = "BTC/USDT";
let socket = null;
let chart = null;
let mainSeries = null;
let symbolData = {};

document.addEventListener("DOMContentLoaded", async () => {
    await loadConfig();
    initChart();
    await loadSymbols();
    const initialSym = (config && config.currencies && config.currencies.includes(config.default_symbol))
        ? config.default_symbol
        : (config && config.currencies && config.currencies[0]) || "BTC/USDT";
    await selectSymbol(initialSym);
    connectWebSocket();
});

async function loadConfig() {
    try {
        const res = await fetch("/api/config");
        config = await res.json();
        currentSymbol = config.default_symbol || (config.currencies && config.currencies[0]) || "BTC/USDT";
        
        document.getElementById("exchange-badge").innerText = `Exchange: ${config.exchange.toUpperCase()}`;
        document.getElementById("chart-type-badge").innerText = `Chart: ${config.chart_type.toUpperCase()}`;

        const modeBadge = document.getElementById("storage-mode-badge");
        const modeVal = document.getElementById("storage-engine-val");
        const isMem = config.is_in_memory || config.storage_mode === "memory";

        if (modeBadge) {
            modeBadge.innerText = isMem ? "Mode: In-Memory (No-DB)" : "Mode: SQLite WAL";
        }
        if (modeVal) {
            modeVal.innerText = isMem 
                ? `In-Memory (Max 3 Cryptos + CSV Files: ${config.csv_dir || 'data'}/*.csv)` 
                : "SQLite WAL (7d Raw / 90d Candles)";
        }
    } catch (e) {
        console.error("Error loading config:", e);
    }
}

function initChart() {
    const container = document.getElementById("chart-container");
    container.innerHTML = "";

    chart = LightweightCharts.createChart(container, {
        layout: {
            backgroundColor: "#0d1322",
            textColor: "#9ca3af",
        },
        grid: {
            vertLines: { color: "rgba(255, 255, 255, 0.05)" },
            horzLines: { color: "rgba(255, 255, 255, 0.05)" },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: "rgba(255, 255, 255, 0.1)",
        },
        timeScale: {
            borderColor: "rgba(255, 255, 255, 0.1)",
            timeVisible: true,
            secondsVisible: true,
        },
    });

    // Check chart type configured in config.yaml
    const isLine = config && config.chart_type === "line";

    if (isLine) {
        mainSeries = chart.addLineSeries({
            color: "#3b82f6",
            lineWidth: 2,
        });
    } else {
        mainSeries = chart.addCandlestickSeries({
            upColor: "#10b981",
            downColor: "#ef4444",
            borderVisible: false,
            wickUpColor: "#10b981",
            wickDownColor: "#ef4444",
        });
    }

    window.addEventListener("resize", () => {
        chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    });
}

async function loadSymbols() {
    try {
        const res = await fetch("/api/symbols");
        const data = await res.json();
        const listContainer = document.getElementById("crypto-list");
        listContainer.innerHTML = "";

        document.getElementById("symbol-count").innerText = `${data.symbols.length} Pairs`;

        data.symbols.forEach(st => {
            symbolData[st.symbol] = st;
            const item = document.createElement("div");
            item.className = `crypto-item ${st.symbol === currentSymbol ? 'active' : ''}`;
            item.id = `item-${st.symbol.replace('/', '-')}`;
            item.onclick = () => selectSymbol(st.symbol);

            const chClass = st.change_24h_pct >= 0 ? "positive" : "negative";
            const chSign = st.change_24h_pct >= 0 ? "+" : "";

            item.innerHTML = `
                <div class="crypto-info">
                    <div class="sym">${st.symbol}</div>
                    <div class="exch">${config ? config.exchange : ''}</div>
                </div>
                <div class="crypto-price-group">
                    <div class="pr" id="price-${st.symbol.replace('/', '-')}">$${formatPrice(st.latest_price)}</div>
                    <div class="ch ${chClass}" id="change-${st.symbol.replace('/', '-')}">${chSign}${st.change_24h_pct}%</div>
                </div>
            `;
            listContainer.appendChild(item);
        });
    } catch (e) {
        console.error("Error loading symbols:", e);
    }
}

async function selectSymbol(symbol) {
    currentSymbol = symbol;
    document.getElementById("active-symbol-title").innerText = symbol;

    // Update active class in sidebar
    document.querySelectorAll(".crypto-item").forEach(el => el.classList.remove("active"));
    const activeEl = document.getElementById(`item-${symbol.replace('/', '-')}`);
    if (activeEl) activeEl.classList.add("active");

    await fetchHistoryAndAnalysis(symbol);
}

async function fetchHistoryAndAnalysis(symbol) {
    try {
        const isLine = config && config.chart_type === "line";
        const mode = isLine ? "ticks" : "candles";

        // Fetch Chart History
        const histRes = await fetch(`/api/history/${encodeURIComponent(symbol)}?mode=${mode}&limit=300`);
        const histData = await histRes.json();

        if (histData.data && histData.data.length > 0) {
            if (isLine) {
                const linePoints = histData.data.map(t => ({
                    time: t.timestamp,
                    value: t.price
                }));
                mainSeries.setData(linePoints);
            } else {
                const candlePoints = histData.data.map(c => ({
                    time: c.timestamp,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close
                }));
                mainSeries.setData(candlePoints);
            }
        }

        // Fetch Analysis Stats
        const analRes = await fetch(`/api/analysis/${encodeURIComponent(symbol)}`);
        const analData = await analRes.json();
        updateAnalysisUI(analData);
    } catch (e) {
        console.error("Error fetching history/analysis:", e);
    }
}

function updateAnalysisUI(data) {
    const stats = data.stats;
    const anal = data.analysis;

    document.getElementById("active-price").innerText = `$${formatPrice(stats.latest_price)}`;
    
    const ch24Pill = document.getElementById("active-24h-change");
    ch24Pill.innerText = `${stats.change_24h_pct >= 0 ? '+' : ''}${stats.change_24h_pct}% (24h)`;
    ch24Pill.className = `price-change-pill ${stats.change_24h_pct >= 0 ? 'positive' : 'negative'}`;

    const ch7dPill = document.getElementById("active-7d-change");
    ch7dPill.innerText = `${stats.change_7d_pct >= 0 ? '+' : ''}${stats.change_7d_pct}% (7d)`;
    ch7dPill.className = `price-change-pill ${stats.change_7d_pct >= 0 ? 'positive' : 'negative'}`;

    document.getElementById("stat-high").innerText = `$${formatPrice(stats.high_24h)}`;
    document.getElementById("stat-low").innerText = `$${formatPrice(stats.low_24h)}`;
    document.getElementById("stat-volume").innerText = formatNumber(stats.volume_24h);

    // Tendency Signals
    const signalBadge = document.getElementById("trend-signal");
    signalBadge.innerText = `${anal.trend} (${anal.confidence_score}%)`;
    signalBadge.className = `confidence-badge ${anal.trend}`;

    document.getElementById("confidence-fill").style.width = `${anal.confidence_score}%`;
    document.getElementById("confidence-val").innerText = `${anal.confidence_score}%`;
    document.getElementById("analysis-summary").innerText = anal.summary;

    // Indicators
    document.getElementById("ind-ema20").innerText = anal.ema20 ? `$${formatPrice(anal.ema20)}` : "--";
    document.getElementById("ind-ema50").innerText = anal.ema50 ? `$${formatPrice(anal.ema50)}` : "--";
    document.getElementById("ind-rsi").innerText = anal.rsi ? anal.rsi : "--";
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/rates`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        document.getElementById("conn-status").innerText = "0.5s Stream Live";
        console.log("WebSocket connected.");
    };

    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "tick") {
            handleLiveTick(msg.data);
        } else if (msg.type === "snapshot") {
            Object.values(msg.data).forEach(t => handleLiveTick(t));
        }
    };

    socket.onclose = () => {
        document.getElementById("conn-status").innerText = "Disconnected (Retrying)";
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

function handleLiveTick(tick) {
    const sym = tick.symbol;
    const price = tick.price;

    // Update sidebar tick
    const priceEl = document.getElementById(`price-${sym.replace('/', '-')}`);
    if (priceEl) priceEl.innerText = `$${formatPrice(price)}`;

    // Update current active chart if matching active symbol
    if (sym === currentSymbol) {
        document.getElementById("active-price").innerText = `$${formatPrice(price)}`;

        const isLine = config && config.chart_type === "line";
        if (isLine) {
            mainSeries.update({
                time: tick.timestamp,
                value: price
            });
        } else {
            // Update candle close
            mainSeries.update({
                time: Math.floor(tick.timestamp / 60) * 60,
                open: price,
                high: price,
                low: price,
                close: price
            });
        }
    }
}

function formatPrice(p) {
    if (!p) return "0.00";
    return p >= 10 ? p.toFixed(2) : p.toFixed(4);
}

function formatNumber(n) {
    if (!n) return "0.00";
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(2) + "K";
    return n.toFixed(2);
}
