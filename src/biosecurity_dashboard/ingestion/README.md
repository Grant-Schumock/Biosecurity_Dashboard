# Ingestion

Shared data-pull orchestration belongs here.

This layer should coordinate source-specific connectors, normalize results, and write data into local storage. The dashboard refresh button can call this layer instead of knowing about individual source APIs.

