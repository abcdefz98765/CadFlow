"""CAD benchmark suite helpers."""

__all__ = ["load_benchmarks", "run_benchmark_suite"]


def __getattr__(name: str):
    if name in __all__:
        from ai_native_cad.benchmarks.runner import load_benchmarks, run_benchmark_suite

        return {
            "load_benchmarks": load_benchmarks,
            "run_benchmark_suite": run_benchmark_suite,
        }[name]
    raise AttributeError(name)
