def optimize_chunks(chunks: list[dict]) -> list[dict]:
    optimized = []
    for chunk in chunks:
        action = chunk["action"]
        
        if action == "REMOVED":
            ref = chunk["duplicate_of"]
            text = f'[duplicate of chunk #{ref} removed]' if ref is not None else "[duplicate removed]"
            
            # PREVENT NEGATIVE REDUCTION: Only replace if the marker is actually smaller than the original text.
            if len(text) >= chunk["length"]:
                text = chunk["text"]
                action = "KEPT"
        else:
            text = chunk["text"]
            
        optimized.append({**chunk, "text": text, "action": action})
    return optimized