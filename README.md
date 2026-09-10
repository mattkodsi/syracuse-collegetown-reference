# Syracuse / Collegetown reference

**[Read the illustrated plans briefing](https://mattkodsi.github.io/syracuse-collegetown-reference/briefing/)** — September 7, 2026.

The briefing explains the plans, priorities and implementation of Syracuse University, city and neighborhood organizations, transport agencies and the medical institutions around University Hill. It includes a timeline, original plan illustrations and a source guide for the team's drawings. Expand the source notes within each chapter for citations.

- [District orientation](https://mattkodsi.github.io/syracuse-collegetown-reference/briefing/district.html)
- [Evidence limits and additional sources](https://mattkodsi.github.io/syracuse-collegetown-reference/briefing/source-notes.html)
- [Earlier reference site](https://mattkodsi.github.io/syracuse-collegetown-reference/) — preserved separately; the new briefing is the current plans account.

This repository publishes the team-facing reading edition. Working records and the wider research archive remain in the project workspace. The source documents and reproduced plan illustrations belong to their respective publishers; source citations are included in the briefing.

## Source and rebuild (reference map)

The reference map's source is in `src/`: `syracuse-reference.html` (the app) and `data/` (`build_parcels.py` pulls the City of Syracuse 2025 Q3 parcel roll and tags the three core neighborhoods — University Hill, University Neighborhood and Westcott — by the roll's NHOOD field; `build_bundle.py` inlines the data into one self-contained file). Rebuild and republish:

```
cd src/data && python3 build_parcels.py --refresh && python3 build_bundle.py && cp ../dist/Syracuse-Reference.html ../../index.html
```
