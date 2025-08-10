import pytest


class TestExample:
    @pytest.mark.asyncio
    async def test_async_example(self):
        assert True

    def test_sync_example(self):
        # A simple synchronous test
        assert 1 + 1 == 2
