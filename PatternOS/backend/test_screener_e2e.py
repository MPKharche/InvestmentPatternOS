"""End-to-end test for Custom Screener feature."""

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import ScreenerCriteria, Universe
from uuid import uuid4

client = TestClient(app)


def test_screener_e2e():
    """Test full screener flow: create, run, view results."""
    db = SessionLocal()
    try:
        # 1. Create a simple screener: RSI < 30 AND PE < 20
        screener_data = {
            "name": "Test RSI Oversold + Low PE",
            "description": "Test screener for E2E test",
            "asset_class": "equity",
            "scope": "nifty50",
            "rules": {
                "logic": "AND",
                "conditions": [
                    {"field": "rsi", "operator": "<", "value": 30},
                    {"field": "pe", "operator": "<", "value": 20},
                ],
            },
        }

        # Create screener via API
        resp = client.post("/api/v1/screener/", json=screener_data)
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        screener = resp.json()
        screener_id = screener["id"]
        print(f"✓ Created screener: {screener_id}")

        # 2. Run the screener
        run_resp = client.post(
            "/api/v1/screener/run",
            json={"screener_id": screener_id, "use_cache": False},
        )
        assert run_resp.status_code == 200, f"Run failed: {run_resp.text}"
        run = run_resp.json()
        run_id = run["run_id"]
        print(f"✓ Started run: {run_id}, status: {run['status']}")

        # 3. Check run status (should be completed since we run synchronously in test)
        status_resp = client.get(f"/api/v1/screener/run/{run_id}/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        print(
            f"✓ Run status: {status['status']}, symbols_total: {status['symbols_total']}, passed: {status['symbols_passed']}"
        )

        # 4. Get results
        results_resp = client.get(f"/api/v1/screener/{screener_id}/results?limit=100")
        assert results_resp.status_code == 200
        results = results_resp.json()
        print(f"✓ Got {len(results)} results")

        # 5. Verify results structure
        if results:
            r = results[0]
            assert "symbol" in r
            assert "passed" in r
            assert "score" in r
            assert "metrics" in r
            print(
                f"✓ Result structure valid: sample {r['symbol']} passed={r['passed']} score={r['score']}"
            )

        # 6. Cleanup: delete screener
        del_resp = client.delete(f"/api/v1/screener/{screener_id}")
        assert del_resp.status_code == 204
        print("✓ Deleted screener")

        print("\n✅ All E2E tests passed!")
        return True

    finally:
        db.close()


if __name__ == "__main__":
    try:
        test_screener_e2e()
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
