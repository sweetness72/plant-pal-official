# Drying model assumptions

Single source of truth for the hard-coded thresholds and rules in
`core/drying_model.py` and the learning logic in `core/db.py::log_watered`.

## Drying model assumptions (at a glance)

Read this block first; sections below spell out the same rules with tables and edge cases.

- **Pot size breakpoint:** `pot_diameter_inches < 6` shortens the interval by 1 day (smaller pot → dries faster). A 6" pot is *not* “small” (`<` is strict).
- **Light:** only **`BRIGHT`** applies a modifier (−1 day). **`LOW`** and **`MEDIUM`** behave the same (no change).
- **Pot material:** only **`TERRACOTTA`** applies a modifier (−1 day). **`PLASTIC`** and **`CERAMIC`** behave the same (no change).
- **Moisture preference:** read from the plant’s **`CareTemplate`** via `Plant.get_moisture_preference()`. If the plant has **no template**, the model uses **`EVENLY_MOIST`** and **7** default base days (not “no preference”).
- **Default fallback (no template):** `EVENLY_MOIST`, `default_drying_days == 7` (see `core/schema.py::Plant`).
- **Coefficient clamp:** `drying_coefficient` in **`[0.5, 1.5]`**, enforced on every `log_watered` update.
- **On-time window (streaks):** watering counts as on-time if `dry_date - 1 <= watered_date <= dry_date + 1` (inclusive on both sides).
- **Minimum drying days (pre-coefficient):** `max(2, base + sum(modifiers))` before multiplying by the coefficient. So the *adjusted* sum is never below 2 days; the final effective interval is still `adjusted * coefficient` (a low coefficient can still yield a very short *effective* float before rounding to the calendar).
- **Rounding — days to next dry date:** `int(round(effective))` where `effective` is the float days from `effective_drying_days`. Uses **Python 3 “banker’s” rounding** (ties to even), e.g. `round(2.5) == 2`, `round(3.5) == 4`.
- **Rounding — water amount (oz):** table lookup, then for `DRY_BETWEEN` / `MOIST_OFTEN` use **integer truncation** `int(oz * factor)` (not banker’s), with a floor of 1 oz for the dry case where applicable. See §3.

## Quick reference

