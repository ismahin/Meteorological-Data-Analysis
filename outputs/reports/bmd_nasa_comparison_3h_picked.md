# BMD vs NASA POWER Comparison Report: `3h_picked`

## Research Basis

This report treats BMD station observations as the reference and NASA POWER as the gridded estimate at the station coordinate. The metric set follows common meteorological and hydroclimate validation practice:

- NASA POWER's own meteorology assessment uses linear regression, Pearson correlation, mean bias error, MAE, and RMSE for station comparisons.
- NASA POWER hourly data are matched to BMD's 3-hour observation timestamps. `PRECTOTCORR` is picked at the exact matching hour under the corrected BMD interpretation.
- Precipitation validation should include both amount metrics and event-detection metrics because rain occurrence can be wrong even when totals look acceptable.
- NSE and KGE are included because hydroclimate studies often use them to evaluate timing, variability, and bias together.
- Seasonal and monthly summaries are included because Bangladesh monsoon behavior can dominate annual statistics.

References are listed at the end of this report.

## Dataset Alignment

- BMD folder: `data/processed/bmd_stations_3hourly/`
- NASA folder: `data/processed/nasa_station_data/3h_picked/`
- Stations: 35
- Time step: 3-hourly
- Period: 2021-01-01 to 2024-12-31
- Rows per station: 11,688
- Columns: `YEAR, MO, DY, HR, T2M, RH2M, PRECTOTCORR, WS10M`
- Rainfall unit treatment: NASA hourly precipitation is picked at the matching BMD observation timestamp.

## Key Findings

- Temperature agreement is strong: `r=0.919`, `RMSE=2.269 deg C`, and mean bias is `-0.568 deg C`.
- Relative humidity agreement is moderate: `r=0.709`, `RMSE=13.964%`, and mean bias is `-2.246%`.
- Wind speed has a positive NASA bias: mean BMD is `1.372 m/s`, mean NASA is `2.781 m/s`, and bias is `1.409 m/s`.
- Precipitation is the largest problem: NASA mean matched-hour precipitation is `8.123 mm` versus BMD `0.732 mm`, with percent bias `1009.6%`.
- Because precipitation is strongly intermittent, use the event-detection table together with RMSE/bias before drawing rainfall conclusions.

## Overall 3-Hourly Metrics

| variable    | unit           |   bmd_mean |   nasa_mean |   bias |    mae |   rmse |   pearson_r |     nse |     kge |   pbias_percent |
|:------------|:---------------|-----------:|------------:|-------:|-------:|-------:|------------:|--------:|--------:|----------------:|
| T2M         | deg C          |     26.117 |      25.548 | -0.568 |  1.803 |  2.269 |       0.919 |   0.822 |   0.911 |          -2.176 |
| RH2M        | %              |     79.502 |      77.256 | -2.246 | 10.331 | 13.964 |       0.709 |   0.343 |   0.695 |          -2.825 |
| PRECTOTCORR | mm at obs hour |      0.732 |       8.123 |  7.391 |  7.696 | 24.402 |       0.301 | -32.993 | -10.19  |        1009.63  |
| WS10M       | m/s            |      1.372 |       2.781 |  1.409 |  2.037 |  2.496 |       0.388 |  -0.453 |  -0.219 |         102.693 |

## Overall Daily Metrics

Daily aggregation uses means for `T2M`, `RH2M`, and `WS10M`, and sums for `PRECTOTCORR`.

| variable    | unit           |   bmd_mean |   nasa_mean |   bias |    mae |    rmse |   pearson_r |     nse |     kge |   pbias_percent |
|:------------|:---------------|-----------:|------------:|-------:|-------:|--------:|------------:|--------:|--------:|----------------:|
| T2M         | deg C          |     26.116 |      25.547 | -0.569 |  1.275 |   1.572 |       0.946 |   0.868 |   0.928 |          -2.178 |
| RH2M        | %              |     79.503 |      77.258 | -2.245 |  7.831 |  10.543 |       0.654 |  -0.438 |   0.35  |          -2.824 |
| PRECTOTCORR | mm at obs hour |      5.657 |      65.993 | 60.336 | 60.464 | 141.892 |       0.633 | -66.116 | -11.766 |        1066.49  |
| WS10M       | m/s            |      1.372 |       2.781 |  1.409 |  1.7   |   2.019 |       0.5   |  -0.782 |  -0.146 |         102.688 |

## Precipitation Event Detection

`POD` is probability of detection, `FAR` is false alarm ratio, `CSI` is critical success index, and frequency bias above 1 means NASA detects too many events.

