import json


def load_portfolio() -> dict[str, float]:
    with open("portfolio.json", encoding="utf-8") as portfolio_file:
        return json.load(portfolio_file)