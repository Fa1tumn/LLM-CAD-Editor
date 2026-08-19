# Edit-Chain Benchmarks

Chains for the sequential-editing benchmark (RQ2) and the defect-injection
set for the four-stage loop's recall (RQ3 / G4).

- `chains_3step/` `chains_5step/` `chains_10step/`: each scenario is a DSL
  sequence + expected result
- `defect_injection/`: injects prior-work failure types (joint gaps,
  boundary-crossing holes, over-editing), used to measure the four-stage
  verification loop's recall

Benchmark v1 files are UTF-8 JSON objects with an ordered `steps` array and
an `expected` object. Load them with `eval.harness.load_chain()`, then pass the
result to `score_chain()`. Each step is an incremental DSL chunk and is
committed only when parsing and reference validation both succeed.
