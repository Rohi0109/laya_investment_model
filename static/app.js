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
    market_reaction_question: "Market reaction",
    materiality_question: "Significance",
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
let articleQuestions = [];
let selected = "";
let snapshot = null;
let loading = false;
let running = false;
let selectionVersion = 0;
const results = new Map();
const newsResults = new Map();
const expandedArticles = new Map();
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
    byId("analyze-news").disabled = running || loading || !selected;
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
        ? "Analyzing..." : "Analyze news";
    byId("stop-screen").hidden = !screening;
    byId("stop-screen").disabled = stopRequested;
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

const positiveChoices = {
    market_reaction_question: "bullish",
};
const negativeChoices = {
    market_reaction_question: "bearish",
};
const unassessedChoices = {
    market_reaction_question: "not_discussed",
    materiality_question: "unclear",
};

function choiceLabel(questionName, choice) {
    if (questionName === "materiality_question") {
        const significanceLabels = { major: "High", minor: "Low", routine: "Routine", unclear: "Unclear" };
        return significanceLabels[choice] || choice?.replaceAll("_", " ");
    }
    return choice?.replaceAll("_", " ");
}

function choiceSentiment(questionName, choice) {
    if (!choice || choice === unassessedChoices[questionName]) return null;
    if (questionName === "materiality_question") {
        // Materiality is about significance, not sentiment: only call out major news.
        return choice === "major" ? "neutral" : null;
    }
    if (choice === positiveChoices[questionName]) return "positive";
    if (choice === negativeChoices[questionName]) return "negative";
    return null;
}

function renderArticleSource(article) {
    const metadata = element("div", "article-source");
    const source = typeof article.source === "string" ? article.source.trim() : "";
    const url = typeof article.url === "string" && URL.canParse(article.url)
        ? new URL(article.url) : null;
    if (url && ["http:", "https:"].includes(url.protocol) && !url.username && !url.password) {
        const link = element("a", "article-source-link", source || "Read article");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.setAttribute("aria-label", `${source ? `Read article on ${source}` : "Read article"} (opens in new tab)`);
        link.title = "Read article (opens in new tab)";
        const icon = element("i");
        icon.dataset.lucide = "external-link";
        icon.setAttribute("aria-hidden", "true");
        link.append(icon);
        metadata.append(link);
    } else {
        metadata.append(element("span", "", source || "Source unavailable"));
    }
    const published = typeof article.time_published === "string"
        ? article.time_published.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/) : null;
    if (published) {
        const iso = `${published[1]}-${published[2]}-${published[3]}T${published[4]}:${published[5]}:${published[6]}.000Z`;
        const date = new Date(iso);
        if (Number.isFinite(date.getTime()) && date.toISOString() === iso) {
            const time = element("time", "", date.toLocaleDateString("en-US", {
                month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
            }));
            time.dateTime = iso.slice(0, 10);
            metadata.append(time);
        }
    }
    return metadata;
}

