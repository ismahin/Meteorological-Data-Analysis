# NASA/BMD Operational Forecast Validation

Training data: scraped OGIMET BMD SYNOP station data paired with scraped NASA POWER station data. No Excel-derived BMD weather observations are used by this artifact.

Leakage controls: 2021-2022 training, 2023 validation, 2024 final test on seven unseen stations.

Training runtime: 3.8 minutes.

## Production quality gates

```json
{
  "T2M": {
    "0-24": true,
    "27-48": true,
    "51-72": true,
    "75-96": true
  },
  "RH2M": {
    "0-24": true,
    "27-48": true,
    "51-72": true,
    "75-96": true
  },
  "PRECTOTCORR": {
    "0-24": true,
    "27-48": true,
    "51-72": true,
    "75-96": true
  },
  "WS10M": {
    "0-24": true,
    "27-48": true,
    "51-72": true,
    "75-96": true
  }
}
```

## Tournament results

| split                      | variable    | horizon_bucket   | candidate            |     n |    bias |     mae |    rmse |   pearson_r |    brier |      pod |      far |      csi |   wet_amount_rmse |   interval_coverage_90 |   weighted_interval_score |
|:---------------------------|:------------|:-----------------|:---------------------|------:|--------:|--------:|--------:|------------:|---------:|---------:|---------:|---------:|------------------:|-----------------------:|--------------------------:|
| validation_2023            | T2M         | 0-24             | hist_gradient_direct | 46465 | -0.0596 |  1.3703 |  1.8414 |      0.9394 | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    0.7162 |
| validation_2023            | T2M         | 0-24             | nasa_persistence     | 46465 | -0.3039 |  3.0368 |  4.1317 |      0.7041 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 27-48            | hist_gradient_direct | 27891 | -0.0777 |  1.5168 |  2.0139 |      0.9267 | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    0.788  |
| validation_2023            | T2M         | 27-48            | nasa_persistence     | 27891 | -0.26   |  3.8175 |  5.0033 |      0.5652 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 51-72            | hist_gradient_direct | 18582 | -0.1119 |  1.5917 |  2.0955 |      0.9217 | nan      | nan      | nan      | nan      |          nan      |                 0.8998 |                    0.8215 |
| validation_2023            | T2M         | 51-72            | nasa_persistence     | 18582 | -0.3355 |  3.4376 |  4.5913 |      0.638  | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 75-96            | hist_gradient_direct | 18582 | -0.1203 |  1.6417 |  2.1503 |      0.9173 | nan      | nan      | nan      | nan      |          nan      |                 0.8998 |                    0.8431 |
| validation_2023            | T2M         | 75-96            | nasa_persistence     | 18582 | -0.341  |  3.5877 |  4.7545 |      0.6124 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 0-24             | hist_gradient_direct | 10905 | -0.4457 |  1.5049 |  2.0332 |      0.9329 | nan      | nan      | nan      | nan      |          nan      |                 0.8637 |                    0.7848 |
| spatial_temporal_test_2024 | T2M         | 0-24             | nasa_persistence     | 10905 | -1.0729 |  2.9715 |  4.0279 |      0.7822 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 27-48            | hist_gradient_direct |  6568 | -0.3989 |  1.674  |  2.279  |      0.9107 | nan      | nan      | nan      | nan      |          nan      |                 0.8627 |                    0.8741 |
| spatial_temporal_test_2024 | T2M         | 27-48            | nasa_persistence     |  6568 | -1.2604 |  3.6188 |  4.7971 |      0.6855 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 51-72            | hist_gradient_direct |  4391 | -0.4477 |  1.7083 |  2.2181 |      0.9172 | nan      | nan      | nan      | nan      |          nan      |                 0.8652 |                    0.8798 |
| spatial_temporal_test_2024 | T2M         | 51-72            | nasa_persistence     |  4391 | -1.066  |  3.1425 |  4.1682 |      0.7642 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 75-96            | hist_gradient_direct |  4404 | -0.4492 |  1.75   |  2.2728 |      0.9131 | nan      | nan      | nan      | nan      |          nan      |                 0.8728 |                    0.9    |
| spatial_temporal_test_2024 | T2M         | 75-96            | nasa_persistence     |  4404 | -1.0642 |  3.2629 |  4.3313 |      0.7443 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 0-24             | hist_gradient_direct | 46353 | -0.181  |  6.4096 |  8.8402 |      0.8704 | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    3.3551 |
| validation_2023            | RH2M        | 0-24             | nasa_persistence     | 46353 | -3.5954 | 15.3574 | 20.5496 |      0.4173 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 27-48            | hist_gradient_direct | 27824 | -0.1875 |  6.7825 |  9.4222 |      0.849  | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    3.5605 |
| validation_2023            | RH2M        | 27-48            | nasa_persistence     | 27824 | -3.8129 | 18.2485 | 23.826  |      0.2078 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 51-72            | hist_gradient_direct | 18543 | -0.1563 |  6.9716 |  9.6977 |      0.8423 | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    3.663  |
| validation_2023            | RH2M        | 51-72            | nasa_persistence     | 18543 | -3.5392 | 16.9548 | 22.412  |      0.305  | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 75-96            | hist_gradient_direct | 18543 | -0.1534 |  7.0519 |  9.8174 |      0.8379 | nan      | nan      | nan      | nan      |          nan      |                 0.8999 |                    3.7058 |
| validation_2023            | RH2M        | 75-96            | nasa_persistence     | 18543 | -3.5301 | 17.3903 | 22.9438 |      0.2708 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 0-24             | hist_gradient_direct | 10876 |  1.09   |  7.8037 | 10.5103 |      0.8057 | nan      | nan      | nan      | nan      |          nan      |                 0.8396 |                    4.1449 |
| spatial_temporal_test_2024 | RH2M        | 0-24             | nasa_persistence     | 10876 |  0.3532 | 14.0731 | 18.781  |      0.4596 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 27-48            | hist_gradient_direct |  6550 |  1.0161 |  8.3366 | 11.1873 |      0.7811 | nan      | nan      | nan      | nan      |          nan      |                 0.8392 |                    4.4132 |
| spatial_temporal_test_2024 | RH2M        | 27-48            | nasa_persistence     |  6550 |  1.2101 | 16.364  | 21.3513 |      0.3085 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 51-72            | hist_gradient_direct |  4378 |  1.0425 |  8.3254 | 11.2421 |      0.7777 | nan      | nan      | nan      | nan      |          nan      |                 0.8486 |                    4.376  |
| spatial_temporal_test_2024 | RH2M        | 51-72            | nasa_persistence     |  4378 |  0.3135 | 14.6442 | 19.5139 |      0.4194 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 75-96            | hist_gradient_direct |  4391 |  1.0253 |  8.4121 | 11.3367 |      0.7735 | nan      | nan      | nan      | nan      |          nan      |                 0.8458 |                    4.4229 |
| spatial_temporal_test_2024 | RH2M        | 75-96            | nasa_persistence     |  4391 |  0.3051 | 15.0797 | 20.0331 |      0.3882 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 0-24             | hist_gradient_direct |  3796 | -0.0323 |  0.7127 |  1.3486 |      0.3719 |   0.2113 |   0.9856 |   0.2874 |   0.7053 |            1.7094 |                 0.8994 |                    0.3852 |
| validation_2023            | PRECTOTCORR | 0-24             | nasa_daily_seasonal  |  3796 | 11.7206 | 11.9624 | 26.2946 |      0.1627 |   0.24   |   0.9237 |   0.2646 |   0.6933 |           34.1001 |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 27-48            | hist_gradient_direct |  2303 | -0.0325 |  0.7321 |  1.3343 |      0.2483 |   0.2156 |   0.9677 |   0.2893 |   0.6943 |            1.6592 |                 0.8988 |                    0.3892 |
| validation_2023            | PRECTOTCORR | 27-48            | nasa_daily_seasonal  |  2303 |  9.7902 | 10.1141 | 22.2923 |      0.1238 |   0.267  |   0.8699 |   0.27   |   0.6581 |           27.42   |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 51-72            | hist_gradient_direct |  1507 | -0.0252 |  0.7217 |  1.326  |      0.2641 |   0.2223 |   0.9696 |   0.2968 |   0.688  |            1.6374 |                 0.8985 |                    0.3852 |
| validation_2023            | PRECTOTCORR | 51-72            | nasa_persistence     |  1507 |  9.1364 |  9.451  | 19.6289 |      0.1187 |   0.2754 |   0.8625 |   0.2769 |   0.6483 |           24.4412 |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 75-96            | hist_gradient_direct |  1507 | -0.0089 |  0.7362 |  1.331  |      0.252  |   0.2215 |   0.9741 |   0.2964 |   0.6906 |            1.6483 |                 0.8985 |                    0.3887 |
| validation_2023            | PRECTOTCORR | 75-96            | nasa_persistence     |  1507 |  8.9261 |  9.2714 | 22.7659 |      0.0887 |   0.29   |   0.8399 |   0.2837 |   0.6303 |           29.6286 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 0-24             | hist_gradient_direct |  1002 | -0.3457 |  1.2771 |  2.4312 |      0.2804 |   0.1106 |   0.9977 |   0.1175 |   0.8807 |            2.5941 |                 0.7814 |                    0.7945 |
| spatial_temporal_test_2024 | PRECTOTCORR | 0-24             | nasa_persistence     |  1002 | 41.7557 | 41.9209 | 90.4942 |      0.2361 |   0.1317 |   0.9642 |   0.1079 |   0.8635 |           98.3495 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 27-48            | hist_gradient_direct |   683 | -0.4383 |  1.348  |  2.5192 |      0.2178 |   0.1167 |   0.9966 |   0.1265 |   0.8709 |            2.6906 |                 0.7818 |                    0.837  |
| spatial_temporal_test_2024 | PRECTOTCORR | 27-48            | nasa_daily_seasonal  |   683 | 28.5966 | 29.2421 | 65.5755 |      0.0464 |   0.1874 |   0.9083 |   0.1215 |   0.8069 |           69.3909 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 51-72            | hist_gradient_direct |   451 | -0.5175 |  1.3868 |  2.59   |      0.1908 |   0.1133 |   0.9974 |   0.1236 |   0.8744 |            2.7621 |                 0.7539 |                    0.8755 |
| spatial_temporal_test_2024 | PRECTOTCORR | 51-72            | nasa_daily_seasonal  |   451 | 27.0134 | 27.4929 | 56.7478 |      0.0702 |   0.1907 |   0.9003 |   0.1178 |   0.8037 |           55.2575 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 75-96            | hist_gradient_direct |   451 | -0.5359 |  1.3888 |  2.6004 |      0.1776 |   0.1112 |   0.9949 |   0.1219 |   0.8742 |            2.7773 |                 0.7783 |                    0.88   |
| spatial_temporal_test_2024 | PRECTOTCORR | 75-96            | nasa_persistence     |   451 | 27.0134 | 27.4929 | 56.7478 |      0.0702 |   0.1907 |   0.9003 |   0.1178 |   0.8037 |           55.2575 |               nan      |                  nan      |
| validation_2023            | WS10M       | 0-24             | hist_gradient_direct | 46491 | -0.0067 |  0.1062 |  0.1779 |      0.6351 | nan      | nan      | nan      | nan      |          nan      |                 0.9455 |                    0.0556 |
| validation_2023            | WS10M       | 0-24             | nasa_persistence     | 46491 |  2.555  |  2.5571 |  2.9122 |      0.2732 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 27-48            | hist_gradient_direct | 27905 | -0.0044 |  0.1111 |  0.1812 |      0.6225 | nan      | nan      | nan      | nan      |          nan      |                 0.9446 |                    0.0572 |
| validation_2023            | WS10M       | 27-48            | nasa_persistence     | 27905 |  2.5535 |  2.5564 |  2.9233 |      0.1704 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 51-72            | hist_gradient_direct | 18590 | -0.0038 |  0.1117 |  0.1732 |      0.614  | nan      | nan      | nan      | nan      |          nan      |                 0.9436 |                    0.0573 |
| validation_2023            | WS10M       | 51-72            | nasa_persistence     | 18590 |  2.554  |  2.5561 |  2.9247 |      0.1638 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 75-96            | hist_gradient_direct | 18590 | -0.004  |  0.1123 |  0.174  |      0.6089 | nan      | nan      | nan      | nan      |          nan      |                 0.9445 |                    0.0576 |
| validation_2023            | WS10M       | 75-96            | nasa_persistence     | 18590 |  2.5587 |  2.5606 |  2.9318 |      0.1385 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 0-24             | hist_gradient_direct | 10907 |  0.0338 |  0.1559 |  0.2187 |      0.3141 | nan      | nan      | nan      | nan      |          nan      |                 0.8018 |                    0.0845 |
| spatial_temporal_test_2024 | WS10M       | 0-24             | nasa_persistence     | 10907 |  2.6426 |  2.6444 |  3.0681 |      0.3837 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 27-48            | hist_gradient_direct |  6570 |  0.0303 |  0.1633 |  0.2293 |      0.2509 | nan      | nan      | nan      | nan      |          nan      |                 0.7935 |                    0.0881 |
| spatial_temporal_test_2024 | WS10M       | 27-48            | nasa_persistence     |  6570 |  2.6329 |  2.6365 |  3.0748 |      0.2296 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 51-72            | hist_gradient_direct |  4392 |  0.0366 |  0.1637 |  0.2294 |      0.211  | nan      | nan      | nan      | nan      |          nan      |                 0.7896 |                    0.0881 |
| spatial_temporal_test_2024 | WS10M       | 51-72            | nasa_persistence     |  4392 |  2.6348 |  2.6389 |  3.0832 |      0.1701 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 75-96            | hist_gradient_direct |  4405 |  0.0356 |  0.1648 |  0.2312 |      0.197  | nan      | nan      | nan      | nan      |          nan      |                 0.7911 |                    0.0888 |
| spatial_temporal_test_2024 | WS10M       | 75-96            | nasa_daily_seasonal  |  4405 |  2.6353 |  2.639  |  3.0844 |      0.1191 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |

