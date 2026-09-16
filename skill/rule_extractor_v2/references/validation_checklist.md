# Validation Checklist

Run this checklist before final output.

## Hard checks

- [ ] Every `rule_id` is unique.
- [ ] Every JSON object has `rule_id`, `description`, `sets`, `parameters`.
- [ ] Every MIN rule contains only the lower-bound fact.
- [ ] Every MAX rule contains only the upper-bound fact.
- [ ] No fixed-value rule is encoded as `min == max`.
- [ ] No rule converts different entities into min/max.
- [ ] No element string joins independent entities with commas when they require separate rules.
- [ ] `description`, `rule_id`, and parameter name describe the same fact.
- [ ] No source rule contains a value that exists only after arithmetic calculation.
- [ ] No silent `% -> 0~1` conversion occurs in source rules.
- [ ] No unit is invented when the source does not provide one.
- [ ] Explicit valid zeros are preserved.
- [ ] Blank / dash cells are not emitted as numeric facts.
- [ ] No unsupported entity, operating mode, topology, or set relation is invented.

## Set checks

For `CDUko`:

```text
element = unit.sidecut.crude
```

For `CDUkoq`:

```text
element = unit.sidecut.crude.property
```

For `SQ`:

```text
element = stream.property
```

For `IU`:

```text
element = unit.stream
```

For `OU`:

```text
element = unit.stream
```

For `OUSQ`:

```text
element = unit.stream.property
```

## Semantic checks

Search the output for suspicious patterns:

```text
"min" and "max" with identical values
description containing both "下限" and "上限"
element containing ","
BOUND on a fixed-value rule
PRODUCT_PROPERTY on a unit sidecut that is not a final product
```

Each occurrence must be justified by the source.

## Count checks

Rule-count growth alone is not evidence of correctness.

Before/after count changes must be explainable by:
- explicit lower/upper split;
- entity split;
- composite-rule split;
- deletion of duplicate/error rules;
- correction of fixed values.

Do not generate extra rules merely to increase coverage.

## Final manual spot-check

Spot-check at least:

1. one tank bound;
2. one CDU YCO/RCO yield;
3. one CDU property;
4. one secondary-unit fixed yield;
5. one secondary-unit fixed property;
6. one blending lower/upper pair;
7. one explicit zero;
8. one missing-value case.

Compare each directly to the original source cells.