function renderArticleSignals(symbol) {
    const newsData = newsResults.get(symbol);
    byId("article-signals").hidden = !newsData;
    if (!newsData) return;
    const expanded = expandedArticles.get(symbol) || new Set();
    byId("signals-label").textContent = `${newsData.articles.length} article${newsData.articles.length === 1 ? "" : "s"}`;
    const body = byId("article-signals-body");
    body.replaceChildren();
    const table = element("table", "signals-table");
    table.setAttribute("role", "table");
    const thead = element("thead");
    thead.setAttribute("role", "rowgroup");
    const headerRow = element("tr");
    headerRow.setAttribute("role", "row");
    headerRow.append(element("th", "signals-th-rel", "Relevance"));
    headerRow.append(element("th", "signals-th-headline", "Headline"));
    articleQuestions.forEach(({ name }) => {
        headerRow.append(element("th", "", labels[name] || name));
    });
    headerRow.querySelectorAll("th").forEach((header) => {
        header.setAttribute("role", "columnheader");
        header.scope = "col";
    });
    thead.append(headerRow);
    table.append(thead);
    const tbody = element("tbody");
    tbody.setAttribute("role", "rowgroup");
    const columnCount = 2 + articleQuestions.length;
    newsData.articles.forEach((article, index) => {
        const row = element("tr", "signals-article-row");
        row.setAttribute("role", "row");
        const relCell = element("td", "signals-rel-cell");
        const dot = element("span", "relevance-dot");
        dot.classList.add(article.relevance >= 0.8 ? "rel-high" : article.relevance >= 0.5 ? "rel-mid" : "rel-low");
        const relevanceLabel = element("span", "mobile-signal-label", "Relevance");
        relevanceLabel.setAttribute("aria-hidden", "true");
        relCell.append(relevanceLabel, dot, element("span", "relevance-score", article.relevance.toFixed(2)));
        row.append(relCell);
        const rawHeadline = typeof article.title === "string" && article.title.trim()
            ? article.title : article.text.split(":")[0] || article.text;
        const headlineCell = element("td", "signals-headline");
        const headlineButton = element("button", "signals-headline-button");
        const chevron = element("i", "article-chevron");
        chevron.dataset.lucide = "chevron-down";
        chevron.setAttribute("aria-hidden", "true");
        headlineButton.append(element("span", "headline-text", rawHeadline), chevron);
        headlineButton.type = "button";
        headlineButton.title = expanded.has(index) ? "Collapse summary" : "Show article summary";
        headlineButton.setAttribute("aria-expanded", String(expanded.has(index)));
        headlineButton.setAttribute("aria-controls", `article-detail-${symbol}-${index}`);
        headlineButton.addEventListener("click", () => {
            const current = expandedArticles.get(symbol) || new Set();
            if (current.has(index)) current.delete(index); else current.add(index);
            expandedArticles.set(symbol, current);
            renderArticleSignals(symbol);
            body.querySelectorAll(".signals-headline-button")[index].focus({ preventScroll: true });
        });
        headlineCell.append(headlineButton, renderArticleSource(article));
        row.append(headlineCell);
        articleQuestions.forEach(({ name }) => {
            const choice = article.answers?.[name]?.choice;
            const cell = element("td");
            const mobileLabel = element("span", "mobile-signal-label", labels[name] || name);
            mobileLabel.setAttribute("aria-hidden", "true");
            cell.append(mobileLabel);
            const badge = element("span", "screen-choice", choiceLabel(name, choice) || "—");
            if (choice) {
                badge.classList.add("assessed");
                const s = choiceSentiment(name, choice);
                if (s === "positive") badge.classList.add("positive");
                else if (s === "negative") badge.classList.add("negative");
                else if (s === "neutral") badge.classList.add("caution");
            }
            cell.append(badge);
            row.append(cell);
        });
        row.querySelectorAll("td").forEach((cell) => cell.setAttribute("role", "cell"));
        tbody.append(row);
        {
            const detailRow = element("tr", "signals-detail-row");
            detailRow.id = `article-detail-${symbol}-${index}`;
            detailRow.hidden = !expanded.has(index);
            detailRow.setAttribute("role", "row");
            const detailCell = element("td", "signals-detail-cell");
            detailCell.append(element("div", "article-copy", article.text));
            detailCell.setAttribute("role", "cell");
            detailCell.colSpan = columnCount;
            detailRow.append(detailCell);
            tbody.append(detailRow);
        }
    });
    table.append(tbody);
    body.append(table);
    window.lucide?.createIcons({ root: body });
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
        cell.colSpan = 6;
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
            const firstConfidence = answerConfidence(results.get(first.symbol)?.answers.market_reaction_question);
            const secondConfidence = answerConfidence(results.get(second.symbol)?.answers.market_reaction_question);
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
        const weightCell = element("td", "screen-weight", formatMetric(weight, "fraction"));
        weightCell.style.setProperty("--holding-weight", `${Math.min(100, Math.max(0, weight * 100))}%`);
        row.append(company, weightCell);
        articleQuestions.forEach(({ name }) => {
            const value = result?.answers[name]?.choice;
            const cell = element("td");
            const badge = element("span", "screen-choice", choiceLabel(name, value) || "Not run");
            if (value) {
                badge.classList.add("assessed");
                const s = choiceSentiment(name, value);
                if (s === "positive") badge.classList.add("positive");
                else if (s === "negative") badge.classList.add("negative");
                else if (s === "neutral") badge.classList.add("caution");
            }
            cell.append(badge);
            row.append(cell);
            if (name === "market_reaction_question") {
                const confidence = answerConfidence(result?.answers[name]);
                const confidenceCell = element("td", "screen-confidence", confidence === null
                    ? result ? "Unknown" : "Not run"
                    : `${(confidence * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`);
                confidenceCell.title = "Laya answer_confidence for market reaction; not a verified probability of correctness.";
                row.append(confidenceCell);
            }
        });
        const error = screenErrors.get(symbol);
        const status = element("td", "screen-row-status", activeSymbol === symbol
            ? "Analyzing..." : error ? `Failed: ${error}` : result
                ? analyzedAt.get(symbol).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : "Not analyzed");
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
    try {
        for (const { symbol } of companies) {
            if (stopRequested) break;
            activeSymbol = symbol;
            results.delete(symbol);
            newsResults.delete(symbol);
            screenErrors.delete(symbol);
            renderOverview();
            byId("screen-status").textContent = `Analyzing ${symbol} / ${completed + 1} of ${companies.length} companies`;
            try {
                const data = await request(`/api/sentiment-each/${encodeURIComponent(symbol)}`);
                newsResults.set(symbol, data);
                results.set(symbol, {
                    symbol: data.symbol,
                    snapshot: data.snapshot,
                    answers: data.aggregate.answers,
                    validated: true,
                    raw: data,
                    timing: data.timing,
                });
                analyzedAt.set(symbol, new Date());
            } catch (error) {
                screenErrors.set(symbol, error.message);
                failed += 1;
            }
            completed += 1;
        }
    } finally {
        activeSymbol = "";
        running = false;
        screening = false;
        byId("screen-status").textContent = `${stopRequested ? "Stopped" : "Screen complete"}. ${completed - failed} succeeded, ${failed} failed, ${companies.length - completed} not processed.`;
        renderOverview();
        updateControls();
    }
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
    byId("research-summary").hidden = !result;
    const findings = byId("summary-findings");
    findings.replaceChildren();
    if (result) {
        articleQuestions.forEach(({ name }) => {
            const choice = result.answers[name]?.choice;
            const finding = element("div");
            const value = element("dd", "screen-choice assessed", choiceLabel(name, choice) || "Unknown");
            const sentiment = choiceSentiment(name, choice);
            if (sentiment) value.classList.add(sentiment === "neutral" ? "caution" : sentiment);
            finding.append(element("dt", "", labels[name] || name), value);
            findings.append(finding);
        });
        const holding = companies.find(({ symbol }) => symbol === selected);
        const weight = element("div");
        weight.append(element("dt", "", "Portfolio weight"), element("dd", "", formatMetric(holding?.weight, "fraction")));
        findings.append(weight);
        byId("summary-method").textContent = `Relevance-weighted result · ${result.raw.articles.length} articles`;
    }
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
        ? `${Object.keys(result.answers).length} of ${Object.keys(result.answers).length} within allowed values`
        : `${articleQuestions.length} constrained choice fields`;
    byId("total-time").textContent = result
        ? `Analysis server time ${result.timing.total_ms.toLocaleString()} ms`
        : "";
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
        newsResults.delete(symbol);
        expandedArticles.delete(symbol);
        screenErrors.delete(symbol);
    }
    showError();
    renderPortfolio();
    renderSnapshot();
    renderResult();
    renderArticleSignals(symbol);
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

