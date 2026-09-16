---
name: petrochemical_knowledge_rule_extractor
description: >
  Extract, normalize, split, and validate petrochemical scheduling knowledge rules
  from local Excel/Word/PDF source materials into the shihua-project JSON format.
  Use for crude oil, tanks, CDU/atmospheric units, secondary processing units,
  sidecut yields/properties, blending rules, operating bounds, and related
  refinery scheduling knowledge.
---

# Petrochemical Knowledge Rule Extractor v2

## Mission

Extract **atomic, traceable, semantically faithful** petrochemical scheduling rules
from the provided source files and write them in the project's JSON format.

The primary goal is not to maximize rule count. The primary goal is:

1. preserve the original meaning of the source;
2. express one independently verifiable fact per rule whenever practical;
3. distinguish source facts from calculated/derived facts;
4. use the project's existing set/index semantics;
5. avoid inventing entities, bounds, units, or topology that the source does not support.

## Source priority

When multiple files are provided, use this priority:

1. **Original source material** (Excel/Word/PDF): authoritative for factual values and field meaning.
2. **Scheduling symbol/specification document**: authoritative for set, index, parameter, and model semantics.
3. **Knowledge-rule examples / category definition**: authoritative for JSON style and naming conventions.
4. Existing extraction results: reference only; never treat them as more authoritative than the source.

If sources disagree, do not silently reconcile them. Preserve the original source meaning and report the conflict.

## Default output

Follow the existing project result structure unless the user explicitly requests another layout.

Typical structure:

```text
extract_result/<date>/
├── 原油类/
│   ├── 原油罐库存上下限.json
│   └── 原油混合侧线收率计算.json
├── 装置类/
│   └── 装置类.json
└── 调和类/
    └── 调合类.json
```

Output only result JSON files by default.  
Do **not** generate README, audit reports, trace tables, or auxiliary files unless requested.

Each JSON file contains a JSON array of rule dictionaries.

## Required JSON schema

Use this structure unless the existing project file for that category requires a stricter variant:

```json
{
  "rule_id": "UNIQUE_RULE_ID",
  "description": "一条只描述当前事实的中文句子。",
  "sets": [
    {
      "set_name": "T",
      "subset_name": null,
      "element": "6101"
    }
  ],
  "parameters": {
    "parameter_name": {
      "value": 2.5,
      "unit": "m"
    }
  }
}
```

Do not add new top-level fields unless explicitly requested.

# Extraction workflow

## Step 1 — Understand the source table before extracting

For every worksheet/table/section:

1. identify the row entity;
2. identify the column entity;
3. determine whether multiple columns represent:
   - upper/lower bounds;
   - different crude oils;
   - different operating modes;
   - different units;
   - different products;
   - different properties;
4. identify explicit units from the source;
5. identify blanks, `—`, `-`, and zeros separately;
6. determine whether the value is direct source data or calculated from other fields.

Never infer semantic meaning from numeric order alone.

Bad reasoning:

```text
YCO = 0.7352
RCO = 0.7365
therefore min = 0.7352, max = 0.7365
```

This is forbidden unless the source explicitly says the two columns are lower/upper bounds.

## Step 2 — Classify each candidate fact

Classify every candidate as one of:

- `single_value`: one direct value;
- `lower_bound`: explicit lower/minimum bound;
- `upper_bound`: explicit upper/maximum bound;
- `entity_specific_value`: value belongs to a particular crude/product/unit/mode;
- `relationship`: calculation or mapping relationship;
- `derived_value`: value computed from source fields;
- `not_extractable`: insufficient or ambiguous evidence.

This classification is conceptual only; do not add it to the JSON unless requested.

## Step 3 — Atomic rule splitting

### Rule A: explicit upper/lower bounds must be separate rules

If the source explicitly gives lower and upper bounds, create two independent rules.

Example source:

```text
6101安全液位下限 = 2.5 m
6101安全液位上限 = 14.3 m
```

Correct:

```json
{
  "rule_id": "CRUDE_INVENTORY_LEVEL_MIN_6101",
  "description": "6101原油罐安全液位下限为2.5米。",
  "parameters": {
    "inventory_level_min": {"value": 2.5, "unit": "m"}
  }
}
```

and

```json
{
  "rule_id": "CRUDE_INVENTORY_LEVEL_MAX_6101",
  "description": "6101原油罐安全液位上限为14.3米。",
  "parameters": {
    "inventory_level_max": {"value": 14.3, "unit": "m"}
  }
}
```

