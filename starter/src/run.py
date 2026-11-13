"""Run preparation, pgvector ingestion, dev selection, fixed test and audit setup."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

from dotenv import load_dotenv

from .artifacts import ROOT, digest, load_artifacts, read_json, read_jsonl, write_json, write_jsonl
from .audits import ensure_anchors, prepare_audits, summarize_audits
from .evaluation import evaluate_query, summarize
from .store import PgVectorStore

RESULTS = ROOT / "results"


def now():
    return datetime.now(timezone(timedelta(hours=7))).isoformat()


def database_url():
    load_dotenv(ROOT / "starter/.env", override=False)
    value = os.getenv("DATABASE_URL")
    if not value:
        raise ValueError("DATABASE_URL missing; copy starter/.env.example to starter/.env")
    return value


def prepare(rebuild=False):
    if rebuild or not (RESULTS / "embedding_run.json").exists():
        commands = [["-m", "src.ingestion"], ["scripts/audit_corpus.py"],
                    ["scripts/prepare_benchmark.py"], ["scripts/build_chunks.py"],
                    ["scripts/build_embeddings.py"]]
        for command in commands:
            subprocess.run([sys.executable, *command], cwd=ROOT / "starter", check=True)
    context = load_artifacts()
    ensure_anchors(context)
    print("Preparation verified: 46 pages, A/B/C chunks and real cached document/query vectors")
    return context


def ingest(context):
    report = {"fingerprint": context["fingerprint"], "recorded_at": now(), "strategies": {}}
    with PgVectorStore(database_url(), context["model"]["dimensions"]) as store:
        store.create_schema()
        report["backend"] = store.backend_info()
        for strategy in context["strategies"]:
            started = time.perf_counter()
            store.upsert(strategy, context["chunks"][strategy], context["vectors"][strategy].tolist(),
                         manifest=context["snapshots"][strategy])
            elapsed = time.perf_counter() - started
            first_count = store.count(strategy)
            store.upsert(strategy, context["chunks"][strategy], context["vectors"][strategy].tolist(),
                         manifest=context["snapshots"][strategy])
            if store.count(strategy) != first_count or first_count != len(context["chunks"][strategy]):
                raise ValueError("Re-ingestion changed row count or created duplicates")
            report["strategies"][strategy] = {"rows": first_count, "first_upsert_seconds": round(elapsed, 6),
                                               "reload_row_count": store.count(strategy), "idempotent": True}
            print(f"Stored {strategy}: {first_count} rows; reload unchanged")
    with PgVectorStore(database_url(), context["model"]["dimensions"]) as store:
        for name in context["strategies"]:
            if store.count(name) != report["strategies"][name]["rows"] or store.snapshot(name) != context["snapshots"][name]:
                raise ValueError("Database reconnect/snapshot validation failed")
    report["reconnect_verified"] = True
    report["timing_scope"] = "Cached-vector validation/conversion and first PostgreSQL snapshot transaction; same procedure per strategy; no embedding/model load"
    write_json(RESULTS / "store_run.json", report)


def _trace_path(split, strategy):
    return RESULTS / f"traces/{split}_{strategy}.jsonl"


def _traces(context, split):
    traces = []
    for strategy in context["strategies"]:
        for trace in read_jsonl(_trace_path(split, strategy)):
            if trace["fingerprint"] != context["fingerprint"]:
                raise ValueError("Trace belongs to another configuration")
            traces.append(trace)
    return traces


def _search_split(context, split):
    traces = []
    with PgVectorStore(database_url(), context["model"]["dimensions"]) as store:
        for strategy, config in context["strategies"].items():
            if store.snapshot(strategy) != context["snapshots"][strategy]:
                raise ValueError(f"Database is stale for {strategy}; run ingest")
            cases = []
            for question in context["questions"][split]:
                filters = question.get("filter", {}) if config["metadata_filter"] else {}
                started = time.perf_counter()
                hits = store.search(strategy, context["query_vectors"][question["id"]].tolist(), filters=filters)
                seconds = time.perf_counter() - started
                if filters and not all(all(hit["metadata"].get(k) == v for k, v in filters.items()) for hit in hits):
                    raise ValueError("Backend returned a result outside the applied filter")
                trace = evaluate_query(question, hits)
                trace.update({"strategy": strategy, "fingerprint": context["fingerprint"],
                              "applied_filter": filters, "search_seconds": seconds, "recorded_at": now()})
                cases.append(trace)
            write_jsonl(_trace_path(split, strategy), cases)
            traces.extend(cases)
    return traces


def _write_metrics(context):
    traces = []
    for split in ["dev", "test"]:
        if all(_trace_path(split, name).exists() for name in context["strategies"]):
            candidate = [row for name in context["strategies"] for row in read_jsonl(_trace_path(split, name))]
            if all(row["fingerprint"] == context["fingerprint"] for row in candidate):
                traces.extend(candidate)
    summary = summarize(traces)
    write_json(RESULTS / "retrieval_metrics.json", summary)
    rows = summary["rows"]
    with (RESULTS / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for strategy in context["strategies"]:
        write_jsonl(RESULTS / f"traces_{strategy}.jsonl", [t for t in traces if t["strategy"] == strategy])
    path = ROOT / "artifacts/experiment_log.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, experiments = reader.fieldnames, list(reader)
    for experiment in experiments:
        for row in rows:
            if experiment["strategy"] == row["strategy"]:
                experiment[f"{row['split']}_hit1"] = row["hit_at_1_fraction"]
                experiment[f"{row['split']}_hit3"] = row["evidence_hit_at_3_fraction"]
                experiment["notes"] = experiment["notes"].replace("retrieval not run", "retrieval results in results/metrics.csv")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(experiments)
    return rows


def run_dev(context):
    selection_path = RESULTS / "selection.json"
    if selection_path.exists():
        selection = read_json(selection_path)
        if selection["fingerprint"] == context["fingerprint"]:
            for relative, expected in selection["dev_trace_sha256"].items():
                if digest(ROOT / relative) != expected:
                    raise ValueError("Selected dev traces changed; retain original selection provenance")
            print(f"Reusing fixed dev selection: {selection['selected_strategy']}")
            return selection
    traces = _search_split(context, "dev")
    rows = summarize(traces)["rows"]
    store_run = read_json(RESULTS / "store_run.json")
    if store_run["fingerprint"] != context["fingerprint"]:
        raise ValueError("Store timing report belongs to another experiment")
    ranking = sorted(rows, key=lambda row: (-row["evidence_hit_at_3"], -row["hit_at_1"],
                     store_run["strategies"][row["strategy"]]["first_upsert_seconds"],
                     len(context["chunks"][row["strategy"]]), row["strategy"]))
    prior = read_json(RESULTS / "test_exposure.json") if (RESULTS / "test_exposure.json").exists() else []
    selection = {"fingerprint": context["fingerprint"], "selected_at": now(),
                 "selected_strategy": ranking[0]["strategy"], "test_used_for_selection": False,
                 "prior_test_exposure_exists": bool(prior), "dev_ranking": ranking,
                 "selection_rule": read_json(ROOT / "benchmark/protocol.json")["dev_selection_rule_before_test"],
                 "timing_definition": store_run["timing_scope"],
                 "ingest_timings_at_selection": store_run["strategies"],
                 "ingest_report_sha256_at_selection": digest(RESULTS / "store_run.json"),
                 "dev_trace_sha256": {_trace_path("dev", name).relative_to(ROOT).as_posix(): digest(_trace_path("dev", name))
                                      for name in context["strategies"]}}
    write_json(selection_path, selection)  # Persist the choice BEFORE any test search.
    _write_metrics(context)
    print(f"Dev selected {selection['selected_strategy']}; test not used for this choice")
    return selection


def run_test(context):
    selection_path = RESULTS / "selection.json"
    if not selection_path.exists():
        raise ValueError("Run dev and fix the selection before evaluating test")
    selection = read_json(selection_path)
    if selection["fingerprint"] != context["fingerprint"]:
        raise ValueError("Configuration changed after dev selection")
    for relative, expected in selection["dev_trace_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Dev results changed after selection")
    exposure_path = RESULTS / "test_exposure.json"
    exposures = read_json(exposure_path) if exposure_path.exists() else []
    prior_other = any(e["fingerprint"] != context["fingerprint"] for e in exposures)
    replay = any(e["fingerprint"] == context["fingerprint"] for e in exposures)
    status = ("not_independent_after_pipeline_change" if prior_other else
              "replay_of_fixed_configuration" if replay else "initial_holdout_on_fixed_configuration")
    # Record exposure before searching, including partial runs that may fail.
    exposures.append({"fingerprint": context["fingerprint"], "started_at": now(),
                      "selected_strategy": selection["selected_strategy"], "holdout_status": status,
                      "selection_sha256": digest(selection_path)})
    write_json(exposure_path, exposures)
    traces = _search_split(context, "test")
    _write_metrics(context)
    write_json(RESULTS / "test_run.json", {"fingerprint": context["fingerprint"], "completed_at": now(),
               "holdout_status": status, "selected_strategy_before_test": selection["selected_strategy"]})
    print(f"Test completed: {status}; no parameter tuning performed")
    return traces


def write_summary(context):
    rows = _write_metrics(context)
    selection = read_json(RESULTS / "selection.json")
    lines = ["# Kết quả pipeline", "", f"Cấu hình chọn trên dev: **{selection['selected_strategy']}**.", "",
             "| Strategy | Split | Hit@1 | Evidence Hit@3 |", "|---|---|---|---|"]
    lines.extend(f"| {r['strategy']} | {r['split']} | {r['hit_at_1_fraction']} | {r['evidence_hit_at_3_fraction']} |" for r in rows)
    lines.extend(["", "Đây là metric tự động theo full gold evidence containment, không phải nhãn coherence/grounding hay độ chính xác câu trả lời LLM.",
                  "", "Nhãn thủ công cần điền ở results/audit/, sau đó chạy `python -m src.run audit-summary`.",
                  "Thông tin học viên và báo cáo cá nhân vẫn cần hoàn thiện."])
    (RESULTS / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "prepare", "ingest", "dev", "test", "audit", "audit-summary", "query"])
    parser.add_argument("--rebuild", action="store_true", help="Rebuild text/chunks/embeddings in prepare/all; never regenerate gold")
    parser.add_argument("--question", help="Question text for an interactive query")
    parser.add_argument("--strategy", default="C", choices=["A", "B", "C"])
    parser.add_argument("--section", help="Optional user-provided section for strategy C")
    args = parser.parse_args()
    context = prepare(args.rebuild) if args.command in {"all", "prepare"} else load_artifacts()
    if args.command in {"all", "ingest"}:
        ensure_anchors(context)
        ingest(context)
    if args.command in {"all", "dev"}:
        run_dev(context)
    if args.command in {"all", "test"}:
        run_test(context)
    if args.command in {"all", "audit"}:
        quality = prepare_audits(context, _traces(context, "test"))
        print(f"Manual audit complete: {quality['manual_review_complete']} (blank labels are never invented)")
        write_summary(context)
    if args.command == "audit-summary":
        print(summarize_audits(context))
    if args.command == "query":
        if not args.question:
            parser.error("query requires --question")
        if args.section and args.strategy != "C":
            parser.error("--section applies only to strategy C")
        from .embeddings import MyEmbedder
        vector = MyEmbedder(context["model"]["model_name"]).embed_query(args.question)
        filters = {"section": args.section} if args.section else {}
        with PgVectorStore(database_url(), context["model"]["dimensions"]) as store:
            if store.snapshot(args.strategy) != context["snapshots"][args.strategy]:
                raise ValueError("Database snapshot is stale; run ingest")
            for rank, hit in enumerate(store.search(args.strategy, vector, filters=filters), 1):
                print(f"\n#{rank} score={hit['score']:.6f} {hit['document_id']} page={hit['page']} "
                      f"section={hit['metadata']['section']}\n{hit['text']}")


if __name__ == "__main__":
    main()
