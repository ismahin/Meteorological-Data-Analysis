# Bangladesh BMD Stations vs NASA POWER

This project compares Bangladesh Meteorological Department (BMD) station observations with NASA POWER gridded meteorological data at the same station coordinates.

Current study period: **2021-01-01 to 2024-12-31**  
Current station set: **35 BMD stations with all four variables available**

Variables:

```text
YEAR,MO,DY,HR,T2M,RH2M,PRECTOTCORR,WS10M
```

- `T2M`: air/dry-bulb temperature, degree Celsius
- `RH2M`: relative humidity, percent
- `PRECTOTCORR`: rainfall/precipitation, millimeter value at the matching 3-hour observation timestamp
- `WS10M`: wind speed, m/s

## Folder Layout

```text
data/
  raw/
    ground/
      Four Years data (2021 to 2024) 4 paramters.xlsx
    ground_ogimet/
      ogimet_getsynop_Bang_*.csv
    nasa_power/
      *_POWER_Point_Hourly_20210101_20241231_UTC.csv
  processed/
    ogimet_synop/by_station/
      <station_id>.csv
    bmd_stations_3hourly/   # legacy Excel-derived data, not used by production artifacts
      <station_id>.csv
    nasa_station_data/
      3h_average/
        <station_id>.csv
      3h_picked/
        <station_id>.csv
    bmd_station_coordinates_35.json
outputs/
  reports/
    bmd_nasa_comparison_3h_average.md
    bmd_nasa_comparison_3h_picked.md
  tables/
    bmd_split_report.csv
    nasa_power_download_report.csv
    nasa_power_3hourly_processing_report.csv
    bmd_nasa_alignment_check.csv
    bmd_nasa_units_check.csv
    bmd_nasa_comparison/
src/
  split_bmd_excel.py
  download_nasa_power.py
  process_nasa_power_3hourly.py
  check_bmd_nasa_alignment.py
  analyze_bmd_nasa_comparison.py
```

## Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Full Reproducible Workflow

Run these commands from the project root.

### 1. Download and Process BMD SYNOP From OGIMET

Production correction and forecasting artifacts use scraped OGIMET BMD SYNOP data,
not the Excel workbook.

Download OGIMET `getsynop` CSV files in UTC:

```powershell
python src/download_ogimet_getsynop.py --start-utc 2021-01-01T00 --end-utc 2024-12-31T23
```

Decode the SYNOP reports:

```powershell
python src/process_ogimet_synop.py
```

Output:

```text
data/raw/ground_ogimet/ogimet_getsynop_Bang_*.csv
data/processed/ogimet_synop/by_station/<station_id>.csv
outputs/tables/ogimet_getsynop_download_report.csv
outputs/tables/ogimet_synop_processing_report.csv
```

Important parser notes:

- OGIMET query begin/end values are UTC.
- Raw SYNOP `PARTE` text is decoded into `T2M`, `RH2M`, `PRECTOTCORR`, and `WS10M`.
- Rainfall is present only when a usable SYNOP precipitation group is reported.

Legacy note: `src/split_bmd_excel.py` can still reproduce the older Excel-derived
CSV folder, but production runtime, corrected-value training, and operational
forecasting no longer use that folder.

### 2. Station Coordinates

Station coordinates are saved in decimal degrees:

```text
data/processed/bmd_station_coordinates_35.json
```

These coordinates are extracted from the BMD workbook station headers and are used by the NASA POWER downloader.

### 3. Download NASA POWER Hourly Data

NASA POWER data are downloaded using:

- API: hourly point endpoint
- community: `RE`
- time standard: `UTC`
- parameters: `T2M,RH2M,PRECTOTCORR,WS10M`
- period: `20210101` to `20241231`

```powershell
python src/download_nasa_power.py
```

Output:

```text
data/raw/nasa_power/<station_id>_POWER_Point_Hourly_20210101_20241231_UTC.csv
outputs/tables/nasa_power_download_report.csv
```

To redownload existing files:

```powershell
python src/download_nasa_power.py --overwrite
```

### 4. Convert NASA Hourly Data to 3-Hourly Data

