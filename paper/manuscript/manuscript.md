---
title: "How well does a worst-case storm-surge envelope track insured losses? NOAA SLOSH MOM versus Hurricane Ian NFIP claims, USGS high-water marks and the effect of areal unit"
author: "Bishal Dhungana [affiliation, ORCID, email: to complete]"
target: "Natural Hazards and Earth System Sciences (research article). Check scope and formatting against the current author guidelines before submission."
status: "Draft manuscript, 2026-10-02. Technical report with full history: ../paper.md"
---

# Abstract

Storm-surge hazard layers are widely used as building-level exposure
proxies, but they are rarely tested in public against what storms actually
did. We test NOAA's SLOSH Maximum of Maximums (MOM) high-tide inundation
envelopes against Hurricane Ian (2022) in Lee County, Florida, using only
public data.
- **Data.** MOM depth is sampled at all 366,764 building footprints. It is
  compared with 28,616 National Flood Insurance Program (NFIP) claims for
  Ian, normalized by the 134,046 policies in force at landfall. Severity is
  measured as the damage ratio. Results are reported at block-group,
  tract and 0.1° grid scale.
- **Frequency.** Mean Category 1 MOM depth tracks the claim rate at every
  scale (block groups: *r* = 0.64, 95% spatial-bootstrap CI 0.52–0.77;
  Dutilleul-corrected *p* < 10⁻⁹).
- **Severity.** The damage ratio is tracked moderately at block-group and
  tract scale (*r* = 0.43–0.46), but not on the grid.
- **Scale and normalization reverse earlier conclusions.** With raw counts
  and payouts on the grid, severity looked robust and frequency weak. The
  apparent share of losses outside the surge zone also halves, from 36%
  to 18%.
- **Category.** Against 239 USGS high-water marks, the Category 1 envelope
  matches Ian's water best (bias +0.3 ft). The envelope for Ian's own
  landfall category, Category 4, overpredicts by 13 ft and tracks losses
  worse.
- **Observed depth.** An observed depth surface built from the marks
  predicts losses only marginally better than MOM. The limit on severity
  prediction is depth itself, not the surge map.

These are findings about insured losses, which come from a selected sample
of buildings.

# 1 Introduction

Public coastal-hazard layers are increasingly used as exposure proxies.
Planners, open-source risk tools, researchers and insurers all overlay
modeled storm-surge depth on building footprints. The most widely used
U.S. layer is the National Hurricane Center's SLOSH Maximum of Maximums
(MOM), which provides a national inundation envelope for each hurricane
category (NOAA NHC, 2026). How well such layers track the losses real
storms cause is rarely tested in public. Commercial and federal flood
models report validation, but their inputs and code are closed. Published
validation of national flood hazard models is mostly against maps or
other models: Bates et al. (2021) validated a national fluvial, pluvial
and coastal model against FEMA 1%-annual-chance maps and local models.

Studies that use NFIP claims as the reference have mostly asked where
losses fall relative to the mapped floodplain. Near Houston, substantial
losses fall outside it (Highfield et al., 2013; Blessing et al., 2017).
Claims have also been used as training labels for hazard models (Mobley
et al., 2021). A recent multi-model comparison against NFIP claims was
retracted by its authors in September 2026. It cited, among other
problems, a failure to account for low insurance take-up and the
resulting risk-selection bias (Dusseau et al., 2026, retracted). That bias
applies to any claims-based validation, this one included.

Two further problems make such validation harder than it looks.
1. **Aggregation.** NFIP claims are public only with coordinates rounded
   to 0.1° (about 11 km), but they also carry a census block-group code.
   Results computed over areal units can change with unit size and shape,
   the Modifiable Areal Unit Problem (Openshaw, 1984).
2. **Normalization.** A raw claim count measures how many insured
   buildings a unit contains as much as it measures hazard. A dollar
   payout reflects property value as well as damage.

We test SLOSH MOM against Hurricane Ian's losses in Lee County, Florida.
Ian made landfall there on 28 September 2022 as a Category 4 hurricane.
We ask three questions:
- (i) Does mean MOM depth track the claim rate and the damage ratio, and
  how do the answers change across block groups, tracts and a 0.1° grid?
- (ii) Which of the five MOM categories best matches Ian's observed water
  and losses?
- (iii) Is the weak link to severity a limit of MOM, or of depth itself?

