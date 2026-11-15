"""
Concept Extractor for Concept Map Generation
Uses LLM (Gemini) to extract concepts and relationships from hybrid context
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from google import genai  # [web:91][web:94]
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

MAX_DOCUMENT_BLOCKS = 10
MAX_WEB_BLOCKS = 8
# Shown in the node details as "<file> — p. <page>"; ConceptNodeDetails.js splits on it.
PAGE_SEPARATOR = " — p. "
_EVIDENCE_ID = re.compile(r"^\[?\s*([DW]\d+)\s*\]?$", re.IGNORECASE)


def document_label(metadata: Dict[str, Any]) -> str:
    file_name = metadata.get("file_name") or "Unknown document"
    page = metadata.get("page_num")
    return f"{file_name}{PAGE_SEPARATOR}{page}" if page is not None else file_name


class Evidence:
    """The numbered context blocks the model may cite: id → (kind, display label)."""

    def __init__(self) -> None:
        self.blocks: Dict[str, Tuple[str, str]] = {}

    def add(self, evidence_id: str, kind: str, label: str) -> None:
        self.blocks[evidence_id] = (kind, label)

    def resolve(self, raw_ids: Any) -> Tuple[str, List[str]]:
        """Map the model's cited ids to (source_type, labels); ids that weren't in the context are dropped."""
        if not isinstance(raw_ids, list):
            return "unknown", []
        kinds: List[str] = []
        labels: List[str] = []
        for raw in raw_ids:
            match = _EVIDENCE_ID.match(str(raw).strip())
            block = self.blocks.get(match.group(1).upper()) if match else None
            if block is None:
                continue
            kind, label = block
            if kind not in kinds:
                kinds.append(kind)
            if label not in labels:
                labels.append(label)
        if not kinds:
            return "unknown", []
        return ("both" if len(kinds) > 1 else kinds[0]), labels


class ConceptExtractor:
    """
    Extracts structured concepts and relationships from text using LLM
    Generates concept maps with proper source attribution
    """

    def __init__(self, client: genai.Client, model_name: str) -> None:
        self.client = client
        self.model_name = model_name

    def build_context(self, retrieval_result: Dict[str, Any]) -> Tuple[str, Evidence]:
        """Number every block ([D1] notes.pdf — p. 4, [W1] title (url)) so the model cites ids, not names.

        A free-written source can name a file that was never retrieved; an id either resolves to a
        block that was in the context or is dropped.
        """
        evidence = Evidence()
        parts: List[str] = []

        doc_results = retrieval_result.get("document_results", [])[:MAX_DOCUMENT_BLOCKS]
        if doc_results:
            parts.append("## From Documents:\n")
            for i, result in enumerate(doc_results, 1):
                label = document_label(result.get("metadata", {}))
                evidence.add(f"D{i}", "document", label)
                parts.append(f"\n[D{i}] {label}:")
                parts.append(result.get("text", ""))

        web_results = retrieval_result.get("web_results", [])[:MAX_WEB_BLOCKS]
        if web_results:
            parts.append("\n\n## From Web:\n")
            for i, result in enumerate(web_results, 1):
                metadata = result.get("metadata", {})
                url = metadata.get("url") or "N/A"
                evidence.add(f"W{i}", "web", url)
                parts.append(f"\n[W{i}] {metadata.get('title', 'Unknown')} ({url}):")
                parts.append(result.get("text", ""))

        return "\n".join(parts), evidence

    def _build_extraction_prompt(
        self,
        topic: str,
        context: str,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> str:
        prompt = f"""You are an expert at creating educational concept maps. Your task is to extract key concepts and their relationships from the given context about "{topic}".

# Context Information:
Each block starts with an id in square brackets: [D1], [D2], … for the user's documents, [W1], [W2], … for web pages.

{context}

# Task:
Create a concept map by identifying:
1. **Key Concepts (Nodes)**: Important ideas, terms, definitions, or entities related to "{topic}"
2. **Relationships (Edges)**: How these concepts connect to each other

# Instructions:
- Extract up to {max_concepts} most important concepts
- Identify up to {max_edges} meaningful relationships between concepts
- Each concept should have:
  - A clear, concise label (2-5 words)
  - A brief definition/description (1-2 sentences)
  - source_ids: the ids of the context blocks that explain it, exactly as written (e.g. "D1", "W2")
- Each relationship should have:
  - Source concept
  - Target concept
  - Relationship label (verb/phrase describing the connection)
- Focus on concepts that are:
  - Central to understanding "{topic}"
  - Well-explained in the context
  - Interconnected with other concepts
- Avoid:
  - Generic concepts (unless central to the topic)
  - Concepts not explained in the context
  - Duplicate or redundant concepts

# Output Format:
Return ONLY a valid JSON object with this exact structure (no markdown, no code blocks, just raw JSON):

{{
  "topic": "{topic}",
  "nodes": [
    {{
      "id": "concept_1",
      "label": "Concept Name",
      "definition": "Brief explanation of the concept",
      "source_ids": ["D1"]
    }}
  ],
  "edges": [
    {{
      "from": "concept_1",
      "to": "concept_2",
      "label": "relationship description"
    }}
  ]
}}

# Important Notes:
1. Use snake_case IDs (e.g., "neural_network", "attention_mechanism")
2. Ensure all edge references point to valid node IDs
3. Keep labels concise (2-5 words)
4. Keep definitions informative but brief (1-2 sentences)
5. Cite only block ids that appear in the context; never write file names or URLs in source_ids
6. Return ONLY the JSON - no explanation, no markdown formatting