|   threshold_mm |   hits |   misses |   false_alarms |   pod |   far |   csi |   frequency_bias |   accuracy |
|---------------:|-------:|---------:|---------------:|------:|------:|------:|-----------------:|-----------:|
|            0.1 |  37762 |      685 |         179824 | 0.982 | 0.826 | 0.173 |            5.659 |      0.559 |
|            5   |  13010 |     2163 |         103956 | 0.857 | 0.889 | 0.109 |            7.709 |      0.741 |
|           10   |   6897 |     2012 |          74730 | 0.774 | 0.916 | 0.082 |            9.162 |      0.812 |
|           25   |   1815 |     1063 |          35388 | 0.631 | 0.951 | 0.047 |           12.927 |      0.911 |

## Seasonal Signal

| season         | variable    |   bias |   rmse |   pearson_r |   pbias_percent |
|:---------------|:------------|-------:|-------:|------------:|----------------:|
| Monsoon_JJAS   | T2M         | -0.689 |  1.857 |       0.732 |          -2.364 |
| Monsoon_JJAS   | RH2M        |  3.339 |  9.428 |       0.664 |           3.95  |
| Monsoon_JJAS   | PRECTOTCORR | 15.162 | 35.348 |       0.257 |         951.285 |
| Monsoon_JJAS   | WS10M       |  1.682 |  2.815 |       0.362 |          98.79  |
| PostMonsoon_ON | T2M         | -1.367 |  2.191 |       0.908 |          -5.232 |
| PostMonsoon_ON | RH2M        |  1.599 | 11.276 |       0.737 |           1.981 |
| PostMonsoon_ON | PRECTOTCORR |  5.232 | 22.549 |       0.382 |        1101.88  |
| PostMonsoon_ON | WS10M       |  1.299 |  2.148 |       0.311 |         152.402 |
| PreMonsoon_MAM | T2M         |  0.365 |  2.559 |       0.85  |           1.298 |
| PreMonsoon_MAM | RH2M        | -9.019 | 17.697 |       0.744 |         -12.232 |
| PreMonsoon_MAM | PRECTOTCORR |  4.951 | 17.775 |       0.25  |        1180.04  |
| PreMonsoon_MAM | WS10M       |  1.121 |  2.521 |       0.418 |          64.098 |
| Winter_DJF     | T2M         | -0.826 |  2.495 |       0.876 |          -4.141 |
| Winter_DJF     | RH2M        | -5.423 | 16.203 |       0.683 |          -6.97  |
| Winter_DJF     | PRECTOTCORR |  0.817 |  7.33  |       0.342 |        1418.85  |
| Winter_DJF     | WS10M       |  1.409 |  2.216 |       0.24  |         157.374 |

## Monthly Mean Bias

|   MO | variable    |     bias |
|-----:|:------------|---------:|
|    1 | T2M         |   -0.658 |
|    1 | RH2M        |   -5.786 |
|    1 | PRECTOTCORR |  104.206 |
|    1 | WS10M       |    1.4   |
|    2 | T2M         |   -0.568 |
|    2 | RH2M        |  -10.571 |
|    2 | PRECTOTCORR |  182.898 |
|    2 | WS10M       |    1.348 |
|    3 | T2M         |    0.193 |
|    3 | RH2M        |  -12.844 |
|    3 | PRECTOTCORR |  484.121 |
|    3 | WS10M       |    1.179 |
|    4 | T2M         |    0.587 |
|    4 | RH2M        |  -11.542 |
|    4 | PRECTOTCORR |  564.197 |
|    4 | WS10M       |    1.088 |
|    5 | T2M         |    0.324 |
|    5 | RH2M        |   -2.763 |
|    5 | PRECTOTCORR | 2725.81  |
|    5 | WS10M       |    1.093 |
|    6 | T2M         |   -0.376 |
|    6 | RH2M        |    2.359 |
|    6 | PRECTOTCORR | 4190.25  |
|    6 | WS10M       |    1.759 |
|    7 | T2M         |   -0.73  |
|    7 | RH2M        |    4.074 |
|    7 | PRECTOTCORR | 3232.76  |
|    7 | WS10M       |    1.835 |
|    8 | T2M         |   -0.644 |
|    8 | RH2M        |    3.06  |
|    8 | PRECTOTCORR | 4578.24  |
|    8 | WS10M       |    1.77  |
|    9 | T2M         |   -1.01  |
|    9 | RH2M        |    3.852 |
|    9 | PRECTOTCORR | 3121.26  |
|    9 | WS10M       |    1.355 |
|   10 | T2M         |   -1.184 |
|   10 | RH2M        |    1.46  |
|   10 | PRECTOTCORR | 2246.4   |
|   10 | WS10M       |    1.232 |
|   11 | T2M         |   -1.556 |
|   11 | RH2M        |    1.743 |
|   11 | PRECTOTCORR |  309.882 |
|   11 | WS10M       |    1.368 |
|   12 | T2M         |   -1.237 |
|   12 | RH2M        |   -0.3   |
|   12 | PRECTOTCORR |  297.639 |
|   12 | WS10M       |    1.474 |

