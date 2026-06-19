# Bias-Correction Validation

Training data: official BMD/NASA paired station data, 2021-2024, 3-hour UTC steps.

Final isolated holdout stations: dhaka, rangpur, rajshahi, sylhet, khulna, cox_s_bazar, teknaf

Selected models:

{
  "T2M": "anchor_idw_bmd",
  "RH2M": "anchor_idw_bmd",
  "PRECTOTCORR": "ml_two_stage",
  "WS10M": "linear_stack"
}

Selected distance decay lengths in km:

{
  "T2M": 150.0,
  "RH2M": 200.0,
  "PRECTOTCORR": 75.0,
  "WS10M": 200.0
}

## Holdout Metrics

| variable    | model                  |     n |    bias |     mae |    rmse |   pearson_r |      nse |   wet_accuracy |      pod |      far |      csi |   frequency_bias |   wet_amount_rmse |
|:------------|:-----------------------|------:|--------:|--------:|--------:|------------:|---------:|---------------:|---------:|---------:|---------:|-----------------:|------------------:|
| T2M         | raw_nasa               | 78392 | -0.7506 |  1.959  |  2.4322 |      0.9092 |   0.7819 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | anchor_idw_bmd         | 78392 | -0.2002 |  0.937  |  1.3026 |      0.9706 |   0.9374 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | global_month_hour_bias | 78392 | -0.2404 |  1.6021 |  2.0686 |      0.9243 |   0.8423 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | idw_residual           | 78392 | -0.2097 |  1.1886 |  1.6049 |      0.9554 |   0.905  |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | linear_stack           | 78392 | -0.3114 |  0.9717 |  1.3323 |      0.9708 |   0.9346 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| T2M         | ml_regressor           | 78392 | -0.4498 |  1.0451 |  1.4262 |      0.9689 |   0.925  |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | raw_nasa               | 79864 | -1.2586 | 10.4927 | 14.1021 |      0.6958 |   0.3101 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | anchor_idw_bmd         | 79864 |  0.9422 |  5.7289 |  7.9274 |      0.8867 |   0.782  |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | global_month_hour_bias | 79864 |  1.2892 |  9.2586 | 12.2344 |      0.747  |   0.4807 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | idw_residual           | 79864 |  0.8952 |  7.145  |  9.7738 |      0.8294 |   0.6686 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | linear_stack           | 79864 |  1.1524 |  5.7758 |  7.9299 |      0.8868 |   0.7818 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| RH2M        | ml_regressor           | 79864 |  1.6856 |  6.346  |  8.8831 |      0.8591 |   0.7262 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| PRECTOTCORR | raw_nasa               | 71349 |  8.3574 |  8.6283 | 29.8946 |      0.2701 | -53.4312 |         0.555  |   0.9818 |   0.8228 |   0.1766 |           5.5408 |           71.881  |
| PRECTOTCORR | anchor_idw_bmd         | 71349 |  0.0226 |  0.8986 |  4.0054 |      0.3875 |   0.0229 |         0.8649 |   0.7723 |   0.6008 |   0.3572 |           1.9348 |           11.8876 |
| PRECTOTCORR | global_month_hour_bias | 71349 |  1.1458 |  8.9367 | 27.6187 |      0.2445 | -45.4589 |         0.8157 |   0.6192 |   0.7099 |   0.2462 |           2.1344 |           83.6956 |
| PRECTOTCORR | idw_residual           | 71349 |  0.1844 |  4.5515 | 19.6587 |      0.0975 | -22.5383 |         0.7604 |   0.5954 |   0.7758 |   0.1946 |           2.6559 |           48.5096 |
| PRECTOTCORR | linear_stack           | 71349 |  0.063  |  0.9507 |  3.7228 |      0.4159 |   0.1559 |         0.5643 |   0.9833 |   0.8195 |   0.1799 |           5.4487 |           11.1295 |
| PRECTOTCORR | ml_two_stage           | 71349 | -0.3508 |  0.6843 |  3.6658 |      0.4358 |   0.1815 |         0.9226 |   0.3744 |   0.3126 |   0.3199 |           0.5447 |           13.3105 |
| WS10M       | raw_nasa               | 81328 |  1.2416 |  1.859  |  2.2958 |      0.3945 |  -0.3969 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | anchor_idw_bmd         | 81328 |  0.1445 |  1.4534 |  2.0414 |      0.3216 |  -0.1045 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | global_month_hour_bias | 81328 | -0.2087 |  1.3127 |  1.8723 |      0.4522 |   0.0709 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | idw_residual           | 81328 |  0.1128 |  1.418  |  1.9662 |      0.4288 |  -0.0247 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | linear_stack           | 81328 | -0.2271 |  1.2406 |  1.7735 |      0.4306 |   0.1664 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
| WS10M       | ml_regressor           | 81328 |  0.1569 |  1.5477 |  2.054  |      0.2569 |  -0.1182 |       nan      | nan      | nan      | nan      |         nan      |          nan      |
