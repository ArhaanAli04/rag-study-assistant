#query decomposition for multi-part questions
from typing import List
import re


class QueryDecomposer:
    """
    Very simple heuristic decomposer.
    Splits on 'and', question marks, or numbered lists.
    """

    def decompose(self, query: str) -> List[str]:
        q = query.strip()
        if not q:
            return []

        # If there's only one question mark and no obvious 'and', treat as single.
        if q.count("?") <= 1 and " and " not in q.lower():
            return [q]

        # Split on '?' and ' and ' heuristically.
        parts = re.split(r"\?|\band\b", q, flags=re.IGNORECASE)
        subqs: List[str] = []
        for p in parts:
            p = p.strip(" .;,\n\t")
            if not p:
                continue
            # Re-add '?' if it looked like a question prefix.
            if not p.endswith("?"):
                p += "?"
            subqs.append(p)

        # Fallback to original if everything got too fragmented.
        if not subqs:
            return [q]
        return subqs
