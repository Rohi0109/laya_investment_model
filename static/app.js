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
    growth_outlook_question: "Growth outlook",
    profitability_outlook_question: "Profitability outlook",
    financial_pressure_question: "Financial pressure",
    valuation_assessment_question: "Valuation assessment",
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
const researchDrafts = new Map();
const quarterDrafts = new Map();
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

function validResearch(text = "") {
    return text.trim().length > 0 && text.length <= 60000;
}

function validQuarter(text = "") {
    return /^[0-9]{4}Q[1-4]$/.test(text.trim());
}

function defaultQuarterGuess() {
    // Two calendar quarters back from today, past typical earnings-reporting lag.
    // Calendar-aligned only; companies with offset fiscal years (e.g. NVIDIA) may need a different value.
    const now = new Date();
    let quarterIndex = Math.floor(now.getMonth() / 3) - 2;
    let year = now.getFullYear();
    while (quarterIndex < 0) {
        quarterIndex += 4;
        year -= 1;
    }
    return `${year}Q${quarterIndex + 1}`;
}

function updateControls() {
    const researchText = byId("research-text").value;
    byId("run").disabled = running || loading || !snapshot || !validResearch(researchText);
    byId("research-text").disabled = running || !selected;
    byId("research-count").textContent = `${researchText.length.toLocaleString()} / 60,000`;
    byId("transcript-quarter").disabled = running || !selected;
    byId("fetch-transcript").disabled = running || loading || !selected
        || !validQuarter(byId("transcript-quarter").value);
    byId("fetch-sentiment").disabled = running || loading || !selected;
    byId("refresh").disabled = running || loading || !selected;
    byId("company-select").disabled = running;
    document.querySelectorAll(".holding").forEach((button) => {
        button.disabled = running;
    });
    document.querySelectorAll(".company-link").forEach((button) => {
        button.disabled = running;
    });
    byId("overview-nav").disabled = running;
    byId("screen-portfolio").disabled = running || loading || !companies.some(
        ({ symbol }) => validResearch(researchDrafts.get(symbol)),
    );
    byId("screen-portfolio").querySelector("span").textContent = screening
        ? "Analyzing..." : "Analyze excerpts";
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

function answerConfidence(answer) {
    const value = answer?.answer_confidence;
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
    const sortedCompanies = [...companies];
    if (sort === "weight-desc" || sort === "weight-asc") {
        sortedCompanies.sort((first, second) =>
            sort === "weight-desc" ? second.weight - first.weight : first.weight - second.weight,
        );
    } else if (sort === "confidence-desc" || sort === "confidence-asc") {
        sortedCompanies.sort((first, second) => {
            const firstConfidence = answerConfidence(results.get(first.symbol)?.answers.growth_outlook_question);
            const secondConfidence = answerConfidence(results.get(second.symbol)?.answers.growth_outlook_question);
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
        questions.forEach(({ name }) => {
            const value = result?.answers[name]?.choice;
            const cell = element("td");
            const badge = element("span", "screen-choice", value?.replaceAll("_", " ") || "Not run");
            if (value) {
                badge.classList.add("assessed");
            }
            cell.append(badge);
            row.append(cell);
            if (name === "growth_outlook_question") {
                const confidence = answerConfidence(result?.answers[name]);
                const confidenceCell = element("td", "screen-confidence", confidence === null
                    ? result ? "Unknown" : "Not run"
                    : `${(confidence * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`);
                confidenceCell.title = "Laya answer_confidence for growth outlook; not a verified probability of correctness.";
                row.append(confidenceCell);
            }
        });
        const error = screenErrors.get(symbol);
        const status = element("td", "screen-row-status", activeSymbol === symbol
            ? "Analyzing..." : error ? `Failed: ${error}` : result
                ? analyzedAt.get(symbol).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : validResearch(researchDrafts.get(symbol)) ? "Ready" : "No excerpt");
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
    const candidates = companies.filter(({ symbol }) => validResearch(researchDrafts.get(symbol)));
    if (running || loading || !candidates.length) return;
    running = true;
    screening = true;
    stopRequested = false;
    showError();
    updateControls();
    let completed = 0;
    let failed = 0;
    const statusTimer = setInterval(updateStatus, 1500);
    try {
        for (const { symbol } of candidates) {
            if (stopRequested) break;
            activeSymbol = symbol;
            results.delete(symbol);
            screenErrors.delete(symbol);
            renderOverview();
            byId("screen-status").textContent = `Analyzing ${symbol} / ${completed + 1} of ${candidates.length} excerpts`;
            try {
                const result = await request(`/api/analyze/${encodeURIComponent(symbol)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ research_text: researchDrafts.get(symbol).trim() }),
                });
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
            `${labels[question.name] || question.name}: ${answer?.choice?.replaceAll("_", " ") || "not run"}. Show criteria`,
        );
        const title = element("span", "decision-title");
        title.append(
            element("span", "decision-number", String(index + 1).padStart(2, "0")),
            element("span", "", labels[question.name] || question.name),
        );
        const choices = element("span", "choices");
        choices.style.setProperty("--choice-columns", Object.keys(question.criteria).length === 4 ? "2" : "3");
        Object.keys(question.criteria).forEach((value) => {
            const choice = element("span", "choice", value.replaceAll("_", " "));
            if (answer?.choice === value) {
                choice.classList.add("chosen");
                choice.setAttribute("aria-label", `${value}, selected result`);
            }
            choices.append(choice);
        });
        summary.append(title, choices);
        const explanation = element("div", "decision-explanation");
        if (answer) {
            const confidence = answerConfidence(answer);
            const score = element("p", "", `Answer confidence: ${confidence === null ? "Unknown"
                : `${(confidence * 100).toFixed(1)}%`}`);
            score.title = "Laya answer_confidence; not a verified probability of correctness.";
            explanation.append(score);
        }
        explanation.append(element("p", "", question.instructions));
        const criteria = element("dl");
        Object.entries(question.criteria).forEach(([value, description]) => {
            criteria.append(element("dt", "", value.replaceAll("_", " ")), element("dd", "", description));
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
        ? `${questions.length} of ${questions.length} within allowed values`
        : `${questions.length} constrained choice fields`;
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
    byId("research-text").value = researchDrafts.get(symbol) || "";
    byId("transcript-quarter").value = quarterDrafts.get(symbol) || defaultQuarterGuess();
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
    const researchText = byId("research-text").value;
    if (running || loading || !snapshot || !validResearch(researchText)) return;
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
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ research_text: researchText.trim() }),
            },
        );
        results.set(selected, result);
        analyzedAt.set(selected, new Date());
        snapshot = result.snapshot;
        renderSnapshot();
        renderResult();
        running = false;
        setActivity(`Analysis complete. All ${questions.length} choices passed validation.`);
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
byId("research-text").addEventListener("input", () => {
    if (!selected || running) return;
    researchDrafts.set(selected, byId("research-text").value);
    results.delete(selected);
    screenErrors.delete(selected);
    analyzedAt.delete(selected);
    renderResult();
    showError();
    updateControls();
    setActivity(validResearch(byId("research-text").value) ? "Excerpt ready. Awaiting analysis." : "Awaiting excerpt.");
});
byId("transcript-quarter").addEventListener("input", () => {
    if (!selected || running) return;
    quarterDrafts.set(selected, byId("transcript-quarter").value);
    updateControls();
});
byId("fetch-transcript").addEventListener("click", async () => {
    if (!selected || running || loading) return;
    const symbol = selected;
    const quarter = byId("transcript-quarter").value.trim();
    if (!validQuarter(quarter)) return;
    showError();
    setActivity(`Fetching ${symbol} ${quarter} transcript...`);
    byId("fetch-transcript").disabled = true;
    try {
        const { research_text, cached } = await request(
            `/api/transcript/${encodeURIComponent(symbol)}?quarter=${encodeURIComponent(quarter)}`,
        );
        if (selected !== symbol) return;
        byId("research-text").value = research_text;
        researchDrafts.set(symbol, research_text);
        results.delete(symbol);
        screenErrors.delete(symbol);
        analyzedAt.delete(symbol);
        renderResult();
        setActivity(
            cached
                ? "Transcript loaded from cache (no API call spent). Awaiting analysis."
                : "Real transcript fetched. Awaiting analysis.",
        );
    } catch (error) {
        if (selected === symbol) showError(error.message);
    } finally {
        updateControls();
    }
});
byId("fetch-sentiment").addEventListener("click", async () => {
    if (!selected || running || loading) return;
    const symbol = selected;
    showError();
    setActivity(`Fetching ${symbol} news sentiment...`);
    byId("fetch-sentiment").disabled = true;
    try {
        const { research_text, cached } = await request(
            `/api/sentiment/${encodeURIComponent(symbol)}`,
        );
        if (selected !== symbol) return;
        byId("research-text").value = research_text;
        researchDrafts.set(symbol, research_text);
        results.delete(symbol);
        screenErrors.delete(symbol);
        analyzedAt.delete(symbol);
        renderResult();
        setActivity(
            cached
                ? "News sentiment loaded from cache (no API call spent). Awaiting analysis."
                : "News sentiment fetched. Awaiting analysis.",
        );
    } catch (error) {
        if (selected === symbol) showError(error.message);
    } finally {
        updateControls();
    }
});
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
        byId("question-count").textContent = questions.length;
        byId("decision-total").textContent = questions.length;
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
        byId("screen-status").textContent = companies.length ? "Awaiting excerpts." : "The portfolio is empty.";
        if (companies.length) await selectCompany(companies[0].symbol);
    } catch (error) {
        showError(`${error.message} Reload the page to retry.`);
        byId("screen-status").textContent = "Unable to load portfolio.";
    }
}
initialize();
