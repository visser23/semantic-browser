import pytest


@pytest.mark.asyncio
async def test_attached_from_cdp_endpoint_if_feasible():
    pytest.skip("CDP endpoint integration requires externally launched Chrome with remote debugging.")