For (iii) we build an observed depth surface from USGS high-water marks
and repeat the analysis with it. Every input is public, and one set of
scripts reproduces every number (Code and data availability).

# 2 Study area and data

**Study area.** Lee County, Florida (FIPS 12071) includes Fort Myers
Beach, Sanibel, Cape Coral and Fort Myers. Hurricane Ian brought
widespread coastal surge to the county as well as heavy rain inland.

**Storm-surge envelopes.** NOAA's national MOM product (version 4) holds
one high-tide raster per hurricane category (1–5). Each cell is the
maximum surge depth above ground across all hypothetical storms of that
category in the SLOSH basin's MEOW set (NOAA NHC, 2026). Depths come in
1-ft classes; we use each class midpoint, and 0 outside the envelope. No
leveed cells (class 99) occur in Lee County in the Category 1 raster.

**Buildings.** All 366,764 Overture Maps building footprints within the
county's 2020 census block groups are reduced to centroids.

**Claims.** OpenFEMA NFIP Redacted Claims v3 records are filtered to Lee
County and FEMA event designation FL0222 (Hurricane Ian), giving 28,616
claims.
- *Census codes:* 99.7% carry a usable block-group code (`censusGeoid`).
  The codes mix 2010 and 2020 vintages. Each of the 214 codes found only in
  2010 is mapped to the 2020 block group it overlaps most by area.
- *Damage ratio:* building damage ÷ building property value, capped at 1.
  It is available for 21,307 claims; the rest have missing or zero value.

**Policies.** OpenFEMA FIMA NFIP Redacted Policies v2 records in force on
28 September 2022: 134,046 policies, 99.96% with a usable block-group
code. Each policy is classed as inside or outside the Special Flood Hazard
Area (SFHA), which covers rated zones beginning with A or V.

**High-water marks.** These come from USGS Short-Term Network event 325.
- Of the 257 Lee County marks, 244 are coastal and of fair quality or
  better (uncertainty ±0.20 ft or less), and 239 of those report height
  above ground.
- Each mark has a surveyed water-surface elevation (NAVD88). Most (96%)
  are seed lines.

**Ground elevation.** The USGS 3DEP 1/3-arc-second (~10 m) DEM, in NAVD88.

# 3 Methods

**Exposure.** For each unit, exposure is the mean MOM depth over its
buildings. Category 1 is the main analysis. The comparison of categories
(Sect. 4.5) was carried out after the main analysis had been fixed, and
it reports all five categories.

**Outcomes.**
- *Claim rate:* Ian claims ÷ policies in force.
- *Mean damage ratio:* computed over claims with a damage ratio.
- *Mean payout:* building plus contents, in USD. Kept only to show what
  the dollar measure adds.
- *Take-up:* policies ÷ building footprints. It is only a proxy, and
  exceeds 1 where condominium policies outnumber footprints, so it is used
  only to form terciles.

**Units.** We use 2020 block groups, tracts (built by truncating
block-group codes) and a 0.1° grid (built by rounding coordinates). A unit
enters with at least 20 policies and 50 buildings. The damage-ratio
analysis additionally needs at least 5 claims with a damage ratio.

**Statistics.**
- *Correlations:* Pearson *r* and Spearman ρ.
- *Confidence intervals:* 95% intervals from a spatial block bootstrap
  with 2,000 replicates, resampling whole 0.1° blocks (0.2° for the grid).
- *Residual clustering:* Moran's *I* of OLS residuals, with
  8-nearest-neighbour weights and 999 permutations.
- *Significance:* Dutilleul's (1993) modified t-test (after Clifford et
  al., 1989), which estimates an effective sample size from correlograms
  of both variables, with 13 distance classes up to half the maximum
  distance.
- *Spatial error model:* fitted by maximum likelihood (spreg; Rey &
  Anselin, 2007) with the same weights.

**Category comparison.** For each category, we compare MOM depth at the
marks with each mark's observed height above ground (bias, RMSE, *r*). We
then re-score every building with that category and rerun the unit
analysis.

**Observed depth.** The marks' water-surface elevations are interpolated
to each building by inverse-distance weighting: the 8 nearest marks within
2 km (5 km as a sensitivity check), with power 2. Observed depth is
interpolated water surface minus DEM ground, floored at 0.
- *Check at the marks:* leave-one-out prediction of each mark's height
  above ground from the other marks.
