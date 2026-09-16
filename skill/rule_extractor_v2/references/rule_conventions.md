# Rule Conventions

## 1. Core principle

A rule is an **atomic, source-grounded fact**.

Preferred form:

```text
one entity/relationship
+ one property or bound
+ one value
= one rule
```

## 2. Source vs derived

### Source rule

A source rule is directly readable from the original source.

Example:

```text
6101安全液位下限 = 2.5 m
```

### Derived rule

A derived rule requires arithmetic or another transformation.

Example:

```text
6101库存质量下限 = 2.5 × 530 = 1325 t
```

Do not represent a derived value as a direct source fact.

## 3. Bounds

Use `MIN` / `MAX` only if the source has bound semantics.

Valid:
- 比例下限 lo
- 比例上限 hi
- 最小加工能力
- 最大加工能力
- 安全液位下限
- 安全液位上限

Invalid reasons for creating bounds:
- two crude oil columns;
- two products;
- two operating modes;
- two observed values;
- fixed value duplicated as min=max.

## 4. Entity dimensions

### CDU yield

```text
U × K × O
```

Example:

```text
300万吨年常压装置.NK1.YCO
```

### CDU property

```text
U × K × O × Q
```

Example:

```text
300万吨年常压装置.NK1.YCO.SPG
```

## 5. Human-readable description

Descriptions should be concise and factual.

Good:

```text
300万吨年常压装置加工YCO时，300_常石脑油侧线比重为0.7352。
```

Bad:

```text
300万吨年常压装置的300_常石脑油侧线比重下限为0.7352，上限为0.7365。
```

when 0.7352 and 0.7365 actually belong to YCO and RCO.

## 6. Stable naming vocabulary

Prefer:

```text
INVENTORY_LEVEL
PROCESSING_CAPACITY
SIDECUT_YIELD
SIDECUT_PROPERTY
SIDECUT_FLOW
BLEND_RECIPE
BLEND_COMPONENT
PRODUCT_RON
PRODUCT_CN
```

Avoid ambiguous names like:

```text
BOUND
PRODUCT_PROPERTY
FEED_BOUND
```

when more precise semantics are available.
