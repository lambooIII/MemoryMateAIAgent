"""Small standard-library API benchmark; start the app before running it."""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def one_request(base_url: str, index: int) -> tuple[float, bool, int]:
    payload = json.dumps(
        {
            "message": "财务部有多少人？",
            "thread_id": f"benchmark-{index}",
            "user_id": "benchmark-user",
            "subject_id": "all",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=120) as response:
            response.read()
            return time.perf_counter() - started, 200 <= response.status < 300, response.status
    except HTTPError as exc:
        return time.perf_counter() - started, False, exc.code
    except URLError:
        return time.perf_counter() - started, False, 0


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(one_request, args.url, index) for index in range(args.requests)]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started
    latencies = [duration for duration, ok, _status in results if ok]
    success_count = sum(1 for _duration, ok, _status in results if ok)
    print(f"请求数: {len(results)}，并发数: {args.concurrency}")
    print(f"成功率: {success_count / len(results):.1%}" if results else "成功率: 0.0%")
    print(f"平均延迟: {statistics.mean(latencies):.3f}s" if latencies else "平均延迟: N/A")
    print(f"P50: {percentile(latencies, 0.50):.3f}s，P95: {percentile(latencies, 0.95):.3f}s")
    print(f"吞吐量: {len(results) / elapsed:.2f} req/s" if elapsed else "吞吐量: N/A")


if __name__ == "__main__":
    main()
