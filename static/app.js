const byId = (id) => document.getElementById(id);
const brands = {
    NVDA: "nvidia",
    META: "meta",
    JPM: "chase",
    XOM: "exxonmobil",
    WMT: "walmart",
    KO: "cocacola",
};
const names = {
    NVDA: "NVIDIA",
    META: "Meta Platforms",
    JPM: "JPMorgan Chase",
    XOM: "Exxon Mobil",
    WMT: "Walmart",
    KO: "Coca-Cola",
};
const labels = {
    research_priority_question: "Research priority",
    risk_question: "Risk",
    market_momentum_question: "Market momentum",
    valuation_question: "Valuation",
    growth_question: "Growth",
    financial_health_question: "Financial health",
};
const metrics = [
    ["forward_pe", "Forward P/E", "ratio"],
    ["revenue_growth", "Revenue growth", "fraction"],
    ["profit_margin", "Profit margin", "fraction"],
    ["peg_ratio", "PEG ratio", "ratio"],
    ["earnings_growth", "Earnings growth", "fraction"],
    ["debt_to_equity", "Debt / equity", "percent"],
    ["beta", "Beta", "ratio"],
    ["one_year_return", "One-year return", "fraction"],
    ["distance_from_high", "From 52-week high", "fraction"],
];
let companies = [];
let questions = [];
let selected = "";
let snapshot = null;
let loading = false;
let running = false;
let selectionVersion = 0;
const results = new Map();

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function logo(symbol) {
    const image = document.createElement("img");
    if (!brands[symbol]) return element("span", "", symbol.slice(0, 2));
    image.src = `/static/${brands[symbol]}.${symbol === "XOM" ? "png" : "svg"}`;
    image.alt = "";
    image.addEventListener("error", () =>
        image.replaceWith(element("span", "", symbol.slice(0, 2))),
    );
    return image;
}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok)
        throw new Error(
            typeof data.detail === "string"
                ? data.detail
                : "Request failed. Please retry.",
        );
    return data;
}

function showError(message = "") {
    byId("error").textContent = message;
    byId("error").hidden = !message;
}

function setActivity(message) {
    byId("activity-text").textContent = message;
    byId("activity-dot").classList.toggle("running", running || loading);
}

function updateControls() {
    byId("run").disabled = running || loading || !snapshot;
    byId("refresh").disabled = running || loading || !selected;
    byId("company-select").disabled = running;
    document.querySelectorAll(".holding").forEach((button) => {
        button.disabled = running;
    });
    byId("run").querySelector("span").textContent = running
        ? "Analyzing..."
        : results.has(selected)
            ? "Run again"
            : "Run analysis";
}

async function updateStatus() {
    try {
        const status = await request("/api/status");
        byId("model-status").textContent = {
            ready: "Model loaded",
            loading: "Loading model...",
            not_loaded: "Model not loaded",
        }[status.model_status];
        byId("model-dot").className =
            `status-dot ${status.model_status === "ready" ? "ready" : status.model_status === "loading" ? "loading" : ""}`;
    } catch {
        byId("model-status").textContent = "Server unavailable";
        byId("model-dot").className = "status-dot";
    }
}

function renderPortfolio() {
    const list = byId("portfolio");
    list.replaceChildren();
    byId("company-select").replaceChildren();
    byId("holding-count").textContent = companies.length;
    companies.forEach(({ symbol, weight }) => {
        const button = element("button", "holding");
        button.type = "button";
        button.dataset.symbol = symbol;
        button.setAttribute("aria-pressed", String(symbol === selected));
        button.classList.toggle("selected", symbol === selected);
        const image = element("span", "holding-logo");
        image.append(logo(symbol));
        button.append(
            image,
            element("span", "holding-name", symbol),
            element("span", "holding-weight", `${(weight * 100).toFixed(0)}%`),
        );
        button.addEventListener("click", () => selectCompany(symbol));
        list.append(button);
        const option = element(
            "option",
            "",
            `${symbol} / ${names[symbol] || symbol} / ${(weight * 100).toFixed(0)}%`,
        );
        option.value = symbol;
        byId("company-select").append(option);
    });
    byId("company-select").value = selected;
}

