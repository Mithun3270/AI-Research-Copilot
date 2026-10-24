"""One-time utility to reclassify indexed papers using category centroid similarity."""

import logging

from backend.research_copilot import ResearchCopilot


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = ResearchCopilot()
    results = engine.reclassify_all_papers()
    changed = [result for result in results if result["previous_category"] != result["category"]]
    print(f"Reclassified {len(results)} papers; {len(changed)} category assignments changed.")
    for result in changed:
        print(f"{result['paper']}: {result['previous_category']} -> {result['category']}")


if __name__ == "__main__":
    main()
