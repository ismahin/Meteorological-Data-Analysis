# BMD vs NASA POWER Comparison Report: `3h_average`

## Research Basis

This report treats BMD station observations as the reference and NASA POWER as the gridded estimate at the station coordinate. The metric set follows common meteorological and hydroclimate validation practice:

- NASA POWER's own meteorology assessment uses linear regression, Pearson correlation, mean bias error, MAE, and RMSE for station comparisons.
- NASA POWER hourly data are matched to BMD's 3-hour observation timestamps. `PRECTOTCORR` is picked at the exact matching hour under the corrected BMD interpretation.
- Precipitation validation should include both amount metrics and event-detection metrics because rain occurrence can be wrong even when totals look acceptable.
- NSE and KGE are included because hydroclimate studies often use them to evaluate timing, variability, and bias together.
- Seasonal and monthly summaries are included because Bangladesh monsoon behavior can dominate annual statistics.

References are listed at the end of this report.

## Dataset Alignment

- BMD folder: `data/processed/ogimet_synop/by_station/`
- NASA folder: `data/processed/nasa_station_data/3h_average/`
- Stations: 35
- Time step: 3-hourly
- Period: 2021-01-01 to 2024-12-31
- Rows per station: 11,688
- Columns: `YEAR, MO, DY, HR, T2M, RH2M, PRECTOTCORR, WS10M`
- Rainfall unit treatment: NASA hourly precipitation is picked at the matching BMD observation timestamp.

## Key Findings

- Temperature agreement is strong: `r=0.890`, `RMSE=2.599 deg C`, and mean bias is `-0.546 deg C`.
- Relative humidity agreement is moderate: `r=0.655`, `RMSE=14.967%`, and mean bias is `-2.268%`.
- Wind speed has a positive NASA bias: mean BMD is `1.372 m/s`, mean NASA is `2.785 m/s`, and bias is `1.413 m/s`.
- Precipitation is the largest problem: NASA mean matched-hour precipitation is `8.123 mm` versus BMD `0.732 mm`, with percent bias `1009.6%`.
- Because precipitation is strongly intermittent, use the event-detection table together with RMSE/bias before drawing rainfall conclusions.

## Overall 3-Hourly Metrics

| variable    | unit           |   bmd_mean |   nasa_mean |   bias |    mae |   rmse |   pearson_r |     nse |     kge |   pbias_percent |
|:------------|:---------------|-----------:|------------:|-------:|-------:|-------:|------------:|--------:|--------:|----------------:|
| T2M         | deg C          |     26.117 |      25.57  | -0.546 |  2.054 |  2.599 |       0.89  |   0.766 |   0.887 |          -2.092 |
| RH2M        | %              |     79.502 |      77.235 | -2.268 | 11.128 | 14.967 |       0.655 |   0.245 |   0.648 |          -2.852 |
| PRECTOTCORR | mm at obs hour |      0.732 |       8.123 |  7.391 |  7.696 | 24.402 |       0.301 | -32.993 | -10.19  |        1009.63  |
| WS10M       | m/s            |      1.372 |       2.785 |  1.413 |  2.043 |  2.501 |       0.381 |  -0.459 |  -0.226 |         102.993 |

## Overall Daily Metrics

Daily aggregation uses means for `T2M`, `RH2M`, and `WS10M`, and sums for `PRECTOTCORR`.

| variable    | unit           |   bmd_mean |   nasa_mean |   bias |    mae |    rmse |   pearson_r |     nse |     kge |   pbias_percent |
|:------------|:---------------|-----------:|------------:|-------:|-------:|--------:|------------:|--------:|--------:|----------------:|
| T2M         | deg C          |     26.116 |      25.569 | -0.547 |  1.269 |   1.567 |       0.946 |   0.869 |   0.929 |          -2.094 |
| RH2M        | %              |     79.503 |      77.235 | -2.268 |  7.827 |  10.545 |       0.654 |  -0.439 |   0.351 |          -2.852 |
| PRECTOTCORR | mm at obs hour |      5.657 |      65.993 | 60.336 | 60.464 | 141.892 |       0.633 | -66.116 | -11.766 |        1066.49  |
| WS10M       | m/s            |      1.372 |       2.785 |  1.413 |  1.703 |   2.022 |       0.499 |  -0.787 |  -0.149 |         102.988 |

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
| Monsoon_JJAS   | T2M         | -0.68  |  2.016 |       0.669 |          -2.33  |
| Monsoon_JJAS   | RH2M        |  3.244 | 10.116 |       0.594 |           3.837 |
| Monsoon_JJAS   | PRECTOTCORR | 15.162 | 35.348 |       0.257 |         951.285 |
| Monsoon_JJAS   | WS10M       |  1.686 |  2.82  |       0.355 |          99.049 |
| PostMonsoon_ON | T2M         | -1.345 |  2.394 |       0.875 |          -5.147 |
| PostMonsoon_ON | RH2M        |  1.622 | 12.078 |       0.688 |           2.009 |
| PostMonsoon_ON | PRECTOTCORR |  5.232 | 22.549 |       0.382 |        1101.88  |
| PostMonsoon_ON | WS10M       |  1.307 |  2.163 |       0.296 |         153.387 |
| PreMonsoon_MAM | T2M         |  0.396 |  2.972 |       0.79  |           1.405 |
| PreMonsoon_MAM | RH2M        | -9.147 | 18.64  |       0.696 |         -12.407 |
| PreMonsoon_MAM | PRECTOTCORR |  4.951 | 17.775 |       0.25  |        1180.04  |
| PreMonsoon_MAM | WS10M       |  1.123 |  2.52  |       0.416 |          64.225 |
| Winter_DJF     | T2M         | -0.796 |  2.987 |       0.809 |          -3.991 |
| Winter_DJF     | RH2M        | -5.265 | 17.723 |       0.598 |          -6.767 |
| Winter_DJF     | PRECTOTCORR |  0.817 |  7.33  |       0.342 |        1418.85  |
| Winter_DJF     | WS10M       |  1.412 |  2.223 |       0.223 |         157.681 |

