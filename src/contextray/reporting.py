from .chunking import MIN_CHUNK_SIZE


def generate_metrics_and_report(original_chunks: list[dict], optimized_chunks: list[dict]) -> dict:
    total_chars_in = sum(c["length"] for c in original_chunks)
    total_chars_out = sum(len(c["text"]) for c in optimized_chunks)
    chars_saved = total_chars_in - total_chars_out
    reduction_percentage = round(chars_saved / total_chars_in * 100, 2) if total_chars_in else 0.0

    metrics = {
        "total_chars_in": total_chars_in,
        "total_chars_out": total_chars_out,
        "chars_saved": chars_saved,
        "reduction_percentage": reduction_percentage,
        "est_tokens_in": total_chars_in / 4,
        "est_tokens_saved": chars_saved / 4,
    }

    by_key = {}
    for chunk in original_chunks:
        # Hash-None chunks (tiny) are grouped by their raw text
        key = chunk["hash"] if chunk["hash"] is not None else chunk["text"]
        by_key.setdefault(key, []).append(chunk)

    top_waste_blocks = []
    for key, duplicates in by_key.items():
        count = len(duplicates)
        if count > 1:
            top_waste_blocks.append(
                {
                    "hash": key,
                    "role": duplicates[0]["role"],
                    "count": count,
                    "chars_wasted": (count - 1) * duplicates[0]["length"],
                }
            )
    top_waste_blocks.sort(key=lambda b: (b["chars_wasted"], b["hash"]), reverse=True)
    top_waste_blocks = top_waste_blocks[:5]

    num_removed = sum(1 for c in optimized_chunks if c["action"] == "REMOVED")
    num_flagged = sum(1 for c in optimized_chunks if c["action"] == "FLAGGED_ONLY")

    role_chars = {}
    for orig_c, opt_c in zip(original_chunks, optimized_chunks):
        entry = role_chars.setdefault(orig_c["role"], {"chars_in": 0, "chars_out": 0})
        entry["chars_in"] += orig_c["length"]
        entry["chars_out"] += len(opt_c["text"])

    role_stats = []
    for role, entry in sorted(role_chars.items()):
        role_saved = entry["chars_in"] - entry["chars_out"]
        role_stats.append(
            {
                "role": role,
                "chars_in": entry["chars_in"],
                "chars_out": entry["chars_out"],
                "chars_saved": role_saved,
                "redundancy_percentage": round(role_saved / entry["chars_in"] * 100, 2) if entry["chars_in"] else 0.0,
            }
        )
    role_stats.sort(key=lambda s: (s["redundancy_percentage"], s["role"]), reverse=True)

    report_lines = [
        f"Impact: {total_chars_in} chars in -> {total_chars_out} chars out "
        f"({chars_saved} chars saved, {reduction_percentage}% reduction)",
        f"Estimated tokens (English heuristic): {metrics['est_tokens_in']} in, {metrics['est_tokens_saved']} saved",
        f"Duplicates removed: {num_removed}",
        f"Cross-role duplicates detected (not removed for safety): {num_flagged}",
        "Top waste blocks:",
    ]
    if top_waste_blocks:
        for block in top_waste_blocks:
            report_lines.append(
                f"  [{block['role']}] block {block['hash'][:12]}... "
                f"repeated {block['count']} times -> {block['chars_wasted']} chars wasted"
            )
    else:
        report_lines.append("  - none")

    report_lines.append("Per-role redundancy:")
    if role_stats:
        for stat in role_stats:
            report_lines.append(
                f"  - {stat['role']}: {stat['redundancy_percentage']}% redundant "
                f"({stat['chars_saved']} of {stat['chars_in']} chars saved)"
            )
    else:
        report_lines.append("  - none")

    report_lines.append("Safety notes:")
    report_lines.append("  - System messages preserved")
    report_lines.append("  - Cross-role duplicates not removed")
    report_lines.append("  - Code blocks protected")
    report_lines.append(f"  - Skipped optimization for chunks < {MIN_CHUNK_SIZE} chars")
    report_lines.append("Note: Only exact duplicates are optimized in this version.")

    return {
        "metrics": metrics,
        "top_waste_blocks": top_waste_blocks,
        "role_stats": role_stats,
        "report": "\n".join(report_lines),
    }