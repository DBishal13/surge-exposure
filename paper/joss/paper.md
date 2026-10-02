---
title: 'SurgeExposure: an open pipeline for building-level storm-surge exposure and its validation against flood-insurance claims'
tags:
  - Python
  - storm surge
  - flood risk
  - NFIP
  - geospatial
  - DuckDB
authors:
  - name: Bishal Dhungana
    orcid: 0000-0000-0000-0000  # TODO: add ORCID
    affiliation: 1
affiliations:
  - name: "TODO: affiliation"
    index: 1
date: 2 October 2026
bibliography: paper.bib
---

# Summary

SurgeExposure scores every building footprint in an area for storm-surge
exposure, and tests that score against real flood-insurance losses, using
only public data. The pipeline has two parts.

**Scoring.**
- *Buildings:* Overture Maps footprints are queried straight from cloud
  GeoParquet with DuckDB, so no local building database is needed.
- *Surge depth:* the National Hurricane Center's SLOSH Maximum of Maximums
  (MOM) inundation raster [@nhc_mom], for a chosen hurricane category, is
  sampled at each building centroid.
- *Live flooding (optional):* NOAA's current flood-inundation polygons can
  be added to the score.
- *Outputs:* GeoJSON from a FastAPI service and an interactive map.

**Validation.**
- *Losses:* scripts fetch FEMA's OpenFEMA NFIP claims and the policies in
  force on the event date, and aggregate both to census block groups,
  tracts and grid cells.
- *Statistics:* they correlate mean depth with claim rate and damage
  ratio, using spatial block-bootstrap confidence intervals, Dutilleul's
  modified t-test [@dutilleul1993] and spatial error models
  [@rey2007pysal].
- *Observed water:* they compare each MOM category with USGS high-water
  marks, and build an observed depth surface from those marks and the
  USGS 3DEP elevation model.

# Statement of need

Overlaying modeled surge depth on buildings is a common first step in
coastal risk screening. But the commercial and federal tools that do this
publish little that a reader can reproduce, and open tools rarely check
their output against outcomes. Published validation of US flood hazard
models is mostly against maps or other models [@bates2021]. Studies that
use NFIP claims as the reference have mostly examined where losses fall
relative to mapped floodplains [@highfield2013; @blessing2017], or used
claims as training labels for hazard models [@mobley2021].

SurgeExposure gives researchers and practitioners a scripted,
end-to-end way to ask the more basic question: "does this hazard layer
track what happened?" It handles the details that make the answer
trustworthy:
- normalizing claims by policies in force, not reporting raw counts;
- measuring severity as a damage ratio, not dollars;
- reconciling 2010 and 2020 census vintages in NFIP records;
- reporting several areal units, since the answer can change with unit
  size and shape [@openshaw1984];
- spatially corrected inference.

In a Hurricane Ian case study [@surge_manuscript], these choices reversed
the conclusions of a simpler grid-based design. The study also showed
that the Category 1 MOM matched Ian's high-water marks far better than the
Category 4 MOM matching Ian's landfall category. Both results came from
running the pipeline's validation scripts rather than from the scoring
code alone.

The intended users are researchers in coastal hazards and flood
insurance, analysts at utilities and public agencies who screen asset
exposure, and educators who need a transparent, inspectable example of
hazard-model validation.

# Design and quality

- **Public data only, fetched on demand.** Buildings are streamed from
  Overture's S3 GeoParquet. NOAA's 1.6 GB national MOM archive is cached
  once, and single category rasters can be extracted from it with HTTP
  range requests. OpenFEMA requests page through results and retry
  transient server errors.
- **Explicit, tested choices.** The MOM category is a setting chosen by
  file name. Building samples used for averages are random with a fixed
  seed. Historical validation turns off the live-flood feed. Each of these
  was added after a documented error.
- **Tests.** The test suite covers:
  - spatially unbiased sampling;
  - category selection;
  - claims-API filtering and time-zone handling;
  - aggregation and rates;
  - Moran's *I* and bootstrap determinism;
  - the effective-sample-size estimate.
- **Reproducibility.** Each analysis is one script that writes per-unit
  CSV and JSON outputs to the repository. Figures are rebuilt from those
  outputs.

# Acknowledgements

TODO. Disclose AI-assistance as required by JOSS policy.

# References