Now extract the concept map:"""

        return prompt

    def _parse_llm_response(self, response_text: str) -> Optional[Dict]:
        """Parse the model's reply into a dict (hand-parsed until S1 moves this to structured output)."""
        cleaned = response_text.strip()
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1:
            cleaned = cleaned[start_idx:end_idx + 1]
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Concept-map reply is not JSON; trying a regex scan")
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not match:
                return None
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.error("Concept-map reply could not be parsed (%d chars)", len(response_text))
                return None
        if not isinstance(result, dict):
            return None
        logger.info("Parsed %d nodes and %d edges", len(result.get("nodes", [])), len(result.get("edges", [])))
        return result

    def _validate_and_clean_concept_map(self, concept_map: Dict) -> Dict:
        """
        Validate and clean the concept map data

        Args:
            concept_map: Raw concept map from LLM

        Returns:
            Cleaned and validated concept map
        """
        # Ensure required fields exist
        if "nodes" not in concept_map:
            concept_map["nodes"] = []
        if "edges" not in concept_map:
            concept_map["edges"] = []

        # Validate nodes
        valid_nodes = []
        node_ids = set()

        for node in concept_map["nodes"]:
            # Check required fields
            if "id" not in node or "label" not in node:
                logger.warning(f" Skipping node without id or label: {node}")
                continue

            # Ensure unique IDs
            if node["id"] in node_ids:
                logger.warning(f" Duplicate node ID: {node['id']}")
                node["id"] = f"{node['id']}_{len(valid_nodes)}"

            node_ids.add(node["id"])

            # Add default values for missing fields
            if "definition" not in node:
                node["definition"] = ""

            valid_nodes.append(node)

        # Validate edges
        valid_edges = []

        for edge in concept_map["edges"]:
            # Check required fields
            if "from" not in edge or "to" not in edge:
                logger.warning(f" Skipping edge without from/to: {edge}")
                continue

            # Check that referenced nodes exist
            if edge["from"] not in node_ids or edge["to"] not in node_ids:
                logger.warning(f" Skipping edge with invalid node reference: {edge['from']} -> {edge['to']}")
                continue

            # Add default label if missing
            if "label" not in edge:
                edge["label"] = "relates to"

            valid_edges.append(edge)

        concept_map["nodes"] = valid_nodes
        concept_map["edges"] = valid_edges

        logger.info(f" Validated: {len(valid_nodes)} nodes, {len(valid_edges)} edges")

        return concept_map

    def _attribute_sources(self, concept_map: Dict, evidence: Evidence) -> Dict:
        """Replace each node's cited ids by the blocks they name; a node citing nothing real gets no sources.

        Until Day 17 an empty node got the first retrieved source of its type — a guess shown as a citation.
        """
        for node in concept_map.get("nodes", []):
            node["source_type"], node["sources"] = evidence.resolve(node.pop("source_ids", None))
        return concept_map

    def _add_source_summary(self, concept_map: Dict, retrieval_result: Dict) -> Dict:
        sources = retrieval_result.get("sources", {})
        doc_sources = sources.get("document_sources", [])
        web_sources = sources.get("web_sources", [])
        concept_map["source_summary"] = {
            "total_sources": len(doc_sources) + len(web_sources),
            "document_sources": doc_sources,
            "web_sources": web_sources,
            "confidence": retrieval_result.get("confidence", 0.0),
        }
        return concept_map

    def extract_concepts_from_hybrid_sources(
        self,
        topic: str,
        retrieval_result: Dict,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> Dict:
        """Build the numbered context from a ConceptMapRetriever result and extract the map from it."""
        context, evidence = self.build_context(retrieval_result)
        logger.info("Extracting concepts (context %d characters)", len(context))

        if len(context.strip()) < 100:
            return self._create_empty_concept_map(topic, "Insufficient context available")

        prompt = self._build_extraction_prompt(
            topic=topic, context=context, max_concepts=max_concepts, max_edges=max_edges
        )
        try:
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
        except (genai_errors.APIError, httpx.HTTPError):
            logger.exception("Concept extraction call failed")
            return self._create_empty_concept_map(topic, "Extraction call failed")

        concept_map = self._parse_llm_response(response.text or "")
        if not concept_map:
            return self._create_empty_concept_map(topic, "Failed to parse LLM response")

        concept_map = self._validate_and_clean_concept_map(concept_map)
        concept_map = self._attribute_sources(concept_map, evidence)
        concept_map = self._add_source_summary(concept_map, retrieval_result)
        concept_map["metadata"] = {
            "topic": topic,
            "node_count": len(concept_map.get("nodes", [])),
            "edge_count": len(concept_map.get("edges", [])),
            "context_length": len(context),
            "model": self.model_name,
        }
        logger.info(
            "Extraction complete: %d nodes, %d edges",
            concept_map["metadata"]["node_count"], concept_map["metadata"]["edge_count"],
        )
        return concept_map

    def _create_empty_concept_map(self, topic: str, reason: str) -> Dict:
        logger.warning("Empty concept map: %s", reason)
        return {
            "topic": topic,
            "nodes": [],
            "edges": [],
            "metadata": {
                "topic": topic,
                "node_count": 0,
                "edge_count": 0,
                "error": reason
            },
            "source_summary": {
                "total_sources": 0,
                "document_sources": [],
                "web_sources": [],
                "confidence": 0.0
            }
        }