Do not keep both bounds in one rule.

### Rule B: a single fixed value must stay a single value

If the source says:

```text
200_催化汽油 RON = 89.3
```

do not create:

```json
{
  "product_ron_min": 89.3,
  "product_ron_max": 89.3
}
```

Correct form:

```json
{
  "rule_id": "UNIT_SIDECUT_PROPERTY_FCC200_GASOLINE_RON",
  "description": "200万催化装置的200_催化汽油侧线辛烷值为89.3。",
  "parameters": {
    "sidecut_ron": {"value": 89.3, "unit": null}
  }
}
```

`min == max` is not a valid way to encode a fixed value unless the source explicitly defines a zero-width interval.

### Rule C: different entities are not bounds

If columns are YCO and RCO, generate entity-specific rules.

Source:

```text
          YCO      RCO
NK1 SPG   0.7352   0.7365
```

Correct:

```text
300万吨年常压装置 + NK1 + YCO + SPG = 0.7352
300万吨年常压装置 + NK1 + RCO + SPG = 0.7365
```

Never transform this into `[0.7352, 0.7365]`.

### Rule D: avoid multi-entity strings

Avoid:

```json
"element": "YCO,RCO"
```

when the values belong to individual crude oils.

Generate one rule per entity instead.

### Rule E: split composite facts

If one existing rule contains independent facts such as:

- calculation relationship;
- component properties;
- final product quality limit;

split them into separate rules.

Example: gasoline blending RON should not place component RON values and product RON specification in the same rule.

## Step 4 — Distinguish source facts from derived facts

A source rule must correspond to a value explicitly present in the source.

Example:

```text
安全液位下限 = 2.5 m
米系数 = 530 t/m
```

These are direct source facts.

```text
库存质量下限 = 2.5 × 530 = 1325 t
```

is a derived fact.

Do not write `1325 t` as if it were directly present in the source.

By default:

- put direct facts in the normal project result files;
- only emit derived rules when the user explicitly requests them or when the source/model specification explicitly defines that calculation as a rule to extract;
- when derived rules are emitted, description must say that the value is calculated/derived.

Never silently mix direct and calculated values.

## Step 5 — Set and index mapping

Use only sets/relations supported by the project's symbol specification or established project convention.

Validated project mappings include:

```text
T       tank set
U       unit set
O       crude oil set
Q       property set
S       stream set

IU      ⊆ U × S
OU      ⊆ U × S
SQ      ⊆ S × Q
OUSQ    ⊆ U × S × Q
CDUko   ⊆ U × K × O
CDUkoq  ⊆ U × K × O × Q
```

For `CDUko`, element order must be:

```text
unit.sidecut.crude
```

For `CDUkoq`, element order must be:

```text
unit.sidecut.crude.property
```

Example:

```json
{
  "set_name": "CDUkoq",
  "subset_name": null,
  "element": "300万吨年常压装置.NK1.YCO.SPG"
}
```

Do not reorder indices.

### Do not invent topology

If the source says:

```text
92#汽油
允许组分：催化汽油、常压石脑油、MTBE、烃化液
```

but no source defines a formal unit named `92#汽油调合`, do not claim that this unit is verified.

If an existing project convention already uses provisional `IU/OU/OUSQ` mappings, preserve them only when required for compatibility and treat them as provisional. Do not invent additional topology.

## Step 6 — Units and scaling

### Preserve source units

Do not silently rescale source values.

If Excel stores:

```text
石脑油质量收率 = 9.48
```

with percent semantics, source rule should be:

```json
"mass_yield": {
  "value": 9.48,
  "unit": "%"
}
```

Do not silently convert it to `0.0948` in the extraction layer.

Any `% -> 0~1` conversion belongs to the model-loading/transformation layer.

### Do not invent units

If the source does not explicitly provide a unit, prefer:

```json
"unit": null
```

unless an existing project rule specification explicitly mandates a unit.

Examples that commonly stay `null` at source layer:
- RON;
- some index-type properties;
- SPG when the source table only labels it as 比重 and gives no explicit unit.

## Step 7 — Zero, blank, dash, and missing values

Never apply a global rule such as:

```python
if value == 0:
    skip
```

Treat these separately:

- blank / empty cell → missing unless source semantics say otherwise;
- `—` or `-` → normally unavailable / not applicable;
- `0` → may be a real value or a placeholder; determine from table semantics.

Example:

```text
MTBE 硫 = 0 ppm
MTBE 苯 = 0%
```

These are explicit valid zeros and must be preserved.

By contrast, a matrix containing hundreds of property zeros with physically impossible values such as `SPG = 0` may use zero as a placeholder. Do not emit those as facts unless supported by a data dictionary or table semantics.

When uncertain, omit rather than invent, and tell the user what is ambiguous.

## Step 8 — Rule ID construction

`rule_id` must encode the semantic subject and fact.

General patterns:

```text
<DOMAIN>_<FACT>_<MIN|MAX|PROPERTY>_<ENTITY...>
```

Examples:

```text
CRUDE_INVENTORY_LEVEL_MIN_6101
CRUDE_INVENTORY_LEVEL_MAX_6101
UNIT_SIDECUT_PROPERTY_FCC200_GASOLINE_RON
CDU_SIDECUT_PROPERTY_300_NK1_SPG_YCO
BLEND_RECIPE_MIN_92_GASOLINE_CAT_GASOLINE
BLEND_RECIPE_MAX_92_GASOLINE_CAT_GASOLINE
PRODUCT_RON_MIN_92_GASOLINE
```

Requirements:

- every `rule_id` must be unique within the extraction result;
- a MIN rule must not describe a MAX value;
- fixed-value rules must not contain `BOUND`, `MIN`, or `MAX`;
- use `SIDECUT` rather than `PRODUCT` when the source is specifically an intermediate unit sidecut/outlet stream rather than a final product.

## Step 9 — Description construction

The description must describe only the current rule.

Bad:

```text
6101原油罐库存下限为1325吨，库存上限为7579吨。
```

inside a MIN-only rule.

Good:

```text
6101原油罐安全液位下限为2.5米。
```

Description requirements:

- mention the correct entity;
- mention only the value(s) represented in this rule;
- state `下限` / `上限` only if the source explicitly supports it;
- for derived values, include wording such as `由……计算得到`;
- do not introduce explanations unsupported by source files.

## Step 10 — Parameter construction

Prefer one independent parameter per rule.

Examples:

```json
"parameters": {
  "inventory_level_min": {
    "value": 2.5,
    "unit": "m"
  }
}
```

```json
"parameters": {
  "sidecut_spg": {
    "value": 0.7352,
    "unit": null
  }
}
```

A rule may contain multiple parameters only when they are inseparable parts of one relationship and the project schema already supports that representation. Default to atomicity.

# Category-specific guidance

## A. Tanks / crude inventory

Direct facts may include:
- safe level lower bound;
- safe level upper bound;
- volume;
- diameter;
- initial level;
- meter factor;
- density.

Do not confuse safe level bounds with mass-inventory bounds.

If mass bounds are calculated from level × meter factor, treat them as derived.

## B. CDU / atmospheric units

For sidecut yield and sidecut property data:

- preserve crude oil dimension;
- preserve sidecut dimension;
- preserve property dimension;
- use `CDUko` / `CDUkoq` when the mapping is defined;
- do not use YCO/RCO as min/max;
- do not automatically add sidecuts that exist in an assay table but are not mapped to the current CDU configuration.

## C. Secondary processing units

Distinguish:

- direct load parameters;
- direct maximum processing load;
- load factors;
- fixed sidecut yields;
- fixed outlet/sidecut properties;
- mode-dependent data.

If mode `m` is required by the formal model but absent from the source, do not fabricate a mode.

For outlet properties, prefer `SIDECUT_PROPERTY` naming unless the source explicitly defines the stream as a final product.

## D. Blending

Separate:
- allowed components;
- component-ratio lower bound;
- component-ratio upper bound;
- component properties;
- calculation relationship;
- final product quality specification.

Do not pack all of these into one rule.

If blending topology is unavailable, do not invent unit/stream relationships beyond established project conventions.

# Final validation

Before writing output, perform all checks in `references/validation_checklist.md`.

The extraction is not complete until all hard validation checks pass.

# Response behavior

When completing an extraction task:

1. write the result JSON files;
2. briefly report file names and rule counts;
3. mention only unresolved ambiguities that materially affect correctness;
4. do not generate extra documentation unless requested.

For modification/review tasks, preserve the user's existing project structure unless explicitly asked to redesign it.
