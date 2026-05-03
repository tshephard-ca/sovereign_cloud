from __future__ import annotations

from host_screen_contracts.contract_model import TransactionContract, contract_to_dict


def test_contract_model_round_trips_to_plain_dict(order_result):
    data = contract_to_dict(order_result().contract)
    loaded = TransactionContract(**data)
    assert loaded.transaction_id == "order_lookup"
    assert loaded.confidence == "HIGH"
