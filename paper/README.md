# paper/

Research write-up for the NFIP claims validation study, kept separate from
the main project [README](../README.md) so it can grow (drafts, figures,
data) without cluttering the repo root.

- **[paper.md](paper.md)** — the report itself: system description,
  literature review, research question, methodology, results, discussion,
  limitations, future work, references.
- **[figures/](figures/)** — light/dark validation charts, regenerated with
  `python scripts/plot_validation_chart.py` from `data/lee_county_grid.csv`.
- **[data/](data/)** — the per-grid-cell CSV produced by
  `python scripts/validate_exposure_bins.py` (mean exposure score, building
  count, claim count, mean claim payout per 0.1° cell). Committed rather
  than gitignored, since it's the evidence behind the paper's numbers, not
  a disposable cache.
- **[drafts/](drafts/)** — earlier/alternate versions of the write-up, kept
  for history rather than squashed away.

Both scripts above live in [`../scripts/`](../scripts/) alongside the
project's other one-off analysis scripts (e.g. `precompute_regions.py`),
consistent with how the rest of the repo is organized.
