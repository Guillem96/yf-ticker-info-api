import functools
import hashlib
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Union

from s3pathlib import S3Path

T = TypeVar("T")


def cache_to_file(
    base_dir: Union[str, Path, S3Path] = ".",
    ttl: Optional[int] = None,
    *,
    disable: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    if isinstance(base_dir, str):
        base_dir = (
            S3Path(base_dir) if base_dir.startswith("s3://") else Path(base_dir)
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if disable:
            return func

        def generate_cache_key(*args, **kwargs) -> str:
            key = f"{func.__name__}:{','.join(map(str, args))}"
            if kwargs:
                key += ":" + ",".join(
                    f"{k}={v}" for k, v in sorted(kwargs.items())
                )
            return hashlib.md5(key.encode()).hexdigest()  # noqa: S324

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not isinstance(base_dir, S3Path):
                base_dir.mkdir(exist_ok=True, parents=True)

            # Generate the cache file path
            cache_key = generate_cache_key(*args, **kwargs)
            cache_file = base_dir / f"{cache_key}.pkl"

            # Check if the cache file exists and if it is still valid
            if cache_file.exists():
                time_, cached = pickle.loads(
                    cache_file.read_bytes()
                )  # noqa: S301
                if ttl is None:
                    return cached

                if time.time() - time_ < ttl:
                    return cached

            # Call the original function and cache the result
            result = func(*args, **kwargs)
            cache_file.write_bytes(pickle.dumps((time.time(), result)))
            return result

        return wrapper

    return decorator
