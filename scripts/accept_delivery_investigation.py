"""Exercise the public 66823 complaint via local SGLang and the AG-UI endpoint."""

import tempfile
from pathlib import Path

from accept_guardrails import _run_case
from fastapi.testclient import TestClient

from operion_etl.agent_app import AgentApplication, create_app
from operion_etl.agent_runtime import AgentSettings
from operion_etl.read_tools import AccessScope, CanonicalRepository
from operion_etl.session_store import ConversationStore


def main():
    with tempfile.TemporaryDirectory() as temp:
        store = ConversationStore(Path(temp) / "sessions.db")
        app = AgentApplication(
            settings=AgentSettings.from_environment(),
            repository=CanonicalRepository(Path("data/canonical/demo-wwi-v1")),
            scope=AccessScope(
                "AI Demo GmbH", frozenset({"wwi:organization:customer:65"})
            ),
            store=store,
            token="local-guardrail-acceptance",
            user_id="guardrail-acceptance",
        )
        with TestClient(create_app(app)) as client:
            result = _run_case(
                client,
                store,
                name="delivery-66823",
                question="Investigate order 66823. Our warehouse says nothing arrived on the 18th. Was it late and did all 48 units arrive? Prepare an investigation card in English.",
            )
        print(result["run_status"], result["tool_names"], result["error_code"])
        print(result["answer"])
        assert result["run_status"] == "succeeded"
        assert "get_order_delivery_evidence" in result["tool_names"]
        assert all(
            token in result["answer"]
            for token in (
                "64067",
                "2016-02-19",
                "after expected date",
                "Not established",
                "Next: verify",
            )
        )


if __name__ == "__main__":
    main()
