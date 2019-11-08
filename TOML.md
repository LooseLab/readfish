Read Until Configuration Files
===

Specification for the TOML files used to drive read until experiments.

---

Table of Contents
===
 - [TOML files](#toml-files)
 - [Config sections](#config-sections)
   - [Guppy connection](#guppy-connection)
   - [Conditions](#conditions)
 - [Validating a TOML](#validating-a-toml)
 
 
TOML files
===
Read Until experiments are configured using TOML files, which are minimal and 
easy-to-read markup files. Each line is either a key-value pair or a 'table' 
heading. See more in the [TOML specification](https://github.com/toml-lang/toml).


Config sections
===

Guppy connection
---
The `guppy_connection` table specifies the basecalling parameters used by guppy.  

The `config` parameter must a valid guppy configuration excluding the file 
extension; these can be found in the `data` folder of the your guppy installation 
directory (`/opt/ont/guppy/data/*.cfg`).  

### Remote basecalling

```toml
[guppy_connection]
inflight = 512
config = "dna_r9.4.1_450bps_fast"
host = "REMOTE_SERVER_IP_ADDRESS"
port = "REMOTE_GUPPY_SERVER_PORT"
procs = 4
``` 

### Local basecalling

```toml
[guppy_connection]
inflight = 512
config = "dna_r9.4.1_450bps_fast"
host = "127.0.0.1"
port = 5555
procs = 4
```

Conditions
---
The `conditions` table holds the location of your minimap2 reference file and sets 
out the experimental conditions across the flowcell.

|          Key |       Type      | Values | Description |
|-------------:|:---------------:|:------:|:------------|
| reference | string | N/A | Required the absolute path for a minimap2 index |
| maintain_order | bool| N/A | (Optional) If `true` region conditions are ordered by their sequential numbering in the TOML file|
| axis | int | [0, 1] | (Optional) The axis that the flowcell is divided on. 0 is rows (left -> right), 1 is columns (top -> bottom) |


```toml
[conditions]
reference = "/absolute/path/to/reference.mmi"
```

Further, the table has sub-tables that determine the experimental conditions 
to apply to the flowcell, these should be sequentially numbered like so:

```toml
[conditions.0]
# ...

[conditions.1]
# ...
```

Each conditions table must contain:

|          Key |       Type      | Values | Description |
|-------------:|:---------------:|:------:|:------------|
|name|string | N/A | The name given to this condition |
| control| bool| N/A | Is this a control condition. If `true` all reads will be ignored in this region|
|min_chunks| int | N/A | The minimum number of read chunks to evaluate |
|max_chunks| int | N/A | The maximum number of read chunks to evaluate |
| targets| string or array | N/A | The genomic targets to accept or reject |
| single_on| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |
|multi_on| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |
|single_off| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |
| multi_off| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |
|no_seq| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |
|no_map| string | [unblock, stop_receiving, proceed]| The action to take when a read is assigned this classification |

Describe how the number of `conditions` tables relates to the flowcell splitting...  

The number of experimental conditions is limited by the number of arrays
of channels  

The number of sub-conditions given determines how the flowcell is split: 

```text
+--------+--------+--------+--------+
|        |        |        |        |
|        |        |        |        |
+        +        +        +        +
|        |        |        |        |
|        |        |        |        |
+--------+--------+--------+--------+
```

<details>
    <summary>JSON representation</summary>
    <p>
    A JSON representation may help visualise:
    <pre>
    {
        "fruit": "Apple",
        "size": "Large",
        "color": "Red"
    }
    </pre>
</details>

Validating a TOML
===

We provide a JSON schema for validating configuration files:

```bash
ru3_validate -i experiment_conf.toml ru_toml.schema.json
```

If you are providing targets using a text file the flag `-t` will attempt to 
check that these are compatible:

```bash
ru3_validate -ti experiment_conf.toml ru_toml.schema.json
```

Any errors with the configuration will be written to the terminal. 