- *Comparison with MOM:* restricted to units where at least 80% of
  buildings have an observed depth, with the same units scored with
  Category 1 MOM.

**Coarse comparison.** To show how much aggregation and normalization
matter, we also repeat the design common in quick validations: raw claim
counts and mean dollar payouts against mean exposure on the 0.1° grid,
with claims from all years or from Ian's date window only. That
comparison uses a random sample of up to 500 buildings per cell (Appendix
A). Its exposure score is proportional to Category 1 MOM depth, capped at
20 ft.

# 4 Results

## 4.1 Frequency and severity across scales

[Figure 1: `../figures/units-chart-light.png`.] Mean Category 1 MOM depth
against claim rate (top) and mean damage ratio (bottom), at block-group,
tract and 0.1°-grid scale.

**Table 1.** Correlation of mean Category 1 MOM depth with Ian outcomes.
Brackets: 95% spatial block-bootstrap CI.

| | Block group | Tract | 0.1° grid |
|---|---|---|---|
| Units used / total | 457 / 578 | 200 / 222 | 34 / 39 |
| Claim rate, *r* | 0.64 [0.52, 0.77] | 0.69 [0.54, 0.82] | 0.71 [0.51, 0.90] |
| Claim rate, ρ | 0.78 [0.73, 0.83] | 0.80 [0.73, 0.85] | 0.83 [0.64, 0.91] |
| Damage ratio, *r* (units) | 0.43 [0.23, 0.55] (209) | 0.46 [0.21, 0.62] (105) | 0.12 [−0.33, 0.56] (26) |
| Damage ratio, ρ | 0.43 | 0.45 | 0.16 |
| Mean payout USD, *r* | 0.50 | 0.54 | 0.37 [−0.33, 0.77] |
| Raw claim count, *r* | 0.66 | 0.64 | 0.24 [−0.06, 0.75] |
| Residual Moran's *I*, claim rate (*p*) | 0.39 (0.001) | 0.28 (0.001) | 0.12 (0.03) |

**Frequency.** MOM depth tracks the claim rate strongly at all three
scales.

**Severity.** The damage ratio rises with depth at block-group and tract
scale (*r* ≈ 0.45), but not on the grid. A 0.1° cell averages
surge-flooded and dry neighbourhoods together. Dollar payouts correlate a
little more strongly than damage ratios (0.50 vs 0.43 at block group).
This is consistent with part of the payout signal reflecting property
value rather than hazard.

## 4.2 Normalization and scale change the conclusions

**The coarse design gives the opposite picture.** Using raw counts and
payouts on the 0.1° grid with claims from all years (37 cells), the
results are:
- frequency: *r* = 0.35 between mean exposure and claim count;
- severity: *r* = 0.49 between mean exposure and payout.

Restricting claims to Ian's date window (34 cells) gives frequency
*r* = 0.21 and severity *r* = 0.49. That design suggests a robust severity
signal and a weak, window-sensitive frequency signal.

**Census units and rates reverse it.** Frequency is robust at every scale
(Table 1). Severity is the scale-dependent result. The grid's weak
frequency signal came from counting claims rather than rating them: at
grid scale, raw counts correlate at *r* = 0.24, rates at 0.71.

**The inland share of losses also depends on the unit.**
- On the grid, 36% of Ian claims fall in cells whose mean MOM depth is
  below 0.67 ft (the equivalent of an exposure score below 0.02).
- At block-group level the share is 18%.
- Only 1.4% fall in block groups where no building has any modeled surge.

A 0.1° cell that straddles the coast can be labelled "low exposure" while
containing heavily flooded blocks.

## 4.3 Flood zone and take-up

- **Inside vs outside the SFHA.** Nearly all Ian claims (97%) and 81% of
  policies were rated inside the SFHA. Inside it, MOM depth tracks the
  block-group claim rate closely (ρ = 0.73 [0.63, 0.82]). Outside it, the
  relationship is less than half as strong (ρ = 0.32 [0.17, 0.46]).
- **Take-up.** Median take-up is 31% of footprints. By tercile of
  take-up, the block-group claim-rate correlation is 0.81 (low), 0.78
  (middle) and 0.51 (high). High-take-up units are also the most exposed
  (mean depth 1.8 ft, vs 0.2 ft in the low tercile), so take-up and hazard
  cannot be separated.

