import functools
import hashlib
import os
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union

T = TypeVar("T")


def cache_to_file(
    base_dir: Union[str, Path] = ".",
    ttl: Optional[int] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    base_dir = Path(base_dir)
    base_dir.mkdir(exist_ok=True, parents=True)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def generate_cache_key(*args, **kwargs) -> str:
            key = (func.__name__, args, frozenset(kwargs.items()))
            return hashlib.md5(pickle.dumps(key)).hexdigest()  # noqa: S324

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Generate the cache file path
            cache_key = generate_cache_key(*args, **kwargs)
            cache_file = base_dir / f"{cache_key}.pkl"

            # Check if the cache file exists and if it is still valid
            if cache_file.exists():
                time_, cached = pickle.loads(cache_file.read_bytes())  # noqa: S301
                if time.time() - time_ < ttl:
                    return cached

            # Call the original function and cache the result
            result = func(*args, **kwargs)
            cache_file.write_bytes(pickle.dumps((time.time(), result)))
            return result

        return wrapper

    return decorator
