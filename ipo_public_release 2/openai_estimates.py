"""OpenAI Responses APIを使った、IPO公開価格の参考推定。"""

import json
from pathlib import Path
from urllib.request import Request, urlopen


RESPONSES_URL = "https://api.openai.com/v1/responses"
CACHE_PATH = Path(__file__).with_name("ai_price_estimates.json")
MODEL = "gpt-5.4-mini"


def load_estimates():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(estimates):
    temporary = CACHE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(estimates, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CACHE_PATH)


def _response_text(payload):
    for output in payload.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    return ""


def estimate_ipo_price(item, api_key):
    if not api_key:
        raise ValueError("OPENAI_API_KEYが設定されていません。")
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["estimated", "insufficient"]},
            "estimated_price_yen": {"type": ["integer", "null"]},
            "low_price_yen": {"type": ["integer", "null"]},
            "high_price_yen": {"type": ["integer", "null"]},
            "confidence": {"type": "string", "enum": ["low", "medium"]},
            "basis": {"type": "array", "items": {"type": "string"}},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                    "required": ["title", "url"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["status", "estimated_price_yen", "low_price_yen", "high_price_yen", "confidence", "basis", "sources"],
        "additionalProperties": False,
    }
    prompt = f"""
日本株IPOの未決定公開価格について、投資勧誘ではない参考推定を作成してください。
会社名: {item['company']}
市場: {item.get('market', '未確認')}
事業: {item.get('business', '未確認')}
上場予定日: {item.get('listing_date', '未確認')}
楽天証券の仮条件: {item.get('price_range', '未定')}

必ず企業公式、取引所、EDINETなど一次情報を優先して検索してください。
想定価格、仮条件、募集規模、業績など数値根拠が確認できない場合はstatusをinsufficientにし、価格をnullにしてください。
推定できる場合も一点断定を避け、下限・中心・上限を示してください。株価上昇や利益を保証しないでください。
"""
    body = {
        "model": MODEL,
        "tools": [{"type": "web_search"}],
        "input": prompt,
        "text": {"format": {"type": "json_schema", "name": "ipo_price_estimate", "strict": True, "schema": schema}},
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        payload = json.load(response)
    text = _response_text(payload)
    if not text:
        raise ValueError("OpenAI APIから分析結果を読み取れませんでした。")
    result = json.loads(text)
    result["model"] = MODEL
    estimates = load_estimates()
    estimates[item["code"]] = result
    _save(estimates)
    return result