## 4.4 Spatially corrected inference

**Table 2.** Modified t-test and spatial error model, Category 1 MOM.

| | Block group, claim rate | Block group, damage ratio | Tract, claim rate | Tract, damage ratio |
|---|---|---|---|---|
| Units *n* | 457 | 209 | 200 | 105 |
| Dutilleul effective *n* | 73 | 52 | 45 | 51 |
| Dutilleul *p* | 7 × 10⁻¹⁰ | 0.002 | 2 × 10⁻⁷ | 0.001 |
| Standardized slope, OLS → spatial error | 0.64 → 0.73 | 0.43 → 0.55 | 0.69 → 0.64 | 0.46 → 0.48 |
| Spatial error λ | 0.74 | 0.76 | 0.67 | 0.64 |

Spatial autocorrelation reduces the effective sample size to roughly a
sixth of the units. Both relationships remain significant. The spatial
error model absorbs the residual clustering and leaves the depth effect
as large as, or larger than, under OLS. Some omitted, spatially structured
factor remains (λ ≈ 0.7).

## 4.5 Which MOM category matches Ian?

[Figure 2: `../figures/categories-chart-light.png`.] Left: observed
high-water-mark depth vs MOM depth for Categories 1 and 4. Right:
block-group correlations by category.

**Table 3.** MOM categories against 239 USGS high-water marks and the
block-group outcomes.

| Category | Bias (ft) | RMSE (ft) | *r* at marks | Marks within 1 ft | Buildings wet | Claim rate *r* | Damage ratio *r* |
|---|---|---|---|---|---|---|---|
| 1 | +0.3 | 2.1 | 0.61 | 42% | 23% | 0.64 [0.52, 0.77] | 0.43 [0.23, 0.55] |
| 2 | +4.2 | 4.9 | 0.49 | 8% | 43% | 0.67 [0.57, 0.76] | 0.35 [0.12, 0.54] |
| 3 | +7.7 | 8.2 | 0.42 | 0% | 62% | 0.61 [0.52, 0.70] | 0.31 [0.07, 0.52] |
| 4 (Ian) | +13.1 | 13.6 | 0.24 | 0% | 80% | 0.53 [0.45, 0.62] | 0.27 [0.06, 0.49] |
| 5 | +16.0 | 16.4 | −0.02 | 0% | 88% | 0.47 [0.39, 0.56] | 0.14 [−0.03, 0.37] |

**Category 1 fits best.**
- *Observed water:* at the marks its mean bias is +0.3 ft (observed mean
  3.7 ft), and 42% of marks fall within 1 ft. Each higher category
  overpredicts by a further 4–16 ft, and tracks the pattern of observed
  water less well.
- *Losses:* the damage-ratio correlation falls steadily with category.
  The claim-rate correlation is similar for Categories 1 and 2, and falls
  from Category 3 upward.

## 4.6 Observed depth: MOM or depth itself?

**The observed surface is better at the marks.** Leave-one-out at the
marks gives bias +0.6 ft, RMSE 1.5 ft and *r* = 0.85, compared with
Category 1 MOM's +0.3 ft, 2.1 ft and 0.61 at the same 237 marks. Most of
the +0.6 ft bias reflects the DEM lying on average 0.6 ft below the
surveyed ground at the marks (RMSE 1.5 ft). A constant offset like this
does not affect correlations.

**Table 4.** Observed vs Category 1 MOM depth on the same well-covered
units (within 2 km of a mark).

| | Block groups | Tracts |
|---|---|---|
| Units (claim rate / damage ratio) | 111 / 89 | 44 / 40 |
| Claim rate: observed / MOM, *r* | 0.56 / 0.53 | 0.56 / 0.54 |
| Damage ratio: observed / MOM, *r* | 0.43 / 0.39 | 0.49 / 0.48 |
| *r* (unit-mean observed, unit-mean MOM depth) | 0.95 | 0.97 |

**Against losses, the two are almost the same.** Observed depth predicts
both outcomes only marginally better than MOM, well within the
confidence intervals (not shown; observed-depth damage ratio CI
[0.11, 0.63]). Averaged over a block group, the two depths are almost the
same variable. With a 5 km limit (254 block groups), the claim rate is
0.60 vs 0.58 and the damage ratio 0.41 vs 0.37.