## Stations With Largest 3-Hourly RMSE

| variable    | station_id   |   bias |    mae |   rmse |   pearson_r |   pbias_percent |
|:------------|:-------------|-------:|-------:|-------:|------------:|----------------:|
| PRECTOTCORR | sylhet       | 18.827 | 20.138 | 55.712 |       0.31  |         755.147 |
| PRECTOTCORR | kutubdia     | 15.319 | 15.534 | 54.479 |       0.285 |        1583.44  |
| PRECTOTCORR | cox_s_bazar  | 14.394 | 14.664 | 49.768 |       0.298 |        1324     |
| RH2M        | chuadanga    | -7.972 | 12.349 | 17.39  |       0.743 |          -9.97  |
| RH2M        | rajshahi     | -8.388 | 12.395 | 17.317 |       0.741 |         -10.495 |
| RH2M        | ishurdi      | -7.547 | 12.418 | 17.257 |       0.735 |          -9.57  |
| T2M         | sitakunda    | -1.669 |  2.214 |  2.647 |       0.93  |          -6.4   |
| T2M         | dinajpur     | -0.162 |  2.038 |  2.621 |       0.917 |          -0.639 |
| T2M         | dhaka        | -1.388 |  2.165 |  2.602 |       0.923 |          -5.156 |
| WS10M       | chittagong   | -1.792 |  3.297 |  4.131 |       0.43  |         -37.143 |
| WS10M       | hatiya       |  2.925 |  3.085 |  3.602 |       0.464 |         249.32  |
| WS10M       | sandwip      |  2.873 |  2.99  |  3.431 |       0.564 |         234.514 |

## Stations With Highest 3-Hourly Correlation

| variable    | station_id   |   bias |   rmse |   pearson_r |
|:------------|:-------------|-------:|-------:|------------:|
| PRECTOTCORR | chandpur     |  6.222 | 17.798 |       0.404 |
| PRECTOTCORR | barisal      |  6.98  | 19.862 |       0.399 |
| PRECTOTCORR | rangamati    |  7.544 | 21.457 |       0.382 |
| RH2M        | khepupara    | -5.017 | 11.769 |       0.788 |
| RH2M        | ambagan_ctg  | -0.402 | 10.816 |       0.788 |
| RH2M        | mongla       | -6.258 | 14.966 |       0.784 |
| T2M         | khepupara    | -0.151 |  1.711 |       0.946 |
| T2M         | bhola        | -0.348 |  1.864 |       0.943 |
| T2M         | barisal      | -0.285 |  1.897 |       0.942 |
| WS10M       | khulna       |  1.943 |  2.402 |       0.568 |
| WS10M       | sandwip      |  2.873 |  3.431 |       0.564 |
| WS10M       | jessore      | -0.222 |  2.769 |       0.551 |

## Interpretation Priorities

1. Use `bias` and `pbias_percent` to identify systematic over/underestimation.
2. Use `MAE` and `RMSE` to judge typical and large-error behavior in physical units.
3. Use `pearson_r`, `NSE`, and `KGE` to judge whether NASA captures timing and variability, not only mean conditions.
4. For precipitation, prioritize event metrics and seasonal/monthly totals; precipitation is intermittent and strongly skewed.
5. Compare this report with the other NASA variant. If the averaged variant improves RMSE for temperature, humidity, and wind without harming correlation, it is generally the better comparison dataset. For precipitation, both variants use the same exact-hour picked value.

## References

- NASA POWER Hourly API: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/
- NASA POWER Meteorology Assessment: https://power.larc.nasa.gov/docs/methodology/meteorology/assessment/
- NOAA/NASA precipitation validation methods: https://precip-val.umd.edu/validation-methods
- HESS discussion of NSE and KGE: https://hess.copernicus.org/articles/23/4323/2019/hess-23-4323-2019.html
- Taylor diagram model evaluation background: https://openair-project.github.io/book/sections/model-evaluation/taylor-diagram.html
