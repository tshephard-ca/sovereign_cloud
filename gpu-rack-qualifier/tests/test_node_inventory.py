from gpu_rack_qualifier.node_inventory import load_node_inventory


def test_loads_node_inventory(tmp_path):
    path = tmp_path / "inventory.yml"
    path.write_text("cluster_id: c1\nrack_id: r1\nnodes:\n  - name: node-a\n    expected_gpu_count: 4\n", encoding="utf-8")
    inventory = load_node_inventory(path)
    assert inventory.cluster_id == "c1"
    assert inventory.by_name()["node-a"].expected_gpu_count == 4