# 5 Discussion

**Where versus how badly.** Category 1 MOM depth is a good proxy for where
insured buildings flooded in Ian, and a moderate one for how badly. The
moderate severity result is not mainly a failure of the envelope. Ian's
observed water, interpolated from high-water marks, does barely better,
and explains about a fifth of the variation in block-group damage ratio.
At the scale of a block group, the errors of a reasonable envelope average
out. What is missing is building-level information: first-floor
elevation, construction, waves and debris, and how long water stayed.
This is consistent with Wing et al. (2020), who found that depth alone is
a poor predictor of NFIP loss magnitude. The NFIP claims records include
the difference between a building's elevation and the base flood
elevation, which is a natural next covariate.

**Do not match the envelope to the storm's category.** The obvious way to
use MOM for a real storm is to choose the raster for its category. For
Ian, that is the second-worst choice of five. A MOM is the cell-by-cell
worst case over hundreds of storm tracks, headings, speeds and landfall
points. It answers "how bad could it get here" for a category, not "how
bad did it get" for one storm of that category. The Category 4 envelope
is wet at 80% of Lee County's buildings. It erases most of the contrast
between flooded and dry neighbourhoods that the claims respond to. We
cannot say from one storm whether "a lower category fits better" holds in
general. Where high-water marks exist, they offer a cheap check of that
choice.

**Report several units, and rate the counts.** The coarse design (counts
and payouts on a 0.1° grid) reached the opposite conclusion to the census
analysis. It also roughly doubled the apparent share of losses outside
the surge zone. Neither scale is the "true" one, but a validation reported
at a single coarse unit with unnormalized outcomes can mislead about both
the size and the shape of a hazard layer's skill. Including census units,
which the NFIP data already permit, is cheap.

**Selection.** Normalizing by policies in force corrects for how many
buildings are insured, not which ones. This is the bias behind the
retraction discussed in Sect. 1. Inside the SFHA, federally backed
mortgages require flood insurance, so policyholders there are close to a
census of mortgaged buildings. Outside it, take-up is voluntary and low,
and the surge–claim relationship is weak. Our results describe insured
losses. A comparison with all damage, for example FEMA Individual
Assistance inspections, would be needed for claims about all buildings.

# 6 Limitations

1. **Ecological inference.** Results are for areal units, not buildings.
2. **One county, one storm.** In particular, the category result needs
   replication on other events with dense high-water-mark surveys.
3. **Coverage of observed depth.** The high-water marks are coastal: the
   observed-depth analysis covers 23% of buildings (51% at 5 km).
4. **Interpolation.** IDW ignores barriers such as causeways and seawalls.
5. **Survivorship of marks.** Marks survive least where destruction was
   greatest, which may understate peak water.
6. **Proxies.** Take-up is approximate, and about a quarter of claims lack
   a property value and drop out of the damage-ratio analysis.
7. **Water-depth fields not used.** The claims' own water-depth fields
   were left out, because their units are ambiguous in FEMA's data
   dictionary.

# 7 Conclusions

In Lee County, the Category 1 high-tide SLOSH MOM envelope tracks
Hurricane Ian's insured losses:
- it tracks where claims occurred strongly (block-group *r* = 0.64);
- it tracks how severe they were moderately, and only at fine scale
  (*r* = 0.43);
- it matches observed high-water marks within 0.3 ft on average.

The envelope for Ian's own category is 13 ft too deep and tracks losses
worse. Replacing the envelope with observed depth barely improves loss
prediction, so better building information, not a better surge map, is
what severity prediction needs. Finally, the answer depends on method:
normalizing claims by policies and moving from a 0.1° grid to census
units reversed which result looked robust.

# Code and data availability

All inputs are public:
- NOAA NHC national storm surge risk maps v4;
- Overture Maps buildings;
- OpenFEMA NFIP claims v3 and policies v2;
- U.S. Census TIGER 2010/2020 block groups;
- USGS STN high-water marks (event 325);
- USGS 3DEP.

Code, per-unit tables and figures are at
https://github.com/DBishal13/surge-exposure. The analysis scripts are:
- `scripts/validate_units.py`
- `scripts/spatial_models.py`
- `scripts/validate_categories.py`
- `scripts/validate_observed_depth.py`
- `scripts/validate_exposure_bins.py` (the coarse comparison)

