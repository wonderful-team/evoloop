import difflib
import logging

logger = logging.getLogger(__name__)

def apply_fuzzy_patch(file_content: str, target: str, replacement: str) -> tuple[bool, str, str]:
    """
    Apply a patch fuzzily.
    Returns: (success, new_content, log_message)
    """
    if not target:
        return False, file_content, "Empty target block"
        
    # 1. Exact Match Check (Should be handled by caller usually, but good safeguard)
    if target in file_content:
        return True, file_content.replace(target, replacement), "Exact match applied"
        
    file_lines = file_content.splitlines(keepends=True)
    target_lines = target.splitlines(keepends=True)
    
    # If target is huge, fuzzy match is dangerous. Limit to e.g. 50 lines?
    # User constraint is usually small edits.
    
    # 2. Normalize Whitespace Match
    # Try to find a block where stripped lines match
    # (Implementation complexity: High without library. Using difflib is easier).
    
    s = difflib.SequenceMatcher(None, file_content, target)
    match = s.find_longest_match(0, len(file_content), 0, len(target))
    
    if match.size > 0:
        # Check if the match covers most of the target
        ratio = match.size / len(target)
        if ratio > 0.85: # Threshold
            # Found a very similar block
            start = match.a
            end = match.a + match.size
            
            # Apply replacement
            # Note: This replaces exactly the matched part. 
            # If target had 10 lines and we matched 9, we are replacing 9 lines with replacement?
            # No, usually we want to replace the whole INTENDED block.
            # Fuzzy patching is tricky.
            
            # Better Strategy: Line-based fuzzy matching
            # Find the best matching block of lines
            pass 

    # Robust Strategy: 
    # Use 'thefuzz' if available? No, stick to standard lib.
    # Logic:
    # 1. Find line in file that matches first line of target (fuzzy).
    # 2. Check subsequent lines.
    
    best_ratio = 0.0
    best_idx = -1
    
    # Heuristic: Only check if target is distinct enough (> 10 chars)
    if len(target) < 10:
        return False, file_content, "Target too short for fuzzy match"

    # Simplify: Strip all whitespace and match?
    def normalize(s): return "".join(s.split())
    
    norm_content = normalize(file_content)
    norm_target = normalize(target)
    
    if norm_target in norm_content:
        # Whitespace mismatch only!
        # We need to find WHERE it is in the original string to replace it.
        # This is hard to map back.
        pass

    # Fallback to difflib.get_close_matches logic tailored for blocks
    # Sliding window of len(target_lines)
    n_target = len(target_lines)
    if n_target == 0: return False, file_content, "Empty target lines"
    
    # This is expensive for large files (O(N*M)). 
    # Limit: if file > 20000 lines, skip fuzzy
    if len(file_lines) > 20000:
         return False, file_content, "File too large for fuzzy patch"
         
    best_score = 0
    best_start_idx = -1
    
    # Optimization: match first line first
    first_line = target_lines[0].strip()
    candidates = []
    
    for i, line in enumerate(file_lines):
        if difflib.SequenceMatcher(None, line.strip(), first_line).ratio() > 0.8:
            candidates.append(i)
            
    if not candidates:
        return False, file_content, "Could not find anchor for start line"
        
    for start_idx in candidates:
        # Check the block starting at start_idx
        end_idx = start_idx + n_target
        if end_idx > len(file_lines): continue
        
        block = "".join(file_lines[start_idx:end_idx])
        score = difflib.SequenceMatcher(None, block, target).ratio()
        
        if score > best_score:
            best_score = score
            best_start_idx = start_idx
            
    if best_score > 0.8: # Threshold
        # Construct new content
        new_lines = file_lines[:best_start_idx] + [replacement] + file_lines[best_start_idx + n_target:]
        return True, "".join(new_lines), f"Fuzzy match applied (score: {best_score:.2f})"
        
    return False, file_content, f"Best match score {best_score:.2f} too low"
