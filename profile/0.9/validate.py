"""Validate the EUonAIR AI-Ready Course Description Profile: example records, JSON Schema and SHACL shapes.

Runs offline. Each example is expanded as published (its @context unchanged) with a document loader that serves only
the pinned official schema.org context and the profile context. Positive tests: both examples pass the JSON Schema and
the SHACL shapes and survive a Turtle round trip. Negative tests: invalid variants must be rejected.

Usage (from the repository root):
    uv run --with pyld --with rdflib --with pyshacl --with jsonschema python validate.py
"""
from __future__ import annotations

import copy
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
NS = {"schema": "http://schema.org/", "euonair": "https://w3id.org/euonair/course#",
      "euvoc": "https://w3id.org/euonair/vocab/", "dcterms": "http://purl.org/dc/terms/"}
LOCAL_CTX_URL = "https://w3id.org/euonair/course/context.jsonld"


@dataclass
class Files:
    context: Path
    schema: Path
    shapes: Path
    schemaorg_context: Path
    minimal: Path
    full: Path

    @classmethod
    def repository(cls, root: Path) -> "Files":
        """Layout of the published repository."""
        return cls(root / "context.jsonld", root / "core.schema.json", root / "shapes.ttl",
                   root / "validation" / "schemaorg-context_2026-10-20.jsonld",
                   root / "examples" / "minimal-record.jsonld", root / "examples" / "full-record.jsonld")


def document_loader(files: Files):
    """Offline loader: pinned official schema.org context and the profile context; nothing else."""
    official = json.loads(files.schemaorg_context.read_text(encoding="utf-8"))
    local = json.loads(files.context.read_text(encoding="utf-8"))

    def load(url: str, options=None) -> dict:
        if re.fullmatch(r"https?://schema\.org/?(docs/jsonldcontext\.jsonld?)?", url):
            doc = official
        elif url == LOCAL_CTX_URL:
            doc = local
        else:
            raise ValueError(f"no remote context allowed: {url}")
        return {"contextUrl": None, "documentUrl": url, "document": doc}
    return load


def to_graph(rec: dict, loader):
    import rdflib
    from pyld import jsonld
    nq = jsonld.to_rdf(rec, {"format": "application/n-quads", "documentLoader": loader})
    g = rdflib.Graph().parse(data=nq, format="nt")
    for k, v in NS.items():
        g.bind(k, v, override=True, replace=True)
    return g


