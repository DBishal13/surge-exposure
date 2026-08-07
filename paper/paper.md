# SurgeExposure: An Open, Reproducible Pipeline for Building-Level Storm-Surge Exposure Scoring, with a Validation Study Against Real NFIP Losses

**Status:** informal research note / technical report produced alongside the
[SurgeExposure](../README.md) open-source project. Not peer-reviewed. The
system description (§2) documents what is actually implemented and
verifiable in this repository; the validation study (§4 onward) is a small,
directional case study — its Limitations section (§8) is not boilerplate,
it is load-bearing, and should be read before trusting any correlation
number in §6.

---

## Abstract

*[Results/Discussion/Conclusion to be finalized once the live validation run
completes — see §6.]* Most publicly visible flood/storm-surge exposure
tools are either closed commercial systems (First Street Foundation, Fathom
Global, FEMA's Risk Rating 2.0) whose scoring methodology and validation are
disclosed only partially, or research prototypes that stop at a demo map
without ever checking the score against outcomes. This report documents
SurgeExposure, an open, fully reproducible pipeline that scores building
footprints for storm-surge and flood exposure using only public data (NOAA
SLOSH, NOAA NWM, Overture Maps) and a transparent, explainable scoring
heuristic, and then — the part most comparable tools skip in public — checks
that heuristic against real losses. Using FEMA's OpenFEMA NFIP claims API,
we compare SurgeExposure's building-level exposure scores against real flood
insurance claims for Lee County, FL following Hurricane Ian (2022), at the
0.1° grid-cell resolution NFIP's privacy rounding permits. We report Pearson
correlations between mean exposure score and both claim frequency and mean
claim severity per cell, and discuss what a lightweight, explainable
heuristic score can and cannot be trusted to predict.

## 1. Introduction

### 1.1 Motivation

A growing number of open-source and consumer-facing tools — including this
project — compute a per-building "exposure score" or "risk score" from
publicly available hazard layers (storm-surge rasters, flood-zone maps,
inundation extents) without ever checking the score against what actually
happened to real buildings in a real storm. That is a reasonable MVP
shortcut for a demo, but it leaves an open question every such tool
inherits silently: **does the score mean anything?**

At the same time, the systems that *do* validate rigorously — First Street
Foundation's Flood Factor, Fathom Global's Risk Scores, FEMA's own Risk
Rating 2.0 — are closed: proprietary models, licensed data, and validation
claims that are asserted ("peer-reviewed," "validated against historic
flood reports") but not independently reproducible by a reader (§3.1). There
is a gap between "open but unvalidated" and "validated but closed." This
project sits in the first category by default; this report is an attempt to
narrow that gap without pretending to close it — SurgeExposure will not
match a commercial catastrophe model's rigor, but it can be honest, public,
and checked.

### 1.2 Contributions

1. **A fully open, live-data exposure-scoring pipeline** (§2): building
   footprints, storm-surge depth, and active-flood extent, all fetched from
   public APIs with no paid data, no proprietary model, and a scoring
   formula that fits in one line of code.
2. **A validation study** (§4-§7) checking that pipeline's output against
   real NFIP flood-insurance claims for a real, severe storm-surge event,
   using only public data end-to-end — including the FEMA claims API client
   built for this study (`data/nfip.py`).
3. **A documented methodological failure and fix** (§5.3): an early version
   of the validation undercounted its own building coverage by a factor of
   ~7 because of an unordered `LIMIT` query, discovered by inspecting the
   data rather than trusting the first result. We keep this in the report
   because catching it changes what the results in §6 can support, and
   because it is a concrete illustration of why "run the pipeline once and
   report the number" is not sufficient rigor even for a small study.
4. **An honest limitations account** (§8) — most importantly, that any
   result here is an *ecological correlation* at ~0.1° grid resolution, not
   a building-level finding, because NFIP's public claims data is
   privacy-rounded and cannot support anything finer.

## 2. System Design: SurgeExposure

This section documents the system being validated, so the validation study
in §4 onward can be read against a concrete implementation rather than a
description of intent. Everything below is implemented in this repository
today; see the linked source files.

### 2.1 Architecture Overview

SurgeExposure is a Python pipeline (`pipeline.py`) fronted by a FastAPI
service (`api/`), with a small set of one-off analysis scripts (`scripts/`)
used to build a static demo and run this validation study. There is no
proprietary model and no licensed dataset anywhere in the stack:

```
data/overture.py        Overture Maps building footprints (live, S3 GeoParquet)
data/storm_surge.py      NOAA SLOSH MOM storm-surge raster (cached once, ~1.6GB)
data/flood_inundation.py NOAA NWM active flood-inundation extent (live, hourly)
data/nfip.py              FEMA OpenFEMA NFIP claims (live) -- built for this study
        |
        v
pipeline.py    -- overlays the three hazard layers into exposure_score / exposure_category
        |
        v
api/main.py (FastAPI)  -- /exposure (GeoJSON), /map (Folium), /geocode, /locations
api/cache.py             -- disk-backed cache, keyed by (bbox, limit), 6h TTL
        |
        v
Leaflet frontend (live) + static GitHub Pages showcase (8 precomputed regions)
```

### 2.2 Data Sources

- **Building footprints — Overture Maps.** Queried live via DuckDB's
  `spatial` and `httpfs` extensions directly against Overture's public
  GeoParquet on S3 (`data/overture.py`). The release version is resolved
  dynamically from Overture's STAC catalog on every query, so the pipeline
  never goes stale against a hardcoded release. Overture's `bbox` struct
  column lets DuckDB push the spatial filter down to the row-group level —
  no local download, no pre-indexing.
- **Storm-surge depth — NOAA SLOSH MOM.** The National Hurricane Center's
  "Maximum of MEOWs" composite storm-surge raster (Texas-to-Maine, 8-bit
  class resolution, ~1.6 GB zipped) is downloaded once and cached locally
  (`data/storm_surge.py`), then sampled at each building's centroid. MOM is
  a *worst-case envelope across many modeled hypothetical storms*, not a
  reconstruction of any specific real event — a distinction that matters
  for how §6's results should be read (a claim asking "did this exact
  storm's surge match the score" would need a different, event-specific
  SLOSH product; see §9).
- **Active flood extent — NOAA NWM.** Live, hourly-updated
  analysis-and-assimilation flood-inundation-mapping polygons from NOAA's
  HydroVIS ArcGIS services (`data/flood_inundation.py`), intersected against
  building footprints.
- **Ground truth for validation — FEMA NFIP claims.** Built specifically for
  this study (`data/nfip.py`): a client for FEMA's OpenFEMA NFIP claims API
  (v3), described fully in §5.

### 2.3 The Exposure Scoring Model

The scoring formula (`pipeline.py`) is deliberately simple and legible
rather than fit to data:

```
exposure_score = 0.6 * min(surge_ft, 20) / 20 + 0.4 * flood_active
```

mapped to five categories by fixed thresholds: `severe` (≥0.75), `high`
(≥0.5), `moderate` (≥0.25), `low` (>0), `none` (0). The 60/40 weighting and
the thresholds were chosen for explainability — a reader can reconstruct a
building's score from its two inputs without a model card — not calibrated
against any outcome data. That is precisely the gap this report's
validation study probes.

### 2.4 Serving Layer: API, Caching, and Latency

The FastAPI service (`api/main.py`) exposes `/exposure` (GeoJSON) and `/map`
(a server-rendered Folium map), plus `/geocode` (free-text place lookup via
OpenStreetMap Nominatim) and `/locations` (hand-picked demo presets). A
live query is dominated by the Overture GeoParquet scan (~35-40s cold); a
disk-backed cache keyed by `(bbox, limit)` with a 6-hour TTL (`api/cache.py`)
brings a repeat request for the same area down to ~60ms. The TTL is a
deliberate trade: NWM flood extent updates hourly, but this is a
demonstration system, not an operational one, so a few hours of staleness
is an acceptable price for not re-running a 35-40s query on every repeat
visit — an explicit design decision, not an oversight (see the comment in
`api/cache.py`).

### 2.5 Frontend: Interactive Map and Static Showcase

Two frontends exist, deliberately serving different purposes:

1. **The live app** (`api/static/index.html`) — search any address, hit the
   live API, see buildings colored by exposure category on a Leaflet map.
   Meant for local/self-hosted use given the live backend it depends on.
2. **A static GitHub Pages showcase** (`docs/`) — eight hurricane-prone
   coastal regions (South Beach Miami, Fort Myers Beach, French Quarter New
   Orleans, Galveston Seawall, and others) precomputed once
   (`scripts/precompute_regions.py`) into static GeoJSON + a colorized
   surge-depth PNG overlay per region, requiring no backend at all. This is
   the version most viewers actually reach, since it needs no
   infrastructure to host.

### 2.6 Deployment

A Docker image exists (`Dockerfile`, `docker-compose.yml`) for the live
API. The 1.6GB SLOSH raster is fetched lazily into a named volume rather
than baked into the image, so it survives container rebuilds without
bloating image size or requiring it at build time.

### 2.7 Testing Philosophy

Unit tests (`tests/`) validate the scoring/categorization logic and
raster-sampling against synthetic data with all live network calls mocked
via `monkeypatch` — they run fast and offline, and are the tests that ran
green throughout this study's development (§5.3's bug was *not* caught by
these tests, since they test the scoring math, not the live Overture query
behavior — a limitation of the test suite worth naming plainly rather than
implying the tests would have caught it).