[Before submission: archive a tagged release on Zenodo and cite its DOI
here.]

# Author contributions, competing interests, AI use

[To complete. Copernicus requires authors to disclose the use of
AI-assisted tools in preparing the manuscript, code or analysis. AI tools
cannot be listed as authors. Describe here how AI assistance was used and
confirm that the author takes responsibility for the content.]

# References

Bates, P. D., Quinn, N., Sampson, C., et al.: Combined modeling of US
fluvial, pluvial, and coastal flood hazard under current and future
climates, Water Resour. Res., 57, e2020WR028673,
https://doi.org/10.1029/2020WR028673, 2021.

Blessing, R., Sebastian, A., and Brody, S. D.: Flood risk delineation in
the United States: How much loss are we capturing?, Nat. Hazards Rev.,
18, 04017002, https://doi.org/10.1061/(ASCE)NH.1527-6996.0000242, 2017.

Clifford, P., Richardson, S., and Hémon, D.: Assessing the significance of
the correlation between two spatial processes, Biometrics, 45, 123–134,
1989.

Dusseau, D., Zobel, Z., and Schwalm, C. R.: Validation and comparison of
U.S. loss estimates from catastrophe flood models, Journal of Catastrophe
Risk and Resilience, 4, 2026. Retracted 16 September 2026; cited only for
the retraction.

Dutilleul, P.: Modifying the t test for assessing the correlation between
two spatial processes, Biometrics, 49, 305–314, 1993.

Highfield, W. E., Norman, S. A., and Brody, S. D.: Examining the 100-year
floodplain as a metric of risk, loss, and household adjustment, Risk
Anal., 33, 186–191, https://doi.org/10.1111/j.1539-6924.2012.01840.x,
2013.

Mobley, W., Sebastian, A., Blessing, R., Highfield, W. E., Stearns, L., and
Brody, S. D.: Quantification of continuous flood hazard using random
forest classification and flood insurance claims at large spatial scales:
a pilot study in southeast Texas, Nat. Hazards Earth Syst. Sci., 21,
807–822, https://doi.org/10.5194/nhess-21-807-2021, 2021.

NOAA National Hurricane Center: National Storm Surge Risk Maps, Version 4,
https://www.nhc.noaa.gov/nationalsurge/, last access: 1 October 2026.

Openshaw, S.: The Modifiable Areal Unit Problem, Concepts and Techniques
in Modern Geography 38, Geo Books, Norwich, 1984.

Rey, S. J. and Anselin, L.: PySAL: A Python library of spatial analytical
methods, Rev. Reg. Stud., 37, 5–27, 2007.

Shin, D. W., Cocke, S., and Kim, B.-M.: A systematic revision of the NFIP
claims hazard data in Florida for flood risk assessment, Appl. Sci., 12,
3537, 2022. [Cite in Sect. 2 if the event-designation filter is
discussed.]

Wing, O. E. J., Pinter, N., Bates, P. D., and Kousky, C.: New insights into
US flood vulnerability revealed from flood insurance big data, Nat.
Commun., 11, 1444, https://doi.org/10.1038/s41467-020-15264-2, 2020.

# Appendix A: Software and reproducibility

The analysis runs on SurgeExposure, an open pipeline that joins Overture
building footprints, the SLOSH MOM raster and OpenFEMA data
(https://github.com/DBishal13/surge-exposure; a software description is
in preparation for the Journal of Open Source Software). Four errors were
found while preparing this study, and each changed the results. They are
recorded here because each one is a hazard for similar work.

1. **Unordered `LIMIT` sampling.** The first grid validation read the
   first N buildings from a partitioned GeoParquet scan. That sample was
   spatially clustered: 5 of 37 cells, all on one coastal strip. Sampling
   is now random with a fixed seed, and is tested for spatial spread.
2. **Time zones.** Comparing naive date bounds with timezone-aware loss
   dates raised an error. The values are now normalized to UTC.
3. **County code.** OpenFEMA filters on the 5-digit FIPS code. The 3-digit
   code silently returned zero claims, so the scripts now refuse an empty
   result.
4. **MOM category.** NOAA's national zip contains five rasters. The
   original download step took the first one, which a CRC check confirms
   is Category 1. The category is now an explicit, tested setting.