## Monthly Mean Bias

|   MO | variable    |     bias |
|-----:|:------------|---------:|
|    1 | T2M         |   -0.631 |
|    1 | RH2M        |   -5.579 |
|    1 | PRECTOTCORR |  104.206 |
|    1 | WS10M       |    1.399 |
|    2 | T2M         |   -0.528 |
|    2 | RH2M        |  -10.382 |
|    2 | PRECTOTCORR |  182.898 |
|    2 | WS10M       |    1.347 |
|    3 | T2M         |    0.234 |
|    3 | RH2M        |  -12.874 |
|    3 | PRECTOTCORR |  484.121 |
|    3 | WS10M       |    1.181 |
|    4 | T2M         |    0.618 |
|    4 | RH2M        |  -11.708 |
|    4 | PRECTOTCORR |  564.197 |
|    4 | WS10M       |    1.089 |
|    5 | T2M         |    0.343 |
|    5 | RH2M        |   -2.965 |
|    5 | PRECTOTCORR | 2725.81  |
|    5 | WS10M       |    1.097 |
|    6 | T2M         |   -0.372 |
|    6 | RH2M        |    2.288 |
|    6 | PRECTOTCORR | 4190.25  |
|    6 | WS10M       |    1.762 |
|    7 | T2M         |   -0.725 |
|    7 | RH2M        |    3.99  |
|    7 | PRECTOTCORR | 3232.76  |
|    7 | WS10M       |    1.836 |
|    8 | T2M         |   -0.634 |
|    8 | RH2M        |    2.965 |
|    8 | PRECTOTCORR | 4578.24  |
|    8 | WS10M       |    1.774 |
|    9 | T2M         |   -0.99  |
|    9 | RH2M        |    3.721 |
|    9 | PRECTOTCORR | 3121.26  |
|    9 | WS10M       |    1.365 |
|   10 | T2M         |   -1.166 |
|   10 | RH2M        |    1.436 |
|   10 | PRECTOTCORR | 2246.4   |
|   10 | WS10M       |    1.24  |
|   11 | T2M         |   -1.53  |
|   11 | RH2M        |    1.814 |
|   11 | PRECTOTCORR |  309.882 |
|   11 | WS10M       |    1.377 |
|   12 | T2M         |   -1.212 |
|   12 | RH2M        |   -0.226 |
|   12 | PRECTOTCORR |  297.639 |
|   12 | WS10M       |    1.485 |

## Stations With Largest 3-Hourly RMSE

| variable    | station_id   |   bias |    mae |   rmse |   pearson_r |   pbias_percent |
|:------------|:-------------|-------:|-------:|-------:|------------:|----------------:|
| PRECTOTCORR | sylhet       | 18.827 | 20.138 | 55.712 |       0.31  |         755.147 |
| PRECTOTCORR | kutubdia     | 15.319 | 15.534 | 54.479 |       0.285 |        1583.44  |
| PRECTOTCORR | cox_s_bazar  | 14.394 | 14.664 | 49.768 |       0.298 |        1324     |
| RH2M        | rangamati    |  2.148 | 14.69  | 18.763 |       0.611 |           2.925 |
| RH2M        | chuadanga    | -8.031 | 13.319 | 18.445 |       0.687 |         -10.043 |
| RH2M        | rajshahi     | -8.447 | 13.368 | 18.411 |       0.686 |         -10.569 |
| T2M         | dinajpur     | -0.128 |  2.363 |  3.059 |       0.884 |          -0.506 |
| T2M         | sydpur       | -0.655 |  2.355 |  2.952 |       0.89  |          -2.562 |
| T2M         | sylhet       | -1.009 |  2.403 |  2.93  |       0.852 |          -3.954 |
| WS10M       | chittagong   | -1.79  |  3.306 |  4.144 |       0.422 |         -37.087 |
| WS10M       | hatiya       |  2.932 |  3.082 |  3.594 |       0.472 |         249.9   |
| WS10M       | sandwip      |  2.88  |  2.989 |  3.421 |       0.575 |         235.069 |

## Stations With Highest 3-Hourly Correlation

| variable    | station_id   |   bias |   rmse |   pearson_r |
|:------------|:-------------|-------:|-------:|------------:|
| PRECTOTCORR | chandpur     |  6.222 | 17.798 |       0.404 |
| PRECTOTCORR | barisal      |  6.98  | 19.862 |       0.399 |
| PRECTOTCORR | rangamati    |  7.544 | 21.457 |       0.382 |
| RH2M        | khepupara    | -5.033 | 12.731 |       0.739 |
| RH2M        | ambagan_ctg  | -0.406 | 11.89  |       0.738 |
| RH2M        | dhaka        |  5.046 | 14.368 |       0.732 |
| T2M         | khepupara    | -0.136 |  1.974 |       0.926 |
| T2M         | bhola        | -0.329 |  2.161 |       0.921 |
| T2M         | barisal      | -0.265 |  2.221 |       0.919 |
| WS10M       | sandwip      |  2.88  |  3.421 |       0.575 |
| WS10M       | khulna       |  1.951 |  2.41  |       0.561 |
| WS10M       | khepupara    |  2.195 |  2.779 |       0.537 |

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