## 3. Related Work

### 3.1 Commercial and Institutional Flood Risk Scoring Systems

SurgeExposure is not the first system to compute a property-level flood
risk score. It differs from the systems below primarily in *openness*, not
in modeling sophistication — these are professionally built and, by their
own account, validated at a scale this report cannot match (§8).

| System | Access | Core data | Output | Validation disclosure |
|---|---|---|---|---|
| **SurgeExposure** (this project) | Open source, free, self-hostable | Overture Maps, NOAA SLOSH, NOAA NWM | Building-level 0-1 score, 5 categories | This report — full methodology and code public |
| **First Street Foundation Flood Factor** | Free lookup (consumer), licensed bulk data | USGS DEMs/NED, proprietary flood model, "80+ experts" | Property-level 1-10 score | Asserted peer-reviewed basis; underlying validation code/data not public |
| **FEMA Risk Rating 2.0** | Public methodology PDF; used internally for NFIP pricing | FEMA mapping + commercial catastrophe models, building characteristics | Per-policy premium, not an exposed public "score" | Methodology document public; underlying commercial model internals are not |
| **Fathom Global Risk Scores** | Commercial/institutional (API, portal) | Fathom Global Flood Map (fluvial/pluvial/coastal) | 0-1,000,000 relative risk *or* 0-100 category | Claims peer-reviewed academic basis; specific validation datasets not public |

