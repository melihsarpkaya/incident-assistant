import pytest

import ingest
from mcp_server import repository


@pytest.fixture(scope="module", autouse=True)
def database():
    ingest.build_database()


def test_lookup_known_and_unknown_error_code():
    known = repository.lookup_error_code("eft-4042")
    assert known["found"] and known["results"][0]["ref"] == "catalog:EFT-4042"
    assert repository.lookup_error_code("APP-9999") == {
        "ok": True, "results": [], "found": False, "note": "APP-9999 is not in the error code catalog."
    }


def test_search_logs_returns_line_refs():
    result = repository.search_logs("TX-20261028-0412", "eft-service")
    refs = [r["ref"] for r in result["results"]]
    assert "log:eft-service.log:4" in refs
    assert all(ref.startswith("log:eft-service.log:") for ref in refs)


def test_search_logs_unknown_service_fails():
    assert not repository.search_logs("x123", "loan-service")["ok"]


def test_search_code_and_read_file_accept_refs():
    hit = repository.search_code("checksumMatches", "eft-service")["results"][0]
    result = repository.read_file(hit["ref"], 1, 5)
    assert result["ok"] and result["results"][0]["ref"].startswith("code:eft-service/")


@pytest.mark.parametrize("path", ["../../incident_assistant/config.py", "/etc/passwd", "../seed.sql"])
def test_read_file_blocks_paths_outside_workspace(path):
    result = repository.read_file(path)
    assert not result["ok"] and "outside" in result["error"]


def test_read_file_limits_lines():
    result = repository.read_file("eft-service/src/main/java/com/demobank/eft/IbanValidator.java", 1, 10_000)
    assert len(result["results"]) <= repository.MAX_READ_LINES


def test_duplicate_card_charge_is_visible_in_transactions():
    rows = repository.get_transaction("TX-20261028-0587")["results"]
    assert [r["ref"] for r in rows] == ["txn:AUTH-88121", "txn:AUTH-88122"]


def test_transaction_query_is_parameterized():
    result = repository.get_transaction("x' OR '1'='1")
    assert result["ok"] and result["results"] == []
