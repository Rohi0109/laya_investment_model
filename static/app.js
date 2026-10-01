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
const screenErrors = new Map();
const analyzedAt = new Map();
let screening = false;
let stopRequested = false;
let activeSymbol = "";

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
    document.querySelectorAll(".company-link").forEach((button) => {
        button.disabled = running;
    });
    byId("overview-nav").disabled = running;
    byId("screen-portfolio").disabled = running || loading || !companies.length;
    byId("screen-portfolio").querySelector("span").textContent = screening
        ? "Screening..." : "Screen portfolio";
    byId("stop-screen").hidden = !screening;
    byId("stop-screen").disabled = stopRequested;
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
    const placeholder = element("option", "", "Select company");
    placeholder.value = "";
    placeholder.disabled = true;
    byId("company-select").append(placeholder);
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

function priorityConfidence(symbol) {
    const value = results.get(symbol)?.answers.research_priority_question?.answer_confidence;
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1
        ? value : null;
}

function renderOverview() {
    byId("overview-count").textContent = companies.length;
    byId("overview-weight").textContent = formatMetric(
        companies.reduce((total, company) => total + company.weight, 0), "fraction",
    );
    byId("overview-screened").textContent = `${results.size} / ${companies.length}`;
    const rows = byId("screen-rows");
    rows.replaceChildren();
    if (!companies.length) {
        const row = element("tr");
        const cell = element("td", "empty-holdings", "No holdings in this portfolio.");
        cell.colSpan = 8;
        row.append(cell);
        rows.append(row);
    }
    const sort = byId("screen-sort").value;
    const priorityOrder = { investigate: 0, monitor: 1, ignore: 2 };
    const priorityRank = (company) =>
        priorityOrder[results.get(company.symbol)?.answers.research_priority_question?.choice] ?? 3;
    const sortedCompanies = [...companies];
    if (sort === "priority") {
        sortedCompanies.sort((first, second) =>
            priorityRank(first) - priorityRank(second) || second.weight - first.weight,
        );
    } else if (sort === "weight-desc" || sort === "weight-asc") {
        sortedCompanies.sort((first, second) =>
            sort === "weight-desc" ? second.weight - first.weight : first.weight - second.weight,
        );
    } else if (sort === "confidence-desc" || sort === "confidence-asc") {
        sortedCompanies.sort((first, second) => {
            const firstConfidence = priorityConfidence(first.symbol);
            const secondConfidence = priorityConfidence(second.symbol);
            if (firstConfidence === null) return secondConfidence === null ? 0 : 1;
            if (secondConfidence === null) return -1;
            return sort === "confidence-desc"
                ? secondConfidence - firstConfidence : firstConfidence - secondConfidence;
        });
    }
    sortedCompanies.forEach(({ symbol, weight }) => {
        const result = results.get(symbol);
        const row = element("tr");
        row.classList.toggle("screen-active", activeSymbol === symbol);
        const company = element("td");
        const button = element("button", "company-link");
        button.type = "button";
        button.disabled = running;
        const image = element("span", "holding-logo");
        image.append(logo(symbol));
        const identity = element("span", "screen-company-name");
        identity.append(
            element("strong", "", result?.snapshot.state.company || names[symbol] || symbol),
            element("span", "", symbol),
        );
        button.append(image, identity);
        button.addEventListener("click", () => selectCompany(symbol));
        company.append(button);
        row.append(company, element("td", "screen-weight", formatMetric(weight, "fraction")));
        ["research_priority_question", "growth_question", "risk_question", "market_momentum_question"].forEach((name) => {
            const value = result?.answers[name]?.choice;
            const cell = element("td");
            const badge = element("span", "screen-choice", value || "Not run");
            if (value) {
                badge.classList.add(
                    ["high", "weak", "negative", "ignore"].includes(value) ? "negative"
                        : ["medium", "moderate", "neutral", "monitor"].includes(value) ? "caution" : "positive",
                );
            }
            cell.append(badge);
            row.append(cell);
            if (name === "research_priority_question") {
                const confidence = priorityConfidence(symbol);
                const confidenceCell = element("td", "screen-confidence", confidence === null
                    ? result ? "Unknown" : "Not run"
                    : `${(confidence * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`);
                confidenceCell.title = "Laya answer_confidence for research priority; not a verified probability of correctness.";
                row.append(confidenceCell);
            }
        });
        const error = screenErrors.get(symbol);
        const status = element("td", "screen-row-status", activeSymbol === symbol
            ? "Analyzing..." : error ? `Failed: ${error}` : result
                ? analyzedAt.get(symbol).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : "Not run");
        status.classList.toggle("screen-failed", Boolean(error));
        row.append(status);
        rows.append(row);
    });
}