async function analyzeNewsArticles() {
    if (running || loading || !snapshot || !selected) return;
    const symbol = selected;
    running = true;
    newsResults.delete(symbol);
    results.delete(symbol);
    screenErrors.delete(symbol);
    renderResult();
    renderArticleSignals(symbol);
    showError();
    updateControls();
    setActivity("Analyzing news articles...");
    const started = performance.now();
    const timer = setInterval(() => {
        byId("elapsed").textContent =
            `${((performance.now() - started) / 1000).toFixed(1)} s elapsed`;
    }, 100);
    try {
        const data = await request(`/api/sentiment-each/${encodeURIComponent(symbol)}`);
        newsResults.set(symbol, data);
        results.set(symbol, {
            symbol: data.symbol,
            snapshot: data.snapshot,
            research_text: `News: ${data.articles.length} articles`,
            answers: data.aggregate.answers,
            validated: true,
            raw: data,
            timing: data.timing,
        });
        analyzedAt.set(symbol, new Date());
        snapshot = data.snapshot;
        renderSnapshot();
        renderResult();
        renderArticleSignals(symbol);
        running = false;
        setActivity(
            `News analysis complete. ${data.articles.length} article${data.articles.length === 1 ? "" : "s"} · weighted aggregate.`,
        );
    } catch (error) {
        running = false;
        screenErrors.set(symbol, error.message);
        showError(error.message);
        setActivity("News analysis failed. Retry.");
    } finally {
        clearInterval(timer);
        byId("elapsed").textContent = "";
        updateControls();
        renderOverview();
    }
}

byId("analyze-news").addEventListener("click", analyzeNewsArticles);
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
    try {
        const portfolio = await request("/api/portfolio");
        companies = portfolio.companies;
        articleQuestions = portfolio.article_questions || [];
        byId("question-count").textContent = articleQuestions.length;
        byId("decision-total").textContent = articleQuestions.length;
        showOverview();
        byId("screen-status").textContent = companies.length ? "Awaiting news analysis." : "The portfolio is empty.";
    } catch (error) {
        showError(`${error.message} Reload the page to retry.`);
        byId("screen-status").textContent = "Unable to load portfolio.";
    }
}
initialize();