BMD observations are 3-hourly, while NASA POWER was downloaded hourly. This script creates two NASA comparison datasets:

```powershell
python src/process_nasa_power_3hourly.py
```

Outputs:

```text
data/processed/nasa_station_data/3h_picked/<station_id>.csv
data/processed/nasa_station_data/3h_average/<station_id>.csv
outputs/tables/nasa_power_3hourly_processing_report.csv
```

Definitions:

- `3h_picked`: picks NASA `T2M`, `RH2M`, `PRECTOTCORR`, and `WS10M` at BMD hours `0,3,6,...,21`.
- `3h_average`: averages NASA `T2M`, `RH2M`, and `WS10M` over `0-2`, `3-5`, etc.
- In both folders, `PRECTOTCORR` is picked at the exact BMD observation timestamp, following the corrected interpretation that the BMD value is the third-hour observation value rather than a 3-hour average.

### 5. Check Dataset Alignment

This validates that BMD and NASA processed files are on the same page.

```powershell
python src/check_bmd_nasa_alignment.py
```

Outputs:

```text
outputs/tables/bmd_nasa_alignment_check.csv
outputs/tables/bmd_nasa_units_check.csv
```

Checks include:

- matching filenames
- matching columns
- matching row counts
- matching `YEAR,MO,DY,HR` keys
- valid dates
- expected 3-hourly hours
- unit compatibility

### 6. Run Comparison Analysis

This creates separate analysis reports for the two NASA processing choices.

```powershell
python src/analyze_bmd_nasa_comparison.py
```

Outputs:

```text
outputs/reports/bmd_nasa_comparison_3h_picked.md
outputs/reports/bmd_nasa_comparison_3h_average.md
outputs/tables/bmd_nasa_comparison/
```

The analysis includes:

- bias, MAE, RMSE, unbiased RMSE
- Pearson correlation and R2
- NSE and KGE
- percent bias
- daily aggregation metrics
- seasonal metrics
- monthly climatology bias
- precipitation event detection: POD, FAR, CSI, frequency bias
- station rankings by RMSE and correlation

## Current Main Finding

The current reports show:

- `3h_picked` performs better than `3h_average` for `T2M`, `RH2M`, and slightly for `WS10M`.
- `PRECTOTCORR` is identical between the two NASA variants because rainfall is exact-hour picked in both.
- Temperature agreement is strong.
- Relative humidity agreement is moderate.
- NASA wind speed has a positive bias.
- Precipitation remains the largest issue, but NASA POWER is now compared using exact-hour picked precipitation rather than a 3-hour sum.

See:

```text
outputs/reports/bmd_nasa_comparison_3h_picked.md
outputs/reports/bmd_nasa_comparison_3h_average.md
```

## NASA POWER References

- Hourly API: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/
- Parameter metadata API: https://power.larc.nasa.gov/docs/services/api/system/manager/
- Meteorology assessment: https://power.larc.nasa.gov/docs/methodology/meteorology/assessment/

## Notes

- The raw NASA files are hourly; do not compare them directly with BMD 3-hourly files.
- Use the processed NASA folders for analysis.
- The v2 API supports post-2024 timestamps with a leakage-tested NASA-history-to-BMD forecast model trained from scraped OGIMET BMD SYNOP data plus scraped NASA POWER station data. It reports the requested timestamp, latest NASA timestamp, lag, forecast horizon, uncertainty, and per-variable quality status.
- Exact requested-time BMD observations are scraped from OGIMET SYNOP when available. If unavailable, the API returns model estimates/forecasts and does not fake BMD raw data. Historical climatology is never presented as a live observation.
- Optional SOTA evaluation uses `requirements-sota.txt`; Chronos-2 resource and holdout results are recorded under `outputs/tables/operational_forecast/` without adding its 1.3 GB process footprint to the production image.
- Use matching filenames to pair datasets, for example:

```text
data/processed/ogimet_synop/by_station/dhaka.csv
data/processed/nasa_station_data/3h_picked/dhaka.csv
data/processed/nasa_station_data/3h_average/dhaka.csv
```
