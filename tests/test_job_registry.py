"""
Simple verification test for JobRegistry functionality
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ofx.runner.job_registry import JobRegistry, JobEntry
from ofx.runner.base import RunnerStatus


def test_job_registry():
    """Test basic JobRegistry operations"""
    registry = JobRegistry()

    # Test 1: Registration
    entry = registry.register("job1", "Test Job 1", {"key": "value"})
    assert entry.job_id == "job1"
    assert entry.name == "Test Job 1"
    assert entry.status == RunnerStatus.IDLE
    print("✓ Job registration works")

    # Test 2: Set result
    registry.set_result("job1", True)
    assert registry.get_result("job1") == True
    print("✓ Result setting works")

    # Test 3: Error handling
    registry.register("job2", "Test Job 2", {})
    registry.set_error("job2", ValueError("test error"))
    assert registry.has_error("job2")
    assert registry.get_result("job2") == False
    assert registry.get_status("job2") == RunnerStatus.FAILED
    print("✓ Error handling works")

    # Test 4: Multiple jobs
    registry.register("job3", "Test Job 3", {})
    registry.set_result("job3", True)
    registry.update_outputs("job3", {"out": "value"}, {"step1": "done"})
    assert registry.get_status("job3") == RunnerStatus.COMPLETED
    print("✓ Output updates work")

    # Test 5: to_dict conversion
    data = registry.to_dict()
    assert "job1" in data
    assert "job2" in data
    assert "job3" in data
    assert data["job3"]["outputs"]["out"] == "value"
    print("✓ Dictionary conversion works")

    # Test 6: Batch operations
    assert registry.all_completed() == False  # job2 failed
    statuses = registry.get_job_statuses()
    assert len(statuses) == 3
    print("✓ Batch operations work")

    # Test 7: Thread-safe operations (basic check)
    assert "job1" in registry
    assert len(registry) == 3
    print("✓ Container operations work")

    print("\n✅ All JobRegistry tests passed!")


if __name__ == "__main__":
    test_job_registry()
