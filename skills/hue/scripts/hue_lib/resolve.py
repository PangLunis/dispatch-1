"""Entity resolution — find lights, groups, and scenes by name."""


def find_entity(name, entities, entity_type="light"):
    """Find an entity by name. Exact match first, then partial.

    Args:
        name: Name to search for (case-insensitive).
        entities: Dict of {key: entity_dict} where each has a "name" field.
        entity_type: "light", "room", or "scene" (for error messages).

    Returns:
        (entity, matches) tuple:
        - If exact or single partial match: (entity_dict, [])
        - If multiple matches: (None, [list of matches])
        - If no match: (None, [])
    """
    name_lower = name.lower()

    # Exact match
    for key, entity in entities.items():
        if entity["name"].lower() == name_lower:
            return entity, []

    # Partial match
    matches = [e for _, e in entities.items() if name_lower in e["name"].lower()]
    if len(matches) == 1:
        return matches[0], []
    elif len(matches) > 1:
        return None, matches

    return None, []