function renderDecisions(result) {
    byId("decisions").replaceChildren();
    questions.forEach((question, index) => {
        const answer = result?.answers[question.name];
        const row = element("details", "decision-row");
        const summary = element("summary");
        summary.setAttribute(
            "aria-label",
            `${labels[question.name] || question.name}: ${answer?.choice || "not run"}. Show criteria`,
        );
        const title = element("span", "decision-title");
        title.append(
            element("span", "decision-number", String(index + 1).padStart(2, "0")),
            element("span", "", labels[question.name] || question.name),
        );
        const choices = element("span", "choices");
        Object.keys(question.criteria).forEach((value) => {
            const choice = element("span", "choice", value);
            if (answer?.choice === value) {
                choice.classList.add("chosen");
                if (
                    ["medium", "moderate", "neutral", "monitor", "reasonable"].includes(
                        value,
                    )
                )
                    choice.classList.add("caution");
                if (["high", "weak", "negative", "ignore", "expensive"].includes(value))
                    choice.classList.add("negative");
                choice.setAttribute("aria-label", `${value}, selected result`);
            }
            choices.append(choice);
        });
        summary.append(title, choices);
        const explanation = element("div", "decision-explanation");
        explanation.append(element("p", "", question.instructions));
        const criteria = element("dl");
        Object.entries(question.criteria).forEach(([value, description]) => {
            criteria.append(element("dt", "", value), element("dd", "", description));
        });
        explanation.append(criteria);
        row.append(summary, explanation);
        byId("decisions").append(row);
    });
}

function formatMetric(value, unit) {
    if (value === null || value === undefined) return "Unknown";
    return `${(unit === "fraction" ? value * 100 : value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${["fraction", "percent"].includes(unit) ? "%" : ""}`;
}

function renderSnapshot() {
    const state = snapshot?.state;
    byId("company-name").textContent =
        state?.company || names[selected] || selected;
    byId("company-sector").textContent =
        state?.sector || (loading ? "Loading..." : "Sector unknown");
    byId("company-symbol").textContent = selected;
    byId("company-logo").replaceChildren(logo(selected));
    byId("fundamentals").replaceChildren();
    metrics.forEach(([field, label, unit]) => {
        const item = element("div", "fundamental");
        item.append(
            element("span", "", label),
            element("strong", "", state ? formatMetric(state[field], unit) : "--"),
        );
        byId("fundamentals").append(item);
    });
    byId("snapshot-time").textContent = snapshot
        ? `Fetched ${new Date(snapshot.fetched_at).toLocaleString()}`
        : "No data loaded";
    byId("fetch-time").textContent = snapshot
        ? `Data fetch ${snapshot.fetch_ms.toLocaleString()} ms`
        : "";
}

function renderResult() {
    const result = results.get(selected);
    renderDecisions(result);
    byId("laya-time").textContent = result
        ? result.timing.laya_ms.toLocaleString(undefined, {
            maximumFractionDigits: 1,
        })
        : "--";
    byId("decision-count").textContent = result
        ? Object.keys(result.answers).length
        : "0";
    byId("contract-status").textContent = result?.validated
        ? "Choices validated"
        : "Awaiting run";
    byId("contract-status").classList.toggle("valid", Boolean(result?.validated));
    byId("contract-note").textContent = result
        ? "6 of 6 within allowed values"
        : "6 constrained choice fields";
    byId("run-model-state").textContent = result
        ? result.timing.model_preloaded
            ? "Reused model"
            : "First load"
        : "Not run";
    byId("setup-note").textContent = result
        ? `Setup ${result.timing.setup_ms.toLocaleString()} ms`
        : "Setup timed separately";
    byId("total-time").textContent = result
        ? `Server total ${result.timing.total_ms.toLocaleString()} ms`
        : "";
    byId("response-json").textContent = result
        ? JSON.stringify(result.raw, null, 2)
        : "No analysis run yet.";
}

