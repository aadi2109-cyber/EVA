from eval import drills


def test_all_degradation_drills_fail_closed():
    results = drills.run_all()
    assert len(results) >= 10
    assert all(d.passed for d in results), [(d.id, d.detail) for d in results if not d.passed]
