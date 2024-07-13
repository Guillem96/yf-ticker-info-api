import random
import time

from py import path

from ticker_info.utils import cache_to_file


def test_disk_cache(tmpdir: path.local) -> None:
    @cache_to_file(str(tmpdir))
    def inspector() -> float:
        return random.random()  # noqa: S311

    # All results are the same because cache is
    assert all(inspector() == inspector() for _ in range(10))


def test_disk_cache_ttl(tmpdir: path.local) -> None:
    @cache_to_file(str(tmpdir), ttl=1)
    def inspector() -> float:
        return random.random()  # noqa: S311

    results = []
    for _ in range(3):
        time.sleep(0.5)  # simulate large period of time to reach ttl
        results.append(inspector())

    assert any(results[0] != r for r in results[1:])
