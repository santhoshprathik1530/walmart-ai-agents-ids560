# AI agent knowledge sources (originals)

Only the sources agreed with the sponsor: Walmart-original documents, Fed Beige Book, NRF holiday forecast, EIA fuel.
Each file has a `.txt` copy next to it for search. `MANIFEST.csv` lists every file with its type, period and source URL.

| Folder | What | Coverage |
|---|---|---|
| `walmart/earnings_releases/` | Earnings releases (SEC 8-K Ex. 99.1) | FY11 Q1 to FY13 Q3 |
| `walmart/earnings_calls/` | Management call transcripts (Walmart IR) | FY11 Q1 to FY13 Q3 |
| `walmart/10k/` | 10-K and annual report (MD&A) | FY2010 to FY2013 |
| `walmart/10q/` | Quarterly reports 10-Q (SEC EDGAR), MD&A by segment | FY13 Q1 to Q3 (added 2026-10-30) |
| `walmart/newsroom/` | Walmart news releases (corporate.walmart.com, and Walmart-issued releases on PR Newswire) | 6 releases, Jul to Oct 2012 (added 2026-10-30) |
| `walmart/other_ir/` | 13-week comp sales and unit count disclosures | Selected quarters |
| `fed_beige_book/` | Full Beige Book reports, all districts | Jan 2010 to Nov 2012 (24 editions) |
| `nrf/` | NRF holiday sales forecasts | 2010, 2011, 2012 (Wayback copies of nrf.com) |
| `eia_fuel/` | EIA weekly regular gasoline prices | US and the 9 regions in `store_mapping.csv` |

Notes: the NRF originals are no longer on nrf.com, so the files are archive.org copies of the 2010-2012 press releases.
`engine_full_backup/data/documents.json` is the 22-passage subset the earlier engine used; these files are the full text behind it.
