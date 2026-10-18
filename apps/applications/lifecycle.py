"""The cumulative ("current") view of a dossier: every accepted sequence applied in order.

ICH eCTD lifecycle operations: ``new`` adds a document, ``replace`` supersedes the leaf named in
``modified-file``, ``append`` adds to it (both stay current) and ``delete`` withdraws it.
"""
from apps.validation.ectd import build_dossier_tree, locate_sequence_dir, parse_modified_file


def _walk(nodes, trail=()):
    for node in nodes:
        path = (*trail, node["label"])
        for leaf in node["leaves"]:
            yield path, leaf
        yield from _walk(node["children"], path)


def _node(index, root, path):
    """The node at ``path`` (a tuple of heading labels), created on first use in sequence order."""
    if path not in index:
        parent = root if len(path) == 1 else _node(index, root, path[:-1])["children"]
        node = {"label": path[-1], "leaves": [], "children": [], "depth": len(path) - 1}
        parent.append(node)
        index[path] = node
    return index[path]


def build_current_view(application) -> dict:
    """{"tree": nested nodes whose leaves carry their history and status, "counts": {...}}.

    A leaf's ``status`` is current, replaced or deleted. Documents that point at a leaf the view cannot
    find (``unresolved``) stay current and are flagged.
    """
    root, index, entries = [], {}, {}
    for sequence in application.accepted_sequences():
        if not sequence.extracted_dir or not sequence.extracted_dir.is_dir():
            continue
        tree = build_dossier_tree(locate_sequence_dir(sequence.extracted_dir)[0])
        for path, leaf in _walk(tree):
            if leaf["path"].endswith("-regional.xml"):
                continue  # the regional backbone is a technical file, sent new in every sequence
            reference = parse_modified_file(leaf["modified_file"])
            target = entries.get((reference[0], reference[2])) if reference else None
            step = {"sequence": sequence.number, "operation": leaf["operation"]}
            if leaf["operation"] == "delete":
                if target:
                    target.update(status="deleted", changed_in=sequence.number)
                    target["history"].append(step)
                continue
            entry = {**leaf, "sequence": sequence.number, "sequence_pk": sequence.pk, "status": "current",
                     "history": [step], "unresolved": bool(reference) and target is None}
            if leaf["operation"] == "replace" and target:
                target.update(status="replaced", changed_in=sequence.number)
                entry["history"] = [*target["history"], step]
            elif leaf["operation"] == "append" and target:
                entry["appends_to"] = target["title"]
            entries[(sequence.number, leaf["id"])] = entry
            _node(index, root, path)["leaves"].append(entry)

    counts = {"current": 0, "replaced": 0, "deleted": 0}
    for entry in entries.values():
        counts[entry["status"]] += 1
    return {"tree": root, "counts": counts, "sequences": [s.number for s in application.accepted_sequences()]}
