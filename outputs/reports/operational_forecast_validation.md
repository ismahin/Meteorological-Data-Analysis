# NASA/BMD Operational Forecast Validation

Leakage controls: 2021-2022 training, 2023 validation, 2024 final test on seven unseen stations.

Training runtime: 1.2 minutes.

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
| validation_2023            | T2M         | 0-24             | hist_gradient_direct | 12740 | -0.0277 |  1.348  |  1.7875 |      0.9432 | nan      | nan      | nan      | nan      |          nan      |                 0.8998 |                    0.6954 |
| validation_2023            | T2M         | 0-24             | nasa_daily_seasonal  | 12740 | -3.3952 |  3.9823 |  5.2848 |      0.7253 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 27-48            | hist_gradient_direct |  7644 | -0.1197 |  1.5499 |  2.0303 |      0.925  | nan      | nan      | nan      | nan      |          nan      |                 0.8995 |                    0.7914 |
| validation_2023            | T2M         | 27-48            | nasa_daily_seasonal  |  7644 | -4.3231 |  4.848  |  6.2067 |      0.6651 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 51-72            | hist_gradient_direct |  5124 | -0.1005 |  1.5702 |  2.0725 |      0.9373 | nan      | nan      | nan      | nan      |          nan      |                 0.8997 |                    0.81   |
| validation_2023            | T2M         | 51-72            | nasa_daily_seasonal  |  5124 | -3.8981 |  4.653  |  6.2217 |      0.645  | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | T2M         | 75-96            | hist_gradient_direct |  5124 | -0.0534 |  1.6702 |  2.1914 |      0.9273 | nan      | nan      | nan      | nan      |          nan      |                 0.8993 |                    0.8659 |
| validation_2023            | T2M         | 75-96            | nasa_daily_seasonal  |  5124 | -3.8639 |  4.7018 |  6.2901 |      0.6225 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 0-24             | hist_gradient_direct |  2842 | -0.4944 |  1.5115 |  1.9905 |      0.9401 | nan      | nan      | nan      | nan      |          nan      |                 0.854  |                    0.799  |
| spatial_temporal_test_2024 | T2M         | 0-24             | nasa_persistence     |  2842 | -3.745  |  4.1823 |  5.399  |      0.7846 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 27-48            | hist_gradient_direct |  1709 | -0.4337 |  1.681  |  2.1617 |      0.9251 | nan      | nan      | nan      | nan      |          nan      |                 0.8695 |                    0.8644 |
| spatial_temporal_test_2024 | T2M         | 27-48            | nasa_persistence     |  1709 | -4.5404 |  4.9247 |  6.2179 |      0.7404 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 51-72            | hist_gradient_direct |  1137 | -0.415  |  1.6949 |  2.217  |      0.9299 | nan      | nan      | nan      | nan      |          nan      |                 0.8628 |                    0.8866 |
| spatial_temporal_test_2024 | T2M         | 51-72            | nasa_persistence     |  1137 | -4.1091 |  4.7704 |  6.2752 |      0.6879 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | T2M         | 75-96            | hist_gradient_direct |  1142 | -0.4775 |  1.8812 |  2.4623 |      0.9144 | nan      | nan      | nan      | nan      |          nan      |                 0.8608 |                    0.9831 |
| spatial_temporal_test_2024 | T2M         | 75-96            | nasa_persistence     |  1142 | -4.1416 |  4.8111 |  6.3206 |      0.6852 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 0-24             | hist_gradient_direct | 12740 |  0.081  |  5.9136 |  8.3422 |      0.8723 | nan      | nan      | nan      | nan      |          nan      |                 0.8998 |                    3.0883 |
| validation_2023            | RH2M        | 0-24             | nasa_persistence     | 12740 |  9.3154 | 14.6335 | 19.7572 |      0.2629 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 27-48            | hist_gradient_direct |  7644 | -0.1159 |  6.6393 |  9.2126 |      0.8641 | nan      | nan      | nan      | nan      |          nan      |                 0.8995 |                    3.4435 |
| validation_2023            | RH2M        | 27-48            | nasa_daily_seasonal  |  7644 | 12.2305 | 17.0402 | 22.4011 |      0.2358 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 51-72            | hist_gradient_direct |  5124 |  0.0997 |  6.4392 |  9.5295 |      0.8832 | nan      | nan      | nan      | nan      |          nan      |                 0.8997 |                    3.4573 |
| validation_2023            | RH2M        | 51-72            | nasa_daily_seasonal  |  5124 | 11.6887 | 18.1379 | 24.3293 |      0.1527 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | RH2M        | 75-96            | hist_gradient_direct |  5124 |  0.2317 |  6.8553 | 10.2349 |      0.8678 | nan      | nan      | nan      | nan      |          nan      |                 0.8993 |                    3.6593 |
| validation_2023            | RH2M        | 75-96            | nasa_daily_seasonal  |  5124 | 11.9363 | 18.3758 | 24.8145 |      0.1342 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 0-24             | hist_gradient_direct |  2881 |  1.4979 |  7.6117 | 10.4491 |      0.7853 | nan      | nan      | nan      | nan      |          nan      |                 0.832  |                    4.0548 |
| spatial_temporal_test_2024 | RH2M        | 0-24             | nasa_persistence     |  2881 | 10.3915 | 14.6725 | 19.6198 |      0.3045 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 27-48            | hist_gradient_direct |  1731 |  1.7352 |  8.406  | 11.3213 |      0.7908 | nan      | nan      | nan      | nan      |          nan      |                 0.8284 |                    4.4284 |
| spatial_temporal_test_2024 | RH2M        | 27-48            | nasa_persistence     |  1731 | 14.2298 | 17.5336 | 22.9278 |      0.3048 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 51-72            | hist_gradient_direct |  1153 |  0.8581 |  7.4756 | 10.4809 |      0.8437 | nan      | nan      | nan      | nan      |          nan      |                 0.8682 |                    3.9445 |
| spatial_temporal_test_2024 | RH2M        | 51-72            | nasa_daily_seasonal  |  1153 | 12.1462 | 17.6987 | 23.7317 |      0.1892 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | RH2M        | 75-96            | hist_gradient_direct |  1158 |  0.854  |  8.082  | 11.3421 |      0.8161 | nan      | nan      | nan      | nan      |          nan      |                 0.8627 |                    4.3865 |
| spatial_temporal_test_2024 | RH2M        | 75-96            | nasa_daily_seasonal  |  1158 | 12.0221 | 17.7652 | 23.8259 |      0.1758 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 0-24             | hist_gradient_direct | 12734 |  0.0202 |  1.3454 |  4.7361 |      0.2779 |   0.0798 |   0.6497 |   0.6469 |   0.2966 |           13.5954 |                 0.93   |                    0.921  |
| validation_2023            | PRECTOTCORR | 0-24             | nasa_daily_seasonal  | 12734 |  8.081  |  8.6804 | 19.6238 |      0.168  |   0.4342 |   0.971  |   0.7958 |   0.203  |           29.4127 |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 27-48            | hist_gradient_direct |  7635 |  0.2848 |  1.4848 |  4.7326 |      0.1395 |   0.078  |   0.6717 |   0.7556 |   0.2183 |           13.4138 |                 0.9346 |                    0.808  |
| validation_2023            | PRECTOTCORR | 27-48            | nasa_daily_seasonal  |  7635 |  8.2174 |  8.8953 | 19.8717 |      0.1169 |   0.4562 |   0.9441 |   0.8324 |   0.1659 |           26.8003 |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 51-72            | hist_gradient_direct |  5116 |  0.6037 |  1.7809 |  4.6392 |      0.1352 |   0.0828 |   0.6811 |   0.7899 |   0.1913 |           11.7155 |                 0.9261 |                    0.8565 |
| validation_2023            | PRECTOTCORR | 51-72            | nasa_daily_seasonal  |  5116 |  8.1992 |  9.0446 | 20.0564 |      0.0535 |   0.4797 |   0.8209 |   0.85   |   0.1452 |           25.714  |               nan      |                  nan      |
| validation_2023            | PRECTOTCORR | 75-96            | hist_gradient_direct |  5120 |  0.1667 |  1.4852 |  4.3405 |      0.1688 |   0.0922 |   0.5818 |   0.7167 |   0.2353 |           10.8583 |                 0.9268 |                    0.8773 |
| validation_2023            | PRECTOTCORR | 75-96            | nasa_daily_seasonal  |  5120 |  8.1761 |  9.0272 | 19.9091 |      0.0846 |   0.4697 |   0.8381 |   0.8229 |   0.1713 |           26.1472 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 0-24             | hist_gradient_direct |  2782 |  0.2227 |  1.5836 |  5.675  |      0.2502 |   0.0771 |   0.6014 |   0.7024 |   0.2486 |           19.332  |                 0.9109 |                    1.1209 |
| spatial_temporal_test_2024 | PRECTOTCORR | 0-24             | nasa_daily_seasonal  |  2782 | 10.9047 | 11.6016 | 30.2762 |      0.1613 |   0.5277 |   0.9091 |   0.8472 |   0.1505 |           49.6611 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 27-48            | hist_gradient_direct |  1617 |  0.3606 |  1.4233 |  4.3338 |      0.2643 |   0.0739 |   0.6938 |   0.719  |   0.25   |           13.9189 |                 0.9351 |                    0.7873 |
| spatial_temporal_test_2024 | PRECTOTCORR | 27-48            | nasa_daily_seasonal  |  1617 | 10.8217 | 11.4511 | 29.9502 |      0.0805 |   0.5294 |   0.9188 |   0.8515 |   0.1466 |           46.2305 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 51-72            | hist_gradient_direct |  1077 |  0.9136 |  1.766  |  4.2263 |      0.1806 |   0.0767 |   0.7282 |   0.7813 |   0.2022 |           11.6157 |                 0.9099 |                    0.8157 |
| spatial_temporal_test_2024 | PRECTOTCORR | 51-72            | nasa_daily_seasonal  |  1077 | 10.969  | 11.4674 | 29.6497 |      0.1748 |   0.5339 |   0.9126 |   0.8576 |   0.1405 |           44.5611 |               nan      |                  nan      |
| spatial_temporal_test_2024 | PRECTOTCORR | 75-96            | hist_gradient_direct |  1082 |  0.4587 |  1.4711 |  4.3912 |      0.2814 |   0.0836 |   0.5421 |   0.768  |   0.194  |           14.1326 |                 0.9177 |                    0.8612 |
| spatial_temporal_test_2024 | PRECTOTCORR | 75-96            | nasa_daily_seasonal  |  1082 | 10.8443 | 11.4324 | 29.8284 |      0.103  |   0.537  |   0.8692 |   0.8591 |   0.138  |           27.3929 |               nan      |                  nan      |
| validation_2023            | WS10M       | 0-24             | hist_gradient_direct | 12740 | -0.0073 |  1.0192 |  1.5077 |      0.684  | nan      | nan      | nan      | nan      |          nan      |                 0.9455 |                    0.5135 |
| validation_2023            | WS10M       | 0-24             | nasa_persistence     | 12740 |  1.369  |  2.063  |  2.476  |      0.3179 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 27-48            | hist_gradient_direct |  7644 |  0.035  |  1.0793 |  1.702  |      0.6445 | nan      | nan      | nan      | nan      |          nan      |                 0.946  |                    0.5432 |
| validation_2023            | WS10M       | 27-48            | nasa_daily_seasonal  |  7644 |  1.1823 |  2.1027 |  2.6558 |      0.1528 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 51-72            | hist_gradient_direct |  5124 |  0.0495 |  1.1057 |  1.5859 |      0.6554 | nan      | nan      | nan      | nan      |          nan      |                 0.9518 |                    0.5515 |
| validation_2023            | WS10M       | 51-72            | nasa_persistence     |  5124 |  1.2374 |  2.1132 |  2.589  |      0.18   | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| validation_2023            | WS10M       | 75-96            | hist_gradient_direct |  5124 | -0.0287 |  1.1719 |  1.7619 |      0.6083 | nan      | nan      | nan      | nan      |          nan      |                 0.9481 |                    0.6019 |
| validation_2023            | WS10M       | 75-96            | nasa_daily_seasonal  |  5124 |  1.0534 |  2.1442 |  2.6492 |      0.1086 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 0-24             | hist_gradient_direct |  3107 |  0.4054 |  1.4667 |  1.914  |      0.3276 | nan      | nan      | nan      | nan      |          nan      |                 0.8217 |                    0.7512 |
| spatial_temporal_test_2024 | WS10M       | 0-24             | nasa_persistence     |  3107 |  1.2928 |  1.8616 |  2.2621 |      0.4282 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 27-48            | hist_gradient_direct |  1868 |  0.3583 |  1.6315 |  2.2601 |      0.2187 | nan      | nan      | nan      | nan      |          nan      |                 0.8014 |                    0.8366 |
| spatial_temporal_test_2024 | WS10M       | 27-48            | nasa_persistence     |  1868 |  1.1136 |  1.9365 |  2.5504 |      0.2653 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 51-72            | hist_gradient_direct |  1243 |  0.389  |  1.615  |  2.3297 |      0.2288 | nan      | nan      | nan      | nan      |          nan      |                 0.8479 |                    0.8425 |
| spatial_temporal_test_2024 | WS10M       | 51-72            | nasa_persistence     |  1243 |  1.0867 |  1.9966 |  2.6711 |      0.2068 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |
| spatial_temporal_test_2024 | WS10M       | 75-96            | hist_gradient_direct |  1249 |  0.4084 |  1.5402 |  2.0273 |      0.2964 | nan      | nan      | nan      | nan      |          nan      |                 0.8663 |                    0.7966 |
| spatial_temporal_test_2024 | WS10M       | 75-96            | nasa_persistence     |  1249 |  1.1208 |  1.9574 |  2.4387 |      0.2504 | nan      | nan      | nan      | nan      |          nan      |               nan      |                  nan      |

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
