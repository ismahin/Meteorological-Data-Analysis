# Bias-Correction Validation

Training data: scraped OGIMET BMD SYNOP station data paired with scraped NASA POWER
station data, 2021-2024, 3-hour UTC steps. No Excel-derived BMD weather observations
are used by this artifact.

Final isolated holdout stations: dhaka, rangpur, rajshahi, sylhet, khulna, cox_s_bazar, teknaf

Selected models:

{
  "T2M": "anchor_idw_bmd",
  "RH2M": "anchor_idw_bmd",
  "PRECTOTCORR": "anchor_idw_bmd",
  "WS10M": "linear_stack"
}

Selected distance decay lengths in km:

{
  "T2M": 200.0,
  "RH2M": 200.0,
  "PRECTOTCORR": 200.0,
  "WS10M": 25.0
}

## Holdout Metrics

| variable    | model                  |     n |    bias |     mae |    rmse |   pearson_r |       nse |   wet_accuracy |      pod |      far |      csi |   frequency_bias |   wet_amount_rmse |
|:------------|:-----------------------|------:|--------:|--------:|--------:|------------:|----------:|---------------:|---------:|---------:|---------:|-----------------:|------------------:|
| T2M         | raw_nasa               | 69878 | -0.7039 |  1.9651 |  2.4626 |      0.9065 |    0.7803 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | anchor_idw_bmd         | 69686 | -0.1975 |  0.9683 |  1.3943 |      0.9669 |    0.9296 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | global_month_hour_bias | 69878 | -0.181  |  1.6008 |  2.0922 |      0.9231 |    0.8414 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | idw_residual           | 69878 | -0.1586 |  1.2068 |  1.6795 |      0.951  |    0.8978 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | linear_stack           | 69878 | -0.2956 |  1.005  |  1.4233 |      0.9664 |    0.9266 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | ml_regressor           | 69878 | -0.4206 |  1.0601 |  1.4833 |      0.9661 |    0.9203 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | raw_nasa               | 69703 | -1.4354 | 10.7629 | 14.4067 |      0.6891 |    0.3106 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | anchor_idw_bmd         | 69512 |  1.1209 |  6.1764 |  8.4441 |      0.8769 |    0.7632 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | global_month_hour_bias | 69703 |  1.1298 |  9.3884 | 12.3903 |      0.7457 |    0.4901 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | idw_residual           | 69703 |  0.896  |  7.3367 |  9.9831 |      0.8258 |    0.669  |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | linear_stack           | 69703 |  1.3368 |  6.2224 |  8.458  |      0.8765 |    0.7624 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | ml_regressor           | 69703 |  2.2591 |  6.5272 |  9.0163 |      0.8643 |    0.73   |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| PRECTOTCORR | raw_nasa               |  4895 | 31.9171 | 32.1687 | 70.0268 |      0.1681 | -531.28   |         0.867  |   0.9785 |   0.1247 |   0.8588 |           1.1179 |           76.9842 |
| PRECTOTCORR | anchor_idw_bmd         |  3604 | -0.0825 |  1.1891 |  2.7706 |      0.2328 |   -0.0525 |         0.8862 |   0.9588 |   0.0874 |   0.8782 |           1.0506 |            2.9968 |
| PRECTOTCORR | global_month_hour_bias |  4895 |  7.6533 | 27.9208 | 61.462  |      0.1624 | -409.039  |         0.4848 |   0.4074 |   0.0705 |   0.3952 |           0.4383 |          101.944  |
| PRECTOTCORR | idw_residual           |  4895 |  9.2154 | 20.7542 | 51.92   |      0.0684 | -291.604  |         0.6219 |   0.6396 |   0.1319 |   0.5829 |           0.7367 |           63.3861 |
| PRECTOTCORR | linear_stack           |  4895 | -0.1787 |  1.035  |  2.9736 |      0.2192 |    0.0402 |         0.8601 |   0.9948 |   0.1416 |   0.8545 |           1.159  |            3.2626 |
| PRECTOTCORR | ml_two_stage           |  4895 | -0.2992 |  0.9819 |  2.9611 |      0.2439 |    0.0482 |         0.878  |   0.9857 |   0.1191 |   0.8698 |           1.1189 |            2.8312 |
| WS10M       | raw_nasa               | 69903 |  2.6182 |  2.6195 |  2.9917 |      0.3647 | -204.4    |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | anchor_idw_bmd         | 69711 |  0.0155 |  0.1574 |  0.2399 |      0.3207 |   -0.3187 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | global_month_hour_bias | 69903 | -0.0406 |  1.0096 |  1.3536 |      0.3059 |  -41.0492 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | idw_residual           | 69903 |  0.0791 |  0.6616 |  1.0012 |      0.1981 |  -22.0054 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | linear_stack           | 69903 | -0.0231 |  0.1348 |  0.1965 |      0.3705 |    0.1138 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | ml_regressor           | 69903 |  0.0117 |  0.1588 |  0.2262 |      0.2709 |   -0.1741 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
