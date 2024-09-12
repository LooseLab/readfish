---
title: "Splitting a flongle into regions"
alt_titles:
  - "Flow cell splitting
  - "Flongle splitting"
  - "ValueError: channel cannot be below 0 or above flowcell_size"
---

The flow cell can be split both vertically and horizontally, with the `split_axis` parameter in the TOML file deciding this.
The axis can be either 0 or 1, with 0 splitting horizontally and 1 splitting vertically.
The default value is 1, so this only needs setting if you wish to split horizontally.

```text
        Vertical (axis=1)                        Horizontal (axis=0)
+------------+     +------+------+   |   +------------+     +------------+
|  1  2  3  4|     |  1  2|  3  4|   |   |  1  2  3  4|     |  1  2  3  4|
|  5  6  7  8| --> |  5  6|  7  8|   |   |  5  6  7  8| --> |  5  6  7  8|
|  9 10 11 12|     |  9 10| 11 12|   |   |  9 10 11 12|     +------------+
| 13 14 15 16|     | 13 14| 15 16|   |   | 13 14 15 16|     |  9 10 11 12|
+------------+     +------+------+   |   +------------+     | 13 14 15 16|
                                                            +------------+
```

This set at the very top of the TOML file, like the `channels` parameter
```toml
split_axis=0

[caller_settings.dorado]
config = "dna_r10.4.1_e8.2_400bps_hac"
address = "ipc:///tmp/.guppy/5555"
debug_log = "basecalled_chunks.fq" #optional
......... # and so on
```

The flongle is a strange shape - 13 columns by 10 rows. 13 is a prime, meaning it cannot be split vertically (except into 13), so flongles must be split horizontally into 2,5 or 10 regions.