## SOTA candidate registry

Chronos-2 CPU resource check: 0.955s prediction, 1321 MB RSS, gate passed=True. Its sampled 2024 unseen-station accuracy is recorded in `chronos2_accuracy_metrics.csv`. It remains supplemental because it has not completed the full 2023 model-selection protocol used by the packaged winner.

| variable    | horizon_bucket   |    n |    bias |     mae |    rmse |
|:------------|:-----------------|-----:|--------:|--------:|--------:|
| T2M         | 0-24             | 1124 | -0.1543 |  1.6784 |  2.2512 |
| T2M         | 27-48            |  843 | -0.1799 |  1.878  |  2.5386 |
| T2M         | 51-72            |  564 | -0.2938 |  1.9117 |  2.4729 |
| T2M         | 75-96            |  562 | -0.3282 |  2.1014 |  2.7496 |
| RH2M        | 0-24             | 1140 |  0.3529 |  8.8318 | 12.5717 |
| RH2M        | 27-48            |  855 |  0.9885 | 10.5257 | 14.231  |
| RH2M        | 51-72            |  570 |  0.8288 |  9.2236 | 13.0437 |
| RH2M        | 75-96            |  570 |  0.9324 |  9.2721 | 12.8191 |
| PRECTOTCORR | 0-24             | 1109 |  4.4325 |  5.3424 | 13.0487 |
| PRECTOTCORR | 27-48            |  843 |  3.1951 |  4.4342 | 10.363  |
| PRECTOTCORR | 51-72            |  577 |  2.284  |  3.8976 |  9.1591 |
| PRECTOTCORR | 75-96            |  577 |  2.327  |  3.6356 |  8.9164 |
| WS10M       | 0-24             | 1228 | -0.3082 |  1.2974 |  2.1499 |
| WS10M       | 27-48            |  921 | -0.1695 |  1.3574 |  2.0204 |
| WS10M       | 51-72            |  616 | -0.2411 |  1.2529 |  1.8382 |
| WS10M       | 75-96            |  614 | -0.1024 |  1.1784 |  1.7377 |

TimeXer, iTransformer, and PatchTST are registered offline candidates. They must write metrics in this same schema and satisfy both the validation protocol and CPU serving gate before replacing the packaged winner.
