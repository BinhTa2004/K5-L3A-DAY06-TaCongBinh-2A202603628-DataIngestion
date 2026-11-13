"""Author once, then verify the frozen dev/test evidence against the local corpus.

Run with --write for initial materialization. Existing changed files are never
silently overwritten. Default mode validates data and the frozen SHA-256 hashes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
D = "gs_driving_review"
G = "gs_general_survey"


def item(number, question, answer, topic, evidence, *, split="dev", filters=None):
    return {"id": f"{split}{number:02d}", "split": split, "question": question,
            "expected_answer": answer, "topic": topic,
            "evidence_selectors": evidence, "filter": filters or {}}


# Selectors locate verbatim source text; they are never used as retrieval queries.
SPECS = [
    item(1, "Vì sao các kỹ thuật tái dựng chủ động gặp khó khăn khi áp dụng cho cảnh ngoài trời?",
         "Chi phí thiết bị cao, tốc độ phát hiện chậm và khả năng khái quát của thuật toán kém.",
         "active_reconstruction_limits", [(D, 2, "Among the 3D scene reconstruction methods", "(Zhou et al. 2024a).")]),
    item(2, "Trong binocular stereo vision (BSV), nguyên lý nào được dùng để suy ra độ sâu và tái dựng 3D?",
         "Nguyên lý tam giác đạc (triangulation).", "stereo_depth",
         [(D, 5, "Then, BSV uses the principle", "three-dimensional reconstruction.")]),
    item(3, "Hạn chế về tài nguyên và thời gian nào của NeRF gây khó khăn cho các ứng dụng cần phản hồi nhanh?",
         "NeRF tốn tài nguyên tính toán khi huấn luyện và rendering, với thời gian huấn luyện/rendering lớn hoặc rendering chậm.",
         "nerf_compute_limits", [(D, 2, "Nonetheless, NeRF models", "(Zhu et al. 2023a)."),
                                 (G, 2, "i) Computational Intensity.", "outputs.")]),
    item(4, "Đám mây điểm thưa dùng để khởi tạo các Gaussian trong 3D GS có thể được tạo bởi kỹ thuật nào?",
         "Structure from Motion (SfM).", "sfm_initialization",
         [(D, 11, "In the 3D Gaussian representation module", "3D Gaussians set."),
          (G, 8, "3D GS starts with the initial set of sparse points", "initialization.")]),
    item(5, "Các hệ số spherical harmonics giúp biểu diễn màu phụ thuộc góc nhìn như thế nào?",
         "Chúng mô hình hóa màu/diện mạo phụ thuộc hướng nhìn, cho phép màu thay đổi theo góc quan sát thay vì một giá trị RGB cố định.",
         "view_dependent_color", [(G, 5, "𝑐 is represented by spherical harmonics (SH) coefficients", "viewing angle."),
                                  (G, 4, "one is directly storing coefficients of directional basis functions", "the viewing direction.")]),
    item(6, "Trong bước densification, Gaussian nhỏ ở vùng tái dựng thiếu và Gaussian lớn ở vùng tái dựng thừa được xử lý khác nhau thế nào?",
         "Clone Gaussian nhỏ ở vùng under-reconstructed; split Gaussian lớn ở vùng over-reconstructed.",
         "density_clone_split", [(G, 8, "It involves either cloning small Gaussians", "over-reconstructed regions.")]),
    item(7, "Thay vì tối ưu trực tiếp ma trận hiệp phương sai, 3D GS tối ưu hai đại lượng nào biểu diễn phép quay và tỉ lệ?",
         "Quaternion q cho phép quay và vector 3D s cho tỉ lệ.", "covariance_parameters",
         [(G, 7, "3D GS chooses to optimize a quaternion", "respectively.")]),
    item(8, "Point pruning loại bỏ những Gaussian nào theo opacity và kích thước?",
         "Gaussian gần như trong suốt có alpha dưới ngưỡng, và Gaussian quá lớn trong world-space hoặc view-space.",
         "pruning_conditions", [(G, 8, "It is executed by eliminating Gaussians", "world-space or view-space.")]),
    item(9, "Positional Encoding và Hierarchical Volume Sampling của NeRF lần lượt giúp cải thiện điều gì?",
         "Positional Encoding giúp biểu diễn chi tiết tần số cao; Hierarchical Volume Sampling cải thiện hiệu quả rendering.",
         "nerf_pec_hvs", [(D, 6, "NeRF introduces two", "image rendering efficiency.")]),
    item(10, "Explicit radiance field có lợi thế truy cập và đánh đổi về bộ nhớ/độ phân giải nào?",
         "Cho phép truy cập dữ liệu radiance trực tiếp và thường nhanh hơn, đổi lại bộ nhớ cao hơn và có thể có độ phân giải thấp hơn.",
         "explicit_field_tradeoff", [(G, 3, "An explicit radiance field directly represents", "potentially lower resolution.")]),
    item(11, "Trong mục Main modules, mô hình 3D GS gốc gồm ba module chính nào?",
         "3D Gaussian representation, attribute optimization và real-time rendering.", "original_modules",
         [(D, 11, "The original 3D GS model based on three main modules:", "attribute optimization, and real-time rendering.")],
         filters={"section": "Main modules"}),
    item(12, "Trong mục Memory-efficient 3D GS, hai hướng chính để giảm nhu cầu bộ nhớ là gì và chúng có thể kết hợp không?",
         "Giảm số lượng Gaussian và nén các thuộc tính Gaussian. Hai hướng không loại trừ nhau, có thể kết hợp trong một framework.",
         "memory_compression_directions", [(G, 9, "Recent research has pursued two primary directions", "hybrid approach combining multiple strategies.")],
         filters={"section": "Memory-efficient 3D GS"}),
    item(13, "Trong mục 3D GS for Sparse Input, đánh đổi giữa regularization-based và generalizability-based methods là gì?",
         "Regularization-based dùng ràng buộc mạnh và tối ưu theo cảnh, ưu tiên chất lượng hình học nhưng tốn tính toán; generalizability-based dùng learned priors để suy luận feed-forward nhanh và khái quát qua cảnh, đôi khi giảm độ trung thực hình học.",
         "sparse_input_tradeoff", [(G, 9, "In practice, there is a trade-off between regularization-based", "geometric fidelity).")],
         filters={"section": "3D GS for Sparse Input"}),
    item(14, "Deformable 3D Gaussians kết hợp canonical space với cấu trúc nào để mô hình hóa động lực không gian-thời gian?",
         "Các Gaussian được học trong canonical space, kết hợp deformation field là một spatial MLP để mô hình hóa động lực không gian-thời gian.",
         "deformation_representation", [(G, 12, "The deformable 3D Gaussians are learned in a canonical space", "spatial-temporal dynamics.")]),
    item(15, "Các hướng COLMAP-free thay sự phụ thuộc vào SfM tính trước bằng cách tối ưu đồng thời những gì?",
         "Đồng thời tối ưu camera poses và các tham số Gaussian theo cách offline/batch.",
         "pose_free_optimization", [(G, 11, "This line of work removes the dependency", "in an offline/batch manner.")]),
    item(1, "Để mở rộng 3D GS sang cảnh động, vì sao cần mô hình hóa thêm chiều thời gian?",
         "Để biểu diễn sự thay đổi của cảnh hoặc vật thể theo thời gian và nắm bắt động lực chuyển động.",
         "dynamic_temporal_dimension", [(G, 14, "The key to adapt 3D GS to dynamic scenes", "scenes that change over time."),
                                        (D, 24, "4D scene reconstruction techniques require", "moving objects.")], split="test"),
    item(2, "Trong mục Vehicle navigation, GaussNav sử dụng ba giai đoạn chính nào?",
         "Sub-Gaussian segmentation, semantic Gaussian construction và Gaussian navigation.",
         "gaussnav_stages", [(D, 26, "GaussNav uses the three main phases", "improve the performance.")],
         split="test", filters={"section": "Vehicle navigation"}),
    item(3, "Trong mục Simultaneous localization and mapping, SplaTAM đơn giản hóa màu và phân bố Gaussian như thế nào?",
         "Chỉ dùng màu không phụ thuộc góc nhìn và làm phân bố Gaussian đẳng hướng (isotropic).",
         "splatam_simplifications", [(D, 20, "SplaTAM streamlines the architecture", "isotropic.")],
         split="test", filters={"section": "Simultaneous localization and mapping"}),
    item(4, "PhysGaussian gắn mô phỏng cơ học vào loại biểu diễn cảnh nào?",
         "Biểu diễn bằng các Gaussian 3D (Gaussian bodies), được dùng để gắn trạng thái cơ học với biểu diễn/rendering cảnh.",
         "physgaussian_representation", [(G, 18, "In PhysGaussian [272], for instance,", "exactly what is rendered."),
                                           (D, 26, "PhysGaussian employs a particular material-pointing method", "Gaussian body,")], split="test"),
    item(5, "Benchmark tái dựng cảnh phẫu thuật sử dụng ba chỉ số chất lượng hình ảnh nào?",
         "PSNR, SSIM và LPIPS.", "surgical_metrics",
         [(G, 21, "• Evaluation Metric: PSNR, SSIM", "adopted for evaluation.")], split="test"),
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def locate(text, beginning, ending):
    """Whitespace-insensitive selector -> exact original character interval."""
    flattened, offsets = [], []
    for token in re.finditer(r"\S+", text):
        if flattened:
            flattened.append(" ")
            offsets.append(token.start())
        flattened.extend(token.group())
        offsets.extend(range(token.start(), token.end()))
    flat = "".join(flattened)
    beginning, ending = " ".join(beginning.split()), " ".join(ending.split())
    start = flat.find(beginning)
    require(start >= 0, f"Missing evidence start: {beginning}")
    require(flat.find(beginning, start + 1) < 0, f"Ambiguous evidence start: {beginning}")
    end = flat.find(ending, start + len(beginning))
    require(end >= 0, f"Missing evidence end: {ending}")
    return offsets[start], offsets[end + len(ending) - 1] + 1


def materialize(pages):
    questions = []
    for spec in SPECS:
        question = {k: v for k, v in spec.items() if k != "evidence_selectors"}
        gold = []
        for document_id, page, beginning, ending in spec["evidence_selectors"]:
            record = pages[document_id, page]
            start, end = locate(record["text"], beginning, ending)
            spans = [s for s in record["metadata"]["section_spans"]
                     if s["start"] <= start and end <= s["end"]]
            require(len(spans) == 1, f"Evidence crosses section boundary: {spec['id']}")
            gold.append({"gold_source_id": document_id, "gold_page": page,
                         "evidence_quote": record["text"][start:end],
                         "evidence_start": start, "evidence_end": end,
                         "section": spans[0]["section"]})
        question.update({key: gold[0][key] for key in
                         ["gold_source_id", "gold_page", "evidence_quote"]})
        question["gold_evidence"] = gold
        question["evidence_verification"] = {
            "method": "Exact normalized local-PDF page substring with offsets; semantic answer/support reviewed by Codex AI assistant.",
            "student_review_status": "not claimed",
        }
        questions.append(question)
    return questions


def validate(questions, pages):
    counts = Counter(q["split"] for q in questions)
    require(counts == {"dev": 15, "test": 5}, "Expected 15 dev / 5 test")
    require(len({q["id"] for q in questions}) == 20, "Duplicate question IDs")
    require(len({q["question"] for q in questions}) == 20, "Duplicate question text")
    require(len({q["topic"] for q in questions}) == 20, "Duplicate topic labels")
    filter_count = 0
    test_filter_count = 0
    alternative_count = 0
    quote_count = 0
    lengths = []
    details = []
    split_gold_pages = {"dev": set(), "test": set()}
    for q in questions:
        require(bool(q["expected_answer"].strip()), f"Missing answer: {q['id']}")
        require(q["id"].startswith(q["split"]), "ID/split mismatch")
        require(set(q["filter"]) <= {"section"}, "Unapproved filter field")
        require(all(field in q for field in
                    ["gold_source_id", "gold_page", "evidence_quote"]), "Missing primary gold")
        primary = q["gold_evidence"][0]
        require(all(q[k] == primary[k] for k in
                    ["gold_source_id", "gold_page", "evidence_quote"]), "Primary gold mismatch")
        if q["filter"]:
            filter_count += 1
            test_filter_count += int(q["split"] == "test")
            require(q["filter"]["section"] in q["question"], "Filter not supplied in question")
        alternative_count += int(len(q["gold_evidence"]) > 1)
        for evidence in q["gold_evidence"]:
            split_gold_pages[q["split"]].add((evidence["gold_source_id"], evidence["gold_page"]))
            record = pages[evidence["gold_source_id"], evidence["gold_page"]]
            start, end = evidence["evidence_start"], evidence["evidence_end"]
            require(0 <= start < end <= len(record["text"]), "Invalid gold offsets")
            require(record["text"][start:end] == evidence["evidence_quote"], "Evidence mismatch")
            require(any(s["start"] <= start and end <= s["end"] and
                        s["section"] == evidence["section"] for s in
                        record["metadata"]["section_spans"]), "Evidence outside claimed section")
            if q["filter"]:
                require(evidence["section"] == q["filter"]["section"], "Gold violates query filter")
            quote_count += 1
            lengths.append(len(evidence["evidence_quote"]))
        details.append({"id": q["id"], "split": q["split"], "filter": q["filter"],
                        "gold_count": len(q["gold_evidence"]),
                        "primary_quote_characters": len(q["evidence_quote"]), "status": "pass"})
    require(filter_count >= 3 and test_filter_count >= 1, "Insufficient filter coverage")
    require(not split_gold_pages["dev"] & split_gold_pages["test"], "Gold page overlap between dev and test")
    return {"status": "pass", "questions": len(questions), "split_counts": dict(counts),
            "filter_questions": filter_count, "test_filter_questions": test_filter_count,
            "questions_with_alternative_evidence": alternative_count,
            "verified_evidence_passages": quote_count,
            "evidence_length_characters": {"minimum": min(lengths), "maximum": max(lengths)},
            "semantic_reviewer": "Codex AI assistant; not a claim of student/human review",
            "gold_pages_disjoint_between_splits": True,
            "retrieval_executed_by_this_script": False, "details": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Materialize only if files are absent or unchanged")
    args = parser.parse_args()
    page_file = ROOT / "data/processed/pages.jsonl"
    rows = [json.loads(line) for line in page_file.read_text(encoding="utf-8").splitlines()]
    pages = {(r["document_id"], r["page"]): r for r in rows}
    folder = ROOT / "benchmark"
    folder.mkdir(exist_ok=True)
    files = [folder / "dev.json", folder / "test.json"]
    lock_file = folder / "lock.json"
    if args.write:
        questions = materialize(pages)
        validate(questions, pages)
        outputs = [(path, encode([q for q in questions if q["split"] == split]))
                   for path, split in zip(files, ["dev", "test"])]
        for path, content in outputs:
            require(not path.exists() or path.read_text(encoding="utf-8") == content,
                    f"Refusing to replace changed benchmark: {path}")
        if lock_file.exists():
            existing = json.loads(lock_file.read_text(encoding="utf-8"))
            for relative, expected in existing["sha256"].items():
                require(sha256(ROOT / relative) == expected, f"Frozen input changed: {relative}")
        for path, content in outputs:
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        if not lock_file.exists():
            tracked = files + [page_file, ROOT / "data/processed/sections.jsonl",
                               ROOT / "data/section_boundaries.json", ROOT / "data/manifest.json",
                               folder / "protocol.json", folder / "README.md"]
            lock = {"schema_version": 1, "benchmark_version": "gs-benchmark-v1",
                    "frozen_on": "2026-11-13", "timezone": "Asia/Barnaul",
                    "frozen_before_retrieval": True,
                    "sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in tracked}}
            lock_file.write_text(encode(lock), encoding="utf-8")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    for relative, expected in lock["sha256"].items():
        require(sha256(ROOT / relative) == expected, f"Frozen input changed: {relative}")
    questions = []
    for path, split in zip(files, ["dev", "test"]):
        subset = json.loads(path.read_text(encoding="utf-8"))
        require(all(q["split"] == split for q in subset), "Question in wrong split file")
        questions.extend(subset)
    result = validate(questions, pages)
    (ROOT / "results/benchmark_checks.json").write_text(encode(result), encoding="utf-8")
    print(f"PASS: {result['questions']} questions, {result['split_counts']}, "
          f"{result['filter_questions']} filters ({result['test_filter_questions']} test), "
          f"{result['verified_evidence_passages']} exact evidence passages")


if __name__ == "__main__":
    main()