| Rule                         | Value                                                                  |
|------------------------------|------------------------------------------------------------------------|
| Pot size breakpoint          | `pot_diameter_inches < 6` → -1 day (strict less-than; a 6" pot is not "small") |
| Light                        | Only `BRIGHT` modifies (-1 day); `LOW` and `MEDIUM` are identical      |
| Pot material                 | Only `TERRACOTTA` modifies (-1 day); `PLASTIC` and `CERAMIC` are identical |
| Moisture preference          | Read from the plant's template only; there is no per-plant override    |
| Default when no template     | `EVENLY_MOIST` (modifier 0), `default_drying_days` = 7                 |
| Coefficient clamp            | `[0.5, 1.5]` enforced on every write in `log_watered`                  |
| On-time window               | `dry_date - 1 <= watered_date <= dry_date + 1` (inclusive both sides)  |
| Pre-coefficient day floor    | `max(2, base + modifiers)` — note the floor is applied **before** multiplying by the coefficient, so a plant with `coef=0.5` can still end up with an effective interval of 1.0 day |
| Rounding — days-to-date      | `int(round(days))` — Python 3 banker's rounding (half-to-even): `round(2.5)==2`, `round(3.5)==4` |
| Rounding — water amount      | `int(oz * 0.8)` for `DRY_BETWEEN`, `int(oz * 1.2)` for `MOIST_OFTEN` — integer truncation toward zero, NOT banker's rounding |
| Rounding — coefficient       | None. The coefficient is stored as an unrounded float; the `coef == 1.0` equality used by the CHECK gate depends on this |


This file exists so that:

1. Product changes to any threshold are a deliberate, reviewable edit.
2. Tests in `tests/test_known_issues.py` and `tests/test_scenarios.py`
   can reference a canonical list instead of re-deriving numbers.
3. Design decisions that look like bugs (but aren't) have a named
   home.

All numbers below are the values as of the current commit.

---

## 1. Drying interval

The effective interval (days) between waterings for a plant is:

```
adjusted = base + pot_size_mod + material_mod + light_mod + moisture_mod
adjusted = max(2, adjusted)            # clamp floor
effective = adjusted * drying_coefficient
```

`base` comes from the plant's `CareTemplate.default_drying_days`; if
the plant has no template the base is **7**.

### 1.1 Modifiers (each is an integer offset to `adjusted`)

| Factor          | Condition                           | Modifier |
|-----------------|-------------------------------------|----------|
| Pot size        | `pot_diameter_inches < 6`           | **-1**   |
| Pot size        | `pot_diameter_inches >= 6`          | 0        |
| Pot material    | `PotMaterial.TERRACOTTA`            | **-1**   |
| Pot material    | `PLASTIC` or `CERAMIC`              | 0        |
| Light           | `LightLevel.BRIGHT`                 | **-1**   |
| Light           | `LOW` or `MEDIUM`                   | 0        |
| Moisture pref   | `MoisturePreference.MOIST_OFTEN`    | **-1**   |
| Moisture pref   | `EVENLY_MOIST`                      | 0        |
| Moisture pref   | `DRY_BETWEEN`                       | **+1**   |

Known coarseness (see model limitations L1–L3 in the audit):

* Pot size has a single breakpoint at 6"; a 24" pot behaves like an 8" pot.
* `LOW` and `MEDIUM` light are treated identically.
* `PLASTIC` and `CERAMIC` are treated identically.

### 1.2 Clamps

* `adjusted` is floored at **2 days** — a plant can never be predicted
  to dry in less than 2 days, regardless of how aggressively modifiers
  stack.
* `drying_coefficient` is clamped to **[0.5, 1.5]** by `log_watered` on
  every update. Cacti and fast-drying tropicals may effectively
  saturate this range.
* `int(round(effective))` rounds to the nearest day using Python's
  banker's rounding (ties go to even).

---

## 2. Action emission

`generate_action_for_plant(plant, today)` returns:

| Condition                                       | Output                                         |
|-------------------------------------------------|------------------------------------------------|
| `plant.last_watered_date is None`               | `WATER` with note **"First watering — start your timer"** |
| `today >= predicted_dry_date`                   | `WATER` with note "Water at soil line"         |
| `today == predicted_dry_date - 1` AND `drying_coefficient == 1.0` | `CHECK` with note "Check soil 2\" down" |
| otherwise                                       | `None` (silence)                               |

Notes:

* `predicted_dry_date` uses `last_watered_date`; if that's `None` it
  falls back to `created_at`. `add_plant` always sets `created_at`,
  so the `if dry_date is None` branch inside `log_watered` is
  unreachable in practice (see bug B1).
* Priority is a fixed `0` for WATER and `2` for CHECK. The UI owns
  any re-ordering.
* There is **no overdue escalation**. An action 30 days late looks
  identical to an action due today (see limitation L7).
* `CHECK` is only emitted while the plant's `drying_coefficient`
  equals exactly `1.0` (strict float equality). This is an intentional
  "has any learning happened yet?" gate — once the model has opinions
  about this plant, the app trusts them silently.

---

## 3. Water-amount table

`water_amount_oz(plant)` uses a fixed lookup by pot diameter:

| Pot diameter (inches) | Recommended oz |
|-----------------------|----------------|
| 4                     | 2              |
| 5                     | 3              |
| 6                     | 4              |
| 8                     | 6              |
| 10                    | 8              |
| 12                    | 10             |
| 14                    | 12             |
| 16                    | 14             |
| 18                    | 16             |
| 20                    | 18             |
| 24                    | 22             |

Rules around the table:

* Values below the smallest key are clamped to the 4" row.
* Values above the largest key are clamped to the 24" row.
* **Between keys, the NEXT HIGHER key is chosen** (not nearest). A 7"
  pot gets 6 oz (8" row), not 4 oz (6" row). This is intentional — the
  app prefers over-watering by a little to under-watering.
* `DRY_BETWEEN` plants multiply by 0.8 (int, floor at 1).
* `MOIST_OFTEN` plants multiply by 1.2 (int, truncated).

---

## 4. Learning rule (`log_watered`)

After the user logs a watering, the coefficient is nudged based on the
`soil_feeling` answer:

| Feeling         | Effect                                                   |
|-----------------|----------------------------------------------------------|
| `"wet"`         | `coef = min(1.5, coef + 0.1)`    — dry slower next time  |
| `"dry"`         | `coef = max(0.5, coef - 0.1)`    — dry faster next time  |
| `"ok"` (< 1.0)  | `coef = min(1.0, coef + 0.05)`   — drift toward 1.0      |
| `"ok"` (> 1.0)  | `coef = max(1.0, coef - 0.05)`   — drift toward 1.0      |
| `"ok"` (== 1.0) | unchanged                                                |
| anything else   | silently ignored                                         |

Side effects of the `±0.1` / `±0.05` asymmetry:

* `wet → ok` lands on `1.05`, never back at exactly `1.0`. Combined
  with the CHECK gate in §2, a plant that has ever received a single
  `"wet"` followed only by `"ok"` feedback will never receive another
  CHECK action.
* `wet → dry` DOES land on exactly `1.0` (floating-point safe), so
  CHECK can resume.

---

## 5. Streak and badges

`log_watered` maintains `current_streak`, `longest_streak`, and
`badges_earned`:

* **On-time window**: `dry_date - 1 <= watered_date <= dry_date + 1`
  (inclusive). Anything outside ±1 day resets `current_streak` to 0.
* **First watering after `add_plant`:** sets streak to **1** on the first
  logged watering (B1 — fixed). See `test_known_issues.py::TestStreakBugFixed`.
* **Longest streak**: monotonic high-water mark, never decreases.
* **Badge milestones** (hard-coded in `BADGE_MILESTONES`):
  `[3, 5, 10, 25, 50, 100, 250, 300, 500]`.
  A badge is appended the first time `current_streak >= milestone`.
  Missing a watering does NOT revoke a badge; it only resets the
  streak counter.

---

## 6. Things that are intentionally **not** modeled

These are model limitations, not bugs. They will be revisited when the
engine moves past v1.

* Season / month of year
* Ambient temperature and humidity
* Recent rainfall (even for "outdoor" templates)
* Plant size, root-bound state, or time since repot
* Co-watering of plants in the same room
* User timezone (everything is server-local `date.today()`)
