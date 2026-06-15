"""Test: batch builder-event overlap query."""
def test_full_id_set_query():
    all_ids = list(range(100))
    batch_size = 20
    all_batches = []
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i:i + batch_size]
        all_batches.append(batch)
    covered = set()
    for batch in all_batches:
        covered.update(batch)
    assert covered == set(all_ids)
    assert len(all_batches) == 5

def test_incomplete_query_misses_overlaps():
    all_ids = list(range(100))
    partial = set(all_ids[:50])
    full = set(all_ids)
    missed = full - partial
    assert len(missed) == 50