The pattern across the three commercial/institutional systems: real
scientific grounding is claimed, but the validation itself — the actual
comparison against observed losses, with numbers a reader can check — is
not published in a form an outside reader can reproduce. SurgeExposure is
strictly less sophisticated than any of these (§8), but §4 onward is an
attempt to make the *validation itself*, not just the score, fully public.

### 3.2 Storm-Surge Model Validation

NOAA's SLOSH (Sea, Lake, and Overland Surges from Hurricanes) model, the
surge layer this project uses, has itself been validated against observed
high-water marks in post-storm studies; NOAA reports roughly 20% error for
significant surges, with better accuracy above ~12-13 ft of surge ([NOAA
National Hurricane Center, Storm Surge Unit](https://www.nhc.noaa.gov/surge/ssu.php);
[NOAA National Storm Surge Risk Maps v4](https://www.nhc.noaa.gov/nationalsurge/)).
That validation is against *surge itself* (a physical quantity) — it says
nothing about how well a downstream *exposure heuristic built on top of*
SLOSH tracks *financial loss*, which is the question §4 asks.

### 3.3 NFIP Claims as a Research Resource

FEMA's public release of ~2.5 million redacted NFIP claims (from 1970
onward) opened claims-level flood research to outside researchers ([Journal
of Real Estate Literature overview](https://www.tandfonline.com/doi/abs/10.1080/09277544.2021.1876435)).
Shin, Cocke & Kim (2022) audited NFIP claims hazard fields for Florida
specifically and found the "cause of loss" and event-attribution fields are
frequently incomplete or wrong, requiring correction against independent
storm-track data (HURDAT2) before the claims data can be trusted for hazard
attribution ([*Applied Sciences* 12(7), 3537](https://www.mdpi.com/2076-3417/12/7/3537)).
This study does *not* perform that correction — claims are used as raw
counts/payouts within a county and time period, not attributed to a
specific storm beyond what `dateOfLoss` implies — which is one more reason
to read §6's numbers as directional (§8).

### 3.4 Depth-Damage Functions and Loss Modeling Limits

Wing, Pinter, Bates & Kousky (2020), analyzing ~2 million NFIP claims,
found that **observed flood losses are not a simple monotonic function of
inundation depth** — the standard federal depth-damage curves performed so
poorly that a flat mean damage value predicted losses better than the
curves, and vulnerability varied substantially by geography and building
vintage ([*Nature Communications* 11, 1444](https://doi.org/10.1038/s41467-020-15264-2)).
This matters directly for §2.3's scoring formula: if depth alone is a weak
predictor of loss *magnitude* nationally, a heuristic that leans 60% on
depth should not be assumed to predict severity well either — it has to be
checked, which is exactly what §4-§6 do.

### 3.5 Catastrophe Model Validation Methodology

Professional catastrophe models are themselves benchmarked against NFIP
claims: Dusseau, Zobel & Schwalm, comparing seven commercial/federal flood
catastrophe models' loss estimates against NFIP claims (1978-2024,
normalized to 2022 exposure), found three NFIP-used models landed within 4%
of historical losses nationally, while others diverged by 2x or more
regionally ([*Journal of Catastrophe Risk and Resilience* 4(1)](https://journalofcrr.com/research/04-01-dusseau-et-al/)).
That validation happens at state/national scale with normalized,
multi-decade data. §4-§6 attempt a structurally similar idea — model score
vs. real claims — at a scale several orders of magnitude smaller (one
county, one event, tens of grid cells), which is precisely why its results
can only be directional (§8).

### 3.6 Spatial Aggregation and the Modifiable Areal Unit Problem

Because NFIP claim coordinates are rounded to 0.1° before release, any
comparison against them is necessarily an *ecological correlation* — a
relationship between area-aggregated quantities, not individual buildings.
This is a textbook instance of the Modifiable Areal Unit Problem (MAUP):
statistical relationships computed over arbitrarily-drawn areal units can
shift, and sometimes reverse, under a different unit size or boundary
placement (Openshaw, 1984; overview in [ScienceDirect: Modifiable Areal Unit
Problem](https://www.sciencedirect.com/topics/earth-and-planetary-sciences/modifiable-areal-unit-problem)).
An ecological correlation is not proof of an individual-level relationship
— this is the single most important methodological caveat for everything in
§6.

## 4. Research Question

> **RQ:** At the 0.1°-grid-cell level, does SurgeExposure's building-level
> `exposure_score` correlate with real NFIP flood-claim outcomes — claim
> frequency and mean claim severity — in Lee County, FL following Hurricane
> Ian?

Two directional hypotheses, tested independently since frequency and
severity are different questions (§3.4 — depth relates to severity in
complex, non-monotonic ways, which gives no a priori reason to expect it
predicts frequency and severity equally well):

- **H1:** mean `exposure_score` per grid cell is positively correlated with
  claim *count* per cell.
- **H2:** mean `exposure_score` per grid cell is positively correlated with
  mean claim *payout* per cell.

## 5. Validation Methodology

**Study area.** Lee County, FL (FEMA county code `12071`) — Fort Myers
Beach, Sanibel, Cape Coral, Fort Myers — struck directly by Hurricane Ian's
storm surge in September 2022.

**Exposure scores.** Computed by the pipeline described in §2.2-§2.3.

**Claims.** Fetched live from FEMA's OpenFEMA NFIP claims API (v3,
`fema.gov/api/open/v3/NfipClaims`), filtered to `state='FL'` and
`countyCode='12071'`, all available years (`data/nfip.py`). A small number
of claims (12 of 48,117, ~0.02%) carry coordinates well outside any
plausible Lee County location (e.g. latitude 29.4°, off the Florida
panhandle) and are dropped as mis-coded records before analysis —
consistent with the data-quality issues Shin et al. (2022) document for
this exact dataset (§3.3).

**Grid-cell join.** Both sides are snapped to a 0.1° lat/lon grid (matching
NFIP's own privacy rounding) and aggregated per cell: mean `exposure_score`
and building count on one side, claim count and mean claim payout
(building + contents, net of the small number of null payout fields) on the
other. Cells are joined with an inner join — only cells with *both* scored
buildings and claims contribute to the correlation.

**5.3 Building sampling — and a bug worth documenting.** An earlier version
of this script queried buildings once, over the whole county bounding box,
with a flat row-count cap (`LIMIT 5000`, no `ORDER BY`). That returned only
5 overlapping grid cells, and inspection showed why: DuckDB's scan order
over Overture's partitioned GeoParquet is not spatially uniform, so the
first 5,000 matching rows all came from one coastal strip, never reaching
the rest of the county. The county's true extent (derived from the claims
data itself, after outlier filtering) contains **~420,000** buildings — too
many to score in full for a validation script — so the fixed version
queries buildings **per claim grid-cell**: a small 0.1°×0.1° Overture query,
capped at 500 buildings, run once for each of the county's claim-bearing
grid cells (37 cells after outlier filtering). This bounds total work while
guaranteeing every claim cell gets a fair chance at building coverage. (See
`scripts/validate_exposure_bins.py` and its git history for the
before/after.)

**Statistic.** Pearson correlation coefficient (`numpy.corrcoef`) between
mean exposure score and each of claim count / mean payout, across
overlapping grid cells. No significance test is reported — see §8 on why
one would be misleading at this *n*.

**Reproducibility.** Every input is public and the pipeline is fully
scripted: `python scripts/validate_exposure_bins.py` reproduces §6 end to
end (requires the cached SLOSH raster and live network access — see the
main [README](../README.md#setup)).

## 6. Results

*[PENDING — the live per-cell validation run was still in progress at the
time this section was drafted. This section will be filled in with the
actual grid-cell table, correlation coefficients, and updated chart the
moment that run completes — no placeholder numbers are reported here.]*

## 7. Discussion

*[To be completed alongside §6.]* The discussion will interpret whatever
H1/H2 pattern the real numbers show against §3 — in particular, whether
depth-driven severity prediction (plausible given Wing et al.'s finding
that depth relates to damage in complex, non-flat ways, §3.4) outperforms
depth-driven frequency prediction (which is more about whether water
reached a structure at all than how graded the exposure is), and what that
would or would not imply for reweighting §2.3's 60/40 heuristic.

## 8. Limitations

However §6 turns out, the following hold regardless and bound how much
weight these results can carry:

1. **Ecological correlation, not individual-level.** Per §3.6 (MAUP), a
   cell-level relationship does not establish that any individual exposed
   building was more or less likely to claim or to claim big. Reversal at a
   different aggregation size is possible in principle and untested here.
2. **Small *n*.** The number of overlapping grid cells is on the order of
   tens, not hundreds — nowhere near enough for a credible significance
   test, let alone for reweighting a production scoring model. Every
   correlation reported is a hint, not a finding.
3. **Spatial autocorrelation.** Neighboring 0.1° cells are not independent
   observations (adjacent coastal cells share storm track, elevation, and
   construction era) — the effective sample size for inference is smaller
   than the raw cell count, which a naive Pearson *r* does not account for.
4. **Single county, single event.** Lee County under Hurricane Ian is one
   storm, one coastline, one building stock. Nothing here generalizes to a
   different storm, coastline type, or state without independent
   replication.
5. **Claims data quality.** Per Shin et al. (2022, §3.3), NFIP
   hazard-attribution fields for Florida are known to be
   incomplete/incorrect in places; this study did not perform their
   correction procedure, and claims are not restricted to Ian
   specifically — some `dateOfLoss` values in the dataset predate 2022,
   folding in unrelated flood events within the same cells.
6. **No control for building value, age, or elevation.** Wing et al. (2020,
   §3.4) found these materially affect loss given depth. `exposure_score`
   doesn't model them, and neither does this validation.
7. **SLOSH MOM is a worst-case envelope, not an Ian-specific reconstruction**
   (§2.2). The surge input to `exposure_score` was never intended to
   reproduce this specific storm's actual water levels — a genuinely
   Ian-specific validation would need an event-specific SLOSH/P-Surge run,
   which is future work (§9), not what this study used.
8. **This system is far less sophisticated than the commercial systems in
   §3.1**, which incorporate elevation, construction type, and
   decades of multi-hazard modeling. This report does not claim
   SurgeExposure's heuristic competes with those systems — only that,
   unlike them, its validation attempt is fully public.

## 9. Future Work

- Replicate across multiple counties/coastlines and multiple storm events
  before treating any correlation as informative for reweighting
  `SURGE_WEIGHT`/`FLOOD_WEIGHT` in `pipeline.py`.
- Restrict claims to a tight post-Ian date window to reduce the
  unrelated-event contamination noted in Limitation 5.
- Use an event-specific SLOSH/P-Surge advisory run for Ian instead of the
  MOM worst-case composite (Limitation 7), for a genuinely storm-specific
  comparison.
- Incorporate `ratedFloodZone` and elevation as additional predictors
  alongside surge depth, informed by Wing et al.'s finding that depth alone
  is a weak severity predictor.
- If a future collaboration secures access to non-redacted (building-level)
  claims coordinates under a FEMA data-use agreement, redo this as an
  actual per-building join instead of a grid-cell ecological correlation.

## 10. Conclusion

*[To be completed alongside §6.]*

## References

- Dusseau, D., Zobel, Z., & Schwalm, C.R. (2026). Validation and Comparison
  of U.S. Loss Estimates from Catastrophe Flood Models. *Journal of
  Catastrophe Risk and Resilience*, 4(1).
  https://journalofcrr.com/research/04-01-dusseau-et-al/
- FEMA. National Flood Insurance Program Risk Rating 2.0: Methodology and
  Data Sources.
  https://www.fema.gov/sites/default/files/documents/FEMA_Risk-Rating-2.0_Methodology-and-Data-Appendix__01-22.pdf
- First Street Foundation. Flood Model Methodology — Calculating
  property-level risk.
  https://help.firststreet.org/hc/en-us/articles/1500000359741-Flood-Model-Methodology-Calculating-property-level-risk
- Fathom Global. Risk Scores — flood risk metrics.
  https://www.fathom.global/product/global-flood-map/risk-scores/
- NOAA National Hurricane Center. Storm Surge Unit — model verification and
  post-storm analysis. https://www.nhc.noaa.gov/surge/ssu.php
- NOAA National Hurricane Center. National Storm Surge Risk Maps, Version 4.
  https://www.nhc.noaa.gov/nationalsurge/
- Openshaw, S. (1984). *The Modifiable Areal Unit Problem*. Concepts and
  Techniques in Modern Geography 38. Geo Books.
- Shin, D.W., Cocke, S., & Kim, B.-M. (2022). A Systematic Revision of the
  NFIP Claims Hazard Data in Florida for Flood Risk Assessment. *Applied
  Sciences*, 12(7), 3537. https://www.mdpi.com/2076-3417/12/7/3537
- Wing, O.E.J., Pinter, N., Bates, P.D., & Kousky, C. (2020). New insights
  into US flood vulnerability revealed from flood insurance big data.
  *Nature Communications*, 11, 1444.
  https://doi.org/10.1038/s41467-020-15264-2

---

*Part of the [SurgeExposure](../README.md) project. Code, data pipeline, and
this document are all public — see the repository root for setup
instructions.*