def run(files: Files) -> tuple[list[tuple[str, str, str, bool]], dict[str, int]]:
    """All tests; returns (test, expected, observed, passed) rows and the triple count per example."""
    import jsonschema
    import pyshacl
    import rdflib
    from rdflib.compare import isomorphic
    RDF = rdflib.RDF
    S = rdflib.Namespace(NS["schema"]); E = rdflib.Namespace(NS["euonair"]); SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    shapes = rdflib.Graph().parse(files.shapes, format="turtle")
    checker = jsonschema.Draft202012Validator(json.loads(files.schema.read_text(encoding="utf-8")),
                                              format_checker=jsonschema.FormatChecker())
    loader = document_loader(files)
    results: list[tuple[str, str, str, bool]] = []

    def shacl(g) -> int:
        _, rg, _ = pyshacl.validate(g, shacl_graph=shapes, allow_infos=True, allow_warnings=True)
        return len(list(rg.subjects(SH.resultSeverity, SH.Violation)))

    def record(test: str, expected: str, observed: str, passed: bool) -> None:
        results.append((test, expected, observed, passed))
        log.info("%s %s: %s", "PASS" if passed else "FAIL", test, observed)

    graphs, records = {}, {}
    for name, path in (("minimal-record", files.minimal), ("full-record", files.full)):
        rec = json.loads(path.read_text(encoding="utf-8"))
        records[name] = rec
        errs = list(checker.iter_errors(rec))
        record(f"{name}: JSON Schema", "valid", "valid" if not errs else f"{len(errs)} errors: {errs[0].message[:120]}", not errs)
        g = to_graph(rec, loader)  # the published JSON-LD, @context unchanged
        ttl = rdflib.Graph().parse(data=g.serialize(format="turtle"), format="turtle")
        iso = isomorphic(g, ttl)
        record(f"{name}: expansion = Turtle round trip", "isomorphic", f"{'isomorphic' if iso else 'NOT isomorphic'} ({len(g)} triples)", iso)
        https = [t for t in g if any(str(x).startswith("https://schema.org/") for x in t)]
        record(f"{name}: no https://schema.org/ IRIs", "0", str(len(https)), not https)
        v = shacl(g)
        record(f"{name}: SHACL", "0 violations", f"{v} violations", v == 0)
        graphs[name] = g

    # SHACL negative tests on the graph: each mutation of the full record must produce a violation.
    full = graphs["full-record"]
    root = next(full.subjects(E.metadataRecord, None))

    def m_no_lo_desc(g):
        for lo in list(g.objects(root, S.teaches)):
            g.remove((lo, S.description, None))

    def m_neg_credits(g):
        for c in list(g.objects(root, S.numberOfCredits)):
            g.set((c, S.value, rdflib.Literal(-5)))

    def m_no_record_type(g):
        for r in list(g.objects(root, E.metadataRecord)):
            g.remove((r, RDF.type, E.MetadataRecord)); g.remove((r, E.generationMethod, None))

    def m_no_country(g):
        for pr in list(g.objects(root, S.provider)):
            for a in list(g.objects(pr, S.address)):
                g.remove((a, S.addressCountry, None))

    def m_weight_and_range(g):
        ac = next(a for a in g.objects(root, E.assessmentComponent) if (a, E.weightMin, None) in g)
        g.add((ac, E.weightPercent, rdflib.Literal(90)))

    for label, f in [("no outcome description", m_no_lo_desc), ("credits -5", m_neg_credits),
                     ("no assessment method", lambda g: g.remove((None, E.assessmentMethod, None))),
                     ("record type and generation method removed", m_no_record_type),
                     ("course-unit type removed", lambda g: g.remove((root, RDF.type, E.CourseUnit))),
                     ("syllabus position removed", lambda g: g.remove((None, S.position, None))),
                     ("provider country removed", m_no_country), ("exact weight plus range", m_weight_and_range)]:
        g = copy.deepcopy(full); f(g)
        v = shacl(g)
        record(f"SHACL negative: {label}", ">0 violations", f"{v} violations", v > 0)

    # JSON Schema tests (negative: must be rejected; positive: must be accepted).
    def jt(label: str, f, accept: bool, base: str = "full-record") -> None:
        r = copy.deepcopy(records[base]); f(r)
        errs = list(checker.iter_errors(r))
        record(f"JSON {'positive' if accept else 'negative'}: {label}", "accepted" if accept else "rejected",
               "accepted" if not errs else "rejected", (not errs) == accept)

    none = {"@id": "euonair:none"}
    jt("empty prerequisite object", lambda r: r.update(coursePrerequisites=[{}]), False)
    jt("explicit none plus a real prerequisite", lambda r: r["coursePrerequisites"].append(none), False)
    jt("empty citation object", lambda r: r.update(citation=[{}]), False)
    jt("arbitrary unit-type IRI", lambda r: r.update({"euonair:unitType": {"@id": "foo:bar"}}), False)
    jt("arbitrary grading-mode IRI", lambda r: r.update({"euonair:gradingMode": {"@id": "http://x.org/whatever"}}), False)
    jt("empty @context", lambda r: r.update({"@context": []}), False)
    jt("exact weight plus range", lambda r: r["euonair:assessmentComponent"][0].update({"euonair:weightPercent": 90}), False)
    jt("provider country missing", lambda r: r["provider"].pop("address"), False, "minimal-record")
    jt("syllabus position missing", lambda r: r["syllabusSections"][0].pop("position"), False)
    jt("plain-text prerequisite (C17 Text)", lambda r: r.update(coursePrerequisites=["Machine Learning passed"]), True)
    jt("language-tagged prerequisite", lambda r: r.update(coursePrerequisites=[{"@value": "Maschinelles Lernen", "@language": "de"}]), True)
    jt("explicit none only", lambda r: r.update(coursePrerequisites=[none]), True)
    jt("full IRI for unit type", lambda r: r.update({"euonair:unitType": {"@id": NS["euvoc"] + "unit-type/course"}}), True)

    # Tests run by both validators: the JSON Schema and the SHACL shapes must agree.
    def both(label: str, f, accept: bool, base: str = "full-record") -> None:
        r = copy.deepcopy(records[base]); f(r)
        errs = list(checker.iter_errors(r))
        v = shacl(to_graph(r, loader))
        kind = "positive" if accept else "negative"
        record(f"JSON {kind}: {label}", "accepted" if accept else "rejected", "accepted" if not errs else "rejected", (not errs) == accept)
        record(f"SHACL {kind}: {label}", "0 violations" if accept else ">0 violations", f"{v} violations", (v == 0) == accept)

    eqf6 = copy.deepcopy(records["full-record"]["educationalLevel"])
    nqf6 = {"@type": "DefinedTerm", "@id": "https://example.edu/ns/nqf/6", "name": "National qualifications framework, level 6 (illustrative)"}
    eqf7 = {"@type": "DefinedTerm", "@id": "http://data.europa.eu/snb/eqf/7"}

    def ac(r, key):  # first specification component that has the given weight property
        return next(a for a in r["euonair:assessmentComponent"] if key in a)

    def drop(d, key):
        d.pop(key)
        return d
    voc = NS["euvoc"]
    both("EQF level plus a national (NQF) level", lambda r: r.update(educationalLevel=[eqf6, nqf6]), True)
    both("two EQF levels", lambda r: r.update(educationalLevel=[eqf6, eqf7]), False)
    both("no EQF level (NQF level only)", lambda r: r.update(educationalLevel=[nqf6]), False)
    both("grading scale as string literal", lambda r: r.update({"euonair:gradingScale": "https://example.edu/regulations/grading-scale"}), False)
    both("ELM export link as string literal", lambda r: r.update({"euonair:elmMapping": "https://example.edu/elm/NLP-3060"}), False)
    both("institutional AI policy as string literal", lambda r: r["euonair:aiUsePolicy"].update(
        {"euonair:institutionalPolicy": "https://example.edu/policies/ai-in-teaching-and-assessment"}), False)
    both("AI-use gate as string literal", lambda r: r["euonair:assessmentComponent"][1]["euonair:aiCondition"].update(
        {"euonair:gatedBy": "https://example.edu/course-units/NLP-3060#ac3"}), False)
    both("undefined grading value euvoc:grading/not-a-real-mode", lambda r: r.update({"euonair:gradingMode": {"@id": "euvoc:grading/not-a-real-mode"}}), False)
    both("undefined disclosure value euvoc:ai-disclosure/not-a-real-value", lambda r: r["euonair:aiUsePolicy"].update(
        {"euonair:disclosureRequirement": {"@id": "euvoc:ai-disclosure/not-a-real-value"}}), False)
    both("undefined value for input of course materials euvoc:ai-material-input/not-a-real-value", lambda r: r["euonair:aiUsePolicy"].update(
        {"euonair:materialInput": {"@id": "euvoc:ai-material-input/not-a-real-value"}}), False)
    both("undefined review status euvoc:review-status/not-a-real-status", lambda r: r["euonair:metadataRecord"].update(
        {"creativeWorkStatus": {"@id": "euvoc:review-status/not-a-real-status"}}), False)
    inner = {"@type": "euonair:AiUsePolicy", "euonair:permissionLevel": {"@id": "euvoc:ai-permission/restricted-to-listed-purposes"},
             "euonair:permittedPurpose": [{"@id": "euvoc:ai-purpose/explanation"}],
             "euonair:interactionModeHint": {"@id": "euvoc:ai-interaction/guided"},
             "euonair:disclosureRequirement": {"@id": "euvoc:ai-disclosure/statement"}}
    both("rule before the gate as a policy of its own (explanations only)", lambda r: r["euonair:assessmentComponent"][1]["euonair:aiCondition"].update(
        {"euonair:beforeGate": copy.deepcopy(inner)}), True)
    both("course-default before a gate on the course-level policy", lambda r: r["euonair:aiUsePolicy"].update(
        {"euonair:gatedBy": {"@id": "https://example.edu/course-units/NLP-3060#ac3"}, "euonair:beforeGate": {"@id": "euvoc:before-gate/course-default"}}), False)
    both("full IRI for grading mode", lambda r: r.update({"euonair:gradingMode": {"@id": voc + "grading/pass-fail"}}), True)
    both("full IRI for AI permission level", lambda r: r["euonair:aiUsePolicy"].update(
        {"euonair:permissionLevel": {"@id": voc + "ai-permission/not-permitted"}}), True)
    both("exact weight plus minimum only", lambda r: ac(r, "euonair:weightPercent").update({"euonair:weightMin": 10}), False)
    both("exact weight plus maximum only", lambda r: ac(r, "euonair:weightPercent").update({"euonair:weightMax": 30}), False)
    both("incomplete range (minimum only)", lambda r: drop(ac(r, "euonair:weightMin"), "euonair:weightMax"), False)
    both("exact weight plus complete range", lambda r: ac(r, "euonair:weightPercent").update(
        {"euonair:weightMin": 10, "euonair:weightMax": 30}), False)
    return results, {n: len(g) for n, g in graphs.items()}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    results, triples = run(Files.repository(Path(__file__).resolve().parent))
    failed = [t for t in results if not t[3]]
    log.info("%d tests, %d passed; triples: %s", len(results), len(results) - len(failed),
             ", ".join(f"{k} {v}" for k, v in triples.items()))
    log.info("Not checked (semantic validator, Annex B.3 of the MS10 report): sums of hours and weights, hours per credit, "
             "weight-range feasibility, offering references, outcome references, topic positions, AI-policy consistency. Passing shows that the records meet the "
             "implemented constraints, not conformance with every rule of the profile.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
