"""Regressão estrutural contra as 82 operações da API anterior (2b05966)."""

import json
from pathlib import Path

from rotalog.api.main import create_app
from rotalog.core.config import Settings


def test_previous_http_contract_remains_consumable():
    schema = create_app(
        Settings(
            _env_file=None, database_url="postgresql+psycopg://localhost/rotalog_test"
        )
    ).openapi()
    previous = json.loads(
        (Path(__file__).parent / "fixtures/api_contract_2b05966.json").read_text()
    )
    assert len(previous) == 82

    def unpack(item):
        if "$ref" in item:
            return unpack(schema["components"]["schemas"][item["$ref"].split("/")[-1]])
        return item

    for key, old in previous.items():
        verb, path = key.split(" ", 1)
        assert path in schema["paths"], key
        assert verb.lower() in schema["paths"][path], key
        current = schema["paths"][path][verb.lower()]
        parameters = {
            p["in"] + ":" + p["name"]
            for p in current.get("parameters", [])
            if p.get("required")
        }
        assert parameters <= set(old["required_parameters"]), key
        content = current.get("requestBody", {}).get("content", {})
        for mime, required in old["body_required"].items():
            assert mime in content, key
            assert set(unpack(content[mime]["schema"]).get("required", [])) <= set(
                required
            ), key
        for status, fields in old["response_fields"].items():
            response = current["responses"][status]["content"]["application/json"][
                "schema"
            ]
            assert set(fields) <= set(unpack(response).get("properties", {})), key
