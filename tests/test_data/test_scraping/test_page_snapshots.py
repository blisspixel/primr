"""Tests for browser render-snapshot comparison."""

from primr.data.scraping.page_snapshots import compare_render_snapshots, html_to_snapshot_text


def test_html_to_snapshot_text_removes_script_noise():
    text = html_to_snapshot_text(
        "<html><body><script>token='secret'</script><main>Real page text</main></body></html>"
    )

    assert text == "Real page text"


def test_compare_render_snapshots_detects_cleared_challenge():
    result = compare_render_snapshots(
        initial_html="<html><body>Checking your browser</body><script>window.KPSDK={}</script></html>",
        final_html="<html><body><main><h1>ExampleCo</h1><p>"
        + "Real company content with operating detail. " * 20
        + "</p></main></body></html>",
    )

    assert result is not None
    assert result.state == "cleared_challenge"
    assert "checking your browser" in result.initial_challenge_markers
    assert result.final_challenge_markers == []
    assert any(item.startswith("render_text_delta:+") for item in result.evidence)


def test_compare_render_snapshots_detects_stable_interstitial():
    result = compare_render_snapshots(
        initial_html="<html><body>Please wait while we verify your browser</body></html>",
        final_html="<html><body>Please wait while we verify your browser</body></html>",
    )

    assert result is not None
    assert result.state == "stable_interstitial"
    assert "please wait while we verify" in result.final_challenge_markers


def test_compare_render_snapshots_returns_none_without_signal():
    assert compare_render_snapshots(initial_html="", final_html="") is None
