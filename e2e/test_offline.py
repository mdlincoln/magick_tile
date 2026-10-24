"""The suite must not reach the network while it runs.

A viewer page that fetched something off the local server would make a run
depend on whatever it got, and would hide the fact that the vendored bundles are
incomplete. The interceptor that enforces this lives in the sweep fixture, so
these assertions read traffic that actually happened; the request-count check
keeps the module from passing on an empty recording.
"""

from e2e.harness import Recording


def test_no_non_local_requests(sweep_recording: Recording) -> None:
    recording = sweep_recording
    assert recording.requested, (
        f"{recording.backend} made no image requests at all, so this test could "
        "not have seen a stray one"
    )
    assert recording.blocked_requests == [], (
        f"{recording.backend} tried to reach the network: "
        f"{recording.blocked_requests[:5]}"
    )
