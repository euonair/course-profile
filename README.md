# EUonAIR AI-Ready Course Description Profile

Version 0.9 · namespace `https://w3id.org/euonair/course#` · vocabularies `https://w3id.org/euonair/vocab/`

A metadata application profile for course descriptions that AI tools and course platforms can use: learning outcomes with cognitive level, workload, assessment with outcome links, prerequisites and machine-readable rules for AI use per course and assessment. It is the result of EUonAIR Milestone MS4, *AI-Ready Course Descriptions* (Work Package 4, Task 4.6, Heilbronn University of Applied Sciences).

| Tier | Elements | Conformance |
|---|---|---|
| Core | 18 | mandatory |
| AI-readiness extension | 14 | recommended |
| Exchange and discovery extension | 32 | optional |
| Record metadata | 14 | 5 mandatory, 9 recommended |

## Files

| File | Content |
|---|---|
| `profile.xlsx` | Element list with definitions, types, cardinalities, vocabularies, mappings (ECTS Users' Guide, ELM, OCCAPI, IEEE LOM, Dublin Core) and evidence |
| `context.jsonld` | JSON-LD 1.1 context with the namespaces of the profile |
| `core.schema.json` | JSON Schema (Draft 2020-12) for the core and the mandatory record fields |
| `shapes.ttl` | SHACL shapes for validation on the RDF graph |
| `examples/full-record.jsonld` | Full example record of a fictitious course unit |
| `examples/minimal-record.jsonld` | Illustrative core-level record |
| `vocab/` | Seed vocabularies (`euvoc:`) |
| `validate.py`, `validation/` | Validator for the example records against the JSON Schema and the SHACL shapes, with the pinned schema.org context |
| `profile/0.9/` | Frozen copy of release 0.9 |

The example records describe a fictitious course at a fictitious institution. Records reference the schema.org context as `https://schema.org/`; schema.org terms expand to `http://schema.org/`, as in the official schema.org context.

## Validation

```
uv run --with pyld --with rdflib --with pyshacl --with jsonschema python validate.py
```

The validator runs offline. It expands both example records as published, with a pinned copy of the official schema.org context (fetched 2026-10-20), checks them against the JSON Schema and the SHACL shapes and runs negative tests with invalid variants (59 tests). Rules that need a semantic validator (sums of hours and weights, outcome references, AI-policy consistency) are not checked; passing shows that a record meets the implemented constraints, not conformance with every rule of the profile.

## Persistent identifiers

`https://w3id.org/euonair/…` redirects to this repository's GitHub Pages site (rules in `w3id/`).

## Licence

CC BY 4.0 (see `LICENSE`). EUonAIR is co-funded by the European Union (ERASMUS-EDU-2024-EUR-UNIV, grant agreement 101177370).
