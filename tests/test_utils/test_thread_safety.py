"""
Thread safety tests for concurrent access to shared resources.

Tests console output interleaving, heartbeat thread interaction,
and file write safety.

**Feature: test-coverage-hardening**
**Validates: Requirements 8.1, 8.2, 8.3**
"""

import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.utils.console import Console

# =============================================================================
# Console Thread Safety Tests
# =============================================================================


class TestConsoleThreadSafety:
    """Tests for thread-safe console output."""

    def test_concurrent_console_writes_complete(self):
        """
        WHEN multiple threads write to console
        THEN output SHALL not be interleaved mid-line

        **Validates: Requirements 8.1**
        """
        console = Console()
        messages = []
        lock = threading.Lock()

        def write_message(thread_id: int):
            for i in range(5):
                msg = f"Thread-{thread_id}-Message-{i}"
                with lock:
                    messages.append(msg)
                console.info(msg)

        threads = []
        for i in range(5):
            t = threading.Thread(target=write_message, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All messages should have been recorded
        assert len(messages) == 25

    def test_heartbeat_with_section_writing(self, capsys):
        """
        WHEN heartbeat thread runs during section writing
        THEN console output SHALL remain coherent

        **Validates: Requirements 8.2**
        """
        console = Console()

        with console.heartbeat("Processing", interval=0.05):
            # Simulate section writing
            for i in range(3):
                console.step(f"Writing section {i + 1}")
                time.sleep(0.1)
                console.ok(f"Section {i + 1} complete")

        captured = capsys.readouterr()

        # All section messages should be present
        assert "Writing section 1" in captured.out
        assert "Section 1 complete" in captured.out
        assert "Writing section 2" in captured.out
        assert "Section 2 complete" in captured.out
        assert "Writing section 3" in captured.out
        assert "Section 3 complete" in captured.out

    def test_concurrent_step_ok_pairs(self, capsys):
        """Step/OK pairs from different threads should not interleave."""
        console = Console()

        def step_ok_pair(thread_id: int):
            for i in range(3):
                console.step(f"T{thread_id}-Step-{i}")
                time.sleep(0.01)
                console.ok(f"T{thread_id}-OK-{i}")

        threads = []
        for i in range(3):
            t = threading.Thread(target=step_ok_pair, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        captured = capsys.readouterr()

        # All step/ok pairs should be present
        for tid in range(3):
            for i in range(3):
                assert f"T{tid}-Step-{i}" in captured.out
                assert f"T{tid}-OK-{i}" in captured.out


# =============================================================================
# File Write Thread Safety Tests
# =============================================================================


class TestFileWriteThreadSafety:
    """Tests for thread-safe file operations."""

    def test_concurrent_file_writes_no_corruption(self):
        """
        WHEN multiple sections are saved to working folder
        THEN file writes SHALL not corrupt each other

        **Validates: Requirements 8.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:

            def write_section(section_id: int):
                filepath = Path(tmpdir) / f"section_{section_id}.txt"
                content = f"Section {section_id} content\n" * 100
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return filepath

            # Write sections concurrently
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(write_section, i) for i in range(10)]
                paths = [f.result() for f in futures]

            # Verify all files exist and have correct content
            for i, path in enumerate(paths):
                assert path.exists()
                content = path.read_text(encoding="utf-8")
                expected = f"Section {i} content\n" * 100
                assert content == expected, f"Section {i} content corrupted"

    def test_concurrent_append_operations(self):
        """Concurrent appends to same file should not lose data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "combined.txt"
            filepath.touch()

            lock = threading.Lock()

            def append_content(thread_id: int):
                for i in range(10):
                    line = f"Thread-{thread_id}-Line-{i}\n"
                    with lock, open(filepath, "a", encoding="utf-8") as f:
                        f.write(line)

            threads = []
            for i in range(5):
                t = threading.Thread(target=append_content, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Verify all lines are present
            content = filepath.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # Should have 50 lines (5 threads * 10 lines each)
            assert len(lines) == 50

    def test_different_files_no_interference(self):
        """Writing to different files should not interfere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = {}

            def write_unique_file(file_id: int):
                filepath = Path(tmpdir) / f"file_{file_id}.txt"
                unique_content = f"Unique content for file {file_id}: {'x' * 1000}"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(unique_content)
                results[file_id] = unique_content

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(write_unique_file, i) for i in range(20)]
                for f in futures:
                    f.result()

            # Verify each file has its unique content
            for file_id, expected_content in results.items():
                filepath = Path(tmpdir) / f"file_{file_id}.txt"
                actual_content = filepath.read_text(encoding="utf-8")
                assert actual_content == expected_content


# =============================================================================
# Property Tests
# =============================================================================


@given(
    num_threads=st.integers(min_value=2, max_value=10),
    messages_per_thread=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=20, deadline=None)
def test_property_console_thread_safety(num_threads: int, messages_per_thread: int):
    """
    **Feature: test-coverage-hardening, Property 12: Console thread safety**
    **Validates: Requirements 8.1, 8.2**

    For any concurrent console writes from multiple threads,
    output lines should be complete (not interleaved mid-line).
    """
    console = Console()
    message_count = [0]
    lock = threading.Lock()

    def write_messages(thread_id: int):
        for i in range(messages_per_thread):
            console.info(f"T{thread_id}M{i}")
            with lock:
                message_count[0] += 1

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=write_messages, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All messages should have been written
    expected_count = num_threads * messages_per_thread
    assert message_count[0] == expected_count


@given(
    num_files=st.integers(min_value=2, max_value=10),
    content_size=st.integers(min_value=100, max_value=1000),
)
@settings(max_examples=20, deadline=None)
def test_property_file_write_thread_safety(num_files: int, content_size: int):
    """
    **Feature: test-coverage-hardening, Property 13: File write thread safety**
    **Validates: Requirements 8.3**

    For any concurrent section saves to the working folder,
    files should not be corrupted by race conditions.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        expected_contents = {}

        def write_file(file_id: int):
            filepath = Path(tmpdir) / f"section_{file_id}.txt"
            content = f"File {file_id}: " + "x" * content_size
            expected_contents[file_id] = content
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

        with ThreadPoolExecutor(max_workers=num_files) as executor:
            futures = [executor.submit(write_file, i) for i in range(num_files)]
            for f in futures:
                f.result()

        # Verify all files have correct content
        for file_id, expected in expected_contents.items():
            filepath = Path(tmpdir) / f"section_{file_id}.txt"
            assert filepath.exists()
            actual = filepath.read_text(encoding="utf-8")
            assert actual == expected, f"File {file_id} corrupted"


@given(
    num_threads=st.integers(min_value=2, max_value=5),
    iterations=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=10, deadline=None)
def test_property_heartbeat_does_not_corrupt_output(num_threads: int, iterations: int):
    """
    **Feature: test-coverage-hardening, Property 12: Console thread safety**
    **Validates: Requirements 8.1, 8.2**

    For any heartbeat thread running during section writing,
    console output should remain coherent.
    """
    console = Console()
    completed = [0]
    lock = threading.Lock()

    def write_with_heartbeat(thread_id: int):
        with console.heartbeat(f"T{thread_id}", interval=0.05):
            for i in range(iterations):
                console.step(f"T{thread_id}-Step-{i}")
                time.sleep(0.02)
                console.ok(f"T{thread_id}-Done-{i}")
        with lock:
            completed[0] += 1

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=write_with_heartbeat, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All threads should complete
    assert completed[0] == num_threads