function showOverview() {
    if (running) return;
    ++selectionVersion;
    selected = "";
    snapshot = null;
    loading = false;
    byId("overview-view").hidden = false;
    byId("company-view").hidden = true;
    byId("overview-nav").setAttribute("aria-pressed", "true");
    showError();
    renderPortfolio();
    renderOverview();
    updateControls();
}

async function screenPortfolio() {
    if (running || loading || !companies.length) return;
    running = true;
    screening = true;
    stopRequested = false;
    showError();
    updateControls();
    let completed = 0;
    let failed = 0;
    const statusTimer = setInterval(updateStatus, 1500);
    try {
        for (const { symbol } of companies) {
            if (stopRequested) break;
            activeSymbol = symbol;
            results.delete(symbol);
            screenErrors.delete(symbol);
            renderOverview();
            byId("screen-status").textContent = `Screening ${symbol} / ${completed + 1} of ${companies.length}`;
            try {
                const result = await request(`/api/analyze/${encodeURIComponent(symbol)}`, { method: "POST" });
                results.set(symbol, result);
                analyzedAt.set(symbol, new Date());
            } catch (error) {
                screenErrors.set(symbol, error.message);
                failed += 1;
            }
            completed += 1;
        }
    } finally {
        clearInterval(statusTimer);
        activeSymbol = "";
        running = false;
        screening = false;
        byId("screen-status").textContent = `${stopRequested ? "Stopped" : "Screen complete"}. ${completed - failed} succeeded, ${failed} failed, ${companies.length - completed} not processed.`;
        renderOverview();
        updateControls();
        updateStatus();
    }
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
    byId("overview-view").hidden = true;
    byId("company-view").hidden = false;
    byId("overview-nav").setAttribute("aria-pressed", "false");
    const version = ++selectionVersion;
    selected = symbol;
    loading = true;
    snapshot = null;
    if (refresh) {
        results.delete(symbol);
        screenErrors.delete(symbol);
    }
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
    screenErrors.delete(selected);
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
        analyzedAt.set(selected, new Date());
        snapshot = result.snapshot;
        renderSnapshot();
        renderResult();
        running = false;
        setActivity("Analysis complete. All six choices passed validation.");
    } catch (error) {
        running = false;
        screenErrors.set(selected, error.message);
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
byId("overview-nav").addEventListener("click", showOverview);
byId("screen-portfolio").addEventListener("click", screenPortfolio);
byId("screen-sort").addEventListener("change", renderOverview);
byId("stop-screen").addEventListener("click", () => {
    stopRequested = true;
    byId("screen-status").textContent = `Stopping after ${activeSymbol}...`;
    updateControls();
});
document.querySelector(".brand").addEventListener("click", (event) => {
    event.preventDefault();
    showOverview();
});
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
        showOverview();
        byId("screen-status").textContent = companies.length ? "Ready to screen." : "The portfolio is empty.";
    } catch (error) {
        showError(`${error.message} Reload the page to retry.`);
        byId("screen-status").textContent = "Unable to load portfolio.";
    }
}
initialize();
