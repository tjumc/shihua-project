# Positive and Negative Examples

## Example 1 — Real lower/upper bounds

### Source

```text
92#汽油中催化汽油比例下限 = 0.3
92#汽油中催化汽油比例上限 = 0.6
```

### Correct

Two rules:

```json
{
  "rule_id": "BLEND_RECIPE_MIN_92_GASOLINE_CAT_GASOLINE",
  "description": "92#汽油中催化汽油配方比例下限为0.3。",
  "parameters": {
    "component_mass_fraction_min": {
      "value": 0.3,
      "unit": "1"
    }
  }
}
```

```json
{
  "rule_id": "BLEND_RECIPE_MAX_92_GASOLINE_CAT_GASOLINE",
  "description": "92#汽油中催化汽油配方比例上限为0.6。",
  "parameters": {
    "component_mass_fraction_max": {
      "value": 0.6,
      "unit": "1"
    }
  }
}
```

## Example 2 — Fixed value

### Source

```text
200_催化汽油 RON = 89.3
```

### Wrong

```json
{
  "product_ron_min": {"value": 89.3},
  "product_ron_max": {"value": 89.3}
}
```

### Correct

```json
{
  "rule_id": "UNIT_SIDECUT_PROPERTY_FCC200_GASOLINE_RON",
  "description": "200万催化装置的200_催化汽油侧线辛烷值为89.3。",
  "parameters": {
    "sidecut_ron": {
      "value": 89.3,
      "unit": null
    }
  }
}
```

## Example 3 — Different crude oils

### Source

```text
NK1 SPG:
YCO = 0.7352
RCO = 0.7365
```

### Wrong

```json
{
  "sidecut_spg_min": {"value": 0.7352},
  "sidecut_spg_max": {"value": 0.7365}
}
```

### Correct

```json
{
  "rule_id": "CDU_SIDECUT_PROPERTY_300_NK1_SPG_YCO",
  "sets": [
    {
      "set_name": "CDUkoq",
      "subset_name": null,
      "element": "300万吨年常压装置.NK1.YCO.SPG"
    }
  ],
  "parameters": {
    "sidecut_spg": {
      "value": 0.7352,
      "unit": null
    }
  }
}
```

and a separate RCO rule.

## Example 4 — Source vs derived

### Source

```text
安全液位下限 = 2.5 m
米系数 = 530 t/m
```

### Direct source rules

```text
inventory_level_min = 2.5 m
meter_factor = 530 t/m
```

### Derived, not direct

```text
inventory_mass_min = 1325 t
```

Do not place 1325 t in the source layer unless the source itself contains that value.

## Example 5 — Explicit zero

### Source

```text
MTBE 硫 = 0 ppm
```

Correct:

```json
{
  "sulfur": {
    "value": 0,
    "unit": "ppm"
  }
}
```

Do not drop this because the value equals zero.

## Example 6 — Missing value

### Source

```text
YCO RON = —
RCO RON = 43.2
```

Correct:
- no YCO RON rule;
- one RCO RON rule with 43.2.

Do not drop the RCO fact just because the YCO cell is missing.
