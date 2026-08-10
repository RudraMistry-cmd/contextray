def detect_duplicates(chunks: list[dict]) -> list[dict]:
    global_seen_hashes: dict[str, int] = {}  # dedup key → first chunk id
    role_seen_hashes: dict[str, set[str]] = {}  # role → set of dedup keys

    updated = []

    for chunk in chunks:
        role = chunk["role"]
        # Tiny chunks carry no hash (see chunk_and_hash): dedupe them by raw text
        # so repetition like "ok" / "ok" / "ok" stays visible. Detection covers ALL chunks.
        dedup_key = chunk["hash"] if chunk["hash"] is not None else chunk["text"]

        # Ensure role set exists
        if role not in role_seen_hashes:
            role_seen_hashes[role] = set()

        # SYSTEM ROLE → always keep
        if role == "system":
            updated.append({
                **chunk,
                "action": "KEPT",
                "duplicate_of": None
            })
            continue

        seen_in_role = dedup_key in role_seen_hashes[role]
        seen_globally = dedup_key in global_seen_hashes

        if seen_in_role:
            action = "REMOVED"
            duplicate_of = global_seen_hashes[dedup_key]

        elif seen_globally:
            action = "FLAGGED_ONLY"
            duplicate_of = global_seen_hashes[dedup_key]

        else:
            action = "KEPT"
            duplicate_of = None

            # Store first occurrence
            global_seen_hashes[dedup_key] = chunk["id"]
            role_seen_hashes[role].add(dedup_key)

        updated.append({
            **chunk,
            "action": action,
            "duplicate_of": duplicate_of
        })

    return updated