async function selectCompany(symbol, refresh = false) {
    if (running) return;
    const version = ++selectionVersion;
    selected = symbol;
    loading = true;
    snapshot = null;
    if (refresh) results.delete(symbol);
    showError();
    renderPortfolio();
    renderSnapshot();
    renderResult();
    updateControls();
    setActivity("Fetching company fundamentals...");
    try {
        const fetched = await request(
            `/api/companies/${encodeURIComponent(symbol)}${refresh ? "?refresh=true" : ""}`,
        );
        if (version !== selectionVersion) return;
        snapshot = results.get(symbol)?.snapshot || fetched;
        loading = false;
        renderSnapshot();
        setActivity(
            results.has(symbol)
                ? "Previous result on the displayed snapshot."
                : "Market data ready. Awaiting analysis.",
        );
    } catch (error) {
        if (version !== selectionVersion) return;
        loading = false;
        showError(error.message);
        setActivity("Data unavailable. Refresh to retry.");
        renderSnapshot();
    } finally {
        if (version === selectionVersion) updateControls();
    }
}

async function runAnalysis() {
    if (running || loading || !snapshot) return;
    running = true;
    results.delete(selected);
    renderResult();
    showError();
    updateControls();
    setActivity(
        "Running live analysis. The first run may download model weights.",
    );
    const started = performance.now();
    const timer = setInterval(() => {
        byId("elapsed").textContent =
            `${((performance.now() - started) / 1000).toFixed(1)} s elapsed`;
    }, 100);
    const statusTimer = setInterval(updateStatus, 1500);
    try {
        const result = await request(
            `/api/analyze/${encodeURIComponent(selected)}`,
            { method: "POST" },
        );
        results.set(selected, result);
        snapshot = result.snapshot;
        renderSnapshot();
        renderResult();
        running = false;
        setActivity("Analysis complete. All six choices passed validation.");
    } catch (error) {
        running = false;
        showError(error.message);
        setActivity("Analysis failed. Run again to retry.");
    } finally {
        clearInterval(timer);
        clearInterval(statusTimer);
        byId("elapsed").textContent = "";
        updateControls();
        updateStatus();
    }
}

function activateTab(tab) {
    document.querySelectorAll("[role=tab]").forEach((button) => {
        const active = button === tab;
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        byId(`panel-${button.dataset.tab}`).hidden = !active;
    });
}

document.querySelectorAll("[role=tab]").forEach((tab, index, tabs) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next =
            event.key === "Home"
                ? 0
                : event.key === "End"
                    ? tabs.length - 1
                    : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
                    tabs.length;
        activateTab(tabs[next]);
        tabs[next].focus();
    });
});
byId("run").addEventListener("click", runAnalysis);
byId("refresh").addEventListener("click", () => selectCompany(selected, true));
byId("company-select").addEventListener("change", (event) =>
    selectCompany(event.target.value),
);

async function initialize() {
    window.lucide?.createIcons();
    updateStatus();
    try {
        const portfolio = await request("/api/portfolio");
        companies = portfolio.companies;
        questions = portfolio.questions;
        const properties = Object.fromEntries(
            questions.map((question) => [
                question.name,
                {
                    type: "object",
                    required: ["type", "choice"],
                    properties: {
                        type: { const: "choice" },
                        choice: { type: "string", enum: Object.keys(question.criteria) },
                    },
                    additionalProperties: true,
                },
            ]),
        );
        byId("schema-json").textContent = JSON.stringify(
            {
                type: "object",
                required: questions.map((question) => question.name),
                properties,
                additionalProperties: false,
            },
            null,
            2,
        );
        if (!companies.length) {
            setActivity("The portfolio is empty.");
            return;
        }
        await selectCompany(companies[0].symbol);
    } catch (error) {
        showError(`${error.message} Reload the page to retry.`);
        setActivity("Unable to load portfolio.");
    }
}
initialize();
